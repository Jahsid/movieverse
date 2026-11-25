"""Database operations for user watchlists."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.models import Movie, User, Watchlist
from app.schemas.watchlist import WatchlistCreate, WatchlistStatus


def _item(record: Watchlist, movie: Movie) -> dict:
    """Combine a watchlist row with its movie details."""
    return {
        "movie_id": record.movie_id,
        "title": movie.title,
        "genres": movie.genres,
        "status": record.status.upper(),
        "created_at": record.added_at,
        "updated_at": record.updated_at or record.added_at,
    }


def _record(db: Session, user_id: int, movie_id: int) -> Watchlist:
    record = db.scalar(select(Watchlist).where(
        Watchlist.user_id == user_id,
        Watchlist.movie_id == movie_id,
    ))
    if record is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return record


def _commit(db: Session, conflict_detail: str) -> None:
    """Commit a mutation and leave the session usable after failure."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=conflict_detail) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database operation failed") from None


def add_to_watchlist(db: Session, data: WatchlistCreate) -> dict:
    """Create one watchlist item, rejecting missing references and duplicates."""
    if db.get(User, data.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    movie = db.get(Movie, data.movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Movie not found")
    if db.scalar(select(Watchlist.id).where(
        Watchlist.user_id == data.user_id,
        Watchlist.movie_id == data.movie_id,
    )) is not None:
        raise HTTPException(status_code=409, detail="Movie already in watchlist")

    record = Watchlist(user_id=data.user_id, movie_id=data.movie_id, status=data.status.value)
    db.add(record)
    _commit(db, "Movie already in watchlist")
    db.refresh(record)
    return _item(record, movie)


def get_user_watchlist(db: Session, user_id: int, page: int, page_size: int) -> dict:
    """Return a page of movie details for an existing user."""
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    total = db.scalar(select(func.count()).select_from(Watchlist).where(
        Watchlist.user_id == user_id,
    )) or 0
    rows = db.execute(select(Watchlist, Movie).join(
        Movie, Watchlist.movie_id == Movie.movie_id,
    ).where(Watchlist.user_id == user_id).order_by(Watchlist.added_at, Watchlist.id)
        .offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "user_id": user_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "watchlist": [_item(record, movie) for record, movie in rows],
    }


def update_watchlist_status(db: Session, user_id: int, movie_id: int,
                            status: WatchlistStatus) -> dict:
    """Update one item and its modification time."""
    record = _record(db, user_id, movie_id)
    record.status = status.value
    record.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _commit(db, "Watchlist update failed")
    db.refresh(record)
    return _item(record, db.get(Movie, movie_id))


def remove_from_watchlist(db: Session, user_id: int, movie_id: int) -> None:
    """Delete one user's watchlist item."""
    record = _record(db, user_id, movie_id)
    db.delete(record)
    _commit(db, "Watchlist deletion failed")
