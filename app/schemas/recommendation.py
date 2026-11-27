"""Response contracts for similar-movie recommendations."""

from pydantic import BaseModel


class SimilarMovieItem(BaseModel):
    movie_id: int
    title: str
    genres: str | None
    similarity: float


class SimilarMoviesResponse(BaseModel):
    movie_id: int
    title: str
    recommendations: list[SimilarMovieItem]
