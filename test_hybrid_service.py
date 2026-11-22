
import pandas as pd

from app.database.connection import SessionLocal
from app.database.models import Rating

from app.recommender.model import MovieRecommender
from app.recommender.content_based import ContentBasedRecommender

from app.recommender.hybrid import calculate_popularity_scores
from app.recommender.hybrid_service import recommend_hybrid_for_user


def main():

    db = SessionLocal()

    try:
        # 1. Load ratings from PostgreSQL
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

        # 2. Select a user with sufficient rating history
        user_rating_counts = ratings.groupby("user_id").size()

        user_id = int(user_rating_counts.idxmax())

        user_ratings = ratings[
            ratings["user_id"] == user_id
        ].copy()

        print(f"\nSelected user: {user_id}")
        print(f"User ratings: {len(user_ratings)}")

        # 3. Train KNN
        knn = MovieRecommender()
        knn.train(ratings)

        # 4. Train Content-Based model
        movies = pd.read_csv("data/raw/movies.csv")

        content = ContentBasedRecommender()
        content.fit(movies)

        # 5. Calculate popularity
        popularity_scores = calculate_popularity_scores(
            ratings,
            rating_threshold=4.0
        )

        # 6. Generate hybrid recommendations
        recommendations = recommend_hybrid_for_user(
            knn_recommender=knn,
            content_recommender=content,
            user_ratings=user_ratings,
            popularity_scores=popularity_scores,
            k=10
        )

        # 7. Display movie titles
        movie_lookup = movies.set_index("movieId")["title"]

        print("\nHYBRID RECOMMENDATIONS")

        for rank, item in enumerate(recommendations, start=1):

            movie_id = item["movie_id"]
            title = movie_lookup.get(movie_id, "Unknown movie")

            print(f"\nRank: {rank}")
            print(f"Movie: {title}")
            print(f"Hybrid Score: {item['hybrid_score']}")
            print(f"KNN Score: {item['knn_score']}")
            print(f"Content Score: {item['content_score']}")
            print(f"Popularity Score: {item['popularity_score']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
