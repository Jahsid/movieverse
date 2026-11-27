"""Shared test data builders."""

from app.database.models import Movie, Rating, User, Watchlist


def seed(database):
    database.add_all([
        Movie(movie_id=1, title="Alpha", genres="Comedy|Drama|Comedy"),
        Movie(movie_id=2, title="Beta", genres="Drama|Sci-Fi"),
        Movie(movie_id=3, title="Gamma", genres="(no genres listed)"),
        Movie(movie_id=4, title="Unrated", genres=None),
        User(user_id=1), User(user_id=2), User(user_id=3),
    ])
    database.flush()
    database.add_all([
        Rating(user_id=1, movie_id=1, rating=5.0),
        Rating(user_id=2, movie_id=1, rating=4.0),
        Rating(user_id=3, movie_id=1, rating=4.0),
        Rating(user_id=1, movie_id=2, rating=5.0),
        Rating(user_id=2, movie_id=2, rating=5.0),
        Rating(user_id=1, movie_id=3, rating=0.5),
        Watchlist(user_id=1, movie_id=1, status="PLANNED"),
        Watchlist(user_id=2, movie_id=1, status="WATCHING"),
        Watchlist(user_id=1, movie_id=2, status="COMPLETED"),
    ])
    database.commit()
