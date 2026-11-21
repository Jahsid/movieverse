
import pandas as pd


def transform_movies(movies):

    movies = movies.copy()

    movies["title"] = (
        movies["title"]
        .str.strip()
    )

    movies["genres"] = (
        movies["genres"]
        .fillna("")
        .str.strip()
    )

    movies["movieId"] = movies["movieId"].astype(int)

    movies["release_year"] = pd.to_numeric(
        movies["title"].str.extract(r"\((\d{4})\)$")[0],
        errors="coerce"
    ).astype("Int64")

    return movies


def transform_ratings(ratings):

    ratings = ratings.copy()

    ratings["userId"] = ratings["userId"].astype(int)

    ratings["movieId"] = ratings["movieId"].astype(int)

    ratings["rating"] = ratings["rating"].astype(float)

    ratings["timestamp"] = ratings["timestamp"].astype(int)

    return ratings
