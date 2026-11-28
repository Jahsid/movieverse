"""Read-only PostgreSQL catalog contract for revision 0001_stage_1f.

Names and definitions below are frozen alongside the revision. Public is the
only application schema in the guarded rehearsal. Never import the app engine.
"""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from scripts.local_postgres_guard import checked_url, verify_identity


BASELINE = "0001_stage_1f"
METADATA_REVISION = "0002_ingestion_metadata"
METADATA_TYPES = {
    "content_fingerprint": "character varying(64)",
    "updated_records": "integer",
    "unchanged_records": "integer",
    "started_at": "timestamp with time zone",
    "completed_at": "timestamp with time zone",
    "duration_ms": "bigint",
    "failure_phase": "character varying(32)",
    "failure_code": "character varying(64)",
}
LEDGER = "alembic_version"
# (column, format_type, NOT NULL, server default); serial also implies ownership.
SERIAL = "serial"
INTEGER = "integer"
VARCHAR = "character varying"
TIME = "timestamp without time zone"
COLUMNS = {
    "movies": [("movie_id", INTEGER, True, SERIAL), ("title", VARCHAR, True, None),
               ("genres", VARCHAR, False, None), ("release_year", INTEGER, False, None)],
    "users": [("user_id", INTEGER, True, SERIAL), ("username", VARCHAR, False, None),
              ("created_at", TIME, False, "now()")],
    "ratings": [("user_id", INTEGER, True, None), ("movie_id", INTEGER, True, None),
                ("rating", "double precision", True, None), ("timestamp", INTEGER, False, None)],
    "watchlist": [("id", INTEGER, True, SERIAL), ("user_id", INTEGER, True, None),
                  ("movie_id", INTEGER, True, None), ("status", VARCHAR, True, "'PLANNED'::character varying"),
                  ("added_at", TIME, False, "now()"), ("updated_at", TIME, True, "now()")],
    "ingestion_jobs": [("id", INTEGER, True, SERIAL), ("filename", VARCHAR, True, None),
                       ("status", VARCHAR, True, None), ("total_records", INTEGER, False, None),
                       ("imported_records", INTEGER, False, None), ("rejected_records", INTEGER, False, None),
                       ("created_at", TIME, False, "now()")],
}
PRIMARY = {"movies": "movie_id", "users": "user_id", "ratings": "user_id, movie_id",
           "watchlist": "id", "ingestion_jobs": "id"}


def expected_objects(versioned):
    objects = {}

    def index(table, name, columns, unique):
        kind = "UNIQUE " if unique else ""
        objects["relation", name] = "i"
        objects["index", name] = f"CREATE {kind}INDEX {name} ON public.{table} USING btree ({columns})"

    tables = dict(COLUMNS)
    primary = dict(PRIMARY)
    if versioned:
        tables[LEDGER] = [("version_num", "character varying(32)", True, None)]
        primary[LEDGER] = "version_num"

    for table, columns in tables.items():
        objects["relation", table] = "r"
        for name, datatype, required, default in columns:
            owner = None
            if default == SERIAL:
                sequence = f"{table}_{name}_seq"
                objects["relation", sequence] = "S"
                objects["sequence", sequence] = ("integer", 1, 1, 2147483647, 1, 1, False)
                default = f"nextval('{sequence}'::regclass)"
                owner = f"public.{sequence}"
            objects["column", f"{table}.{name}"] = (datatype, required, default, owner, "", "")
        pk = "alembic_version_pkc" if table == LEDGER else f"{table}_pkey"
        objects["constraint", table + "." + pk] = f"PRIMARY KEY ({primary[table]})"
        index(table, pk, primary[table], True)

    for table in ("ratings", "watchlist"):
        for column, parent in (("user_id", "users"), ("movie_id", "movies")):
            objects["constraint", f"{table}.{table}_{column}_fkey"] = (
                f"FOREIGN KEY ({column}) REFERENCES {parent}({column})"
            )
    objects["constraint", "watchlist.unique_user_movie"] = "UNIQUE (user_id, movie_id)"
    index("watchlist", "unique_user_movie", "user_id, movie_id", True)
    for table, column in (("movies", "movie_id"), ("watchlist", "id"), ("ingestion_jobs", "id")):
        index(table, f"ix_{table}_{column}", column, False)
    return objects


def catalog(connection):
    # pg_get_* renders expressions relative to search_path. Require the same
    # path for comparisons and Alembic's unqualified table operations.
    if connection.scalar(text("SELECT current_schemas(false)")) != ["public"]:
        raise ValueError("Verification requires public as the only effective schema")
    objects = {}
    queries = {
        "relation": """SELECT relname, relkind FROM pg_class
            WHERE relnamespace = 'public'::regnamespace""",
        "column": """SELECT c.relname || '.' || a.attname, format_type(a.atttypid,a.atttypmod),
            a.attnotnull, pg_get_expr(d.adbin,d.adrelid),
            pg_get_serial_sequence(format('%I.%I','public',c.relname),a.attname),
            a.attidentity, a.attgenerated
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE c.relnamespace='public'::regnamespace AND c.relkind='r'
            AND a.attnum>0 AND NOT a.attisdropped""",
        "constraint": """SELECT c.relname || '.' || k.conname, pg_get_constraintdef(k.oid)
            FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
            WHERE c.relnamespace='public'::regnamespace AND k.contype <> 'n'""",
        "index": """SELECT c.relname, CASE WHEN i.indisvalid AND i.indisready
            THEN pg_get_indexdef(c.oid) ELSE 'invalid index' END
            FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
            WHERE c.relnamespace='public'::regnamespace""",
        "sequence": """SELECT c.relname, format_type(s.seqtypid,NULL), s.seqstart,
            s.seqmin,s.seqmax,s.seqincrement,s.seqcache,s.seqcycle
            FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid
            WHERE c.relnamespace='public'::regnamespace""",
        "routine": """SELECT p.oid::regprocedure::text, true FROM pg_proc p
            WHERE p.pronamespace='public'::regnamespace""",
        "type": """SELECT typname, true FROM pg_type WHERE typnamespace='public'::regnamespace
            AND typrelid=0 AND typelem=0""",
        "policy": """SELECT c.relname || '.' || p.polname, true FROM pg_policy p
            JOIN pg_class c ON c.oid=p.polrelid WHERE c.relnamespace='public'::regnamespace""",
        "table_options": """SELECT relname, true FROM pg_class
            WHERE relnamespace='public'::regnamespace AND relkind='r'
            AND (relrowsecurity OR relforcerowsecurity OR relpersistence <> 'p' OR relispartition)""",
        "collation_override": """SELECT c.relname || '.' || a.attname, true
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_type t ON t.oid=a.atttypid WHERE c.relnamespace='public'::regnamespace
            AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped AND a.attcollation<>t.typcollation""",
        "rule": """SELECT c.relname || '.' || r.rulename, true FROM pg_rewrite r
            JOIN pg_class c ON c.oid=r.ev_class WHERE c.relnamespace='public'::regnamespace""",
        "trigger": """SELECT c.relname || '.' || t.tgname, true FROM pg_trigger t
            JOIN pg_class c ON c.oid=t.tgrelid WHERE c.relnamespace='public'::regnamespace
            AND NOT t.tgisinternal""",
    }
    for category, query in queries.items():
        for name, *values in connection.execute(text(query)):
            if category == "column" and values[2] == "CURRENT_TIMESTAMP":
                values[2] = "now()"
            objects[category, name] = values[0] if len(values) == 1 else tuple(values)
    return objects


def compare(objects, revisions, *, allow_metadata=False):
    versioned = ("relation", LEDGER) in objects
    expected = expected_objects(versioned)
    metadata = allow_metadata and versioned and revisions == [METADATA_REVISION]
    if metadata:
        for name, datatype in METADATA_TYPES.items():
            expected["column", "ingestion_jobs." + name] = (datatype, False, None, None, "", "")
    differences = []
    for key in sorted(objects.keys() | expected.keys()):
        if key not in objects:
            reason = "missing"
        elif key not in expected:
            reason = "unexpected"
        elif objects[key] != expected[key]:
            reason = "incompatible"
        else:
            continue
        differences.append(f"{reason} {key[0]} {key[1]}")
    if not metadata and revisions != ([BASELINE] if versioned else []):
        differences.append("incompatible migration history")
    return differences


def verify_baseline(connection, *, allow_metadata=False):
    guard_connection(connection)
    objects = catalog(connection)
    versioned = ("relation", LEDGER) in objects
    revisions = []
    # Only query a ledger whose object type and columns have been verified.
    ledger_keys = (("relation", LEDGER), ("column", LEDGER + ".version_num"))
    baseline = expected_objects(True)
    if versioned and all(objects.get(key) == baseline[key] for key in ledger_keys):
        revisions = list(connection.scalars(text("SELECT version_num FROM public.alembic_version")))
    differences = compare(objects, revisions, allow_metadata=allow_metadata)
    if differences:
        raise ValueError("Baseline verification failed: " + ", ".join(differences))
    return versioned


def guard_connection(connection):
    if os.getenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION") != "1":
        raise RuntimeError("Local PostgreSQL opt-in required")
    if connection.engine.url != checked_url(os.getenv("MOVIEVERSE_TEST_DATABASE_URL", "")):
        raise RuntimeError("Unexpected migration connection")
    verify_identity(connection)


def main():
    """Optional read-only audit of an explicitly configured local test fixture."""
    if os.getenv("MOVIEVERSE_RUN_POSTGRES_INTEGRATION") != "1":
        raise SystemExit("Local PostgreSQL opt-in required")
    url = checked_url(os.getenv("MOVIEVERSE_TEST_DATABASE_URL", ""))
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.exec_driver_sql("SET LOCAL search_path TO public")
            versioned = verify_baseline(connection)
            print("Verified baseline ledger" if versioned else "Verified unversioned baseline")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
