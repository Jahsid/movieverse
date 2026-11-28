import hashlib
import logging
from io import BytesIO
from pathlib import Path
from time import perf_counter

from sqlalchemy import false, or_, update
from sqlalchemy.dialects.postgresql import insert

from app.data_pipeline.extractor import extract_movies, extract_ratings
from app.data_pipeline.manifest import content_fingerprint
from app.data_pipeline.quality_report import orphan_movie_references
from app.data_pipeline.transformer import transform_movies, transform_ratings
from app.data_pipeline.validator import validate_movies, validate_ratings
from app.database.models import Movie, User, Rating, IngestionJob


BATCH_SIZE = 1000


def insert_in_batches(db, model, records):
    """Insert records in batches and count actual inserted rows."""

    inserted_count = 0

    for start in range(0, len(records), BATCH_SIZE):

        batch = records[start:start + BATCH_SIZE]

        statement = (
            insert(model)
            .values(batch)
            .on_conflict_do_nothing()
            .returning(*model.__table__.primary_key.columns)
        )

        result = db.execute(statement)

        # Count rows actually returned by PostgreSQL.
        inserted_count += len(result.fetchall())

    return inserted_count


def upsert_in_batches(db, model, records, fields):
    keys = list(model.__table__.primary_key.columns)
    inserted = updated = 0
    # Consistent lock order across concurrent ingestion jobs.
    ordered = sorted(records, key=lambda row: tuple(row[key.name] for key in keys))
    for start in range(0, len(ordered), BATCH_SIZE):
        batch = ordered[start:start + BATCH_SIZE]
        stmt = insert(model).values(batch)
        # WHERE false locks conflicting rows without rewriting them. RETURNING
        # therefore identifies inserts, and locked keys cannot disappear below.
        claim = stmt.on_conflict_do_update(
            index_elements=keys,
            set_={fields[0]: stmt.excluded[fields[0]]},
            where=false(),
        )
        new_keys = set(db.execute(claim.returning(*keys)).all())
        inserted += len(new_keys)
        existing = [row for row in batch if tuple(row[key.name] for key in keys) not in new_keys]
        if existing:
            stmt = insert(model).values(existing)
            replacements = {field: stmt.excluded[field] for field in fields}
            changed = or_(*(model.__table__.c[field].is_distinct_from(value)
                            for field, value in replacements.items()))
            stmt = stmt.on_conflict_do_update(index_elements=keys, set_=replacements, where=changed)
            updated += len(db.execute(stmt.returning(*keys)).all())
    return inserted, updated


def load_movie_files(db, movie_path, rating_path, *, previous_fingerprint=None):
    files = []

    def extract(path, reader):
        path = Path(path)
        data = path.read_bytes()
        files.append({"relative_path": path.name, "sha256": hashlib.sha256(data).hexdigest()})
        return reader(BytesIO(data))

    def read_frames():
        return extract(movie_path, extract_movies), extract(rating_path, extract_ratings)

    result = _run_job(db, read_frames, transform=True)
    fingerprint = content_fingerprint(files)
    result["content_fingerprint"] = fingerprint
    result["source_changed"] = None if previous_fingerprint is None else fingerprint != previous_fingerprint
    return result


def load_movie_data(db, movies, ratings):
    """Load prepared frames using a dedicated ingestion session."""
    return _run_job(db, lambda: (movies, ratings), transform=False)


def _run_job(db, read_frames, transform):
    started = perf_counter()
    job = IngestionJob(filename="movielens_latest_small", status="processing")
    try:
        db.add(job)
        db.flush()
        job_id = job.id
        db.commit()
    except Exception:
        db.rollback()
        raise

    total = 0
    phase = "extraction"
    try:
        movies, ratings = read_frames()
        total = len(movies) + len(ratings)
        phase = "validation"
        validate_movies(movies)
        validate_ratings(ratings)
        orphan_mask, _ = orphan_movie_references(movies, ratings)
        if orphan_mask.any():
            raise ValueError("Ratings reference movies absent from the movie file")

        phase = "transformation"
        if transform:
            movies = transform_movies(movies)
            ratings = transform_ratings(ratings)

        # Convert pandas missing values to Python None.
        movies = movies.astype(object).where(movies.notna(), None)
        ratings = ratings.astype(object).where(ratings.notna(), None)

        movie_records = [
            {
                "movie_id": row["movieId"],
                "title": row["title"],
                "genres": row["genres"],
                "release_year": row["release_year"],
            }
            for row in movies.to_dict("records")
        ]

        # Create distinct users before inserting ratings.
        user_ids = sorted(ratings["userId"].unique().tolist())

        user_records = [
            {"user_id": user_id}
            for user_id in user_ids
        ]

        rating_records = [
            {
                "user_id": row["userId"],
                "movie_id": row["movieId"],
                "rating": row["rating"],
                "timestamp": row["timestamp"],
            }
            for row in ratings.to_dict("records")
        ]

        phase = "insertion"
        # Insert parent records before dependent records.
        users_inserted = insert_in_batches(
            db, User, user_records
        )

        movies_inserted, movies_updated = upsert_in_batches(
            db, Movie, movie_records, ("title", "genres", "release_year")
        )
        ratings_inserted, ratings_updated = upsert_in_batches(
            db, Rating, rating_records, ("rating", "timestamp")
        )

        job.status = "completed"
        inserted = movies_inserted + ratings_inserted
        updated = movies_updated + ratings_updated
        unchanged = total - inserted - updated
        job.total_records = total
        job.imported_records = inserted
        job.rejected_records = 0
        phase = "commit"
        db.commit()
    except Exception as error:
        db.rollback()
        logging.getLogger(__name__).error(
            "Ingestion job %d failed during %s (%s) after %.3fs",
            job_id, phase, type(error).__name__, perf_counter() - started,
        )
        # A lost commit acknowledgement may conceal a completed transaction.
        db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job_id, IngestionJob.status == "processing")
            .values(status="failed", total_records=total)
        )
        db.commit()
        raise

    return {
        "status": "success",
        "job_id": job_id,
        "processed_records": total,
        "inserted_records": inserted,
        "skipped_records": unchanged,
        "updated_records": updated,
        "unchanged_records": unchanged,
        "movies_updated": movies_updated,
        "ratings_updated": ratings_updated,
        "users_inserted": users_inserted,
        "users_skipped": len(user_records) - users_inserted,
        "movies_inserted": movies_inserted,
        "ratings_inserted": ratings_inserted,
        "elapsed_seconds": perf_counter() - started,
    }
