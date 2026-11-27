
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import Movie
from app.schemas.recommendation import SimilarMoviesResponse
from app.services.recommendation_service import get_similar_movies


router = APIRouter(
    prefix="/api/v1/recommendations",
    tags=["Recommendations"]
)


@router.get("/similar/{movie_id}", response_model=SimilarMoviesResponse)
def recommend_similar_movies(
    movie_id: int,
    request: Request,
    k: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):

    recommender = getattr(
        request.app.state,
        "recommender",
        None
    )

    if recommender is None or not recommender.is_trained:
        raise HTTPException(
            status_code=503,
            detail="Recommendation model is not ready"
        )

    movie = db.get(Movie, movie_id)

    if movie is None:
        raise HTTPException(
            status_code=404,
            detail="Movie not found"
        )

    recommendations = get_similar_movies(
        db=db,
        recommender=recommender,
        movie_id=movie_id,
        k=k
    )

    return {
        "movie_id": movie.movie_id,
        "title": movie.title,
        "recommendations": recommendations
    }
