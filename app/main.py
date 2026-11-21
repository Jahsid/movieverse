from fastapi import FastAPI

from app.database.connection import Base, engine, SessionLocal
from app.database import models

Base.metadata.create_all(bind=engine)
db = SessionLocal()

app = FastAPI(
    title="MovieVerse API",
    description="Movie Discovery and Recommendation Platform",
    version="1.0.0"
)

@app.get("/")
def home():
    return {"message": "Welcome to MovieVerse"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}