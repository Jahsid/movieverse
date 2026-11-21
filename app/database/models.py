
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    UniqueConstraint
)

from sqlalchemy.sql import func

from app.database.connection import Base


class Movie(Base):

    __tablename__ = "movies"

    movie_id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)

    genres = Column(String)

    release_year = Column(Integer)


class User(Base):

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)

    username = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now())


class Rating(Base):

    __tablename__ = "ratings"

    user_id = Column(Integer, ForeignKey("users.user_id"), primary_key=True)

    movie_id = Column(Integer, ForeignKey("movies.movie_id"), primary_key=True)

    rating = Column(Float, nullable=False)

    timestamp = Column(Integer)


class Watchlist(Base):

    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)

    movie_id = Column(Integer, ForeignKey("movies.movie_id"), nullable=False)

    status = Column(String, default="planned")

    added_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "movie_id",
            name="unique_user_movie"
        ),
    )


class IngestionJob(Base):

    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String, nullable=False)

    status = Column(String, nullable=False)

    total_records = Column(Integer, default=0)

    imported_records = Column(Integer, default=0)

    rejected_records = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())
