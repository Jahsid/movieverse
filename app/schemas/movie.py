from pydantic import BaseModel, ConfigDict
from typing import List


class MovieResponse(BaseModel):
    movie_id: int
    title: str
    genres: str | None = None
    release_year: int | None = None

    model_config = ConfigDict(from_attributes=True)


class MovieListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    movies: List[MovieResponse]