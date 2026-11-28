"""Offline SQL by default. Online migrations require the guarded test harness."""

import os

from alembic import context
from sqlalchemy import text

from app.database.models import Base
from scripts.baseline_verification import BASELINE, COLUMNS, guard_connection, verify_baseline


def run():
    if context.is_offline_mode():
        context.configure(dialect_name="postgresql", target_metadata=Base.metadata,
                          literal_binds=True)
    else:
        connection = context.config.attributes.get("connection")
        if connection is None or os.getenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION") != "1":
            raise RuntimeError("Online migrations require the guarded local test connection")
        guard_connection(connection)
        if connection.scalar(text("SELECT current_schemas(true)")) != ["pg_catalog", "public"]:
            raise ValueError("Unexpected migration search path")
        context.configure(connection=connection, target_metadata=Base.metadata)
        # In the pinned Alembic version stamp passes a tuple of destinations.
        # It can also purge a ledger before running revision steps.
        options = context.get_context().opts
        destination = options.get("destination_rev")
        if isinstance(destination, tuple):
            if (destination != (BASELINE,) or options.get("purge")
                    or context.get_tag_argument() != "authorize-stage-1f-adoption"):
                raise ValueError("Explicit authorization for baseline stamping required")
            if verify_baseline(connection):
                raise ValueError("Baseline already recorded")
            # Hold the verified tables stable through Alembic's ledger write.
            for table in sorted(COLUMNS):
                connection.exec_driver_sql(f"LOCK TABLE public.{table} IN ACCESS SHARE MODE")
            if verify_baseline(connection):
                raise ValueError("Baseline already recorded")
        elif connection.scalar(text("SELECT EXISTS (SELECT FROM pg_class "
                                    "WHERE relnamespace = 'public'::regnamespace)")):
            if not verify_baseline(connection, allow_metadata=True):
                raise ValueError("Unversioned schema requires verified baseline adoption")

    with context.begin_transaction():
        context.run_migrations()


run()
