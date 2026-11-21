
from sqlalchemy.dialects.postgresql import insert

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


def load_movie_data(db, movies, ratings):

    try:
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
        user_ids = ratings["userId"].drop_duplicates().tolist()

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

        job = IngestionJob(
            filename="movielens_latest_small",
            status="processing",
            total_records=len(movie_records) + len(rating_records),
        )

        db.add(job)
        db.flush()

        # Insert parent records before dependent records.
        users_inserted = insert_in_batches(
            db, User, user_records
        )

        movies_inserted = insert_in_batches(
            db, Movie, movie_records
        )

        ratings_inserted = insert_in_batches(
            db, Rating, rating_records
        )

        job.status = "completed"
        job.imported_records = (
            users_inserted + movies_inserted + ratings_inserted
        )
        job.rejected_records = 0

        db.commit()

        return {
            "status": "success",
            "job_id": job.id,
            "users_inserted": users_inserted,
            "movies_inserted": movies_inserted,
            "ratings_inserted": ratings_inserted,
        }

    except Exception:
        db.rollback()
        raise
