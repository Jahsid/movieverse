
import pandas as pd


def _valid_positive_ids(values):
    """Accept only non-null positive whole-number identifiers."""
    numbers = pd.to_numeric(values, errors="coerce")
    return numbers.notna() & (numbers > 0) & (numbers % 1 == 0)


def validate_movies(movies):

    required_columns = [
        "movieId",
        "title",
        "genres"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in movies.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing movie columns: {missing_columns}"
        )

    if movies["movieId"].isnull().any():
        raise ValueError("Movie IDs cannot be missing")

    if not _valid_positive_ids(movies["movieId"]).all():
        raise ValueError("Movie IDs must be positive integers")

    if movies["title"].isnull().any():
        raise ValueError("Movie titles cannot be missing")

    if not movies["title"].map(lambda title: isinstance(title, str) and bool(title.strip())).all():
        raise ValueError("Movie titles cannot be blank")

    if pd.to_numeric(movies["movieId"]).duplicated().any():
        raise ValueError("Duplicate movie IDs found")

    return True


def validate_ratings(ratings):

    required_columns = [
        "userId",
        "movieId",
        "rating",
        "timestamp"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in ratings.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing rating columns: {missing_columns}"
        )

    if ratings[["userId", "movieId", "rating", "timestamp"]].isnull().any().any():
        raise ValueError("Required rating fields cannot be missing")

    if not all(_valid_positive_ids(ratings[column]).all()
               for column in ("userId", "movieId")):
        raise ValueError("User and movie IDs must be positive integers")

    numeric_ratings = pd.to_numeric(ratings["rating"], errors="coerce")
    if not (numeric_ratings.between(0.5, 5.0) &
            (numeric_ratings * 2 % 1 == 0)).all():
        raise ValueError("Ratings must be half-star values between 0.5 and 5.0")

    timestamps = pd.to_numeric(ratings["timestamp"], errors="coerce")
    if not (timestamps.notna() & (timestamps % 1 == 0)).all():
        raise ValueError("Rating timestamps must be whole numbers")

    normalized = ratings.assign(
        userId=pd.to_numeric(ratings["userId"]),
        movieId=pd.to_numeric(ratings["movieId"]),
    )
    if normalized.duplicated(
        subset=["userId", "movieId"]
    ).any():
        raise ValueError("Duplicate user-movie ratings found")

    return True
