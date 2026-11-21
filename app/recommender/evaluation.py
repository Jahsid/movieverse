
import pandas as pd

from app.recommender.model import MovieRecommender


def precision_recall_at_k(
    recommended_ids,
    relevant_ids,
    k
):
    recommended_ids = recommended_ids[:k]

    relevant_ids = set(relevant_ids)

    hits = len(set(recommended_ids) & relevant_ids)

    precision = hits / k if k > 0 else 0

    recall = (
        hits / len(relevant_ids)
        if relevant_ids else 0
    )

    return precision, recall


def evaluate_model(
    ratings: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    test_fraction: float = 0.2
):

    # Split ratings separately for each user.
    test_data = ratings.groupby(
        "user_id",
        group_keys=False
    ).sample(
        frac=test_fraction,
        random_state=42
    )

    train_data = ratings.drop(test_data.index)

    print(f"Training records: {len(train_data)}")
    print(f"Testing records: {len(test_data)}")

    # Train a fresh model using training data only.
    recommender = MovieRecommender()
    recommender.train(train_data)

    precision_scores = []
    recall_scores = []

    evaluated_users = 0

    for user_id, user_test in test_data.groupby("user_id"):

        user_train = train_data[
            train_data["user_id"] == user_id
        ]

        # Relevant held-out movies.
        relevant_movies = set(
            user_test.loc[
                user_test["rating"] >= rating_threshold,
                "movie_id"
            ]
        )

        if not relevant_movies:
            continue

        if user_train.empty:
            continue

        # Select a highly rated movie as the seed.
        liked_movies = user_train[
            user_train["rating"] >= rating_threshold
        ]

        if liked_movies.empty:
            liked_movies = user_train

        seed_movie_id = int(
            liked_movies.sort_values(
                ["rating", "movie_id"],
                ascending=[False, True]
            ).iloc[0]["movie_id"]
        )

        # Exclude movies already seen in training.
        seen_movies = set(user_train["movie_id"])

        # Retrieve extra candidates before filtering seen movies.
        candidate_count = min(
            len(recommender.movie_mapper) - 1,
            k + len(seen_movies) + 10
        )

        candidates = recommender.recommend(
            movie_id=seed_movie_id,
            k=candidate_count
        )

        recommended_movies = [
            item["movie_id"]
            for item in candidates
            if item["movie_id"] not in seen_movies
        ][:k]

        precision, recall = precision_recall_at_k(
            recommended_movies,
            relevant_movies,
            k
        )

        precision_scores.append(precision)
        recall_scores.append(recall)

        evaluated_users += 1

    if evaluated_users == 0:
        raise ValueError(
            "No users available for evaluation"
        )

    return {
        "precision_at_k": sum(precision_scores) / evaluated_users,
        "recall_at_k": sum(recall_scores) / evaluated_users,
        "k": k,
        "evaluated_users": evaluated_users
    }


def evaluate_multi_seed_model(
    ratings: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    test_fraction: float = 0.2,
    seed_count: int = 5
):

    # Split ratings separately for each user.
    test_data = ratings.groupby(
        "user_id",
        group_keys=False
    ).sample(
        frac=test_fraction,
        random_state=42
    )

    train_data = ratings.drop(test_data.index)

    print(f"Training records: {len(train_data)}")
    print(f"Testing records: {len(test_data)}")

    # Train model using training data only.
    recommender = MovieRecommender()
    recommender.train(train_data)

    precision_scores = []
    recall_scores = []

    evaluated_users = 0

    for user_id, user_test in test_data.groupby("user_id"):

        user_train = train_data[
            train_data["user_id"] == user_id
        ]

        # Relevant movies in test data.
        relevant_movies = set(
            user_test.loc[
                user_test["rating"] >= rating_threshold,
                "movie_id"
            ]
        )

        if not relevant_movies or user_train.empty:
            continue

        # Generate recommendations using multiple liked movies.
        recommendations = recommender.recommend_for_user(
            user_ratings=user_train,
            k=k,
            seed_count=seed_count,
            candidates_per_seed=50
        )

        recommended_ids = [
            item["movie_id"]
            for item in recommendations
        ]

        precision, recall = precision_recall_at_k(
            recommended_ids,
            relevant_movies,
            k
        )

        precision_scores.append(precision)
        recall_scores.append(recall)

        evaluated_users += 1

    if evaluated_users == 0:
        raise ValueError("No users available for evaluation")

    return {
        "precision_at_k": sum(precision_scores) / evaluated_users,
        "recall_at_k": sum(recall_scores) / evaluated_users,
        "k": k,
        "seed_count": seed_count,
        "evaluated_users": evaluated_users
    }


def evaluate_popularity_baseline(
    ratings: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    test_fraction: float = 0.2
):

    # Use exactly the same split as the KNN evaluation.
    test_data = ratings.groupby(
        "user_id",
        group_keys=False
    ).sample(
        frac=test_fraction,
        random_state=42
    )

    train_data = ratings.drop(test_data.index)

    # Rank movies by the number of high ratings.
    popular_movies = (
        train_data[
            train_data["rating"] >= rating_threshold
        ]
        .groupby("movie_id")
        .size()
        .sort_values(ascending=False)
        .index
        .tolist()
    )

    precision_scores = []
    recall_scores = []

    evaluated_users = 0

    for user_id, user_test in test_data.groupby("user_id"):

        user_train = train_data[
            train_data["user_id"] == user_id
        ]

        relevant_movies = set(
            user_test.loc[
                user_test["rating"] >= rating_threshold,
                "movie_id"
            ]
        )

        if not relevant_movies or user_train.empty:
            continue

        seen_movies = set(user_train["movie_id"])

        recommended_movies = [
            movie_id
            for movie_id in popular_movies
            if movie_id not in seen_movies
        ][:k]

        precision, recall = precision_recall_at_k(
            recommended_movies,
            relevant_movies,
            k
        )

        precision_scores.append(precision)
        recall_scores.append(recall)

        evaluated_users += 1

    return {
        "precision_at_k": sum(precision_scores) / evaluated_users,
        "recall_at_k": sum(recall_scores) / evaluated_users,
        "k": k,
        "evaluated_users": evaluated_users
    }

