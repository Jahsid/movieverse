
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

    if movies["title"].isnull().any():
        raise ValueError("Movie titles cannot be missing")

    if movies["movieId"].duplicated().any():
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

    if ratings[["userId", "movieId", "rating"]].isnull().any().any():
        raise ValueError("Required rating fields cannot be missing")

    if not ratings["rating"].between(0.5, 5.0).all():
        raise ValueError("Ratings must be between 0.5 and 5.0")

    if ratings.duplicated(
        subset=["userId", "movieId"]
    ).any():
        raise ValueError("Duplicate user-movie ratings found")

    return True
