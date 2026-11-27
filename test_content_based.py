
import pandas as pd

from app.recommender.content_based import ContentBasedRecommender

def main():
    # Load movies
    movies = pd.read_csv("data/raw/movies.csv")

    # Create and train model
    recommender = ContentBasedRecommender()
    recommender.fit(movies)

    # Simulated user rating history
    user_ratings = pd.DataFrame({
        "movie_id": [1, 2, 3, 6, 10],
        "rating": [5.0, 5.0, 4.5, 2.0, 2.0]
    })

    # Generate recommendations
    recommendations = recommender.recommend_for_user(user_ratings, k=10)
    print("\nPersonalized Recommendations:\n")
    for movie in recommendations:
        print(movie)


if __name__ == "__main__":
    main()
