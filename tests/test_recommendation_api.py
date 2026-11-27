"""Contract tests for the existing similar-movie recommendation route."""

import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import recommendations as recommendations_api
from app.database.connection import Base, get_db
from app.database.models import Movie
from app.main import app


class FakeRecommender:
    is_trained = True

    def recommend(self, movie_id: int, k: int = 5) -> list[dict]:
        if movie_id != 1:
            return []
        return [
            {"movie_id": 3, "similarity": 0.987654},
            {"movie_id": 2, "similarity": 0.5},
            {"movie_id": 99, "similarity": 0.25},
        ][:k]


@pytest.fixture
def recommendation_client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    recommender = FakeRecommender()
    with Session(engine) as db:
        db.add_all([
            Movie(movie_id=1, title="Seed", genres="Drama"),
            Movie(movie_id=2, title="No genre", genres=None),
            Movie(movie_id=3, title="Comedy", genres="Comedy"),
            Movie(movie_id=4, title="Unrated", genres=None),
        ])
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        monkeypatch.setattr(app.state, "recommender", recommender, raising=False)
        try:
            yield TestClient(app), recommender
        finally:
            app.dependency_overrides.clear()
    engine.dispose()


def test_similar_movies_existing_json_contract(recommendation_client):
    client, _ = recommendation_client

    response = client.get("/api/v1/recommendations/similar/1?k=3")

    assert response.status_code == 200
    assert response.json() == {
        "movie_id": 1,
        "title": "Seed",
        "recommendations": [
            {"movie_id": 3, "title": "Comedy", "genres": "Comedy", "similarity": 0.9877},
            {"movie_id": 2, "title": "No genre", "genres": None, "similarity": 0.5},
        ],
    }
    assert client.get("/api/v1/recommendations/similar/4").json() == {
        "movie_id": 4, "title": "Unrated", "recommendations": [],
    }


def test_similar_movies_existing_error_contract(recommendation_client):
    client, recommender = recommendation_client
    path = "/api/v1/recommendations/similar"

    missing = client.get(f"{path}/999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Movie not found"}

    recommender.is_trained = False
    unavailable = client.get(f"{path}/1")
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "Recommendation model is not ready"}

    recommender.is_trained = True
    for k in (0, 21):
        invalid = client.get(f"{path}/1?k={k}")
        assert invalid.status_code == 422
        assert isinstance(invalid.json()["detail"], list)


def test_similar_movies_openapi_response_schema(recommendation_client):
    client, _ = recommendation_client
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/recommendations/similar/{movie_id}"]["get"]

    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SimilarMoviesResponse",
    }
    response_model = schema["components"]["schemas"]["SimilarMoviesResponse"]
    item_model = schema["components"]["schemas"]["SimilarMovieItem"]
    assert set(response_model["required"]) == {"movie_id", "title", "recommendations"}
    assert response_model["properties"]["recommendations"]["items"] == {
        "$ref": "#/components/schemas/SimilarMovieItem",
    }
    assert set(item_model["required"]) == {"movie_id", "title", "genres", "similarity"}
    assert {choice["type"] for choice in item_model["properties"]["genres"]["anyOf"]} == {
        "string", "null",
    }


def test_similar_movies_rejects_invalid_service_response(recommendation_client, monkeypatch):
    client, _ = recommendation_client
    monkeypatch.setattr(recommendations_api, "get_similar_movies", lambda **kwargs: [
        {"movie_id": 2, "title": "No genre", "similarity": 0.5},
    ])

    with pytest.raises(ResponseValidationError):
        client.get("/api/v1/recommendations/similar/1")
