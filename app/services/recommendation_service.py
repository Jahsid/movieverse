
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Movie
from app.recommender.model import MovieRecommender


def get_similar_movies(
    db: Session,
    recommender: MovieRecommender,
    movie_id: int,
    k: int = 5
):

    # Generate recommendations using KNN.
    recommendations = recommender.recommend(
        movie_id=movie_id,
        k=k
    )

    if not recommendations:
        return []

    # Retrieve movie details from PostgreSQL.
    movie_ids = [
        item["movie_id"]
        for item in recommendations
    ]

    movies = db.scalars(
        select(Movie).where(Movie.movie_id.in_(movie_ids))
    ).all()

    movie_lookup = {
        movie.movie_id: movie
        for movie in movies
    }

    # Preserve KNN ranking.
    results = []

    for item in recommendations:

        movie = movie_lookup.get(item["movie_id"])

        if movie is None:
            continue

        results.append({
            "movie_id": movie.movie_id,
            "title": movie.title,
            "genres": movie.genres,
            "similarity": round(item["similarity"], 4)
        })

    return results
