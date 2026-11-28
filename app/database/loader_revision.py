"""Read-only PostgreSQL schema preflight for file ingestion."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from scripts.baseline_verification import LEDGER, catalog, compare, expected_objects


class LoaderSchemaError(RuntimeError):
    """A diagnostic safe to display in the loader CLI."""


def configured_head():
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError:
        raise LoaderSchemaError("Install the repository's requirements-migrations.txt for the loader.") from None

    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    try:
        heads = ScriptDirectory.from_config(Config(str(ini))).get_heads()
        if len(heads) == 1:
            return heads[0]
    except Exception:
        pass
    raise LoaderSchemaError("Check alembic.ini and the revision files; the loader requires one migration head.")


def require_current_schema(connection):
    head = configured_head()
    guidance = "Review the target and migrations/README.md before retrying."
    try:
        if connection.scalar(text("SELECT current_schemas(true)")) != ["pg_catalog", "public"]:
            raise LoaderSchemaError(f"Unexpected PostgreSQL search path. {guidance}")
        objects = catalog(connection)
        if ("relation", LEDGER) not in objects:
            raise LoaderSchemaError(f"Migration ledger missing. {guidance}")
        # Read revision values only from the expected ordinary table and column.
        expected = expected_objects(True)
        for key in (("relation", LEDGER), ("column", LEDGER + ".version_num")):
            if objects.get(key) != expected[key]:
                raise LoaderSchemaError(f"Incompatible migration ledger. {guidance}")
        revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version LIMIT 2")))
        if revisions != [head]:
            raise LoaderSchemaError(f"Migration ledger must contain exactly the current revision {head}. {guidance}")
        if compare(objects, revisions, allow_metadata=True):
            raise LoaderSchemaError(f"Database schema differs from the recorded revision. {guidance}")
    except (SQLAlchemyError, ValueError):
        raise LoaderSchemaError(f"Could not inspect the PostgreSQL schema. Check connectivity and read access. {guidance}") from None
