"""Guarded Alembic lifecycle for disposable ETL benchmark runs."""

import os
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from scripts.baseline_verification import compare, catalog, expected_objects
from scripts.local_postgres_guard import checked_url, verify_identity


INI = Path(__file__).resolve().parents[1] / "alembic.ini"
LOCK_ID = 731924055221


class BenchmarkDatabaseError(RuntimeError):
    """Sanitized benchmark database lifecycle failure."""


def expected_head():
    heads = ScriptDirectory.from_config(Config(str(INI))).get_heads()
    if len(heads) != 1:
        raise BenchmarkDatabaseError("Benchmark migrations must have exactly one head.")
    return heads[0]


def _require_opt_in():
    if os.getenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION") != "1":
        raise BenchmarkDatabaseError("Set the explicit local PostgreSQL benchmark opt-in.")
    raw_url = os.getenv("MOVIEVERSE_TEST_DATABASE_URL")
    if not raw_url:
        raise BenchmarkDatabaseError("Set MOVIEVERSE_TEST_DATABASE_URL for movieverse_itest.")
    return checked_url(raw_url)


def _public_relations(connection):
    return connection.execute(text(
        "SELECT c.relname, c.relkind FROM pg_class c "
        "WHERE c.relnamespace = 'public'::regnamespace "
        "AND c.relkind IN ('r','p','v','m','S','f')"
    )).all()


@contextmanager
def benchmark_database():
    """Initialize Alembic head on an empty guarded DB and clean owned objects."""
    url = _require_opt_in()
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    lock_connection = None
    created = []
    try:
        lock_connection = engine.connect()
        verify_identity(lock_connection)
        locked = lock_connection.scalar(text("SELECT pg_try_advisory_lock(:lock_id)"),
                                        {"lock_id": LOCK_ID})
        if not locked:
            raise BenchmarkDatabaseError("Another local benchmark invocation holds the database lock.")
        if _public_relations(lock_connection):
            raise BenchmarkDatabaseError("movieverse_itest public schema must be empty before benchmark setup.")

        config = Config(str(INI))
        with engine.begin() as connection:
            verify_identity(connection)
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            created = _public_relations(connection)
            head = expected_head()
            revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version")))
            if revisions != [head] or compare(catalog(connection), revisions, allow_metadata=True):
                raise BenchmarkDatabaseError("Benchmark schema verification failed after migration.")

        try:
            yield engine
        finally:
            with engine.begin() as connection:
                verify_identity(connection)
                current = _public_relations(connection)
                created_names = {name for name, _ in created}
                current_names = {name for name, _ in current}
                if not created_names.issubset(current_names):
                    raise BenchmarkDatabaseError("Benchmark cleanup found an unexpected schema change.")
                for name, kind in sorted(created, key=lambda item: item[1] != "S"):
                    if kind in ("r", "p", "v", "m", "f", "S"):
                        connection.exec_driver_sql(f'DROP {"SEQUENCE" if kind == "S" else "TABLE"} '
                                                   f'"public"."{name}" CASCADE')
                remaining = _public_relations(connection)
                if remaining:
                    raise BenchmarkDatabaseError("Benchmark cleanup was incomplete.")
    except BenchmarkDatabaseError:
        raise
    except Exception:
        raise BenchmarkDatabaseError("Guarded benchmark database lifecycle failed; inspect the local test database.") from None
    finally:
        if lock_connection is not None:
            try:
                verify_identity(lock_connection)
                lock_connection.scalar(text("SELECT pg_advisory_unlock(:lock_id)"),
                                       {"lock_id": LOCK_ID})
            finally:
                lock_connection.close()
        engine.dispose()
