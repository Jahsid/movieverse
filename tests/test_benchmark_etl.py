import pandas as pd
import pytest

from app.data_pipeline.manifest import generate_manifest
from app.data_pipeline.validator import validate_movies, validate_ratings
from scripts.benchmark_etl import build_changed_variant, build_dataset


def write_dataset(directory, movie_count=7, rating_count=13):
    directory.mkdir(parents=True)
    pd.DataFrame([
        {"movieId": index + 1, "title": f"Film {index} (2000)", "genres": "Drama"}
        for index in range(movie_count)
    ]).to_csv(directory / "movies.csv", index=False)
    pd.DataFrame([
        {"userId": index % 4 + 1, "movieId": index % movie_count + 1,
         "rating": float((index % 10 + 1) / 2), "timestamp": index}
        for index in range(rating_count)
    ]).drop_duplicates(["userId", "movieId"]).to_csv(directory / "ratings.csv", index=False)


def test_samples_are_seeded_referentially_valid_and_fingerprinted(tmp_path):
    source = tmp_path / "source"
    write_dataset(source, movie_count=120, rating_count=100)
    first = build_dataset("small", source, tmp_path / "first", seed=4)
    second = build_dataset("small", source, tmp_path / "second", seed=4)
    assert first["movie_rows"] == second["movie_rows"]
    assert first["rating_rows"] == second["rating_rows"] == 100
    assert first["source_fingerprint"] == generate_manifest(source)["content_fingerprint"]
    assert first["content_fingerprint"] == second["content_fingerprint"]
    movies = pd.read_csv(tmp_path / "first/movies.csv")
    ratings = pd.read_csv(tmp_path / "first/ratings.csv")
    validate_movies(movies)
    validate_ratings(ratings)
    assert set(ratings.movieId).issubset(set(movies.movieId))


def test_small_sources_report_actual_counts_and_full_is_sorted(tmp_path):
    source = tmp_path / "source"
    write_dataset(source, movie_count=7, rating_count=13)
    small = build_dataset("small", source, tmp_path / "small", seed=9)
    full = build_dataset("full", source, tmp_path / "full")
    assert (small["movie_rows"], small["rating_rows"]) == (7, 13)
    assert (full["movie_rows"], full["rating_rows"]) == (7, 13)
    assert pd.read_csv(tmp_path / "full/movies.csv").movieId.tolist() == list(range(1, 8))
    ratings = pd.read_csv(tmp_path / "full/ratings.csv")
    assert ratings[["userId", "movieId"]].values.tolist() == (
        ratings.sort_values(["userId", "movieId"])[["userId", "movieId"]].values.tolist()
    )


def test_changed_variant_is_deterministic_and_changes_one_percent(tmp_path):
    source = tmp_path / "source"
    write_dataset(source, movie_count=100, rating_count=200)
    build_dataset("full", source, tmp_path / "full")
    left = build_changed_variant(tmp_path / "full", tmp_path / "left", seed=22)
    right = build_changed_variant(tmp_path / "full", tmp_path / "right", seed=22)
    assert left["changed_movie_rows"] == 1
    assert left["changed_rating_rows"] == 1
    assert left["content_fingerprint"] == right["content_fingerprint"]
    assert left["content_fingerprint"] != left["source_fingerprint"]
    assert left["movie_rows"] == 100 and left["rating_rows"] == 100
    movies = pd.read_csv(tmp_path / "left/movies.csv")
    ratings = pd.read_csv(tmp_path / "left/ratings.csv")
    validate_movies(movies)
    validate_ratings(ratings)
    assert set(ratings.movieId).issubset(set(movies.movieId))


def test_empty_rating_source_is_supported(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    pd.DataFrame([{"movieId": 1, "title": "Film", "genres": "Drama"}]).to_csv(
        source / "movies.csv", index=False
    )
    pd.DataFrame(columns=["userId", "movieId", "rating", "timestamp"]).to_csv(
        source / "ratings.csv", index=False
    )
    with pytest.raises(ValueError):
        build_dataset("small", source, tmp_path / "out")



def test_full_sampling_preserves_unrated_movies(tmp_path):
    source = tmp_path / "source"
    write_dataset(source, movie_count=8, rating_count=13)
    original_movies = pd.read_csv(source / "movies.csv")
    original_ratings = pd.read_csv(source / "ratings.csv")
    original_movies.loc[len(original_movies)] = [99, "Unrated film", "Drama"]
    original_movies.to_csv(source / "movies.csv", index=False)
    rated_ids = set(original_ratings.movieId)
    unrated_ids = set(original_movies.movieId) - rated_ids
    assert unrated_ids

    result = build_dataset("full", source, tmp_path / "full")
    sampled_movies = pd.read_csv(tmp_path / "full/movies.csv")
    sampled_ratings = pd.read_csv(tmp_path / "full/ratings.csv")
    assert result["movie_rows"] == len(original_movies) == 9
    assert result["rating_rows"] == len(original_ratings)
    assert unrated_ids.issubset(set(sampled_movies.movieId))
    assert sampled_ratings.equals(original_ratings.sort_values(
        ["userId", "movieId"], kind="stable"
    ).reset_index(drop=True))
    assert set(sampled_ratings.movieId).issubset(set(sampled_movies.movieId))



def test_offline_timing_result_is_json_serializable(tmp_path):
    import json

    source = tmp_path / "source"
    write_dataset(source, movie_count=12, rating_count=13)
    result = build_dataset("full", source, tmp_path / "full")
    serialized = json.loads(json.dumps(result))
    timings = serialized["timings_seconds"]
    assert set(timings) == {
        "extraction", "validation", "transformation", "fingerprinting",
        "total_offline_pipeline",
    }
    assert all(value >= 0 for value in timings.values())
    assert serialized["source_records_processed"] == (
        serialized["movie_rows"] + serialized["rating_rows"]
    )
    assert serialized["source_records_per_second"] > 0
    assert "no database ingestion" in serialized["measurement_scope"]


def test_peak_working_set_reports_none_off_windows(monkeypatch):
    import scripts.benchmark_etl as benchmark

    monkeypatch.setattr(benchmark.os, "name", "posix")
    assert benchmark.peak_working_set_mib() is None


def test_subprocess_result_and_failure_handling(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace

    import scripts.benchmark_etl as benchmark

    payload = {"timings_seconds": {"total_offline_pipeline": 0.1}}
    monkeypatch.setattr(benchmark.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout=__import__("json").dumps(payload)))
    assert benchmark.run_case("small", tmp_path, tmp_path / "out") == payload

    monkeypatch.setattr(benchmark.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=3, stdout=""))
    with pytest.raises(RuntimeError, match="failed with code"):
        benchmark.run_case("small", tmp_path, tmp_path / "out")

    monkeypatch.setattr(benchmark.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="not json"))
    with pytest.raises(RuntimeError, match="malformed JSON"):
        benchmark.run_case("small", tmp_path, tmp_path / "out")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(benchmark.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="timed out"):
        benchmark.run_case("small", tmp_path, tmp_path / "out")
