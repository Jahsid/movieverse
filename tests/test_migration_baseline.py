"""Offline baseline contract and opt-in transactional PostgreSQL verification."""

import os
from io import StringIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateColumn
from sqlalchemy.orm import Session

pytest.importorskip("alembic", reason="requires requirements-migrations.txt")
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database.models import Base, IngestionJob
from app.data_pipeline.manifest import generate_manifest
from app.database.loader_revision import LoaderSchemaError
from load_data import load_dataset
from app.services.ingestion_service import load_movie_files
from scripts.baseline_verification import METADATA_REVISION, METADATA_TYPES, compare, expected_objects, verify_baseline
from scripts.local_postgres_guard import checked_url, verify_identity


INI = Path(__file__).resolve().parents[1] / "alembic.ini"
BASELINE = "0001_stage_1f"
LEGACY_SCHEMA = Path(__file__).parent / "fixtures" / "stage_1f_schema.sql"


def legacy_statements():
    return [sql.strip() for sql in LEGACY_SCHEMA.read_text().split(";") if sql.strip()]


def test_frozen_baseline_sql(monkeypatch):
    def unexpected_engine(*args, **kwargs):
        pytest.fail("Offline migration attempted to construct an engine")

    monkeypatch.setattr(sa, "create_engine", unexpected_engine)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MOVIEVERSE_TEST_DATABASE_URL", raising=False)
    output = StringIO()
    config = Config(str(INI), output_buffer=output)
    assert ScriptDirectory.from_config(config).get_heads() == [METADATA_REVISION]
    command.upgrade(config, BASELINE, sql=True)
    normalized = " ".join(" ".join(s for s in output.getvalue().splitlines()
                                   if not s.startswith("--")).split())
    for statement in legacy_statements():
        assert " ".join(statement.split()) + ";" in normalized
    assert normalized.count("CREATE TABLE ") == 6
    assert normalized.count("CREATE INDEX ") == 3
    assert "INSERT INTO alembic_version" in normalized and BASELINE in normalized

    output.seek(0)
    output.truncate()
    command.downgrade(config, f"{BASELINE}:base", sql=True)
    assert "DELETE FROM alembic_version" in output.getvalue()
    drops = [line for line in output.getvalue().splitlines() if line.startswith("DROP TABLE")]
    assert drops == [f"DROP TABLE {name};" for name in
                     ("ingestion_jobs", "watchlist", "ratings", "users", "movies")]


def test_model_import_is_connection_independent():
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c",
                    "import sys; from app.database.models import Base; "
                    "assert 'app.database.connection' not in sys.modules; "
                    "assert 'dotenv' not in sys.modules; assert len(Base.metadata.tables) == 5"],
                   cwd=INI.parent, check=True)


def test_online_cli_refuses_application_url(monkeypatch):
    monkeypatch.setenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION", "1")
    monkeypatch.setenv("DATABASE_URL", "unused")
    with pytest.raises(RuntimeError, match="guarded local test connection"):
        command.upgrade(Config(str(INI)), "head")


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy-adoption"])
def test_guarded_local_baseline(legacy, tmp_path):
    if os.getenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires dedicated local PostgreSQL opt-in")
    url = checked_url(os.getenv("MOVIEVERSE_TEST_DATABASE_URL", ""))
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection, connection.begin() as transaction:
            verify_identity(connection)
            connection.exec_driver_sql("SET LOCAL search_path TO public")
            existing = connection.scalar(sa.text(
                "SELECT count(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace"
            ))
            assert existing == 0, "Refusing to alter nonempty public schema"
            config = Config(str(INI))
            config.attributes["connection"] = connection
            if legacy:
                # Reproduce the original loader initialization independently of Alembic.
                for statement in legacy_statements():
                    connection.exec_driver_sql(statement)
                connection.exec_driver_sql("INSERT INTO users(username) VALUES ('legacy user')")
                connection.exec_driver_sql("INSERT INTO movies(title) VALUES ('legacy film')")
                connection.exec_driver_sql("INSERT INTO ratings VALUES (1,1,4.5,100)")
                connection.exec_driver_sql("INSERT INTO watchlist(user_id,movie_id) VALUES (1,1)")
                connection.exec_driver_sql("INSERT INTO ingestion_jobs(filename,status,imported_records)"
                                           " VALUES ('legacy.csv','completed',17)")
                def rows():
                    return {name: connection.exec_driver_sql(f"SELECT * FROM public.{name}").all()
                            for name in ("users", "movies", "ratings", "watchlist", "ingestion_jobs")}

                before = rows()
                assert not verify_baseline(connection)
                with pytest.raises(ValueError, match="Explicit authorization"):
                    command.stamp(config, BASELINE)
                for drift in ("ALTER TABLE watchlist DROP COLUMN updated_at",
                              "ALTER TABLE watchlist DROP CONSTRAINT unique_user_movie",
                              "ALTER SEQUENCE users_user_id_seq INCREMENT BY 2"):
                    savepoint = connection.begin_nested()
                    connection.exec_driver_sql(drift)
                    with pytest.raises(ValueError, match="Baseline verification failed"):
                        command.stamp(config, BASELINE, tag="authorize-stage-1f-adoption")
                    assert not sa.inspect(connection).has_table("alembic_version", schema="public")
                    savepoint.rollback()
                command.stamp(config, BASELINE, tag="authorize-stage-1f-adoption")
                assert rows() == before
            command.upgrade(config, BASELINE)
            command.upgrade(config, BASELINE)
            assert verify_baseline(connection)
            if legacy:
                assert rows() == before
            savepoint = connection.begin_nested()
            connection.exec_driver_sql("UPDATE alembic_version SET version_num='unknown'")
            with pytest.raises(ValueError, match="incompatible migration history"):
                command.stamp(config, BASELINE, tag="authorize-stage-1f-adoption")
            savepoint.rollback()
            if not legacy:
                connection.exec_driver_sql("INSERT INTO ingestion_jobs(filename,status) "
                                           "VALUES ('old.csv','completed')")
            old_columns = ", ".join(col["name"] for col in sa.inspect(connection).get_columns("ingestion_jobs"))
            original_job = connection.exec_driver_sql(f"SELECT {old_columns} FROM ingestion_jobs").one()
            for attempt in range(2):
                command.upgrade(config, "head")
                command.upgrade(config, "head")
                assert verify_baseline(connection, allow_metadata=True)
                assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == METADATA_REVISION
                metadata_columns = ", ".join(METADATA_TYPES)
                values = connection.exec_driver_sql(f"SELECT {metadata_columns} FROM ingestion_jobs").one()
                assert tuple(values) == (None,) * len(METADATA_TYPES)
                assert connection.exec_driver_sql(f"SELECT {old_columns} FROM ingestion_jobs").one() == original_job
                if attempt == 0:
                    command.downgrade(config, BASELINE)
                    assert verify_baseline(connection)
                    assert connection.exec_driver_sql("SELECT * FROM ingestion_jobs").one() == original_job
            check_loader_rejections(connection, tmp_path)
            check_migrated_job_metadata(connection, tmp_path)
            assert connection.exec_driver_sql(
                f"SELECT {old_columns} FROM ingestion_jobs WHERE id=1"
            ).one() == original_job
            command.downgrade(config, "base")
            assert set(sa.inspect(connection).get_table_names()) == {"alembic_version"}
            transaction.rollback()
        with engine.connect() as cleanup_connection:
            verify_identity(cleanup_connection)
            remaining = cleanup_connection.scalar(sa.text(
                "SELECT count(*) FROM pg_class WHERE relnamespace = 'public'::regnamespace"
            ))
            assert remaining == 0, "Rollback left relations in the public schema"
    finally:
        engine.dispose()


def check_loader_rejections(connection, tmp_path):
    tables = ("ingestion_jobs", "users", "movies", "ratings", "watchlist")

    def rows():
        return [connection.exec_driver_sql(f"SELECT * FROM public.{name}").all() for name in tables]

    before = rows()
    for change in ("DROP TABLE public.alembic_version",
                   "UPDATE public.alembic_version SET version_num='0001_stage_1f'",
                   "UPDATE public.alembic_version SET version_num='unknown'",
                   "INSERT INTO public.alembic_version VALUES ('extra')",
                   "ALTER TABLE public.alembic_version RENAME COLUMN version_num TO unexpected"):
        savepoint = connection.begin_nested()
        connection.exec_driver_sql(change)
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            with pytest.raises(LoaderSchemaError):
                load_dataset(session, tmp_path / "movies.csv", tmp_path / "ratings.csv")
        assert rows() == before
        savepoint.rollback()


def check_migrated_job_metadata(connection, tmp_path):
    movies = tmp_path / "movies.csv"
    ratings = tmp_path / "ratings.csv"
    movies.write_text("movieId,title,genres\n99,Example (2001),Drama\n")
    ratings.write_text("userId,movieId,rating,timestamp\n99,99,4.5,100\n")
    expected_hash = generate_manifest(tmp_path)["content_fingerprint"]
    with Session(connection, join_transaction_mode="create_savepoint") as session:
        result = load_dataset(session, movies, ratings)
        job = session.get(IngestionJob, result["job_id"])
        assert job.content_fingerprint == expected_hash
        assert (job.total_records, job.imported_records, job.updated_records, job.unchanged_records) == (2, 2, 0, 0)
        assert job.started_at.utcoffset() is not None and job.completed_at.utcoffset() is not None
        assert job.duration_ms >= 0 and job.failure_phase is None and job.failure_code is None
        assert result["users_inserted"] == 1

        ratings.write_text("userId,movieId,rating,timestamp\n99,100,4.5,100\n")
        with pytest.raises(ValueError, match="absent"):
            load_movie_files(session, movies, ratings)
        failure = session.scalars(sa.select(IngestionJob).where(IngestionJob.status == "failed")).one()
        assert (failure.failure_phase, failure.failure_code) == ("validation", "invalid_input")
        assert failure.content_fingerprint == generate_manifest(tmp_path)["content_fingerprint"]
        assert failure.duration_ms >= 0 and failure.completed_at.utcoffset() is not None


@pytest.mark.parametrize("change, issue", [
    (("column", "watchlist.updated_at"), "missing column"),
    (("constraint", "ratings.ratings_movie_id_fkey"), "incompatible constraint"),
    (("index", "ix_watchlist_id"), "incompatible index"),
    (("sequence", "users_user_id_seq"), "incompatible sequence"),
    (("relation", "unexpected_view"), "unexpected relation"),
])
def test_baseline_drift(change, issue):
    objects = expected_objects(False)
    if issue.startswith("missing"):
        del objects[change]
    else:
        objects[change] = "different"
    assert any(issue in message for message in compare(objects, []))


@pytest.mark.parametrize("versioned, revisions, valid", [
    (False, [], True), (True, [BASELINE], True), (True, [], False),
    (True, ["unknown"], False), (True, [BASELINE, "unknown"], False),
])
def test_baseline_history(versioned, revisions, valid):
    assert (compare(expected_objects(versioned), revisions) == []) == valid


def test_metadata_revision_sql_and_model():
    stream = StringIO()
    config = Config(str(INI), output_buffer=stream)
    command.upgrade(config, f"{BASELINE}:{METADATA_REVISION}", sql=True)
    dialect = postgresql.dialect()
    sql = stream.getvalue()
    additions = [line for line in sql.splitlines() if line.startswith("ALTER TABLE")]
    expected = []
    for name in METADATA_TYPES:
        column = IngestionJob.__table__.c[name]
        assert column.nullable and column.default is None and column.server_default is None
        definition = CreateColumn(column).compile(dialect=dialect)
        expected.append(f"ALTER TABLE ingestion_jobs ADD COLUMN {definition};")
    assert additions == expected
    assert "UPDATE ingestion_jobs" not in sql
    stream.seek(0)
    stream.truncate()
    command.downgrade(config, f"{METADATA_REVISION}:{BASELINE}", sql=True)
    drops = [line for line in stream.getvalue().splitlines() if line.startswith("ALTER TABLE")]
    assert drops == [f"ALTER TABLE ingestion_jobs DROP COLUMN {name};" for name in reversed(METADATA_TYPES)]


def test_metadata_schema_requires_matching_ledger():
    objects = expected_objects(True)
    assert compare(objects, [METADATA_REVISION], allow_metadata=True)
    for name, datatype in METADATA_TYPES.items():
        objects["column", f"ingestion_jobs.{name}"] = (datatype, False, None, None, "", "")
    assert compare(objects, [METADATA_REVISION], allow_metadata=True) == []
    assert compare(objects, [BASELINE], allow_metadata=True)
    assert compare(objects, [METADATA_REVISION])
    objects["column", "ingestion_jobs.started_at"] = ("timestamp without time zone", False, None, None, "", "")
    assert compare(objects, [METADATA_REVISION], allow_metadata=True)
