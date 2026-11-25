"""Watchlist API tests with an in-memory session double; no database is contacted."""

import os
from datetime import datetime

os.environ["DATABASE_URL"] = "postgresql+psycopg://unused:unused@127.0.0.1:1/unused"

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_db
from app.database.models import Movie, User, Watchlist
from app.main import app


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    """Implement only the Session operations used by the watchlist service."""

    def __init__(self):
        self.users = {1: User(user_id=1)}
        self.movies = {
            1: Movie(movie_id=1, title="Toy Story (1995)", genres="Animation"),
            2: Movie(movie_id=2, title="Jumanji (1995)", genres="Adventure"),
        }
        self.items = {}
        self.pending = None
        self.deleted = None
        self.next_id = 1

    def get(self, model, key):
        if model is User:
            return self.users.get(key)
        if model is Movie:
            return self.movies.get(key)
        return None

    def _matching(self, statement):
        # SQLAlchemy's compiled parameters encode the two watchlist predicates.
        params = list(statement.compile().params.values())
        if len(params) >= 2:
            return self.items.get((params[0], params[1]))
        return None

    def scalar(self, statement):
        names = [entry["name"] for entry in statement.column_descriptions]
        if names == ["count"]:
            params = list(statement.compile().params.values())
            return sum(uid == params[0] for uid, _ in self.items)
        item = self._matching(statement)
        if names == ["id"]:
            return item.id if item else None
        return item

    def execute(self, statement):
        params = statement.compile().params
        user_id = next(iter(params.values()))
        rows = [(item, self.movies[item.movie_id]) for (uid, _), item in self.items.items()
                if uid == user_id]
        rows.sort(key=lambda pair: (pair[0].added_at, pair[0].id))
        return FakeResult(rows[params.get("param_2", 0):][:params.get("param_1", 20)])

    def add(self, item):
        self.pending = item

    def delete(self, item):
        self.deleted = item

    def commit(self):
        if self.pending is not None:
            self.pending.id = self.next_id
            self.next_id += 1
            self.pending.added_at = datetime(2026, 1, 1)
            self.pending.updated_at = self.pending.added_at
            self.items[(self.pending.user_id, self.pending.movie_id)] = self.pending
            self.pending = None
        if self.deleted is not None:
            self.items.pop((self.deleted.user_id, self.deleted.movie_id))
            self.deleted = None

    def refresh(self, item):
        pass


@pytest.fixture
def client():
    db = FakeSession()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.clear()


def test_post_validations_and_duplicate(client):
    url = "/api/v1/watchlist/"
    assert client.post(url, json={"user_id": 9, "movie_id": 1}).status_code == 404
    assert client.post(url, json={"user_id": 1, "movie_id": 9}).status_code == 404
    assert client.post(url, json={"user_id": 1, "movie_id": 1,
                                  "status": "INVALID"}).status_code == 422
    created = client.post(url, json={"user_id": 1, "movie_id": 1,
                                     "status": "PLANNED"})
    assert created.status_code == 201
    assert created.json()["title"] == "Toy Story (1995)"
    assert client.post(url, json={"user_id": 1, "movie_id": 1}).status_code == 409


def test_get_populated_empty_and_missing(client):
    url = "/api/v1/watchlist/"
    assert client.get(url + "1").json()["watchlist"] == []
    assert client.get(url + "9").status_code == 404
    client.post(url, json={"user_id": 1, "movie_id": 1})
    response = client.get(url + "1")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["watchlist"][0]["genres"] == "Animation"
    client.post(url, json={"user_id": 1, "movie_id": 2})
    second_page = client.get(url + "1?page=2&page_size=1")
    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert second_page.json()["watchlist"][0]["movie_id"] == 2


def test_patch_status_and_validation(client):
    url = "/api/v1/watchlist/1/1"
    assert client.patch(url, json={"status": "COMPLETED"}).status_code == 404
    client.post("/api/v1/watchlist/", json={"user_id": 1, "movie_id": 1})
    assert client.patch(url, json={"status": "INVALID"}).status_code == 422
    response = client.patch(url, json={"status": "COMPLETED"})
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["updated_at"] is not None


def test_delete_and_verify_absent(client):
    url = "/api/v1/watchlist/1/1"
    assert client.delete(url).status_code == 404
    client.post("/api/v1/watchlist/", json={"user_id": 1, "movie_id": 1})
    response = client.delete(url)
    assert response.status_code == 204
    assert response.content == b""
    assert client.get("/api/v1/watchlist/1").json()["total"] == 0
    assert client.delete(url).status_code == 404


def test_openapi_and_existing_routes(client):
    """Confirm route registration without starting a production database session."""
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/v1/watchlist/"]
    assert "get" in paths["/api/v1/watchlist/{user_id}"]
    item_path = paths["/api/v1/watchlist/{user_id}/{movie_id}"]
    assert {"patch", "delete"}.issubset(item_path)
    assert "get" in paths["/api/v1/movies/{movie_id}"]
    assert "get" in paths["/api/v1/recommendations/similar/{movie_id}"]
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/movies/99").status_code == 404
    assert client.get("/api/v1/recommendations/similar/1").status_code == 503
