import sys

from app.database.loader_revision import LoaderSchemaError, require_current_schema


def load_dataset(db, movie_path="data/raw/movies.csv", rating_path="data/raw/ratings.csv"):
    from app.services.ingestion_service import load_movie_files

    require_current_schema(db.connection())
    return load_movie_files(db, movie_path, rating_path)


def main():
    try:
        from app.database.connection import SessionLocal

        with SessionLocal() as db:
            result = load_dataset(db)
        print("INGESTION RESULT", result)
    except LoaderSchemaError as error:
        print(f"INGESTION FAILED: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"INGESTION FAILED ({type(error).__name__}). Check database configuration and ingestion logs.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
