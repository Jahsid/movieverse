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


def main():
    # 1. Extract
    movies = extract_movies("data/raw/movies.csv")
    ratings = extract_ratings("data/raw/ratings.csv")

    # 2. Validate
    validate_movies(movies)
    validate_ratings(ratings)

    # 3. Transform
    movies = transform_movies(movies)
    ratings = transform_ratings(ratings)

    # 4. Display results
    print("\nProcessed Movies:")
    print(movies.head())
    print("\nProcessed Ratings:")
    print(ratings.head())
    print("\nPipeline completed successfully!")


if __name__ == "__main__":
    main()
