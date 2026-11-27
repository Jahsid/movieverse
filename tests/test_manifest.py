"""Raw CSV manifest metadata and stable content fingerprints."""

import hashlib
import json
import re
import sys

import pytest

from app.data_pipeline.manifest import (
    compare_manifests,
    generate_manifest,
    inspect_csv,
)


def write_inputs(directory):
    (directory / "movies.csv").write_text(
        'movieId,title,genres\n1,"A film, part one",Drama\n2,"A film\npart two",Comedy\n',
        encoding="utf-8",
    )
    (directory / "ratings.csv").write_text(
        "userId,movieId,rating,timestamp\n1,1,4.0,123\n",
        encoding="utf-8",
    )


def test_file_metadata_counts_csv_records_and_hashes_actual_bytes(tmp_path):
    write_inputs(tmp_path)
    movie_path = tmp_path / "movies.csv"
    metadata = inspect_csv(tmp_path, "movies.csv")

    assert metadata == {
        "relative_path": "movies.csv",
        "size_bytes": movie_path.stat().st_size,
        "sha256": hashlib.sha256(movie_path.read_bytes()).hexdigest(),
        "row_count": 2,
        "columns": ["movieId", "title", "genres"],
    }
    manifest = generate_manifest(tmp_path)
    assert manifest["files"][1]["row_count"] == 1
    assert manifest["files"][1]["columns"] == ["userId", "movieId", "rating", "timestamp"]
    assert manifest["source"] == {"name": "MovieLens", "url": None}
    assert manifest["dataset_version"] is None
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest["generated_at_utc"])


def test_unchanged_content_has_same_fingerprint_regardless_of_timestamp(tmp_path):
    write_inputs(tmp_path)
    first = generate_manifest(tmp_path)
    second = generate_manifest(tmp_path)
    second["generated_at_utc"] = "2099-01-01T00:00:00Z"

    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert compare_manifests(first, second) == {
        "changed": False, "added": [], "removed": [], "modified": [],
        "unchanged": ["movies.csv", "ratings.csv"],
    }


def test_changed_content_changes_file_and_dataset_fingerprints(tmp_path):
    write_inputs(tmp_path)
    before = generate_manifest(tmp_path)
    with (tmp_path / "ratings.csv").open("a", encoding="utf-8") as destination:
        destination.write("2,2,3.5,456\n")
    after = generate_manifest(tmp_path)

    assert before["files"][1]["sha256"] != after["files"][1]["sha256"]
    assert before["content_fingerprint"] != after["content_fingerprint"]
    assert after["files"][1]["row_count"] == 2
    assert compare_manifests(before, after)["modified"] == ["ratings.csv"]


def test_missing_file_is_reported(tmp_path):
    (tmp_path / "movies.csv").write_text("movieId,title\n1,Film\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="ratings.csv"):
        generate_manifest(tmp_path)


@pytest.mark.parametrize("contents, message", [
    (b"", "Empty CSV file"),
    (b"movieId,title\n", "no data rows"),
    (b"movieId,\n1,Film\n", "Missing CSV header"),
    (b"movieId,movieId\n1,Film\n", "Duplicate CSV columns"),
    (b"movieId,title\n1\n", "Malformed CSV row"),
    (b'movieId,title\n1,"unclosed\n', "Malformed CSV file"),
    (b"movieId,title\n1,\xff\n", "Malformed CSV file"),
])
def test_empty_and_malformed_csv_are_rejected(tmp_path, contents, message):
    (tmp_path / "movies.csv").write_bytes(contents)
    with pytest.raises(ValueError, match=message):
        inspect_csv(tmp_path, "movies.csv")


def test_manifest_serialization_and_cli_comparison(tmp_path, monkeypatch, capsys):
    from app.data_pipeline import manifest as module

    write_inputs(tmp_path)
    saved = tmp_path / "manifest.json"
    monkeypatch.setattr(sys, "argv", ["manifest", "--directory", str(tmp_path),
                                      "--output", str(saved)])
    module.main()
    captured = json.loads(capsys.readouterr().out)
    assert json.loads(saved.read_text(encoding="utf-8")) == captured

    monkeypatch.setattr(sys, "argv", ["manifest", "--directory", str(tmp_path),
                                      "--compare", str(saved)])
    module.main()
    comparison = json.loads(capsys.readouterr().out)["comparison"]
    assert comparison["changed"] is False
    assert comparison["unchanged"] == ["movies.csv", "ratings.csv"]


def test_file_names_must_be_relative_to_dataset_directory(tmp_path):
    with pytest.raises(ValueError, match="inside the dataset"):
        inspect_csv(tmp_path, "../elsewhere.csv")


def test_manifest_requires_at_least_one_file(tmp_path):
    with pytest.raises(ValueError, match="At least one"):
        generate_manifest(tmp_path, file_names=())
