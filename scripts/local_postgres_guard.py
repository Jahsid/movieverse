"""Target checks for the opt-in local PostgreSQL tests."""

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


TEST_DATABASE = "movieverse_itest"
TEST_ROLE = "movieverse_itest"


def checked_url(raw_url):
    """Reject every target except the dedicated loopback database and role."""
    try:
        url = make_url(raw_url)
        allowed = (
            url.drivername == "postgresql+psycopg"
            and url.host == "127.0.0.1"
            and url.port == 5432
            and url.database == TEST_DATABASE
            and url.username == TEST_ROLE
            and bool(url.password)
            and not url.query
        )
    except (ArgumentError, AttributeError, TypeError, ValueError):
        allowed = False
    if not allowed:
        raise ValueError("Integration target must be the dedicated local movieverse_itest database and role")
    return url


def verify_identity(connection):
    row = connection.execute(text(
        "SELECT current_database(), current_user, host(inet_server_addr()), "
        "inet_server_port()"
    )).one()
    if tuple(row) != (TEST_DATABASE, TEST_ROLE, "127.0.0.1", 5432):
        raise RuntimeError("Connected PostgreSQL identity does not match the local test target")

    privileges = connection.execute(text(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = current_user"
    )).one()
    if any(privileges):
        raise RuntimeError("Integration login has privileged role attributes")
