"""Watchlist CRUD routes."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.watchlist import (
    WatchlistCreate, WatchlistItemResponse, WatchlistResponse, WatchlistUpdate,
)
from app.services.watchlist_service import (
    add_to_watchlist, get_user_watchlist, remove_from_watchlist,
    update_watchlist_status,
)

router = APIRouter(prefix="/api/v1/watchlist", tags=["Watchlist"])


@router.post("/", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(data: WatchlistCreate, db: Session = Depends(get_db)):
    """Add a movie to a user's watchlist."""
    return add_to_watchlist(db, data)


@router.get("/{user_id}", response_model=WatchlistResponse)
def list_watchlist(user_id: int, page: int = Query(1, ge=1),
                   page_size: int = Query(20, ge=1, le=100),
                   db: Session = Depends(get_db)):
    """List a user's watchlist with movie details."""
    return get_user_watchlist(db, user_id, page, page_size)


@router.patch("/{user_id}/{movie_id}", response_model=WatchlistItemResponse)
def patch_watchlist_item(user_id: int, movie_id: int, data: WatchlistUpdate,
                         db: Session = Depends(get_db)):
    """Change the status of a user's movie."""
    return update_watchlist_status(db, user_id, movie_id, data.status)


@router.delete("/{user_id}/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_item(user_id: int, movie_id: int,
                          db: Session = Depends(get_db)) -> Response:
    """Remove a movie from a user's watchlist."""
    remove_from_watchlist(db, user_id, movie_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
