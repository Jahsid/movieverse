"""Isolated FastAPI lifespan and in-process HTTP benchmark; no external DB access."""

import argparse
import ctypes
import json
import math
import os
import statistics
import time
from types import SimpleNamespace

# Set this before importing application modules, which construct the configured engine.
os.environ["DATABASE_URL"] = "postgresql+psycopg://127.0.0.1:1/unused"

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database.connection import Base, get_db
from app.database.models import Movie, Rating, User


def working_set():
    """Return current and process-high-water working set in MiB on Windows."""
    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("page_faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in (
                "peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
                "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong
    )
    process = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        process, ctypes.byref(counters), counters.cb
    ):
        raise OSError("GetProcessMemoryInfo failed")
    mib = 1024 * 1024
    return {"current_mib": round(counters.working_set / mib, 2),
            "process_peak_mib": round(counters.peak_working_set / mib, 2)}


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def make_database(limit):
    ratings = pd.read_csv(
        "data/raw/ratings.csv", usecols=["userId", "movieId", "rating"], nrows=limit
    )
    movies = pd.read_csv("data/raw/movies.csv", usecols=["movieId", "title", "genres"])
    movies = movies[movies["movieId"].isin(ratings["movieId"].unique())]
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(User.__table__.insert(), [
            {"user_id": int(user_id)} for user_id in ratings["userId"].unique()
        ])
        connection.execute(Movie.__table__.insert(), [
            {"movie_id": int(row.movieId), "title": row.title, "genres": row.genres}
            for row in movies.itertuples(index=False)
        ])
        connection.execute(Rating.__table__.insert(), [
            {"user_id": int(row.userId), "movie_id": int(row.movieId),
             "rating": float(row.rating)}
            for row in ratings.itertuples(index=False)
        ])
    movie_id = int(ratings["movieId"].value_counts().index[0])
    return engine, len(ratings), len(movies), ratings["userId"].nunique(), movie_id


def measure_once(engine, movie_id, request_count):
    timings = {}
    original_session = main_module.SessionLocal
    original_dataframe_module = main_module.pd
    original_recommender = main_module.MovieRecommender
    previous_overrides = main_module.app.dependency_overrides.copy()

    class TimedQuery:
        def __init__(self, query):
            self.query = query

        def all(self):
            started = time.perf_counter()
            result = self.query.all()
            timings["rating_load_s"] = time.perf_counter() - started
            return result

    class TimedSession:
        def __init__(self):
            self.session = Session(engine)

        def query(self, *columns):
            return TimedQuery(self.session.query(*columns))

        def close(self):
            self.session.close()

    def timed_dataframe(*args, **kwargs):
        started = time.perf_counter()
        result = pd.DataFrame(*args, **kwargs)
        timings["dataframe_s"] = time.perf_counter() - started
        return result

    class TimedRecommender(original_recommender):
        def train(self, ratings):
            started = time.perf_counter()
            try:
                return super().train(ratings)
            finally:
                timings["training_s"] = time.perf_counter() - started

    def isolated_db():
        with Session(engine) as session:
            yield session

    main_module.SessionLocal = TimedSession
    main_module.pd = SimpleNamespace(DataFrame=timed_dataframe)
    main_module.MovieRecommender = TimedRecommender
    main_module.app.dependency_overrides[get_db] = isolated_db
    before_memory = working_set()
    try:
        started = time.perf_counter()
        with TestClient(main_module.app) as client:
            lifespan_s = time.perf_counter() - started
            ready = client.get("/ready")
            if ready.status_code != 200:
                raise RuntimeError("Isolated application did not become ready")
            ready_s = time.perf_counter() - started
            startup_memory = working_set()
            path = f"/api/v1/recommendations/similar/{movie_id}?k=5"
            for _ in range(5):
                if client.get(path).status_code != 200:
                    raise RuntimeError("Recommendation warm-up failed")
            latencies_ms = []
            for _ in range(request_count):
                request_started = time.perf_counter()
                response = client.get(path)
                latencies_ms.append((time.perf_counter() - request_started) * 1000)
                if response.status_code != 200:
                    raise RuntimeError("Recommendation request failed")
        return {
            "lifespan_s": lifespan_s, "rating_load_s": timings["rating_load_s"],
            "dataframe_s": timings["dataframe_s"], "training_s": timings["training_s"],
            "time_until_ready_s": ready_s, "memory_before": before_memory,
            "memory_after_ready": startup_memory, "http_latency_ms": latencies_ms,
        }
    finally:
        main_module.SessionLocal = original_session
        main_module.pd = original_dataframe_module
        main_module.MovieRecommender = original_recommender
        main_module.app.dependency_overrides.clear()
        main_module.app.dependency_overrides.update(previous_overrides)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", type=int, default=10000)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--requests", type=int, default=30)
    args = parser.parse_args()
    if min(args.ratings, args.repetitions, args.requests) < 1:
        parser.error("All counts must be positive")
    engine, rating_count, movie_count, user_count, movie_id = make_database(args.ratings)
    try:
        runs = [measure_once(engine, movie_id, args.requests)
                for _ in range(args.repetitions)]
    finally:
        engine.dispose()
    latencies = [value for run in runs for value in run["http_latency_ms"]]
    for run in runs:
        run["http_latency_ms"] = {
            "count": len(run["http_latency_ms"]),
            "p50": statistics.median(run["http_latency_ms"]),
            "p95_nearest_rank": percentile(run["http_latency_ms"], 0.95),
        }
    print(json.dumps({
        "dataset": {"ratings": rating_count, "rated_movies": movie_count,
                    "users": int(user_count), "query_movie_id": movie_id},
        "environment": "in-memory SQLite, real FastAPI lifespan, in-process TestClient",
        "warmup_requests_per_run": 5,
        "runs": runs,
        "pooled_http_latency_ms": {"count": len(latencies),
                                   "p50": statistics.median(latencies),
                                   "p95_nearest_rank": percentile(latencies, 0.95)},
    }, indent=2))


if __name__ == "__main__":
    main()
