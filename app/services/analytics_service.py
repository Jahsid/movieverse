"""Read-only aggregations over MovieVerse database records."""

from collections import Counter

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.database.models import Movie, Rating, User, Watchlist


def _genre_counts(db: Session) -> list[dict]:
    """Count each movie once per listed genre, ignoring empty placeholders."""
    counts: Counter[str] = Counter()
    for (genres,) in db.execute(select(Movie.genres)):
        if genres:
            counts.update({genre.strip() for genre in genres.split("|")
                           if genre.strip() and genre.strip() != "(no genres listed)"})
    return [{"genre": genre, "movie_count": count}
            for genre, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def get_overview(db: Session) -> dict:
    """Return platform totals and the average rating across all ratings."""
    total_movies = db.scalar(select(func.count()).select_from(Movie)) or 0
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_ratings, average_rating = db.execute(
        select(func.count(Rating.rating), func.avg(Rating.rating))
    ).one()
    total_watchlist_items = db.scalar(select(func.count()).select_from(Watchlist)) or 0
    return {
        "total_movies": total_movies,
        "total_users": total_users,
        "total_ratings": total_ratings,
        "total_watchlist_items": total_watchlist_items,
        "average_rating": average_rating,
        "total_genres": len(_genre_counts(db)),
    }


def get_genres(db: Session) -> dict:
    """Return genre counts sorted by frequency and then name."""
    return {"genres": _genre_counts(db)}


def get_ratings(db: Session) -> dict:
    """Return aggregate rating values and counts for values present in the table."""
    total, average, minimum, maximum = db.execute(select(
        func.count(Rating.rating), func.avg(Rating.rating),
        func.min(Rating.rating), func.max(Rating.rating),
    )).one()
    distribution = db.execute(select(Rating.rating, func.count().label("count"))
                              .group_by(Rating.rating).order_by(Rating.rating)).all()
    return {
        "average_rating": average,
        "minimum_rating": minimum,
        "maximum_rating": maximum,
        "total_ratings": total,
        "distribution": [{"rating": rating, "count": count}
                         for rating, count in distribution],
    }


def _rated_movies(db: Session, limit: int, min_ratings: int | None = None) -> dict:
    rating_count = func.count(Rating.rating).label("rating_count")
    average_rating = func.avg(Rating.rating).label("average_rating")
    statement = (select(Movie.movie_id, Movie.title, average_rating, rating_count)
                 .join(Rating, Rating.movie_id == Movie.movie_id)
                 .group_by(Movie.movie_id, Movie.title))
    if min_ratings is not None:
        statement = statement.having(func.count(Rating.rating) >= min_ratings)
        statement = statement.order_by(desc(average_rating), desc(rating_count), Movie.movie_id)
    else:
        statement = statement.order_by(desc(rating_count), desc(average_rating), Movie.movie_id)
    rows = db.execute(statement.limit(limit)).all()
    return {"movies": [{"movie_id": movie_id, "title": title,
                        "average_rating": average, "rating_count": count}
                       for movie_id, title, average, count in rows]}


def get_top_rated(db: Session, limit: int, min_ratings: int) -> dict:
    """Rank rated movies by average, subject to a minimum vote count."""
    return _rated_movies(db, limit, min_ratings)


def get_popular(db: Session, limit: int) -> dict:
    """Rank rated movies by number of ratings."""
    return _rated_movies(db, limit)


def get_watchlist(db: Session) -> dict:
    """Return watchlist totals, most added movies, and stored status counts."""
    total, users = db.execute(select(
        func.count(Watchlist.id), func.count(func.distinct(Watchlist.user_id))
    )).one()
    count = func.count(Watchlist.id).label("watchlist_count")
    movies = db.execute(
        select(Movie.movie_id, Movie.title, count)
        .join(Watchlist, Watchlist.movie_id == Movie.movie_id)
        .group_by(Movie.movie_id, Movie.title)
        .order_by(desc(count), Movie.movie_id).limit(10)
    ).all()
    statuses = db.execute(
        select(Watchlist.status, func.count().label("count"))
        .group_by(Watchlist.status).order_by(Watchlist.status)
    ).all()
    return {
        "total_watchlist_items": total,
        "users_with_watchlist_items": users,
        "most_added_movies": [{"movie_id": movie_id, "title": title,
                               "watchlist_count": movie_count}
                              for movie_id, title, movie_count in movies],
        "status_distribution": [{"status": status, "count": status_count}
                                for status, status_count in statuses],
    }
