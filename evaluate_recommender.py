
import pandas as pd

from app.database.connection import SessionLocal
from app.database.models import Rating

from app.recommender.evaluation import (
    evaluate_model,
    evaluate_multi_seed_model,
    evaluate_popularity_baseline
)


def main():

    db = SessionLocal()

    try:

        print("STEP 1: Loading ratings from PostgreSQL")

        records = db.query(
            Rating.user_id,
            Rating.movie_id,
            Rating.rating
        ).all()

        ratings = pd.DataFrame(
            records,
            columns=["user_id", "movie_id", "rating"]
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

    finally:
        db.close()


if __name__ == "__main__":
    main()
