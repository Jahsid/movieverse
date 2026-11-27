"""Movie routes against isolated SQLAlchemy records."""

from app.database.models import Movie


def test_list_details_and_pagination(client, database):
    database.add_all([
        Movie(movie_id=2, title="Beta", genres="Drama"),
        Movie(movie_id=1, title="Alpha", genres="Comedy", release_year=2000),
    ])
    database.commit()
    first = client.get("/api/v1/movies/?page_size=1")
    assert first.status_code == 200
    assert first.json() == {"total": 2, "page": 1, "page_size": 1,
                            "movies": [{"movie_id": 1, "title": "Alpha",
                                        "genres": "Comedy", "release_year": 2000}]}
    second = client.get("/api/v1/movies/?page=2&page_size=1")
    assert [movie["movie_id"] for movie in second.json()["movies"]] == [2]
    assert client.get("/api/v1/movies/1").json()["title"] == "Alpha"
    assert client.get("/api/v1/movies/99").status_code == 404
    assert client.get("/api/v1/movies/nope").status_code == 422


def test_search_and_empty_results(client, database):
    database.add_all([
        Movie(movie_id=1, title="Space One"),
        Movie(movie_id=2, title="space Two"),
        Movie(movie_id=3, title="Other"),
    ])
    database.commit()
    response = client.get("/api/v1/movies/search?q=SPACE&page_size=1")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["movies"][0]["title"] == "Space One"
    assert client.get("/api/v1/movies/search?q=absent").json()["movies"] == []
    assert client.get("/api/v1/movies/search").status_code == 422


def test_empty_catalogue(client):
    assert client.get("/api/v1/movies/").json()["total"] == 0
    assert client.get("/api/v1/movies/search?q=x").json()["movies"] == []


def test_invalid_pagination(client):
    for url in ("/api/v1/movies/?page=0", "/api/v1/movies/?page_size=0",
                "/api/v1/movies/?page_size=101", "/api/v1/movies/search?q=x&page=-1"):
        assert client.get(url).status_code == 422
