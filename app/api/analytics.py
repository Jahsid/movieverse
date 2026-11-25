"""Analytics routes backed by SQLAlchemy aggregations."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.schemas.analytics import (GenresResponse, MoviesResponse, OverviewResponse,
                                   RatingsResponse, WatchlistAnalyticsResponse)
from app.services import analytics_service

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


def _respond(db: Session, service: Callable[..., dict], *args: int) -> dict:
    """Translate database failures into the API's 503 error response."""
    try:
        return service(db, *args)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database operation failed") from None


@router.get("/overview", response_model=OverviewResponse)
def overview(db: Session = Depends(get_db)):
    """Show platform totals and average rating."""
    return _respond(db, analytics_service.get_overview)


@router.get("/genres", response_model=GenresResponse)
def genres(db: Session = Depends(get_db)):
    """Show counts of movies per genre."""
    return _respond(db, analytics_service.get_genres)


@router.get("/ratings", response_model=RatingsResponse)
def ratings(db: Session = Depends(get_db)):
    """Show rating aggregates and distribution."""
    return _respond(db, analytics_service.get_ratings)


@router.get("/top-rated", response_model=MoviesResponse)
def top_rated(limit: int = Query(10, ge=1, le=100),
              min_ratings: int = Query(10, ge=1), db: Session = Depends(get_db)):
    """Show highest-average movies with enough ratings."""
    return _respond(db, analytics_service.get_top_rated, limit, min_ratings)


@router.get("/popular", response_model=MoviesResponse)
def popular(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """Show movies with the most ratings."""
    return _respond(db, analytics_service.get_popular, limit)


@router.get("/watchlist", response_model=WatchlistAnalyticsResponse)
def watchlist(db: Session = Depends(get_db)):
    """Show watchlist totals, common movies, and status distribution."""
    return _respond(db, analytics_service.get_watchlist)
