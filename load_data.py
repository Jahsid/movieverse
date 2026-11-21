
from app.database.connection import Base, engine, SessionLocal
from app.database import models

from app.data_pipeline.extractor import (
    extract_movies,
    extract_ratings
)

from app.data_pipeline.validator import (
    validate_movies,
    validate_ratings
)

from app.data_pipeline.transformer import (
    transform_movies,
    transform_ratings
)

from app.services.ingestion_service import load_movie_data


def main():

    # Step 0: Create database tables
    print("STEP 0: Initializing PostgreSQL tables")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        print("\nSTEP 1: Extracting data")

        movies = extract_movies("data/raw/movies.csv")
        ratings = extract_ratings("data/raw/ratings.csv")

        print("\nSTEP 2: Validating data")

        validate_movies(movies)
        validate_ratings(ratings)

        print("Validation successful!")

        print("\nSTEP 3: Transforming data")

        movies = transform_movies(movies)
        ratings = transform_ratings(ratings)

        print("Transformation successful!")

        print("\nSTEP 4: Loading data into PostgreSQL")

        result = load_movie_data(db, movies, ratings)

        print("\nINGESTION RESULT")
        print(result)

    except Exception as error:
        print("\nINGESTION FAILED")
        print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()
