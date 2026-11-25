"""Response models for database-backed analytics endpoints."""

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    total_movies: int
    total_users: int
    total_ratings: int
    total_watchlist_items: int
    average_rating: float | None
    total_genres: int


class GenreCount(BaseModel):
    genre: str
    movie_count: int


class GenresResponse(BaseModel):
    genres: list[GenreCount]


class RatingCount(BaseModel):
    rating: float
    count: int


class RatingsResponse(BaseModel):
    average_rating: float | None
    minimum_rating: float | None
    maximum_rating: float | None
    total_ratings: int
    distribution: list[RatingCount]


class RatedMovie(BaseModel):
    movie_id: int
    title: str
    average_rating: float
    rating_count: int


class MoviesResponse(BaseModel):
    movies: list[RatedMovie]


class WatchlistMovie(BaseModel):
    movie_id: int
    title: str
    watchlist_count: int


class WatchlistStatusCount(BaseModel):
    status: str
    count: int


class WatchlistAnalyticsResponse(BaseModel):
    total_watchlist_items: int
    users_with_watchlist_items: int
    most_added_movies: list[WatchlistMovie]
    status_distribution: list[WatchlistStatusCount]
