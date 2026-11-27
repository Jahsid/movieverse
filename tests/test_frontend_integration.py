"""Exercise the frontend client against the actual FastAPI app in memory."""

import importlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import seed

from app.database.connection import get_db
from app.main import app
from frontend import api_client


@pytest.fixture
def connected_client(database, monkeypatch):
    seed(database)
    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(main_module, "SessionLocal", lambda: Session(database.bind))
    app.dependency_overrides[get_db] = lambda: database
    previous = getattr(app.state, "recommender", None)
    try:
        with TestClient(app) as backend:
            def dispatch(method, url, **kwargs):
                path = url.removeprefix(api_client.API_BASE_URL)
                return backend.request(method, path, params=kwargs.get("params"),
                                       json=kwargs.get("json"))

            monkeypatch.setattr(api_client.requests, "request", dispatch)
            yield
    finally:
        app.dependency_overrides.clear()
        if previous is None and hasattr(app.state, "recommender"):
            del app.state.recommender
        elif previous is not None:
            app.state.recommender = previous


def test_frontend_read_flows(connected_client):
    first_page = api_client.get("/api/v1/movies/", {"page": 1, "page_size": 2})
    second_page = api_client.get("/api/v1/movies/", {"page": 2, "page_size": 2})
    assert first_page["total"] == 4
    assert [movie["movie_id"] for movie in first_page["movies"]] == [1, 2]
    assert [movie["movie_id"] for movie in second_page["movies"]] == [3, 4]
    assert api_client.get("/api/v1/movies/search", {"q": "Alpha"})["movies"][0]["movie_id"] == 1
    assert api_client.get("/api/v1/movies/search", {"q": "absent"})["movies"] == []
    assert api_client.get("/api/v1/movies/1")["title"] == "Alpha"
    assert api_client.get("/api/v1/recommendations/similar/1", {"k": 1})["recommendations"]
    assert api_client.get("/api/v1/recommendations/similar/4")["recommendations"] == []
    for route in ("overview", "genres", "ratings", "top-rated", "popular", "watchlist"):
        assert isinstance(api_client.get(f"/api/v1/analytics/{route}"), dict)
    with pytest.raises(api_client.APIError, match="not found"):
        api_client.get("/api/v1/movies/999")
    with pytest.raises(api_client.APIError, match="not found"):
        api_client.get("/api/v1/recommendations/similar/999")
    with pytest.raises(api_client.APIError, match="entered values"):
        api_client.get("/api/v1/movies/", {"page": 0})


def test_frontend_watchlist_mutations(connected_client):
    path = "/api/v1/watchlist"
    assert api_client.get(f"{path}/3")["total"] == 0
    added = api_client.post(f"{path}/", {"user_id": 3, "movie_id": 2,
                                         "status": "PLANNED"})
    assert added["status"] == "PLANNED"
    assert api_client.get(f"{path}/3")["total"] == 1
    with pytest.raises(api_client.APIError, match="already"):
        api_client.post(f"{path}/", {"user_id": 3, "movie_id": 2})
    updated = api_client.patch(f"{path}/3/2", {"status": "COMPLETED"})
    assert updated["status"] == "COMPLETED"
    api_client.delete(f"{path}/3/2")
    assert api_client.get(f"{path}/3")["total"] == 0


def test_frontend_client_connection_and_response_errors(monkeypatch):
    import requests

    def disconnected(*args, **kwargs):
        raise requests.ConnectionError("internal address")

    monkeypatch.setattr(api_client.requests, "request", disconnected)
    with pytest.raises(api_client.APIError, match="Cannot reach") as exc:
        api_client.get("/api/v1/movies/")
    assert "internal address" not in str(exc.value)

    class BadResponse:
        status_code = 200

        def json(self):
            return []

    monkeypatch.setattr(api_client.requests, "request", lambda *args, **kwargs: BadResponse())
    with pytest.raises(api_client.APIError, match="unexpected response"):
        api_client.get("/api/v1/movies/")


def test_streamlit_pages_render_with_api_shapes(monkeypatch):
    """Render every page in Streamlit's test runner with API-shaped data."""
    from streamlit.testing.v1 import AppTest

    overview = {"total_movies": 2, "total_users": 1, "total_ratings": 1,
                "total_watchlist_items": 0, "average_rating": 4.0, "total_genres": 1}
    movie = {"movie_id": 1, "title": "One", "genres": "Drama", "release_year": 2001}
    responses = {
        "/api/v1/analytics/overview": overview,
        "/api/v1/analytics/genres": {"genres": [{"genre": "Drama", "movie_count": 2}]},
        "/api/v1/analytics/ratings": {"distribution": [{"rating": 4.0, "count": 1}]},
        "/api/v1/analytics/top-rated": {"movies": [{"movie_id": 1, "title": "One",
                                                     "average_rating": 4.0, "rating_count": 1}]},
        "/api/v1/analytics/popular": {"movies": [{"movie_id": 1, "title": "One",
                                                   "average_rating": 4.0, "rating_count": 1}]},
        "/api/v1/analytics/watchlist": {"total_watchlist_items": 0,
                                         "users_with_watchlist_items": 0,
                                         "status_distribution": [], "most_added_movies": []},
        "/api/v1/movies/": {"movies": [movie], "total": 1, "page": 1, "page_size": 20},
        "/api/v1/movies/1": movie,
        "/api/v1/watchlist/1": {"watchlist": [], "total": 0},
    }
    monkeypatch.setattr(api_client, "get", lambda path, params=None: responses[path])
    app_test = AppTest.from_file("../frontend/streamlit_app.py", default_timeout=20).run()
    assert not app_test.exception
    for page in ("Discover", "For You", "My Watchlist", "Insights"):
        app_test.sidebar.radio[0].set_value(page).run()
        assert not app_test.exception


def test_discover_search_and_pagination_survive_reruns(monkeypatch):
    from streamlit.testing.v1 import AppTest

    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path == "/api/v1/analytics/overview":
            return {"total_movies": 40}
        if path in ("/api/v1/analytics/popular", "/api/v1/analytics/top-rated"):
            return {"movies": []}
        if path == "/api/v1/analytics/genres":
            return {"genres": [{"genre": "Drama", "movie_count": 40}]}
        if path in ("/api/v1/movies/", "/api/v1/movies/search"):
            page = params["page"]
            return {"total": 40, "page": page, "page_size": 20,
                    "movies": [{"movie_id": page, "title": f"Film {page}",
                                "genres": "Drama", "release_year": 2000}]}
        raise AssertionError(path)

    monkeypatch.setattr(api_client, "get", fake_get)
    app_test = AppTest.from_file("../frontend/streamlit_app.py", default_timeout=20).run()
    app_test.sidebar.radio[0].set_value("Discover").run()
    assert not app_test.exception
    app_test.text_input[0].set_value("Film")
    next(button for button in app_test.button if button.label == "Search").click().run()
    assert any(path == "/api/v1/movies/search" and params["q"] == "Film"
               for path, params in calls)
    next(button for button in app_test.button if button.label == "Next →").click().run()
    assert any(path == "/api/v1/movies/search" and params["page"] == 2
               for path, params in calls)
    assert not app_test.exception


def test_title_picker_recommendations_and_watchlist_actions(monkeypatch):
    """Exercise title-first recommendations and watchlist controls across reruns."""
    from streamlit.testing.v1 import AppTest

    movie = {"movie_id": 1, "title": "Toy Story (1995)", "genres": "Animation",
             "release_year": 1995}
    saved = []
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path == "/api/v1/analytics/overview":
            return {"total_movies": 1}
        if path in ("/api/v1/analytics/popular", "/api/v1/analytics/top-rated"):
            return {"movies": []}
        if path == "/api/v1/analytics/genres":
            return {"genres": []}
        if path == "/api/v1/movies/":
            return {"movies": [movie], "total": 1, "page": 1, "page_size": 8}
        if path == "/api/v1/movies/search":
            return {"movies": [movie], "total": 1, "page": 1, "page_size": 20}
        if path == "/api/v1/recommendations/similar/1":
            return {"movie_id": 1, "title": movie["title"],
                    "recommendations": [{"movie_id": 2, "title": "Jumanji (1995)",
                                         "genres": "Adventure", "similarity": 0.8}]}
        if path == "/api/v1/watchlist/1":
            return {"watchlist": saved.copy(), "total": len(saved)}
        raise AssertionError(path)

    def fake_post(path, payload):
        saved.append({**movie, "status": payload["status"]})
        return saved[0]

    def fake_patch(path, payload):
        saved[0]["status"] = payload["status"]
        return saved[0]

    def fake_delete(path):
        saved.clear()

    monkeypatch.setattr(api_client, "get", fake_get)
    monkeypatch.setattr(api_client, "post", fake_post)
    monkeypatch.setattr(api_client, "patch", fake_patch)
    monkeypatch.setattr(api_client, "delete", fake_delete)
    app_test = AppTest.from_file("../frontend/streamlit_app.py", default_timeout=20).run()
    app_test.text_input[0].set_value("Toy")
    next(button for button in app_test.button if button.label == "Discover movies").click().run()
    assert app_test.sidebar.radio[0].value == "Discover"
    assert any(path == "/api/v1/movies/search" for path, _ in calls)
    app_test.sidebar.radio[0].set_value("For You").run()
    app_test.text_input[0].set_value("Toy")
    next(button for button in app_test.button if button.label == "Find movies").click().run()
    next(button for button in app_test.button if button.label == "Show similar movies").click().run()
    assert any(path == "/api/v1/recommendations/similar/1" for path, _ in calls)
    assert not app_test.exception

    app_test.sidebar.radio[0].set_value("My Watchlist").run()
    app_test.text_input[0].set_value("Toy")
    next(button for button in app_test.button if button.label == "Find movies").click().run()
    next(button for button in app_test.button if button.label == "Add to watchlist").click().run()
    assert len(saved) == 1
    assert not app_test.exception
    next(item for item in app_test.selectbox if item.label == "Status").set_value("COMPLETED")
    next(button for button in app_test.button if button.label == "Update status").click().run()
    assert saved[0]["status"] == "COMPLETED"
    next(button for button in app_test.button if button.label == "Remove").click().run()
    assert saved == []
    assert not app_test.exception


def test_streamlit_handles_unavailable_api(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def unavailable(path, params=None):
        raise api_client.APIError("Cannot reach the MovieVerse API. Start the backend and try again.")

    monkeypatch.setattr(api_client, "get", unavailable)
    app_test = AppTest.from_file("../frontend/streamlit_app.py", default_timeout=20).run()
    assert not app_test.exception
    assert app_test.error
    app_test.sidebar.radio[0].set_value("Discover").run()
    assert not app_test.exception
    assert app_test.error
