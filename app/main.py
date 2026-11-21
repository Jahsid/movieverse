
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI

from app.database.connection import Base, engine, SessionLocal
from app.database import models
from app.database.models import Rating

from app.recommender.model import MovieRecommender

from app.api.movies import router as movies_router
from app.api.recommendations import router as recommendations_router


# Initialize database tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):

    db = SessionLocal()

    try:
        print("Loading ratings from PostgreSQL...")

        records = db.query(
            Rating.user_id,
            Rating.movie_id,
            Rating.rating
        ).all()

        if not records:
            raise RuntimeError(
                "No ratings found. Please load MovieLens data first."
            )

        ratings = pd.DataFrame(
            records,
            columns=["user_id", "movie_id", "rating"]
        )

        print(f"Loaded {len(ratings)} ratings")

        print("Training recommendation model...")

        recommender = MovieRecommender()
        recommender.train(ratings)

        app.state.recommender = recommender

        print("Recommendation model loaded successfully!")

        yield

    finally:
        db.close()


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
