
from fastapi import FastAPI

app = FastAPI(
    title="MovieVerse API",
    description="Movie Discovery and Recommendation Platform",
    version="1.0.0"
)


@app.get("/")
def home():
    return {
        "message": "Welcome to MovieVerse"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "MovieVerse"
    }
