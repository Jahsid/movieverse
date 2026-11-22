import pandas as pd
from app.recommender.model import MovieRecommender
from app.recommender.content_based import ContentBasedRecommender
from app.recommender.hybrid import calculate_popularity_scores
from app.recommender.hybrid_service import recommend_hybrid_for_user

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
    seed_count: int = 5,
    candidates_per_seed: int = 50,
    random_state: int = 42
):

    # Split ratings separately for each user.
    test_data = ratings.groupby(
        "user_id",
        group_keys=False
    ).sample(
        frac=test_fraction,
        random_state=random_state
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
            candidates_per_seed=candidates_per_seed
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


def evaluate_temporal_model(
    ratings: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    test_fraction: float = 0.2,
    seed_count: int = 20,
    candidates_per_seed: int = 50
):
    """
    Evaluate recommendations using a chronological train/test split.

    Older interactions are used for training.
    Newer interactions are used for testing.
    """

    # Validate timestamp availability
    if "timestamp" not in ratings.columns:
        raise ValueError("Ratings must contain timestamp column")

    if ratings["timestamp"].isna().any():
        raise ValueError("Missing timestamps found")

    # Sort interactions chronologically
    ratings = ratings.sort_values("timestamp").copy()

    # Convert Unix timestamps into readable dates for reporting
    ratings["rated_at"] = pd.to_datetime(
        ratings["timestamp"],
        unit="s",
        utc=True
    )

    # Determine a global chronological cutoff
    cutoff = ratings["timestamp"].quantile(
        1 - test_fraction
    )

    # Older interactions -> Training
    train_data = ratings[
        ratings["timestamp"] < cutoff
    ].copy()

    # Newer interactions -> Testing
    test_data = ratings[
        ratings["timestamp"] >= cutoff
    ].copy()

    print("\nTEMPORAL SPLIT")
    print(f"Cutoff timestamp: {cutoff}")
    print(f"Training records: {len(train_data)}")
    print(f"Testing records: {len(test_data)}")

    print(
        "Training period:",
        train_data["rated_at"].min(),
        "to",
        train_data["rated_at"].max()
    )

    print(
        "Testing period:",
        test_data["rated_at"].min(),
        "to",
        test_data["rated_at"].max()
    )

    # Train recommendation model only on historical ratings
    recommender = MovieRecommender()
    recommender.train(
        train_data[["user_id", "movie_id", "rating"]]
    )

    precision_scores = []
    recall_scores = []

    evaluated_users = 0

    # Evaluate users with both historical and future interactions
    for user_id, user_test in test_data.groupby("user_id"):

        user_train = train_data[
            train_data["user_id"] == user_id
        ]

        if user_train.empty:
            continue

        relevant_movies = set(
            user_test.loc[
                user_test["rating"] >= rating_threshold,
                "movie_id"
            ]
        )

        if not relevant_movies:
            continue

        recommendations = recommender.recommend_for_user(
            user_ratings=user_train,
            k=k,
            seed_count=seed_count,
            candidates_per_seed=candidates_per_seed
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
        raise ValueError(
            "No eligible users found for temporal evaluation"
        )

    return {
        "precision_at_k": sum(precision_scores) / evaluated_users,
        "recall_at_k": sum(recall_scores) / evaluated_users,
        "k": k,
        "seed_count": seed_count,
        "candidates_per_seed": candidates_per_seed,
        "evaluated_users": evaluated_users,
        "cutoff_timestamp": cutoff
    }


def evaluate_temporal_popularity_baseline(
    ratings: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    test_fraction: float = 0.2
):
    """
    Evaluate a popularity-based recommender using
    a chronological train/test split.
    """

    if "timestamp" not in ratings.columns:
        raise ValueError("Ratings must contain timestamp column")

    if ratings["timestamp"].isna().any():
        raise ValueError("Missing timestamps found")

    # Sort ratings chronologically
    ratings = ratings.sort_values("timestamp").copy()

    # Use the same global temporal cutoff as KNN
    cutoff = ratings["timestamp"].quantile(
        1 - test_fraction
    )

    train_data = ratings[
        ratings["timestamp"] < cutoff
    ].copy()

    test_data = ratings[
        ratings["timestamp"] >= cutoff
    ].copy()

    print("\nTEMPORAL POPULARITY BASELINE")

    print(f"Training records: {len(train_data)}")
    print(f"Testing records: {len(test_data)}")

    # Rank movies by count of high ratings in training data
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

        if user_train.empty:
            continue

        relevant_movies = set(
            user_test.loc[
                user_test["rating"] >= rating_threshold,
                "movie_id"
            ]
        )

        if not relevant_movies:
            continue

        # Exclude movies already rated by the user
        seen_movies = set(user_train["movie_id"])

        recommendations = [
            movie_id
            for movie_id in popular_movies
            if movie_id not in seen_movies
        ][:k]

        precision, recall = precision_recall_at_k(
            recommendations,
            relevant_movies,
            k
        )

        precision_scores.append(precision)
        recall_scores.append(recall)

        evaluated_users += 1

    if evaluated_users == 0:
        raise ValueError(
            "No eligible users for temporal popularity evaluation"
        )

    return {
        "precision_at_k": sum(precision_scores) / evaluated_users,
        "recall_at_k": sum(recall_scores) / evaluated_users,
        "k": k,
        "evaluated_users": evaluated_users,
        "cutoff_timestamp": cutoff
    }



def evaluate_rolling_temporal_models(
    ratings: pd.DataFrame,
    movies: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    seed_count: int = 20,
    candidates_per_seed: int = 50
):
    """
    Compare multi-seed KNN and popularity using
    four expanding-window temporal evaluation folds.

    Calculates:
    1. Overall Precision@K and Recall@K
    2. Warm-start Precision@K and Recall@K
    3. Data coverage diagnostics
    """

    # Validate timestamp availability
    if "timestamp" not in ratings.columns:
        raise ValueError("Ratings must contain timestamp column")

    if ratings["timestamp"].isna().any():
        raise ValueError("Missing timestamps found")

    # Define temporal evaluation folds
    folds = [
        ("2016-09-01", "2017-03-01"),
        ("2017-03-01", "2017-09-01"),
        ("2017-09-01", "2018-03-01"),
        ("2018-03-01", "2018-09-01"),
    ]

    fold_results = []

    # Overall aggregate metrics
    all_knn_precision = []
    all_knn_recall = []

    all_pop_precision = []
    all_pop_recall = []

    # Warm-start aggregate metrics
    # IMPORTANT: Initialize these outside the fold loop.
    all_warm_knn_precision = []
    all_warm_knn_recall = []

    all_warm_pop_precision = []
    all_warm_pop_recall = []

    # Content-Based aggregate metrics
    all_content_precision = []
    all_content_recall = []

    # Content-Based warm-start aggregate metrics
    all_warm_content_precision = []
    all_warm_content_recall = []

    # Hybrid overall aggregate metrics
    all_hybrid_precision = []
    all_hybrid_recall = []

    # Hybrid warm-start aggregate metrics
    all_warm_hybrid_precision = []
    all_warm_hybrid_recall = []

    # Process each temporal fold
    for fold_number, (start_date, end_date) in enumerate(folds, 1):

        start_timestamp = pd.Timestamp(
            start_date, tz="UTC"
        ).timestamp()

        end_timestamp = pd.Timestamp(
            end_date, tz="UTC"
        ).timestamp()

        # Expanding historical training window
        train_data = ratings[
            ratings["timestamp"] < start_timestamp
        ].copy()

        # Current future test window
        test_data = ratings[
            (ratings["timestamp"] >= start_timestamp) &
            (ratings["timestamp"] < end_timestamp)
        ].copy()

        print(f"\n{'=' * 50}")
        print(f"ROLLING TEMPORAL FOLD {fold_number}")
        print(f"{'=' * 50}")

        print(f"Training cutoff: {start_date}")
        print(f"Testing period: {start_date} to {end_date}")

        print(f"Training records: {len(train_data)}")
        print(f"Testing records: {len(test_data)}")

        # Temporal data coverage diagnostics
        train_users = set(train_data["user_id"])
        test_users = set(test_data["user_id"])

        users_with_history = train_users & test_users

        positive_test = test_data[
            test_data["rating"] >= rating_threshold
        ]

        users_with_positive_ratings = set(
            positive_test["user_id"]
        )

        eligible_users = (
            users_with_history & users_with_positive_ratings
        )

        training_movies = set(train_data["movie_id"])

        known_positive_movies = positive_test[
            positive_test["movie_id"].isin(training_movies)
        ]

        unknown_positive_movies = positive_test[
            ~positive_test["movie_id"].isin(training_movies)
        ]

        print("\nDATA COVERAGE DIAGNOSTICS")

        print(f"Unique training users: {len(train_users)}")
        print(f"Unique testing users: {len(test_users)}")

        print(
            f"Users with historical interactions: "
            f"{len(users_with_history)}"
        )

        print(
            f"Users with positive future ratings: "
            f"{len(users_with_positive_ratings)}"
        )

        print(f"Eligible users: {len(eligible_users)}")

        print(f"Positive test ratings: {len(positive_test)}")

        print(
            f"Positive ratings for known movies: "
            f"{len(known_positive_movies)}"
        )

        print(
            f"Positive ratings for unseen movies: "
            f"{len(unknown_positive_movies)}"
        )

        if train_data.empty or test_data.empty:
            print("Skipping fold: insufficient data")
            continue

        # Train KNN using historical interactions only
        recommender = MovieRecommender()

        recommender.train(
            train_data[["user_id", "movie_id", "rating"]]
        )

        # Train Content-Based model using movie genres
        content_recommender = ContentBasedRecommender()

        content_recommender.fit(movies)

        # Popularity ranking using the same training data
        popular_movies = (
            train_data[
                train_data["rating"] >= rating_threshold
            ]
            .groupby("movie_id")
            .size()
            .sort_values(ascending=False)
            .index.tolist()
        )

        # Popularity scores for Hybrid model
        popularity_scores = calculate_popularity_scores(
            train_data,
            rating_threshold=rating_threshold
        )

        # Per-fold overall metrics
        knn_precision = []
        knn_recall = []

        pop_precision = []
        pop_recall = []

        content_precision = []
        content_recall = []

        # Per-fold warm-start metrics
        warm_knn_precision = []
        warm_knn_recall = []

        warm_pop_precision = []
        warm_pop_recall = []

        warm_content_precision = []
        warm_content_recall = []

        # Hybrid warm-start metrics
        warm_hybrid_precision = []
        warm_hybrid_recall = []

        # Hybrid overall metrics
        hybrid_precision = []
        hybrid_recall = []

        evaluated_users = 0

        # Both models are evaluated on exactly the same users
        for user_id, user_test in test_data.groupby("user_id"):

            user_train = train_data[
                train_data["user_id"] == user_id
            ]

            if user_train.empty:
                continue

            # Relevant positive movies in future test data
            relevant_movies = set(
                user_test.loc[
                    user_test["rating"] >= rating_threshold,
                    "movie_id"
                ]
            )

            if not relevant_movies:
                continue

            # Warm-start relevant movies:
            # Only movies available in the training catalogue.
            warm_relevant_movies = relevant_movies.intersection(
                training_movies
            )

            seen_movies = set(user_train["movie_id"])

            # KNN recommendations
            knn_recommendations = recommender.recommend_for_user(
                user_ratings=user_train,
                k=k,
                seed_count=seed_count,
                candidates_per_seed=candidates_per_seed
            )

            # Content-Based recommendations
            content_user_ratings = user_train[
                ["movie_id", "rating"]
            ]

            content_recommendations = content_recommender.recommend_for_user(
                user_ratings=content_user_ratings,
                k=k,
                rating_threshold=rating_threshold
            )

            content_ids = [
                item["movie_id"]
                for item in content_recommendations
            ]

            # Content-Based recommendations restricted to warm-start candidates
            content_warm_recommendations = content_recommender.recommend_for_user(
                user_ratings=content_user_ratings,
                k=k,
                rating_threshold=rating_threshold,
                candidate_movie_ids=training_movies
            )

            content_warm_ids = [
                item["movie_id"]
                for item in content_warm_recommendations
            ]

            knn_ids = [
                item["movie_id"]
                for item in knn_recommendations
            ]

            # Popularity recommendations
            popularity_ids = [
                movie_id
                for movie_id in popular_movies
                if movie_id not in seen_movies
            ][:k]

            # Hybrid recommendations
            hybrid_recommendations = recommend_hybrid_for_user(
                knn_recommender=recommender,
                content_recommender=content_recommender,
                user_ratings=user_train,
                popularity_scores=popularity_scores,
                candidate_movie_ids=None,
                k=k,
                seed_count=seed_count,
                candidates_per_seed=candidates_per_seed
            )

            hybrid_ids = [
                item["movie_id"]
                for item in hybrid_recommendations
            ]

            # Overall evaluation
            p_knn, r_knn = precision_recall_at_k(
                knn_ids,
                relevant_movies,
                k
            )

            p_content, r_content = precision_recall_at_k(
                content_ids,
                relevant_movies,
                k
            )

            p_pop, r_pop = precision_recall_at_k(
                popularity_ids,
                relevant_movies,
                k
            )

            p_hybrid, r_hybrid = precision_recall_at_k(
                hybrid_ids,
                relevant_movies,
                k
            )

            knn_precision.append(p_knn)
            knn_recall.append(r_knn)

            pop_precision.append(p_pop)
            pop_recall.append(r_pop)

            content_precision.append(p_content)
            content_recall.append(r_content)

            hybrid_precision.append(p_hybrid)
            hybrid_recall.append(r_hybrid)

            # Warm-start evaluation
            # Skip users with no known positive future movies.
            if warm_relevant_movies:

                wp_knn, wr_knn = precision_recall_at_k(
                    knn_ids,
                    warm_relevant_movies,
                    k
                )

                wp_pop, wr_pop = precision_recall_at_k(
                    popularity_ids,
                    warm_relevant_movies,
                    k
                )

                wp_content, wr_content = precision_recall_at_k(
                    content_warm_ids,
                    warm_relevant_movies,
                    k
                )

                # Warm-start Hybrid recommendations
                warm_hybrid_recommendations = recommend_hybrid_for_user(
                    knn_recommender=recommender,
                    content_recommender=content_recommender,
                    user_ratings=user_train,
                    popularity_scores=popularity_scores,
                    candidate_movie_ids=training_movies,
                    k=k,
                    seed_count=seed_count,
                    candidates_per_seed=candidates_per_seed
                )

                warm_hybrid_ids = [
                    item["movie_id"]
                    for item in warm_hybrid_recommendations
                ]

                wp_hybrid, wr_hybrid = precision_recall_at_k(
                    warm_hybrid_ids,
                    warm_relevant_movies,
                    k
                )

                warm_knn_precision.append(wp_knn)
                warm_knn_recall.append(wr_knn)

                warm_pop_precision.append(wp_pop)
                warm_pop_recall.append(wr_pop)

                warm_content_precision.append(wp_content)
                warm_content_recall.append(wr_content)

                warm_hybrid_precision.append(wp_hybrid)
                warm_hybrid_recall.append(wr_hybrid)

            evaluated_users += 1

        if evaluated_users == 0:
            print("No eligible users in this fold")
            continue

        warm_evaluated_users = len(warm_knn_precision)

        # Store per-fold results
        fold_result = {
            "fold": fold_number,
            "start_date": start_date,
            "end_date": end_date,
            "training_records": len(train_data),
            "testing_records": len(test_data),
            "evaluated_users": evaluated_users,

            # Overall metrics
            "knn_precision": sum(knn_precision) / evaluated_users,
            "knn_recall": sum(knn_recall) / evaluated_users,
            "pop_precision": sum(pop_precision) / evaluated_users,
            "pop_recall": sum(pop_recall) / evaluated_users,
            "content_precision": sum(content_precision) / evaluated_users,
            "content_recall": sum(content_recall) / evaluated_users,
            "hybrid_precision": sum(hybrid_precision) / evaluated_users,
            "hybrid_recall": sum(hybrid_recall) / evaluated_users,

            # Warm-start metrics
            "warm_evaluated_users": warm_evaluated_users,

            "warm_knn_precision": (
                sum(warm_knn_precision) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_knn_recall": (
                sum(warm_knn_recall) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_pop_precision": (
                sum(warm_pop_precision) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_pop_recall": (
                sum(warm_pop_recall) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_content_precision": (
                sum(warm_content_precision) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_content_recall": (
                sum(warm_content_recall) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_hybrid_precision": (
                sum(warm_hybrid_precision) / warm_evaluated_users
                if warm_evaluated_users else 0
            ),

            "warm_hybrid_recall": (
                sum(warm_hybrid_recall) / warm_evaluated_users
                if warm_evaluated_users else 0
            )
        }

        # Accumulate overall metrics across folds
        all_knn_precision.extend(knn_precision)
        all_knn_recall.extend(knn_recall)

        all_pop_precision.extend(pop_precision)
        all_pop_recall.extend(pop_recall)

        all_content_precision.extend(content_precision)
        all_content_recall.extend(content_recall)

        # Accumulate Hybrid overall metrics
        all_hybrid_precision.extend(hybrid_precision)
        all_hybrid_recall.extend(hybrid_recall)

        # Accumulate warm-start metrics across folds
        # Do NOT reinitialize these lists inside the fold loop.
        all_warm_knn_precision.extend(warm_knn_precision)
        all_warm_knn_recall.extend(warm_knn_recall)

        all_warm_pop_precision.extend(warm_pop_precision)
        all_warm_pop_recall.extend(warm_pop_recall)

        all_warm_content_precision.extend(warm_content_precision)
        all_warm_content_recall.extend(warm_content_recall)

        # Accumulate Hybrid warm-start metrics
        all_warm_hybrid_precision.extend(warm_hybrid_precision)
        all_warm_hybrid_recall.extend(warm_hybrid_recall)

        fold_results.append(fold_result)

        # Print overall fold results
        print(f"\nEvaluated users: {evaluated_users}")

        print(
            f"KNN Precision@{k}: "
            f"{fold_result['knn_precision']:.4f}"
        )

        print(
            f"KNN Recall@{k}: "
            f"{fold_result['knn_recall']:.4f}"
        )

        print(
            f"Popularity Precision@{k}: "
            f"{fold_result['pop_precision']:.4f}"
        )

        print(
            f"Popularity Recall@{k}: "
            f"{fold_result['pop_recall']:.4f}"
        )

        print(
            f"Hybrid Precision@{k}: "
            f"{fold_result['hybrid_precision']:.4f}"
        )

        print(
            f"Hybrid Recall@{k}: "
            f"{fold_result['hybrid_recall']:.4f}"
        )

        print(
            f"Hybrid Warm Precision@{k}: "
            f"{fold_result['warm_hybrid_precision']:.4f}"
        )

        print(
            f"Hybrid Warm Recall@{k}: "
            f"{fold_result['warm_hybrid_recall']:.4f}"
        )

        # Print warm-start fold results
        print("\nWARM-START RESULTS")

        print(
            f"Warm-start evaluated users: "
            f"{warm_evaluated_users}"
        )

        print(
            f"KNN Warm Precision@{k}: "
            f"{fold_result['warm_knn_precision']:.4f}"
        )

        print(
            f"KNN Warm Recall@{k}: "
            f"{fold_result['warm_knn_recall']:.4f}"
        )

        print(
            f"Popularity Warm Precision@{k}: "
            f"{fold_result['warm_pop_precision']:.4f}"
        )

        print(
            f"Popularity Warm Recall@{k}: "
            f"{fold_result['warm_pop_recall']:.4f}"
        )

        print(
            f"Content-Based Precision@{k}: "
            f"{fold_result['content_precision']:.4f}"
        )

        print(
            f"Content-Based Recall@{k}: "
            f"{fold_result['content_recall']:.4f}"
        )

        print(
            f"Content-Based Warm Precision@{k}: "
            f"{fold_result['warm_content_precision']:.4f}"
        )

        print(
            f"Content-Based Warm Recall@{k}: "
            f"{fold_result['warm_content_recall']:.4f}"
        )


    if not fold_results:
        raise ValueError("No valid rolling temporal folds found")

    
    # Aggregate across all eligible user-fold observations
    overall = {
        "knn_precision": (
            sum(all_knn_precision) / len(all_knn_precision)
        ),

        "knn_recall": (
            sum(all_knn_recall) / len(all_knn_recall)
        ),

        "pop_precision": (
            sum(all_pop_precision) / len(all_pop_precision)
        ),

        "pop_recall": (
            sum(all_pop_recall) / len(all_pop_recall)
        ),

        "evaluated_user_periods": len(all_knn_precision),

        # Aggregate warm-start metrics
        "warm_knn_precision": (
            sum(all_warm_knn_precision) / len(all_warm_knn_precision)
            if all_warm_knn_precision else 0
        ),

        "warm_knn_recall": (
            sum(all_warm_knn_recall) / len(all_warm_knn_recall)
            if all_warm_knn_recall else 0
        ),

        "warm_pop_precision": (
            sum(all_warm_pop_precision) / len(all_warm_pop_precision)
            if all_warm_pop_precision else 0
        ),

        "warm_pop_recall": (
            sum(all_warm_pop_recall) / len(all_warm_pop_recall)
            if all_warm_pop_recall else 0
        ),

        "warm_evaluated_user_periods": len(all_warm_knn_precision),

        # Content-Based overall metrics
        "content_precision": (
            sum(all_content_precision) / len(all_content_precision)
            if all_content_precision else 0
        ),

        "content_recall": (
            sum(all_content_recall) / len(all_content_recall)
            if all_content_recall else 0
        ),

        "hybrid_precision": (
            sum(all_hybrid_precision) / len(all_hybrid_precision)
            if all_hybrid_precision else 0
        ),

        "hybrid_recall": (
            sum(all_hybrid_recall) / len(all_hybrid_recall)
            if all_hybrid_recall else 0
        ),

        # Content-Based warm-start aggregate metrics
        "warm_content_precision": (
            sum(all_warm_content_precision) / len(all_warm_content_precision)
            if all_warm_content_precision else 0
        ),

        "warm_content_recall": (
            sum(all_warm_content_recall) / len(all_warm_content_recall)
            if all_warm_content_recall else 0
        ),

        "warm_hybrid_precision": (
            sum(all_warm_hybrid_precision) / len(all_warm_hybrid_precision)
            if all_warm_hybrid_precision else 0
        ),

        "warm_hybrid_recall": (
            sum(all_warm_hybrid_recall) / len(all_warm_hybrid_recall)
            if all_warm_hybrid_recall else 0
        )
    }

    return {
        "folds": fold_results,
        "overall": overall
    }

