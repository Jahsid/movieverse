"""Read-only quality counts, duplicate policy, and validator compatibility."""

import json
import sys

import pandas as pd
import pytest

from app.data_pipeline.manifest import generate_manifest
from app.data_pipeline.quality_report import build_report, summarize_file
from app.data_pipeline.validator import (
    MOVIE_REQUIRED_COLUMNS,
    RATING_REQUIRED_COLUMNS,
    movie_quality_issues,
    rating_row_issues,
    validate_movies,
    validate_ratings,
)


def test_movie_reasons_can_overlap_without_double_counting_rejected_rows():
    movies = pd.DataFrame([
        {"movieId": 1, "title": "Film", "genres": "Drama"},
        {"movieId": 1, "title": "Duplicate", "genres": "Drama"},
        {"movieId": 0, "title": " ", "genres": "Drama"},
        {"movieId": "oops", "title": 42, "genres": "Drama"},
        {"movieId": None, "title": None, "genres": "Drama"},
        {"movieId": 2, "title": "Valid", "genres": None},
    ])
    result = summarize_file(movies, MOVIE_REQUIRED_COLUMNS, movie_quality_issues, "hash")

    assert (result["total_records"], result["accepted_records"], result["rejected_records"]) == (
        6, 2, 4
    )
    assert result["accepted_percent"] == 33.33
    assert result["rejected_percent"] == 66.67
    assert result["missing_values"] == {"movieId": 1, "title": 1, "genres": 1}
    assert result["rejection_reasons"] == {
        "missing_required_field": 1,
        "invalid_data_type": 1,
        "invalid_id": 2,
        "invalid_title": 2,
        "duplicate_key": 1,
    }
    with pytest.raises(ValueError, match="Movie IDs cannot be missing"):
        validate_movies(movies)


def test_rating_reasons_can_overlap_without_double_counting_rejected_rows():
    ratings = pd.DataFrame([
        {"userId": 1, "movieId": 1, "rating": 4.5, "timestamp": 100},
        {"userId": 1, "movieId": 1, "rating": 4.0, "timestamp": 100},
        {"userId": 0, "movieId": 2, "rating": 5.5, "timestamp": 1.5},
        {"userId": "oops", "movieId": 3, "rating": "bad", "timestamp": "bad"},
        {"userId": None, "movieId": 4, "rating": None, "timestamp": None},
        {"userId": 2, "movieId": 2, "rating": 3.0, "timestamp": 200},
    ])
    result = summarize_file(ratings, RATING_REQUIRED_COLUMNS, rating_row_issues, "hash")

    assert (result["total_records"], result["accepted_records"], result["rejected_records"]) == (
        6, 2, 4
    )
    assert result["rejection_reasons"] == {
        "missing_required_field": 1,
        "invalid_data_type": 1,
        "invalid_id": 2,
        "invalid_rating": 2,
        "invalid_timestamp": 2,
        "duplicate_key": 1,
    }
    with pytest.raises(ValueError, match="Required rating fields cannot be missing"):
        validate_ratings(ratings)


@pytest.mark.parametrize("kind,required,issues", [
    ("movies", MOVIE_REQUIRED_COLUMNS, movie_quality_issues),
    ("ratings", RATING_REQUIRED_COLUMNS, rating_row_issues),
])
def test_missing_required_column_rejects_every_row(kind, required, issues):
    frame = pd.DataFrame({required[0]: [1, 2]})
    result = summarize_file(frame, required, issues, "hash")
    assert result["total_records"] == result["rejected_records"] == 2
    assert result["accepted_records"] == 0
    assert result["missing_required_columns"] == list(required[1:])
    assert result["rejection_reasons"] == {"missing_required_column": 2}


def test_valid_rows_and_empty_frame_percentage():
    movies = pd.DataFrame([{"movieId": 1, "title": "Film", "genres": None}])
    assert validate_movies(movies)
    result = summarize_file(movies, MOVIE_REQUIRED_COLUMNS, movie_quality_issues, "hash")
    assert result["accepted_records"] == 1
    assert result["accepted_percent"] == 100.0
    assert result["missing_values"]["genres"] == 1

    empty = movies.iloc[0:0]
    result = summarize_file(empty, MOVIE_REQUIRED_COLUMNS, movie_quality_issues, "hash")
    assert result["total_records"] == 0
    assert result["accepted_percent"] is None


def test_report_cli_json_matches_manifest_fingerprint(tmp_path, monkeypatch, capsys):
    from app.data_pipeline import quality_report

    (tmp_path / "movies.csv").write_text(
        "movieId,title,genres\n1,Film,Drama\n2,Second,Comedy\n", encoding="utf-8"
    )
    (tmp_path / "ratings.csv").write_text(
        "userId,movieId,rating,timestamp\n1,1,4.0,123\n1,1,5.0,124\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["quality_report", "--directory", str(tmp_path)])
    quality_report.main()
    output = capsys.readouterr().out
    report = json.loads(output)

    assert report == build_report(tmp_path) | {"generated_at_utc": report["generated_at_utc"]}
    assert report["dataset_content_fingerprint"] == generate_manifest(tmp_path)[
        "content_fingerprint"
    ]
    assert report["files"]["movies.csv"]["accepted_records"] == 2
    assert report["files"]["ratings.csv"]["rejected_records"] == 1
    assert report["files"]["ratings.csv"]["rejection_reasons"]["duplicate_key"] == 1
    assert report["movie_references"] == {
        "checked": True, "orphan_rating_records": 0,
        "distinct_missing_movie_ids": [],
    }


def test_orphans_use_valid_normalized_ids_without_double_counting(tmp_path):
    (tmp_path / "movies.csv").write_text(
        "movieId,title,genres\n1,One,Drama\n2,Two,Comedy\n", encoding="utf-8"
    )
    (tmp_path / "ratings.csv").write_text(
        "userId,movieId,rating,timestamp\n"
        "1,1,4.0,100\n"
        "2,3,4.0,100\n"
        "2,3.0,5.5,200\n"
        "3,0,4.0,300\n"
        "4,bad,4.0,400\n"
        "5,2.0,3.5,500\n",
        encoding="utf-8",
    )
    report = build_report(tmp_path)
    ratings = report["files"]["ratings.csv"]

    assert report["movie_references"] == {
        "checked": True, "orphan_rating_records": 2,
        "distinct_missing_movie_ids": [3],
    }
    assert (ratings["total_records"], ratings["accepted_records"],
            ratings["rejected_records"]) == (6, 2, 4)
    assert ratings["rejection_reasons"]["orphan_movie_reference"] == 2
    assert ratings["rejection_reasons"]["invalid_id"] == 2
    assert ratings["rejection_reasons"]["duplicate_key"] == 1
    assert report["dataset_content_fingerprint"] == generate_manifest(tmp_path)[
        "content_fingerprint"
    ]


def test_missing_movie_id_column_marks_reference_check_unverified(tmp_path):
    (tmp_path / "movies.csv").write_text(
        "title,genres\nOne,Drama\n", encoding="utf-8"
    )
    (tmp_path / "ratings.csv").write_text(
        "userId,movieId,rating,timestamp\n1,1,4.0,100\n", encoding="utf-8"
    )
    report = build_report(tmp_path)

    assert report["movie_references"] == {
        "checked": False, "orphan_rating_records": None,
        "distinct_missing_movie_ids": None,
    }
    assert report["files"]["movies.csv"]["rejected_records"] == 1
    assert "orphan_movie_reference" not in report["files"]["ratings.csv"]["rejection_reasons"]
