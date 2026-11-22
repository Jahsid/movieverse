import pandas as pd

def normalize_scores(scores: dict[int, float]) -> dict[int, float]:
    """
    Normalize movie recommendation scores to the range [0, 1].

    Args:
        scores: Dictionary mapping movie_id to recommendation score.

    Returns:
        Dictionary mapping movie_id to normalized score.
    """
    if not scores:
        return {}

    min_score = min(scores.values())
    max_score = max(scores.values())

    # Handle the case where every movie has the same score.
    if max_score == min_score:
        return {
            movie_id: 0.5
            for movie_id in scores
        }

    normalized = {}

    for movie_id, score in scores.items():
        normalized[movie_id] = (
            (score - min_score) / (max_score - min_score)
        )

    return normalized


def calculate_hybrid_scores(
    knn_scores: dict[int, float],
    content_scores: dict[int, float],
    popularity_scores: dict[int, float],
    knn_weight: float = 0.5,
    content_weight: float = 0.3,
    popularity_weight: float = 0.2
) -> dict[int, float]:
    """
    Combine normalized scores from three recommendation models.
    """

    weights = [knn_weight, content_weight, popularity_weight]

    if any(weight < 0 for weight in weights):
        raise ValueError("Weights cannot be negative.")

    if not abs(sum(weights) - 1.0) < 1e-9:
        raise ValueError("Weights must sum to 1.")

    knn_normalized = normalize_scores(knn_scores)
    content_normalized = normalize_scores(content_scores)
    popularity_normalized = normalize_scores(popularity_scores)

    # Include every movie recommended by at least one model.
    all_movie_ids = (
        set(knn_scores)
        | set(content_scores)
        | set(popularity_scores)
    )

    hybrid_scores = {}

    for movie_id in all_movie_ids:
        score = (
            knn_weight * knn_normalized.get(movie_id, 0.0)
            + content_weight * content_normalized.get(movie_id, 0.0)
            + popularity_weight * popularity_normalized.get(movie_id, 0.0)
        )

        hybrid_scores[movie_id] = score

    return dict(
        sorted(
            hybrid_scores.items(),
            key=lambda item: item[1],
            reverse=True
        )
    )

def calculate_popularity_scores(
    ratings: pd.DataFrame,
    rating_threshold: float = 4.0
) -> dict[int, float]:
    """
    Calculate movie popularity using the number of
    ratings greater than or equal to rating_threshold.

    Use training ratings only when evaluating the model.
    """

    required_columns = ["movie_id", "rating"]

    missing = [
        column for column in required_columns
        if column not in ratings.columns
    ]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    if ratings.empty:
        return {}

    popular_movies = (
        ratings[ratings["rating"] >= rating_threshold]
        .groupby("movie_id")
        .size()
    )

    return {
        int(movie_id): float(count)
        for movie_id, count in popular_movies.items()
    }
