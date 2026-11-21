from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db

from app.schemas.movie import (
    MovieResponse,
    MovieListResponse
)

from app.services.movie_service import (
    get_movies,
    get_movie_by_id,
    search_movies
)


router = APIRouter(
    prefix="/api/v1/movies",
    tags=["Movies"]
)


# Search movies
@router.get("/search", response_model=MovieListResponse)
def search_movie_endpoint(
    q: str = Query(..., min_length=1, description="Movie title keyword"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):

    return search_movies(db, q, page, page_size)


# List movies
@router.get("/", response_model=MovieListResponse)
def list_movies_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):

    return get_movies(db, page, page_size)


# Get movie by ID
@router.get("/{movie_id}", response_model=MovieResponse)
def get_movie_endpoint(
    movie_id: int,
    db: Session = Depends(get_db)
):

    movie = get_movie_by_id(db, movie_id)

    if movie is None:
        raise HTTPException(
            status_code=404,
            detail=f"Movie with ID {movie_id} not found"
        )

    return movie