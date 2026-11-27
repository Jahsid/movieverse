import logging
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal, get_db
from app.database.models import Rating

from app.recommender.model import MovieRecommender

from app.api.movies import router as movies_router
from app.api.recommendations import router as recommendations_router
from app.api.watchlist import router as watchlist_router
from app.api.analytics import router as analytics_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.recommender = None
    db = SessionLocal()

    try:
        print("Loading ratings from PostgreSQL...")

        records = db.query(
            Rating.user_id,
            Rating.movie_id,
            Rating.rating
        ).all()

        if records:
            ratings = pd.DataFrame(
                records,
                columns=["user_id", "movie_id", "rating"]
            )
            print(f"Loaded {len(ratings)} ratings")
            print("Training recommendation model...")
            try:
                recommender = MovieRecommender()
                recommender.train(ratings)
                if not recommender.is_trained:
                    raise RuntimeError("Model training did not complete")
            except MemoryError:
                raise
            except Exception:
                logger.warning("Recommendation model initialization failed")
            else:
                app.state.recommender = recommender
                print("Recommendation model loaded successfully!")
        else:
            logger.warning("No ratings available; recommendations are unavailable")

        yield

    finally:
        try:
            db.close()
        finally:
            app.state.recommender = None


# Create FastAPI application
app = FastAPI(
    title="MovieVerse API",
    description="Movie Discovery and Recommendation Platform",
    version="1.0.0",
    lifespan=lifespan
)


# Register API routers
app.include_router(movies_router)
app.include_router(recommendations_router)
app.include_router(watchlist_router)
app.include_router(analytics_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to MovieVerse API"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "MovieVerse"
    }


@app.get("/ready")
def readiness_check(request: Request, db: Session = Depends(get_db)):
    """Report whether both the database and recommendation model can serve."""
    try:
        db.execute(text("SELECT 1"))
        database_status = "available"
    except SQLAlchemyError:
        database_status = "unavailable"

    recommender = getattr(request.app.state, "recommender", None)
    model_status = "available" if recommender is not None and getattr(
        recommender, "is_trained", False
    ) else "unavailable"
    ready = database_status == "available" and model_status == "available"
    response = {
        "status": "ready" if ready else "not_ready",
        "database": database_status,
        "recommendation_model": model_status,
    }
    if not ready:
        return JSONResponse(status_code=503, content=response)
    return response
