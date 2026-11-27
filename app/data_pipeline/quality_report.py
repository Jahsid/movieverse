"""Read-only MovieLens CSV quality report using ingestion's business rules."""

import argparse
import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.data_pipeline.extractor import extract_movies, extract_ratings
from app.data_pipeline.manifest import generate_manifest
from app.data_pipeline.validator import (
    MOVIE_REQUIRED_COLUMNS,
    RATING_REQUIRED_COLUMNS,
    missing_columns,
    movie_quality_issues,
    normalized_valid_ids,
    rating_row_issues,
)


def orphan_movie_references(movies: pd.DataFrame, ratings: pd.DataFrame):
    """Find ratings with a valid movie ID absent from the movie file."""
    if "movieId" not in movies.columns or "movieId" not in ratings.columns:
        return None, None
    movie_ids = normalized_valid_ids(movies["movieId"])
    rating_ids = normalized_valid_ids(ratings["movieId"])
    orphan_mask = rating_ids.notna() & ~rating_ids.isin(movie_ids.dropna())
    missing_ids = sorted(int(value) for value in rating_ids[orphan_mask].unique())
    return orphan_mask, missing_ids


def summarize_file(
    frame: pd.DataFrame, required_columns, issues_function, file_hash: str,
    extra_issues=None,
) -> dict:
    """Count each rejected row once; reason counts may overlap."""
    total = len(frame)
    missing = missing_columns(frame, required_columns)
    missing_values = {column: int(count) for column, count in frame.isna().sum().items()}
    if missing:
        reasons = {"missing_required_column": total}
        rejected = total
    else:
        reasons_by_category = {**issues_function(frame), **(extra_issues or {})}
        rejected_mask = pd.Series(False, index=frame.index)
        for mask in reasons_by_category.values():
            rejected_mask |= mask
        rejected = int(rejected_mask.sum())
        reasons = {reason: int(mask.sum()) for reason, mask in reasons_by_category.items()}

    accepted = total - rejected
    return {
        "sha256": file_hash,
        "total_records": total,
        "accepted_records": accepted,
        "rejected_records": rejected,
        "accepted_percent": round(100 * accepted / total, 2) if total else None,
        "rejected_percent": round(100 * rejected / total, 2) if total else None,
        "missing_values": missing_values,
        "missing_required_columns": missing,
        "rejection_reasons": reasons,
    }


def build_report(directory: Path = Path("data/raw")) -> dict:
    """Inspect the same raw files as ingestion, without transforming or loading."""
    manifest = generate_manifest(directory)
    with redirect_stdout(io.StringIO()):
        movies = extract_movies(directory / "movies.csv")
        ratings = extract_ratings(directory / "ratings.csv")
    after = generate_manifest(directory)
    if manifest["content_fingerprint"] != after["content_fingerprint"]:
        raise ValueError("Dataset files changed during quality reporting")

    hashes = {item["relative_path"]: item["sha256"] for item in manifest["files"]}
    orphan_mask, missing_movie_ids = orphan_movie_references(movies, ratings)
    orphan_count = int(orphan_mask.sum()) if orphan_mask is not None else None
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
        "dataset_content_fingerprint": manifest["content_fingerprint"],
        "duplicate_policy": "For valid keys, later occurrences are rejected by file order",
        "movie_references": {
            "checked": orphan_mask is not None,
            "orphan_rating_records": orphan_count,
            "distinct_missing_movie_ids": missing_movie_ids,
        },
        "files": {
            "movies.csv": summarize_file(
                movies, MOVIE_REQUIRED_COLUMNS, movie_quality_issues, hashes["movies.csv"]
            ),
            "ratings.csv": summarize_file(
                ratings, RATING_REQUIRED_COLUMNS, rating_row_issues, hashes["ratings.csv"],
                {"orphan_movie_reference": orphan_mask} if orphan_mask is not None else None,
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("data/raw"))
    args = parser.parse_args()
    try:
        report = build_report(args.directory)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Data quality report error: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
