import pytest

from scripts import benchmark_postgres as lifecycle


def test_lifecycle_requires_opt_in_and_test_url(monkeypatch):
    monkeypatch.delenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION", raising=False)
    monkeypatch.delenv("MOVIEVERSE_TEST_DATABASE_URL", raising=False)
    with pytest.raises(lifecycle.BenchmarkDatabaseError, match="opt-in"):
        lifecycle._require_opt_in()
    monkeypatch.setenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION", "1")
    with pytest.raises(lifecycle.BenchmarkDatabaseError, match="MOVIEVERSE_TEST_DATABASE_URL"):
        lifecycle._require_opt_in()


def test_lifecycle_rejects_nonlocal_url(monkeypatch):
    monkeypatch.setenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION", "1")
    monkeypatch.setenv(
        "MOVIEVERSE_TEST_DATABASE_URL",
        "postgresql+psycopg://role:secret@remote.example:5432/movieverse_itest",
    )
    with pytest.raises(ValueError, match="dedicated local"):
        lifecycle._require_opt_in()


def test_lifecycle_rejects_nonempty_schema_and_unlocks(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION", "1")
    monkeypatch.setenv("MOVIEVERSE_TEST_DATABASE_URL",
                       "postgresql+psycopg://movieverse_itest:x@127.0.0.1:5432/movieverse_itest")
    connection = Mock()
    connection.scalar.return_value = True
    engine = Mock()
    engine.connect.return_value = connection
    monkeypatch.setattr(lifecycle, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(lifecycle, "verify_identity", lambda _: None)
    monkeypatch.setattr(lifecycle, "_public_relations", lambda _: [("existing", "r")])
    with pytest.raises(lifecycle.BenchmarkDatabaseError, match="must be empty"):
        with lifecycle.benchmark_database():
            pass
    connection.close.assert_called_once()
    engine.dispose.assert_called_once()
