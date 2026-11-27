"""Shared fixtures and a deliberately unreachable database configuration."""

import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://127.0.0.1:1/unused"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.connection import Base, get_db
from app.main import app


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def client(database):
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: database
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
