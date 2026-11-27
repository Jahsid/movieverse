"""Liveness, readiness, and isolated startup behavior."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.main import app
from tests.helpers import seed


class FakeRecommender:
    is_trained = True

    def train(self, ratings):
        raise AssertionError("Readiness must not train the model")


@pytest.fixture
def isolated_startup(database, monkeypatch):
    """Run the real lifespan against SQLite, then restore shared app state."""
    from app import main as main_module

    previous_recommender = getattr(app.state, "recommender", None)
    previous_overrides = app.dependency_overrides.copy()
    monkeypatch.setattr(main_module, "SessionLocal", lambda: Session(database.bind))
    app.dependency_overrides[get_db] = lambda: database
    try:
        yield main_module
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        app.state.recommender = previous_recommender


def test_health_contract_stays_static_when_dependencies_are_missing(client, monkeypatch):
    monkeypatch.setattr(app.state, "recommender", None, raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "application": "MovieVerse"}


def test_ready_checks_database_and_trained_model_without_training(client, monkeypatch):
    monkeypatch.setattr(app.state, "recommender", FakeRecommender(), raising=False)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready", "database": "available", "recommendation_model": "available",
    }


def test_ready_returns_503_without_exposing_database_error(client, database, monkeypatch):
    monkeypatch.setattr(app.state, "recommender", FakeRecommender(), raising=False)

    def unavailable(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("private database host"))

    monkeypatch.setattr(database, "execute", unavailable)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready", "database": "unavailable",
        "recommendation_model": "available",
    }
    assert "private database host" not in response.text
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("model", [None, SimpleNamespace(is_trained=False)])
def test_ready_returns_503_without_trained_model(client, monkeypatch, model):
    monkeypatch.setattr(app.state, "recommender", model, raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready", "database": "available",
        "recommendation_model": "unavailable",
    }


def test_empty_ratings_allow_catalogue_but_not_recommendations(isolated_startup):
    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "healthy", "application": "MovieVerse",
        }
        assert client.get("/api/v1/movies/").status_code == 200
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json() == {
            "status": "not_ready", "database": "available",
            "recommendation_model": "unavailable",
        }
        recommendation = client.get("/api/v1/recommendations/similar/1")
        assert recommendation.status_code == 503
        assert recommendation.json() == {"detail": "Recommendation model is not ready"}
    assert app.state.recommender is None


def test_training_failure_allows_catalogue_with_unready_model(
    isolated_startup, database, monkeypatch
):
    seed(database)

    class FailingRecommender:
        is_trained = False

        def train(self, ratings):
            raise RuntimeError("private training detail")

    monkeypatch.setattr(isolated_startup, "MovieRecommender", FailingRecommender)
    with TestClient(app) as client:
        assert client.get("/api/v1/movies/1").json()["title"] == "Alpha"
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["recommendation_model"] == "unavailable"
        assert "private training detail" not in response.text
        assert client.get("/api/v1/recommendations/similar/1").status_code == 503
    assert app.state.recommender is None


def test_memory_exhaustion_during_training_stops_startup(
    isolated_startup, database, monkeypatch
):
    seed(database)

    class OutOfMemoryRecommender:
        is_trained = False

        def train(self, ratings):
            raise MemoryError("model allocation failed")

    monkeypatch.setattr(isolated_startup, "MovieRecommender", OutOfMemoryRecommender)
    with pytest.raises(MemoryError):
        with TestClient(app):
            pass
    assert app.state.recommender is None


def test_database_query_failure_stops_startup_and_closes_session(
    isolated_startup, monkeypatch
):
    closed = []

    class UnavailableSession:
        def query(self, *args):
            raise OperationalError("ratings", {}, Exception("private database host"))

        def close(self):
            closed.append(True)

    monkeypatch.setattr(isolated_startup, "SessionLocal", UnavailableSession)
    with pytest.raises(OperationalError):
        with TestClient(app):
            pass
    assert closed == [True]
    assert app.state.recommender is None
