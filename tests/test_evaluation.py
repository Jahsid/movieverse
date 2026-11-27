"""Regression coverage for the active offline evaluation entry point."""

import pandas as pd

from app.recommender.evaluation import evaluate_multi_seed_model


def test_multi_seed_evaluation_returns_precision_and_recall():
    ratings = pd.DataFrame(
        [(1, movie_id, 5.0) for movie_id in (1, 2, 3, 4)]
        + [(2, movie_id, 5.0) for movie_id in (4, 3, 2, 1)],
        columns=["user_id", "movie_id", "rating"],
    )

    result = evaluate_multi_seed_model(
        ratings,
        k=1,
        test_fraction=0.25,
        seed_count=2,
        candidates_per_seed=3,
        random_state=42,
    )

    assert result == {
        "precision_at_k": 1.0,
        "recall_at_k": 1.0,
        "k": 1,
        "seed_count": 2,
        "evaluated_users": 2,
    }
