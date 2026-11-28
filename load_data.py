import sys

from app.database.connection import Base, engine, SessionLocal
from app.services.ingestion_service import load_movie_files


def main():
    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            result = load_movie_files(db, "data/raw/movies.csv", "data/raw/ratings.csv")
        print("INGESTION RESULT", result)
    except Exception as error:
        print(f"INGESTION FAILED ({type(error).__name__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
