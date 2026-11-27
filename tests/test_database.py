"""SQLAlchemy integrity and session lifecycle checks on isolated SQLite."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import Movie, Rating, User, Watchlist


@pytest.fixture(autouse=True)
def enforce_foreign_keys(database):
    """SQLite disables foreign keys by default; mirror PostgreSQL enforcement."""
    database.execute(select(1))
    database.commit()
    database.connection().exec_driver_sql("PRAGMA foreign_keys=ON")


def test_connection_and_model_records(database):
    assert database.scalar(select(1)) == 1
    database.add_all([User(user_id=1), Movie(movie_id=1, title="One")])
    database.commit()
    database.add_all([
        Rating(user_id=1, movie_id=1, rating=4.5),
        Watchlist(user_id=1, movie_id=1, status="PLANNED"),
    ])
    database.commit()
    assert database.get(Rating, (1, 1)).rating == 4.5
    assert database.scalar(select(Watchlist.user_id)) == 1


def test_foreign_keys_and_rollback(database):
    database.add(Watchlist(user_id=99, movie_id=99, status="PLANNED"))
    with pytest.raises(IntegrityError):
        database.commit()
    database.rollback()
    database.add_all([User(user_id=1), Movie(movie_id=1, title="One")])
    database.commit()
    assert database.get(User, 1) is not None


def test_unique_watchlist_and_rating_constraints(database):
    database.add_all([User(user_id=1), Movie(movie_id=1, title="One"),
                      Watchlist(user_id=1, movie_id=1, status="PLANNED")])
    database.commit()
    database.add(Watchlist(user_id=1, movie_id=1, status="WATCHING"))
    with pytest.raises(IntegrityError):
        database.commit()
    database.rollback()
    database.add(Rating(user_id=1, movie_id=1, rating=4.0))
    database.commit()
    database.add(Rating(user_id=1, movie_id=1, rating=5.0))
    with pytest.raises(IntegrityError):
        database.commit()
    database.rollback()
    assert database.get(Rating, (1, 1)).rating == 4.0


def test_get_db_closes_session(monkeypatch):
    from app.database import connection

    class TrackedSession:
        closed = False

        def close(self):
            self.closed = True

    session = TrackedSession()
    monkeypatch.setattr(connection, "SessionLocal", lambda: session)
    dependency = connection.get_db()
    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)
    assert session.closed


def test_watchlist_http_writes_against_real_session(client, database):
    database.add_all([User(user_id=1), Movie(movie_id=1, title="One")])
    database.commit()
    path = "/api/v1/watchlist/"
    assert client.post(path, json={"user_id": 1, "movie_id": 1}).status_code == 201
    assert client.post(path, json={"user_id": 1, "movie_id": 1}).status_code == 409
    assert client.patch(path + "1/1", json={"status": "COMPLETED"}).json()["status"] == "COMPLETED"
    assert client.get(path + "1").json()["total"] == 1
    assert client.delete(path + "1/1").status_code == 204
    assert client.get(path + "1").json()["total"] == 0
