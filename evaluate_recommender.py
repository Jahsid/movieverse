
import pandas as pd
import numpy as np

from app.database.connection import SessionLocal
from app.database.models import Rating

from app.recommender.evaluation import (
    evaluate_model,
    evaluate_multi_seed_model,
    evaluate_temporal_model,
    evaluate_temporal_popularity_baseline,
    evaluate_rolling_temporal_models
)

movies = pd.read_csv("data/raw/movies.csv")

def main():

    db = SessionLocal()

    try:

        print("STEP 1: Loading ratings from PostgreSQL")

        records = db.query(
            Rating.user_id,
            Rating.movie_id,
            Rating.rating,
            Rating.timestamp
        ).all()

        ratings = pd.DataFrame(
            records,
            columns=["user_id", "movie_id", "rating", "timestamp"]
        )

        print(f"Loaded {len(ratings)} ratings")

        print("\nSTEP 2: Evaluating KNN model")

        results = evaluate_model(
            ratings=ratings,
            k=10,
            rating_threshold=4.0,
            test_fraction=0.2
        )

        print("\nEVALUATION RESULTS")

        print(
            f"Precision@{results['k']}: "
            f"{results['precision_at_k']:.4f}"
        )

        print(
            f"Recall@{results['k']}: "
            f"{results['recall_at_k']:.4f}"
        )

        print(
            f"Evaluated users: "
            f"{results['evaluated_users']}"
        )

        print("\nSTEP 3: Evaluating multi-seed KNN")

        multi_results = evaluate_multi_seed_model(
            ratings=ratings,
            k=10,
            rating_threshold=4.0,
            test_fraction=0.2,
            seed_count=5
        )

        print("\nMULTI-SEED KNN RESULTS")

        print(
            f"Precision@10: "
            f"{multi_results['precision_at_k']:.4f}"
        )

        print(
            f"Recall@10: "
            f"{multi_results['recall_at_k']:.4f}"
        )

        print(
            f"Evaluated users: "
            f"{multi_results['evaluated_users']}"
        )

        print("\nSTEP 4: Comparing KNN configurations")

        experiments = [
            {"seed_count": 10, "candidates_per_seed": 50},
            {"seed_count": 10, "candidates_per_seed": 100},
            {"seed_count": 15, "candidates_per_seed": 50},
            {"seed_count": 20, "candidates_per_seed": 50},
        ]

        for experiment in experiments:

            print(
                f"\nTesting seeds={experiment['seed_count']}, "
                f"candidates={experiment['candidates_per_seed']}"
            )

            result = evaluate_multi_seed_model(
                ratings,
                k=10,
                seed_count=experiment["seed_count"],
                candidates_per_seed=experiment["candidates_per_seed"]
            )

            print(f"Precision@10: {result['precision_at_k']:.4f}")
            print(f"Recall@10: {result['recall_at_k']:.4f}")

        print("\nSTEP 5: Evaluating model stability")

        random_states = [21, 42, 100, 123, 2026]

        precision_scores = []
        recall_scores = []

        for state in random_states:

            print(f"\nEvaluating random state: {state}")

            result = evaluate_multi_seed_model(
                ratings=ratings,
                k=10,
                seed_count=20,
                candidates_per_seed=50,
                random_state=state
            )

            precision_scores.append(result["precision_at_k"])
            recall_scores.append(result["recall_at_k"])

            print(
                f"Precision@10: {result['precision_at_k']:.4f}"
            )

            print(
                f"Recall@10: {result['recall_at_k']:.4f}"
            )

        print("\nMODEL STABILITY RESULTS")

        print(
            f"Average Precision@10: "
            f"{np.mean(precision_scores):.4f}"
        )

        print(
            f"Precision Standard Deviation: "
            f"{np.std(precision_scores, ddof=1):.4f}"
        )

        print(
            f"Average Recall@10: "
            f"{np.mean(recall_scores):.4f}"
        )

        print(
            f"Recall Standard Deviation: "
            f"{np.std(recall_scores, ddof=1):.4f}"
        )
        print("\nSTEP 6: Temporal model evaluation")

        temporal_results = evaluate_temporal_model(
            ratings=ratings,
            k=10,
            rating_threshold=4.0,
            test_fraction=0.2,
            seed_count=20,
            candidates_per_seed=50
        )

        print("\nTEMPORAL EVALUATION RESULTS")

        print(
            f"Precision@10: "
            f"{temporal_results['precision_at_k']:.4f}"
        )

        print(
            f"Recall@10: "
            f"{temporal_results['recall_at_k']:.4f}"
        )

        print(
            f"Evaluated users: "
            f"{temporal_results['evaluated_users']}"
        )

        print("\nSTEP 7: Temporal popularity baseline")

        baseline_results = evaluate_temporal_popularity_baseline(
            ratings=ratings,
            k=10,
            rating_threshold=4.0,
            test_fraction=0.2
        )

        print("\nTEMPORAL POPULARITY RESULTS")

        print(
            f"Precision@10: "
            f"{baseline_results['precision_at_k']:.4f}"
        )

        print(
            f"Recall@10: "
            f"{baseline_results['recall_at_k']:.4f}"
        )

        print(
            f"Evaluated users: "
            f"{baseline_results['evaluated_users']}"
        )

        print("\nSTEP 8: Rolling temporal evaluation")

        rolling_results = evaluate_rolling_temporal_models(
            ratings=ratings,
            movies=movies,
            k=10,
            rating_threshold=4.0,
            seed_count=20,
            candidates_per_seed=50
        )

        print("\nROLLING TEMPORAL SUMMARY")

        for fold in rolling_results["folds"]:

            print(f"\nFold {fold['fold']}")

            print(
                f"Period: {fold['start_date']} to {fold['end_date']}"
            )

            print(
                f"KNN Precision@10: {fold['knn_precision']:.4f}"
            )

            print(
                f"Popularity Precision@10: {fold['pop_precision']:.4f}"
            )

            print(
                f"KNN Recall@10: {fold['knn_recall']:.4f}"
            )

            print(
                f"Popularity Recall@10: {fold['pop_recall']:.4f}"
            )

        
        print("\nOVERALL RESULTS")

        print(
            f"KNN Precision@10: "
            f"{rolling_results['overall']['knn_precision']:.4f}"
        )

        print(
            f"KNN Recall@10: "
            f"{rolling_results['overall']['knn_recall']:.4f}"
        )

        print(
            f"Popularity Precision@10: "
            f"{rolling_results['overall']['pop_precision']:.4f}"
        )

        print(
            f"Popularity Recall@10: "
            f"{rolling_results['overall']['pop_recall']:.4f}"
        )

        print(
            f"Evaluated user-periods: "
            f"{rolling_results['overall']['evaluated_user_periods']}"
        )

        print(
            f"Content-Based Precision@10: "
            f"{rolling_results['overall']['content_precision']:.4f}"
        )

        print(
            f"Content-Based Recall@10: "
            f"{rolling_results['overall']['content_recall']:.4f}"
        )

        print(
            f"Hybrid Precision@10: "
            f"{rolling_results['overall']['hybrid_precision']:.4f}"
        )

        print(
            f"Hybrid Recall@10: "
            f"{rolling_results['overall']['hybrid_recall']:.4f}"
        )

        print("\nOVERALL WARM-START RESULTS")

        print(
            f"KNN Warm Precision@10: "
            f"{rolling_results['overall']['warm_knn_precision']:.4f}"
        )

        print(
            f"KNN Warm Recall@10: "
            f"{rolling_results['overall']['warm_knn_recall']:.4f}"
        )

        print(
            f"Popularity Warm Precision@10: "
            f"{rolling_results['overall']['warm_pop_precision']:.4f}"
        )

        print(
            f"Popularity Warm Recall@10: "
            f"{rolling_results['overall']['warm_pop_recall']:.4f}"
        )

        print(
            f"Warm-start evaluated user-periods: "
            f"{rolling_results['overall']['warm_evaluated_user_periods']}"
        )

        print(
            f"Content-Based Precision@10: "
            f"{rolling_results['overall']['content_precision']:.4f}"
        )

        print(
            f"Content-Based Recall@10: "
            f"{rolling_results['overall']['content_recall']:.4f}"
        )

        print(
            f"Content-Based Warm Precision@10: "
            f"{rolling_results['overall']['warm_content_precision']:.4f}"
        )

        print(
            f"Content-Based Warm Recall@10: "
            f"{rolling_results['overall']['warm_content_recall']:.4f}"
        )

        print(
            f"Hybrid Warm Precision@10: "
            f"{rolling_results['overall']['warm_hybrid_precision']:.4f}"
        )

        print(
            f"Hybrid Warm Recall@10: "
            f"{rolling_results['overall']['warm_hybrid_recall']:.4f}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
