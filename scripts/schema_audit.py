"""Read-only comparison of SQLAlchemy models with the configured PostgreSQL schema."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise SystemExit("DATABASE_URL is not configured")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
if not database_url.startswith("postgresql+psycopg://"):
    raise SystemExit("Schema audit requires a PostgreSQL connection")

from app.database.models import Base  # noqa: E402

engine = create_engine(database_url, connect_args={"connect_timeout": 5})
try:
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        inspector = inspect(connection)
        for table in Base.metadata.sorted_tables:
            name = table.name
            if not inspector.has_table(name):
                print(f"{name}: table missing")
                continue
            actual = {column["name"]: column for column in inspector.get_columns(name)}
            expected = {column.name: column for column in table.columns}
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            print(f"{name}: missing={missing}, extra={extra}")
            for column_name in sorted(set(expected) & set(actual)):
                expected_column = expected[column_name]
                actual_column = actual[column_name]
                expected_type = str(expected_column.type).upper()
                actual_type = str(actual_column["type"]).upper()
                type_mismatch = not isinstance(actual_column["type"], type(expected_column.type))
                default_mismatch = (expected_column.server_default is not None
                                    and actual_column["default"] is None)
                if (type_mismatch or expected_column.nullable != actual_column["nullable"]
                        or default_mismatch):
                    print(f"  {column_name}: model {expected_type} nullable={expected_column.nullable}; "
                          f"database {actual_type} nullable={actual_column['nullable']}; "
                          f"missing_server_default={default_mismatch}")
            if name == "watchlist":
                print(f"  primary_key={inspector.get_pk_constraint(name)['constrained_columns']}")
                print(f"  foreign_keys={sorted(tuple(fk['constrained_columns']) for fk in inspector.get_foreign_keys(name))}")
                print(f"  unique_constraints={sorted((item['name'], tuple(item['column_names'])) for item in inspector.get_unique_constraints(name))}")
                print(f"  indexes={sorted((item['name'], tuple(item['column_names'])) for item in inspector.get_indexes(name))}")
                counts = connection.execute(text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE status IS NULL) AS null_status, "
                    "count(*) FILTER (WHERE added_at IS NULL) AS null_added_at "
                    "FROM watchlist"
                )).one()
                print(f"  rows={counts.total}, null_status={counts.null_status}, "
                      f"null_added_at={counts.null_added_at}")
                for column_name in ("id", "user_id", "movie_id", "status", "added_at", "updated_at"):
                    if column_name in actual:
                        column = actual[column_name]
                        print(f"  {column_name}: {column['type']}, nullable={column['nullable']}, "
                              f"default={column['default'] is not None}")
except SQLAlchemyError:
    raise SystemExit("Schema audit could not connect or read metadata; no changes were made") from None
finally:
    engine.dispose()
