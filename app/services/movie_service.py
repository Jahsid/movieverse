from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database.models import Movie


def get_movies(db: Session, page: int = 1, page_size: int = 20):

    offset = (page - 1) * page_size

    # Retrieve total movie count.
    total = db.scalar(
        select(func.count()).select_from(Movie)
    )

    # Retrieve movies for the requested page.
    movies = db.scalars(
        select(Movie)
        .order_by(Movie.movie_id)
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "total": total or 0,
        "page": page,
        "page_size": page_size,
        "movies": movies
    }


def get_movie_by_id(db: Session, movie_id: int):

    movie = db.scalar(
        select(Movie).where(Movie.movie_id == movie_id)
    )

    return movie


def search_movies(db: Session, query: str, page: int = 1, page_size: int = 20):

    offset = (page - 1) * page_size

    # Case-insensitive title search.
    search_filter = Movie.title.ilike(f"%{query}%")

    total = db.scalar(
        select(func.count())
        .select_from(Movie)
        .where(search_filter)
    )

    movies = db.scalars(
        select(Movie)
        .where(search_filter)
        .order_by(Movie.title)
        .offset(offset)
        .limit(page_size)
    ).all()

    return {
        "total": total or 0,
        "page": page,
        "page_size": page_size,
        "movies": movies
    }