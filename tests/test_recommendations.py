
import pandas as pd

from app.database.connection import SessionLocal
from app.database.models import Rating

from app.recommender.model import MovieRecommender


def main():

    db = SessionLocal()

    try:

        print("STEP 1: Loading ratings from PostgreSQL")

        rating_records = db.query(
            Rating.user_id,
            Rating.movie_id,
            Rating.rating
        ).all()

        ratings = pd.DataFrame(
            rating_records,
            columns=["user_id", "movie_id", "rating"]
        )

        print(f"Loaded {len(ratings)} ratings")

        print("\nSTEP 2: Initializing KNN model")

        recommender = MovieRecommender()

        print("\nSTEP 3: Training model")

        recommender.train(ratings)

        print("\nSTEP 4: Generating recommendations")

        movie_id = 1

        recommendations = recommender.recommend(
            movie_id=movie_id,
            k=5
        )

        print(f"\nRecommendations for movie ID {movie_id}:")

        for recommendation in recommendations:
            print(recommendation)

    finally:
        db.close()


if __name__ == "__main__":
    main()
