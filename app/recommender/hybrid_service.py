
from app.recommender.hybrid import (
    normalize_scores,
    calculate_hybrid_scores
)


def recommend_hybrid_for_user(
    knn_recommender,
    content_recommender,
    user_ratings,
    popularity_scores: dict[int, float],
    candidate_movie_ids=None,
    k: int = 10,
    seed_count: int = 20,
    candidates_per_seed: int = 50,
    candidate_pool_size: int = 100,
    knn_weight: float = 0.5,
    content_weight: float = 0.3,
    popularity_weight: float = 0.2
):
    """
    Generate personalized recommendations using
    KNN, Content-Based and Popularity models.

    The recommenders must already be trained.
    popularity_scores must be calculated from training data.

    candidate_movie_ids:
        Optional set of eligible movie IDs.
        None means use the full available catalogue.
        Pass training movie IDs for warm-start evaluation.
    """

    if k < 1 or candidate_pool_size < 1:
        raise ValueError(
            "k and candidate_pool_size must be positive"
        )

    if user_ratings.empty:
        return []

    seen_movies = set(
        user_ratings["movie_id"].astype(int)
    )

    # 1. Generate KNN recommendations
    knn_recommendations = knn_recommender.recommend_for_user(
        user_ratings=user_ratings,
        k=candidate_pool_size,
        seed_count=seed_count,
        candidates_per_seed=candidates_per_seed
    )

    knn_scores = {
        int(item["movie_id"]): float(item["similarity"])
        for item in knn_recommendations
    }

    # 2. Generate Content-Based recommendations
    content_user_ratings = user_ratings[
        ["movie_id", "rating"]
    ]

    content_recommendations = (
        content_recommender.recommend_for_user(
            user_ratings=content_user_ratings,
            k=candidate_pool_size,
            candidate_movie_ids=candidate_movie_ids
        )
    )

    content_scores = {
        int(item["movie_id"]): float(item["similarity"])
        for item in content_recommendations
    }

    # 3. Generate Popularity candidates
    popularity_candidates = {
        int(movie_id): float(score)
        for movie_id, score in popularity_scores.items()
        if int(movie_id) not in seen_movies
        and (
            candidate_movie_ids is None
            or int(movie_id) in candidate_movie_ids
        )
    }

    popularity_candidates = dict(
        sorted(
            popularity_candidates.items(),
            key=lambda item: item[1],
            reverse=True
        )[:candidate_pool_size]
    )

    # 4. Normalize individual model scores
    knn_normalized = normalize_scores(knn_scores)
    content_normalized = normalize_scores(content_scores)
    popularity_normalized = normalize_scores(
        popularity_candidates
    )

    # 5. Combine all three recommendation models
    hybrid_scores = calculate_hybrid_scores(
        knn_scores=knn_scores,
        content_scores=content_scores,
        popularity_scores=popularity_candidates,
        knn_weight=knn_weight,
        content_weight=content_weight,
        popularity_weight=popularity_weight
    )

    # 6. Return ranked recommendations with component scores
    recommendations = []

    for movie_id, hybrid_score in hybrid_scores.items():

        if movie_id in seen_movies:
            continue

        if (
            candidate_movie_ids is not None
            and movie_id not in candidate_movie_ids
        ):
            continue

        recommendations.append({
            "movie_id": int(movie_id),
            "hybrid_score": round(
                float(hybrid_score), 4
            ),
            "knn_score": round(
                knn_normalized.get(movie_id, 0.0), 4
            ),
            "content_score": round(
                content_normalized.get(movie_id, 0.0), 4
            ),
            "popularity_score": round(
                popularity_normalized.get(movie_id, 0.0), 4
            )
        })

    return recommendations[:k]
