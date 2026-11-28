from unittest.mock import Mock

import pytest

from app.database import loader_revision
from scripts.baseline_verification import BASELINE, LEDGER, METADATA_REVISION, METADATA_TYPES, expected_objects


@pytest.mark.parametrize("state, diagnostic", [
    ("current", None),
    ("absent", "ledger missing"),
    ("old", "exactly the current revision"),
    ("unknown", "exactly the current revision"),
    ("empty", "exactly the current revision"),
    ("multiple", "exactly the current revision"),
    ("bad_column", "Incompatible migration ledger"),
    ("drift", "schema differs"),
])
def test_loader_revision(state, diagnostic, monkeypatch):
    connection = Mock()
    connection.scalar.return_value = ["pg_catalog", "public"]
    objects = expected_objects(True)
    for name, datatype in METADATA_TYPES.items():
        objects["column", "ingestion_jobs." + name] = (datatype, False, None, None, "", "")
    revisions = {"old": [BASELINE], "unknown": ["private-value"], "empty": [],
                 "multiple": [METADATA_REVISION, BASELINE]}
    connection.scalars.return_value = revisions.get(state, [METADATA_REVISION])
    if state == "absent":
        del objects["relation", LEDGER]
    elif state == "bad_column":
        del objects["column", LEDGER + ".version_num"]
    elif state == "drift":
        del objects["column", "ingestion_jobs.duration_ms"]
    monkeypatch.setattr(loader_revision, "catalog", lambda _: objects)
    if diagnostic:
        with pytest.raises(loader_revision.LoaderSchemaError, match=diagnostic) as error:
            loader_revision.require_current_schema(connection)
        assert "private-value" not in str(error.value)
    else:
        loader_revision.require_current_schema(connection)
