"""Create deterministic, integrity-preserving ETL benchmark CSV fixtures."""

import argparse
import ctypes
import os
import platform
import subprocess
import sys
import json
import random
import tempfile
import time
from pathlib import Path

import pandas as pd

from app.data_pipeline.manifest import generate_manifest
from app.data_pipeline.validator import validate_movies, validate_ratings


TARGETS = {"small": (100, 5_000), "medium": (500, 25_000), "full": (None, None)}


def _read_sources(source_directory):
    movies = pd.read_csv(source_directory / "movies.csv")
    ratings = pd.read_csv(source_directory / "ratings.csv")
    validate_movies(movies)
    validate_ratings(ratings)
    if not set(ratings["movieId"]).issubset(set(movies["movieId"])):
        raise ValueError("Source ratings reference movies missing from the movie file")
    return movies, ratings


def build_dataset(size, source_directory, output_directory, seed=2026):
    """Write one matched deterministic dataset and return its measured manifest."""
    if size not in TARGETS:
        raise ValueError(f"Unknown dataset size: {size}")
    source_directory = Path(source_directory)
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    total_started = time.perf_counter()
    extraction_started = time.perf_counter()
    movies = pd.read_csv(source_directory / "movies.csv")
    ratings = pd.read_csv(source_directory / "ratings.csv")
    extraction_seconds = time.perf_counter() - extraction_started

    validation_started = time.perf_counter()
    validate_movies(movies)
    validate_ratings(ratings)
    if not set(ratings["movieId"]).issubset(set(movies["movieId"])):
        raise ValueError("Source ratings reference movies missing from the movie file")
    validation_seconds = time.perf_counter() - validation_started

    transformation_started = time.perf_counter()
    if size == "full":
        selected_movies = movies.sort_values("movieId", kind="stable").reset_index(drop=True)
        selected_ratings = ratings.sort_values(
            ["userId", "movieId"], kind="stable"
        ).reset_index(drop=True)
    else:
        _, rating_target = TARGETS[size]
        rng = random.Random(seed)
        rating_positions = sorted(rng.sample(
            range(len(ratings)), min(rating_target, len(ratings))
        ))
        selected_ratings = ratings.iloc[rating_positions].sort_values(
            ["userId", "movieId"], kind="stable"
        ).reset_index(drop=True)
        required_movie_ids = set(selected_ratings["movieId"])
        selected_movies = movies[movies["movieId"].isin(required_movie_ids)].sort_values(
            "movieId", kind="stable"
        ).reset_index(drop=True)
    transformation_seconds = time.perf_counter() - transformation_started

    selected_movies.to_csv(output_directory / "movies.csv", index=False)
    selected_ratings.to_csv(output_directory / "ratings.csv", index=False)
    fingerprint_started = time.perf_counter()
    source_manifest = generate_manifest(source_directory)
    dataset_manifest = generate_manifest(output_directory)
    fingerprinting_seconds = time.perf_counter() - fingerprint_started
    total_seconds = time.perf_counter() - total_started
    total_records = len(selected_movies) + len(selected_ratings)
    return {
        "measurement_scope": "offline diagnostic timings; no database ingestion or PostgreSQL timing",
        "timings_seconds": {
            "extraction": extraction_seconds,
            "validation": validation_seconds,
            "transformation": transformation_seconds,
            "fingerprinting": fingerprinting_seconds,
            "total_offline_pipeline": total_seconds,
        },
        "source_records_processed": total_records,
        "source_records_per_second": total_records / total_seconds if total_seconds else 0.0,
        "size": size,
        "seed": seed,
        "source_fingerprint": source_manifest["content_fingerprint"],
        "content_fingerprint": dataset_manifest["content_fingerprint"],
        "movie_rows": len(selected_movies),
        "rating_rows": len(selected_ratings),
        "target_movie_rows": None if size == "full" else TARGETS[size][0],
        "target_rating_rows": TARGETS[size][1],
        "files": dataset_manifest["files"],
    }


def build_changed_variant(source_directory, output_directory, seed=2026):
    """Copy a dataset while changing approximately one percent of each source."""
    source_directory = Path(source_directory)
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    movies = pd.read_csv(source_directory / "movies.csv")
    ratings = pd.read_csv(source_directory / "ratings.csv")
    rng = random.Random(seed)

    movie_count = min(len(movies), max(1, round(len(movies) * 0.01))) if len(movies) else 0
    rating_count = min(len(ratings), max(1, round(len(ratings) * 0.01))) if len(ratings) else 0
    movie_positions = sorted(rng.sample(range(len(movies)), movie_count))
    rating_positions = sorted(rng.sample(range(len(ratings)), rating_count))
    for position in movie_positions:
        title = movies.at[position, "title"]
        movies.at[position, "title"] = f"{title} [benchmark update]"
    for position in rating_positions:
        value = float(ratings.at[position, "rating"])
        ratings.at[position, "rating"] = 4.5 if value != 4.5 else 4.0

    validate_movies(movies)
    validate_ratings(ratings)
    if not set(ratings["movieId"]).issubset(set(movies["movieId"])):
        raise ValueError("Changed ratings reference movies missing from the source dataset")
    movies.to_csv(output_directory / "movies.csv", index=False)
    ratings.to_csv(output_directory / "ratings.csv", index=False)
    manifest = generate_manifest(output_directory)
    return {
        "seed": seed,
        "source_fingerprint": generate_manifest(source_directory)["content_fingerprint"],
        "content_fingerprint": manifest["content_fingerprint"],
        "movie_rows": len(movies),
        "rating_rows": len(ratings),
        "changed_movie_rows": movie_count,
        "changed_rating_rows": rating_count,
        "files": manifest["files"],
    }


def create_benchmark_datasets(source_directory, output_directory, seed=2026):
    output_directory = Path(output_directory)
    result = {}
    for size in TARGETS:
        result[size] = build_dataset(size, source_directory, output_directory / size, seed)
    result["changed"] = build_changed_variant(
        output_directory / "medium", output_directory / "medium_changed", seed
    )
    return result


def peak_working_set_mib():
    """Return process high-water working set on Windows, or None elsewhere."""
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
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError("Could not read process working set")
    return round(counters.peak_working_set / (1024 * 1024), 2)


def run_case(size, source, output, seed=2026, timeout_seconds=120):
    """Run one measured case in a new Python process."""
    command = [
        sys.executable, "-m", "scripts.benchmark_etl", "--worker",
        "--size", size, "--source", str(Path(source).resolve()),
        "--output", str(Path(output).resolve()), "--seed", str(seed),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds,
            check=False, cwd=Path(__file__).resolve().parents[1],
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Benchmark child process timed out") from None
    if completed.returncode:
        raise RuntimeError(f"Benchmark child process failed with code {completed.returncode}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("Benchmark child returned malformed JSON") from None
    if not isinstance(result, dict) or "timings_seconds" not in result:
        raise RuntimeError("Benchmark child returned an invalid result")
    return result


def _worker(size, source, output, seed):
    result = build_dataset(size, source, output, seed)
    result.update({
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "peak_process_memory_mib": peak_working_set_mib(),
        "memory_scope": "whole child process high-water working set, including interpreter imports and all ETL phases; not phase-specific",
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--size", choices=tuple(TARGETS))
    parser.add_argument("--source", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, help="Output directory")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.worker:
        if args.size is None or args.output is None:
            parser.error("worker mode requires --size and --output")
        result = _worker(args.size, args.source, args.output, args.seed)
        print(json.dumps(result))
        return
    if args.size:
        if args.output is None:
            parser.error("single-case mode requires --output")
        print(json.dumps(run_case(args.size, args.source, args.output, args.seed, args.timeout), indent=2))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, help="Temporary output directory; omitted uses a temporary directory")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    if args.output:
        output = args.output
        output.mkdir(parents=True, exist_ok=True)
        result = create_benchmark_datasets(args.source, output, args.seed)
    else:
        with tempfile.TemporaryDirectory(prefix="movieverse-etl-") as temporary:
            result = create_benchmark_datasets(args.source, temporary, args.seed)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
