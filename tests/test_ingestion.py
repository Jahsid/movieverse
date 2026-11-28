"""ETL validation, transformation, and transaction tests without Render access."""

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.data_pipeline.extractor import extract_movies, extract_ratings
from app.data_pipeline.transformer import transform_movies, transform_ratings
from app.data_pipeline.validator import validate_movies, validate_ratings
from app.database.models import IngestionJob, Movie, Rating, User
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


def test_ingestion_rollback_on_failure(database, movie_frame, rating_frame, monkeypatch, caplog):
    insert_batch = ingestion_service.upsert_in_batches

    def fail_on_ratings(db, model, records, fields, batch_size=ingestion_service.BATCH_SIZE):
        if model is Rating:
            assert db.get(User, 1) and db.get(Movie, 1)
            raise RuntimeError("private row value")
        return insert_batch(db, model, records, fields, batch_size)

    monkeypatch.setattr(ingestion_service, "upsert_in_batches", fail_on_ratings)
    with pytest.raises(RuntimeError):
        ingestion_service.load_movie_data(database, transform_movies(movie_frame),
                                          transform_ratings(rating_frame))
    assert database.in_transaction() is False
    job = database.scalars(select(IngestionJob)).one()
    assert (job.status, job.total_records, job.imported_records) == ("failed", 2, 0)
    assert (job.failure_phase, job.failure_code) == ("insertion", "dataset_write_failed")
    assert (job.updated_records, job.unchanged_records, job.content_fingerprint) == (0, 0, None)
    assert database.get(Movie, 1) is None and database.get(User, 1) is None
    assert "insertion (RuntimeError)" in caplog.text
    assert "private row value" not in caplog.text


def test_file_load_and_partial_duplicate(database, tmp_path, movie_frame, rating_frame):
    movies, ratings = tmp_path / "movies.csv", tmp_path / "ratings.csv"
    movie_frame.to_csv(movies, index=False)
    rating_frame.to_csv(ratings, index=False)
    first = ingestion_service.load_movie_files(database, movies, ratings)
    assert (first["processed_records"], first["inserted_records"], first["users_inserted"]) == (2, 2, 1)
    assert first["skipped_records"] == 0 and first["elapsed_seconds"] >= 0
    pd.concat([movie_frame, movie_frame.assign(movieId=2)]).to_csv(movies, index=False)
    second = ingestion_service.load_movie_files(database, movies, ratings)
    assert (second["processed_records"], second["inserted_records"], second["skipped_records"]) == (3, 1, 2)
    assert second["users_skipped"] == 1
    job = database.get(IngestionJob, second["job_id"])
    assert (job.status, job.total_records, job.imported_records, job.rejected_records) == ("completed", 3, 1, 0)


def test_ingestion_batch_size_defaults_to_1000(database, movie_frame, rating_frame, monkeypatch):
    observed = []
    insert_batch = ingestion_service.insert_in_batches
    upsert_batch = ingestion_service.upsert_in_batches

    def record_insert(db, model, records, batch_size=ingestion_service.BATCH_SIZE):
        observed.append(batch_size)
        return insert_batch(db, model, records, batch_size)

    def record_upsert(db, model, records, fields, batch_size=ingestion_service.BATCH_SIZE):
        observed.append(batch_size)
        return upsert_batch(db, model, records, fields, batch_size)

    monkeypatch.setattr(ingestion_service, "insert_in_batches", record_insert)
    monkeypatch.setattr(ingestion_service, "upsert_in_batches", record_upsert)
    ingestion_service.load_movie_data(database, transform_movies(movie_frame),
                                      transform_ratings(rating_frame))
    assert observed == [1000, 1000, 1000]


@pytest.mark.parametrize("batch_size", [250, 1000, 2000])
def test_ingestion_accepts_benchmark_batch_sizes(database, movie_frame, rating_frame, batch_size):
    result = ingestion_service.load_movie_data(
        database, transform_movies(movie_frame), transform_ratings(rating_frame),
        batch_size=batch_size,
    )
    assert result["inserted_records"] == 2
    assert result["updated_records"] == 0
    assert result["unchanged_records"] == 0


@pytest.mark.parametrize("batch_size", [0, -1, 1.5, True, "250", None])
def test_ingestion_rejects_invalid_batch_size(database, movie_frame, rating_frame, batch_size):
    with pytest.raises(ValueError, match="positive integer"):
        ingestion_service.load_movie_data(database, transform_movies(movie_frame),
                                          transform_ratings(rating_frame), batch_size=batch_size)
    assert database.scalars(select(IngestionJob)).all() == []


def test_orphan_fails_before_inserts(database, movie_frame, rating_frame, monkeypatch):
    def unexpected_insert(*args):
        pytest.fail("Validation must precede all dataset inserts")

    monkeypatch.setattr(ingestion_service, "insert_in_batches", unexpected_insert)
    with pytest.raises(ValueError, match="absent"):
        ingestion_service.load_movie_data(database, transform_movies(movie_frame),
                                          transform_ratings(rating_frame.assign(movieId=2)))
    assert database.scalars(select(IngestionJob.status)).one() == "failed"


def test_extraction_failure_records_started_job(database, tmp_path, monkeypatch, caplog):
    movies = tmp_path / "movies.csv"
    movies.write_bytes(b"title")
    def fail_read(path):
        assert database.scalars(select(IngestionJob.status)).one() == "processing"
        raise OSError("private filename")

    monkeypatch.setattr(ingestion_service, "extract_movies", fail_read)
    with pytest.raises(OSError):
        ingestion_service.load_movie_files(database, movies, "ratings.csv")
    job = database.scalars(select(IngestionJob)).one()
    assert (job.status, job.total_records, job.imported_records) == ("failed", 0, 0)
    assert job.started_at and job.completed_at and job.duration_ms >= 0
    assert (job.failure_phase, job.failure_code, job.content_fingerprint) == ("extraction", "source_read_failed", None)
    assert "extraction (OSError)" in caplog.text
    assert "private filename" not in caplog.text


def test_lost_commit_acknowledgement_preserves_completed_job(
    database, movie_frame, rating_frame, monkeypatch
):
    commit = database.commit

    def commit_then_disconnect():
        completed = any(isinstance(row, IngestionJob) and row.status == "completed"
                        for row in database.dirty)
        commit()
        if completed:
            raise ConnectionError("lost acknowledgement")

    monkeypatch.setattr(database, "commit", commit_then_disconnect)
    with pytest.raises(ConnectionError):
        ingestion_service.load_movie_data(database, transform_movies(movie_frame),
                                          transform_ratings(rating_frame))
    job = database.scalars(select(IngestionJob)).one()
    assert (job.status, job.imported_records) == ("completed", 2)
    assert (job.failure_phase, job.failure_code, job.content_fingerprint) == (None, None, None)
    assert (job.updated_records, job.unchanged_records) == (0, 0)
    assert job.started_at and job.completed_at and job.duration_ms >= 0
    assert database.scalar(select(Rating.rating)) == 4.5


def test_incremental_file_counts_and_fingerprint(database, tmp_path, movie_frame, rating_frame):
    from app.data_pipeline.manifest import generate_manifest

    movies, ratings = tmp_path / "movies.csv", tmp_path / "ratings.csv"
    pd.concat([movie_frame, movie_frame.assign(movieId=9)]).to_csv(movies, index=False)
    rating_frame.to_csv(ratings, index=False)
    first = ingestion_service.load_movie_files(database, movies, ratings)
    assert first["content_fingerprint"] == generate_manifest(tmp_path)["content_fingerprint"]
    assert first["source_changed"] is None
    database.get(User, 1).username = "existing-profile"
    database.commit()

    # Omit movie 9, correct movie 1 (including a now-null year), add movie 2.
    pd.concat([movie_frame.assign(title="Corrected"), movie_frame.assign(movieId=2)]).to_csv(
        movies, index=False
    )
    rating_frame.assign(rating=3.0, timestamp=5).to_csv(ratings, index=False)
    changed = ingestion_service.load_movie_files(
        database, movies, ratings, previous_fingerprint=first["content_fingerprint"]
    )
    assert changed["source_changed"] is True
    assert (changed["inserted_records"], changed["updated_records"], changed["unchanged_records"]) == (1, 2, 0)
    assert (changed["movies_updated"], changed["ratings_updated"]) == (1, 1)
    assert database.get(Movie, 1).release_year is None
    assert database.get(Movie, 9) and database.get(User, 1).username == "existing-profile"
    assert database.get(Rating, (1, 1)).timestamp == 5

    def repeat():
        return ingestion_service.load_movie_files(
            database, movies, ratings, previous_fingerprint=changed["content_fingerprint"]
        )

    identical = repeat()
    assert identical["source_changed"] is False
    assert (identical["inserted_records"], identical["updated_records"], identical["unchanged_records"]) == (0, 0, 3)
    database.get(Rating, (1, 1)).rating = 1.0
    database.commit()
    repaired = repeat()
    for result in (first, changed, identical, repaired):
        job = database.get(IngestionJob, result["job_id"])
        assert job.content_fingerprint == result["content_fingerprint"]
        assert (job.imported_records, job.updated_records, job.unchanged_records) == (
            result["inserted_records"], result["updated_records"], result["unchanged_records"]
        )
        assert job.total_records == job.imported_records + job.updated_records + job.unchanged_records
        assert job.started_at and job.completed_at and 0 <= job.duration_ms <= result["elapsed_seconds"] * 1000
        assert job.failure_phase is None and job.failure_code is None
    assert repaired["source_changed"] is False and repaired["ratings_updated"] == 1
    assert database.get(Rating, (1, 1)).rating == 3.0


def test_duplicate_batch_preserves_existing_movie(database, movie_frame, rating_frame):
    def load(movies, ratings):
        return ingestion_service.load_movie_data(database, transform_movies(movies), transform_ratings(ratings))

    load(movie_frame, rating_frame)
    with pytest.raises(ValueError, match="Duplicate"):
        load(movie_frame.assign(title="Correction"), pd.concat([rating_frame, rating_frame]))
    assert database.get(Movie, 1).title == "Film (2001)"
    assert database.scalars(select(IngestionJob.status).order_by(IngestionJob.id)).all() == ["completed", "failed"]


def test_rating_write_failure_rolls_back_movie_update(database, movie_frame, rating_frame, monkeypatch):
    movies, ratings = transform_movies(movie_frame), transform_ratings(rating_frame)
    ingestion_service.load_movie_data(database, movies, ratings)
    real_upsert = ingestion_service.upsert_in_batches

    def fail_after_movie(db, model, records, fields, batch_size=ingestion_service.BATCH_SIZE):
        if model is Rating:
            assert db.scalar(select(Movie.title)) == "Correction"
            raise RuntimeError("rating write failed")
        return real_upsert(db, model, records, fields, batch_size)

    monkeypatch.setattr(ingestion_service, "upsert_in_batches", fail_after_movie)
    with pytest.raises(RuntimeError, match="rating write failed"):
        ingestion_service.load_movie_data(database, movies.assign(title="Correction"), ratings)
    assert database.get(Movie, 1).title == "Film (2001)"
    assert database.scalars(select(IngestionJob.status).order_by(IngestionJob.id)).all() == ["completed", "failed"]


def test_file_validation_failure_persists_known_fingerprint(database, tmp_path, movie_frame, rating_frame):
    from app.data_pipeline.manifest import generate_manifest

    movies, ratings = tmp_path / "movies.csv", tmp_path / "ratings.csv"
    movie_frame.to_csv(movies, index=False)
    rating_frame.assign(movieId=99).to_csv(ratings, index=False)
    with pytest.raises(ValueError, match="absent"):
        ingestion_service.load_movie_files(database, movies, ratings)
    job = database.scalars(select(IngestionJob)).one()
    assert job.content_fingerprint == generate_manifest(tmp_path)["content_fingerprint"]
    assert (job.failure_phase, job.failure_code) == ("validation", "invalid_input")
    assert (job.total_records, job.imported_records, job.updated_records, job.unchanged_records) == (2, 0, 0, 0)
