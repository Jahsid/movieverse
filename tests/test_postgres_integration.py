"""Opt-in checks against the dedicated, empty local PostgreSQL test database."""

import os

import pandas as pd
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.data_pipeline.transformer import transform_movies, transform_ratings
from app.services.ingestion_service import load_movie_data
from scripts.local_postgres_guard import checked_url, verify_identity
from app.database.connection import Base
from app.database.models import Movie, Rating, User, Watchlist


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://movieverse_itest:test-only@remote.example:5432/movieverse_itest",
    "postgresql+psycopg://movieverse_itest:test-only@127.0.0.1:5432/postgres",
    "postgresql+psycopg://postgres:test-only@127.0.0.1:5432/movieverse_itest",
    "postgresql+psycopg://movieverse_itest:test-only@127.0.0.1:5433/movieverse_itest",
])
def test_reject_unsafe_integration_target(url):
    with pytest.raises(ValueError, match="dedicated local"):
        checked_url(url)


def test_local_postgres_schema_and_transactions():
    if os.environ.get("MOVIEVERSE_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("Set MOVIEVERSE_RUN_POSTGRES_INTEGRATION=1 for the opt-in local test")

    raw_url = os.environ.get("MOVIEVERSE_TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("Set MOVIEVERSE_TEST_DATABASE_URL independently of DATABASE_URL")
    url = checked_url(raw_url)
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    created = False
    try:
        with engine.connect() as connection:
            verify_identity(connection)  # No DDL or DML occurs before this check.
            existing = connection.scalar(text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')"
            ))
            if existing:
                pytest.fail("The test database public schema is not empty; refusing to alter it")

        with engine.begin() as connection:
            verify_identity(connection)
            Base.metadata.create_all(connection)
            created = True

        with Session(engine) as session:
            verify_identity(session.connection())
            session.add_all([
                User(user_id=1), Movie(movie_id=1, title="Integration test movie"),
                Watchlist(user_id=1, movie_id=1, status="PLANNED"),
            ])
            session.commit()
            session.add(Watchlist(user_id=1, movie_id=1, status="WATCHING"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            assert session.scalar(select(Watchlist.status)) == "PLANNED"

            session.add(Movie(movie_id=2, title="Rollback candidate"))
            session.flush()
            session.rollback()
            assert session.get(Movie, 2) is None

            movies = transform_movies(pd.DataFrame([
                {"movieId": 2, "title": "Ingested (2001)", "genres": "Drama"},
            ]))
            ratings = transform_ratings(pd.DataFrame([
                {"movieId": 2, "userId": 1, "rating": 4.5, "timestamp": 10},
            ]))
            first = load_movie_data(session, movies, ratings)
            retry = load_movie_data(session, movies, ratings)
            assert (first["inserted_records"], first["users_skipped"]) == (2, 1)
            assert (retry["inserted_records"], retry["skipped_records"]) == (0, 2)
            movies = movies.assign(title="Correction", release_year=None)
            ratings = ratings.assign(rating=2.5, timestamp=11)
            changed = load_movie_data(session, movies, ratings)
            assert (changed["inserted_records"], changed["updated_records"], changed["unchanged_records"]) == (0, 2, 0)
            assert session.get(Movie, 2).release_year is None
            assert session.get(Rating, (1, 2)).rating == 2.5
            assert session.get(Movie, 1).title == "Integration test movie"
            repeat = load_movie_data(session, movies, ratings)
            assert (repeat["inserted_records"], repeat["updated_records"], repeat["unchanged_records"]) == (0, 0, 2)
    finally:
        if created:
            with engine.begin() as connection:
                verify_identity(connection)
                Base.metadata.drop_all(connection)
        engine.dispose()
