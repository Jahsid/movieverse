"""Analytics API tests using an isolated, in-memory SQL database."""

import importlib
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://unused:unused@127.0.0.1:1/unused"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.database.models import Movie, Rating, User, Watchlist
from app.main import app

BASE_URL = "/api/v1/analytics"


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(database):
    app.dependency_overrides[get_db] = lambda: database
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def seed(database):
    database.add_all([
        Movie(movie_id=1, title="Alpha", genres="Comedy|Drama|Comedy"),
        Movie(movie_id=2, title="Beta", genres="Drama|Sci-Fi"),
        Movie(movie_id=3, title="Gamma", genres="(no genres listed)"),
        Movie(movie_id=4, title="Unrated", genres=None),
        User(user_id=1), User(user_id=2), User(user_id=3),
    ])
    database.flush()
    database.add_all([
        Rating(user_id=1, movie_id=1, rating=5.0),
        Rating(user_id=2, movie_id=1, rating=4.0),
        Rating(user_id=3, movie_id=1, rating=4.0),
        Rating(user_id=1, movie_id=2, rating=5.0),
        Rating(user_id=2, movie_id=2, rating=5.0),
        Rating(user_id=1, movie_id=3, rating=0.5),
        Watchlist(user_id=1, movie_id=1, status="PLANNED"),
        Watchlist(user_id=2, movie_id=1, status="WATCHING"),
        Watchlist(user_id=1, movie_id=2, status="COMPLETED"),
    ])
    database.commit()


def test_overview_and_genres(client, database):
    seed(database)
    overview = client.get(f"{BASE_URL}/overview")
    assert overview.status_code == 200
    assert overview.json() == {
        "total_movies": 4, "total_users": 3, "total_ratings": 6,
        "total_watchlist_items": 3, "average_rating": pytest.approx(23.5 / 6),
        "total_genres": 3,
    }
    genres = client.get(f"{BASE_URL}/genres")
    assert genres.json() == {"genres": [
        {"genre": "Drama", "movie_count": 2},
        {"genre": "Comedy", "movie_count": 1},
        {"genre": "Sci-Fi", "movie_count": 1},
    ]}


def test_rating_statistics_and_rankings(client, database):
    seed(database)
    ratings = client.get(f"{BASE_URL}/ratings")
    assert ratings.status_code == 200
    assert ratings.json() == {
        "average_rating": pytest.approx(23.5 / 6),
        "minimum_rating": 0.5, "maximum_rating": 5.0, "total_ratings": 6,
        "distribution": [
            {"rating": 0.5, "count": 1},
            {"rating": 4.0, "count": 2},
            {"rating": 5.0, "count": 3},
        ],
    }
    assert client.get(f"{BASE_URL}/top-rated").json() == {"movies": []}
    top = client.get(f"{BASE_URL}/top-rated?min_ratings=2&limit=1")
    assert top.status_code == 200
    assert top.json() == {"movies": [
        {"movie_id": 2, "title": "Beta", "average_rating": 5.0, "rating_count": 2}
    ]}
    popular = client.get(f"{BASE_URL}/popular?limit=2")
    assert popular.status_code == 200
    assert popular.json()["movies"] == [
        {"movie_id": 1, "title": "Alpha", "average_rating": pytest.approx(13 / 3),
         "rating_count": 3},
        {"movie_id": 2, "title": "Beta", "average_rating": 5.0,
         "rating_count": 2},
    ]


def test_watchlist_statistics(client, database):
    seed(database)
    response = client.get(f"{BASE_URL}/watchlist")
    assert response.status_code == 200
    assert response.json() == {
        "total_watchlist_items": 3,
        "users_with_watchlist_items": 2,
        "most_added_movies": [
            {"movie_id": 1, "title": "Alpha", "watchlist_count": 2},
            {"movie_id": 2, "title": "Beta", "watchlist_count": 1},
        ],
        "status_distribution": [
            {"status": "COMPLETED", "count": 1},
            {"status": "PLANNED", "count": 1},
            {"status": "WATCHING", "count": 1},
        ],
    }


def test_empty_tables(client):
    assert client.get(f"{BASE_URL}/overview").json() == {
        "total_movies": 0, "total_users": 0, "total_ratings": 0,
        "total_watchlist_items": 0, "average_rating": None, "total_genres": 0,
    }
    assert client.get(f"{BASE_URL}/genres").json() == {"genres": []}
    assert client.get(f"{BASE_URL}/ratings").json() == {
        "average_rating": None, "minimum_rating": None, "maximum_rating": None,
        "total_ratings": 0, "distribution": [],
    }
    assert client.get(f"{BASE_URL}/top-rated").json() == {"movies": []}
    assert client.get(f"{BASE_URL}/popular").json() == {"movies": []}
    assert client.get(f"{BASE_URL}/watchlist").json() == {
        "total_watchlist_items": 0, "users_with_watchlist_items": 0,
        "most_added_movies": [], "status_distribution": [],
    }


@pytest.mark.parametrize("path", [
    "/top-rated?limit=0", "/top-rated?limit=101", "/top-rated?limit=abc",
    "/top-rated?min_ratings=0", "/top-rated?min_ratings=-1",
    "/popular?limit=0", "/popular?limit=101", "/popular?limit=abc",
])
def test_invalid_parameters(client, path):
    assert client.get(BASE_URL + path).status_code == 422


def test_docs_and_existing_routes(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for route in ("overview", "genres", "ratings", "top-rated", "popular", "watchlist"):
        assert "get" in paths[f"{BASE_URL}/{route}"]
    assert "get" in paths["/api/v1/movies/{movie_id}"]
    assert "get" in paths["/api/v1/recommendations/similar/{movie_id}"]
    assert "get" in paths["/api/v1/watchlist/{user_id}"]


def test_local_app_startup_and_existing_apis(database, monkeypatch):
    """Start the complete FastAPI lifespan on isolated records and exercise HTTP routes."""
    seed(database)
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(main_module, "SessionLocal", lambda: Session(database.bind))
    previous_recommender = getattr(app.state, "recommender", None)
    app.dependency_overrides[get_db] = lambda: database
    try:
        with TestClient(app) as client:
            assert client.get("/docs").status_code == 200
            for route in ("overview", "genres", "ratings", "top-rated", "popular", "watchlist"):
                assert client.get(f"{BASE_URL}/{route}").status_code == 200
            assert client.get("/api/v1/movies/1").json()["title"] == "Alpha"
            assert client.get("/api/v1/watchlist/1").json()["total"] == 2
            recommendation = client.get("/api/v1/recommendations/similar/1?k=1")
            assert recommendation.status_code == 200
            assert len(recommendation.json()["recommendations"]) == 1
    finally:
        app.dependency_overrides.clear()
        if previous_recommender is None and hasattr(app.state, "recommender"):
            del app.state.recommender
        elif previous_recommender is not None:
            app.state.recommender = previous_recommender
