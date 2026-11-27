"""ETL validation, transformation, and transaction tests without Render access."""

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.data_pipeline.extractor import extract_movies, extract_ratings
from app.data_pipeline.transformer import transform_movies, transform_ratings
from app.data_pipeline.validator import validate_movies, validate_ratings
from app.database.models import IngestionJob, Movie
from app.services import ingestion_service


@pytest.fixture
def movie_frame():
    return pd.DataFrame([{"movieId": 1, "title": " Film (2001) ",
                          "genres": "Drama"}])


@pytest.fixture
def rating_frame():
    return pd.DataFrame([{"userId": 1, "movieId": 1, "rating": 4.5,
                          "timestamp": 1234567890}])


def test_extract_validate_transform(tmp_path, movie_frame, rating_frame):
    movie_path = tmp_path / "movies.csv"
    rating_path = tmp_path / "ratings.csv"
    movie_frame.to_csv(movie_path, index=False)
    rating_frame.to_csv(rating_path, index=False)
    movies = extract_movies(movie_path)
    ratings = extract_ratings(rating_path)
    assert validate_movies(movies)
    assert validate_ratings(ratings)
    assert transform_movies(movies).iloc[0]["release_year"] == 2001
    assert transform_movies(movies).iloc[0]["title"] == "Film (2001)"
    assert transform_ratings(ratings).iloc[0]["rating"] == 4.5
    assert movies.iloc[0]["title"] == " Film (2001) "


@pytest.mark.parametrize("column,value", [
    ("movieId", None), ("movieId", 0), ("movieId", "bad"),
    ("movieId", 1.5), ("title", None), ("title", " "),
])
def test_invalid_movies(movie_frame, column, value):
    movie_frame[column] = pd.Series([value], dtype=object)
    with pytest.raises(ValueError):
        validate_movies(movie_frame)


def test_duplicate_movies(movie_frame):
    with pytest.raises(ValueError, match="Duplicate"):
        validate_movies(pd.concat([movie_frame, movie_frame], ignore_index=True))


@pytest.mark.parametrize("column,value", [
    ("userId", None), ("movieId", 0), ("movieId", "bad"),
    ("userId", 1.5), ("rating", None), ("rating", "bad"),
    ("rating", 0.0), ("rating", 5.5), ("rating", 3.7),
    ("timestamp", None), ("timestamp", "bad"), ("timestamp", 1.5),
])
def test_invalid_ratings(rating_frame, column, value):
    rating_frame[column] = pd.Series([value], dtype=object)
    with pytest.raises(ValueError):
        validate_ratings(rating_frame)


def test_duplicate_ratings(rating_frame):
    with pytest.raises(ValueError, match="Duplicate"):
        validate_ratings(pd.concat([rating_frame, rating_frame], ignore_index=True))


def test_missing_columns(movie_frame, rating_frame):
    with pytest.raises(ValueError, match="Missing movie columns"):
        validate_movies(movie_frame.drop(columns="genres"))
    with pytest.raises(ValueError, match="Missing rating columns"):
        validate_ratings(rating_frame.drop(columns="timestamp"))


def test_postgres_insert_conflict_is_idempotent_by_returned_rows():
    """Check generated PostgreSQL conflict handling without connecting to Render."""
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

    class FakeDb:
        def __init__(self):
            self.calls = 0

        def execute(self, statement):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            assert "ON CONFLICT DO NOTHING" in sql
            assert "RETURNING" in sql
            self.calls += 1
            return FakeResult([(1,)] if self.calls == 1 else [])

    db = FakeDb()
    records = [{"movie_id": 1, "title": "One"}]
    assert ingestion_service.insert_in_batches(db, Movie, records) == 1
    assert ingestion_service.insert_in_batches(db, Movie, records) == 0


def test_ingestion_rollback_on_failure(database, movie_frame, rating_frame, monkeypatch):
    def fail_on_ratings(db, model, records):
        if model.__tablename__ == "ratings":
            raise RuntimeError("test failure")
        return len(records)

    monkeypatch.setattr(ingestion_service, "insert_in_batches", fail_on_ratings)
    with pytest.raises(RuntimeError, match="test failure"):
        ingestion_service.load_movie_data(database, transform_movies(movie_frame),
                                          transform_ratings(rating_frame))
    assert database.in_transaction() is False
    assert database.scalar(select(IngestionJob.id)) is None
