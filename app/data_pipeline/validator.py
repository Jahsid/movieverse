"""MovieLens rules shared by fail-fast ingestion and read-only quality reports."""

import pandas as pd


MOVIE_REQUIRED_COLUMNS = ("movieId", "title", "genres")
RATING_REQUIRED_COLUMNS = ("userId", "movieId", "rating", "timestamp")


def _valid_positive_ids(values):
    """Accept only non-null positive whole-number identifiers."""
    numbers = pd.to_numeric(values, errors="coerce")
    return numbers.notna() & (numbers > 0) & (numbers % 1 == 0)


def normalized_valid_ids(values):
    """Normalize IDs with the same positive-whole-number rule as validation."""
    return pd.to_numeric(values, errors="coerce").where(_valid_positive_ids(values))


def missing_columns(frame, required_columns):
    return [column for column in required_columns if column not in frame.columns]


def movie_row_issues(movies):
    """Return overlapping masks for the same rules used by validate_movies."""
    missing = missing_columns(movies, MOVIE_REQUIRED_COLUMNS)
    if missing:
        raise ValueError(f"Missing movie columns: {missing}")

    ids = movies["movieId"]
    numeric_ids = pd.to_numeric(ids, errors="coerce")
    valid_ids = _valid_positive_ids(ids)
    titles = movies["title"]
    text_titles = titles.map(lambda title: isinstance(title, str)).astype(bool)
    valid_titles = titles.map(
        lambda title: isinstance(title, str) and bool(title.strip())
    ).astype(bool)

    return {
        "missing_movie_id": ids.isna(),
        "invalid_movie_id": ids.notna() & ~valid_ids,
        "missing_title": titles.isna(),
        "invalid_title": titles.notna() & ~valid_titles,
        "invalid_data_type": (ids.notna() & numeric_ids.isna()) |
                             (titles.notna() & ~text_titles),
        "duplicate_key": valid_ids & numeric_ids.duplicated(keep="first"),
    }


def movie_quality_issues(movies):
    """Group movie rule masks into report categories without changing validation."""
    issues = movie_row_issues(movies)
    return {
        "missing_required_field": issues["missing_movie_id"] | issues["missing_title"],
        "invalid_data_type": issues["invalid_data_type"],
        "invalid_id": issues["invalid_movie_id"],
        "invalid_title": issues["invalid_title"],
        "duplicate_key": issues["duplicate_key"],
    }


def rating_row_issues(ratings):
    """Return overlapping masks for the same rules used by validate_ratings."""
    missing = missing_columns(ratings, RATING_REQUIRED_COLUMNS)
    if missing:
        raise ValueError(f"Missing rating columns: {missing}")

    required = ratings[list(RATING_REQUIRED_COLUMNS)]
    numeric = {column: pd.to_numeric(required[column], errors="coerce")
               for column in RATING_REQUIRED_COLUMNS}
    valid_user = _valid_positive_ids(ratings["userId"])
    valid_movie = _valid_positive_ids(ratings["movieId"])
    rating = numeric["rating"]
    timestamp = numeric["timestamp"]
    valid_rating = rating.between(0.5, 5.0) & (rating * 2 % 1 == 0)
    valid_timestamp = timestamp.notna() & (timestamp % 1 == 0)
    types_invalid = pd.concat([
        required[column].notna() & numeric[column].isna()
        for column in RATING_REQUIRED_COLUMNS
    ], axis=1).any(axis=1)
    duplicate = (valid_user & valid_movie) & pd.DataFrame({
        "userId": numeric["userId"], "movieId": numeric["movieId"]
    }).duplicated(subset=["userId", "movieId"], keep="first")

    return {
        "missing_required_field": required.isna().any(axis=1),
        "invalid_data_type": types_invalid,
        "invalid_id": (required["userId"].notna() & ~valid_user) |
                      (required["movieId"].notna() & ~valid_movie),
        "invalid_rating": required["rating"].notna() & ~valid_rating,
        "invalid_timestamp": required["timestamp"].notna() & ~valid_timestamp,
        "duplicate_key": duplicate,
    }


def validate_movies(movies):
    issues = movie_row_issues(movies)
    if issues["missing_movie_id"].any():
        raise ValueError("Movie IDs cannot be missing")
    if issues["invalid_movie_id"].any():
        raise ValueError("Movie IDs must be positive integers")
    if issues["missing_title"].any():
        raise ValueError("Movie titles cannot be missing")
    if issues["invalid_title"].any():
        raise ValueError("Movie titles cannot be blank")
    if issues["duplicate_key"].any():
        raise ValueError("Duplicate movie IDs found")
    return True


def validate_ratings(ratings):
    issues = rating_row_issues(ratings)
    if issues["missing_required_field"].any():
        raise ValueError("Required rating fields cannot be missing")
    if issues["invalid_id"].any():
        raise ValueError("User and movie IDs must be positive integers")
    if issues["invalid_rating"].any():
        raise ValueError("Ratings must be half-star values between 0.5 and 5.0")
    if issues["invalid_timestamp"].any():
        raise ValueError("Rating timestamps must be whole numbers")
    if issues["duplicate_key"].any():
        raise ValueError("Duplicate user-movie ratings found")
    return True
