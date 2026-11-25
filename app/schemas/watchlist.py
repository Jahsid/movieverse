"""Request and response models for watchlist operations."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class WatchlistStatus(str, Enum):
    PLANNED = "PLANNED"
    WATCHING = "WATCHING"
    COMPLETED = "COMPLETED"
    DROPPED = "DROPPED"


class WatchlistCreate(BaseModel):
    user_id: int = Field(gt=0)
    movie_id: int = Field(gt=0)
    status: WatchlistStatus = WatchlistStatus.PLANNED


class WatchlistUpdate(BaseModel):
    status: WatchlistStatus


class WatchlistItemResponse(BaseModel):
    movie_id: int
    title: str
    genres: str | None
    status: WatchlistStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WatchlistResponse(BaseModel):
    user_id: int
    total: int
    page: int
    page_size: int
    watchlist: list[WatchlistItemResponse]
