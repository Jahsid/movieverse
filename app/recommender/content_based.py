import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics.pairwise import cosine_similarity

class ContentBasedRecommender:

    def __init__(self):
        self.model = NearestNeighbors(
            metric="cosine",
            algorithm="brute"
        )

        self.vectorizer = TfidfVectorizer(
            token_pattern=r"(?u)\b[\w-]+\b"
        )

        self.movies = None
        self.movie_vectors = None
        self.movie_id_to_index = {}
        self.is_trained = False

    def fit(self, movies: pd.DataFrame):

        self.movies = movies.copy()

        # Convert pipe-separated genres into space-separated tokens
        self.movies["genres"] = (
            self.movies["genres"]
            .fillna("")
            .str.replace("|", " ", regex=False)
        )

        # Convert genres into TF-IDF numerical vectors
        self.movie_vectors = self.vectorizer.fit_transform(
            self.movies["genres"]
        )

        # Create movie ID to matrix index mapping
        self.movie_id_to_index = {
            movie_id: index
            for index, movie_id in enumerate(self.movies["movieId"])
        }

        # Train nearest neighbors model
        self.model.fit(self.movie_vectors)

        self.is_trained = True

        print("Content-Based model trained successfully!")
        print(f"Movies: {len(self.movies)}")
        print(f"Features: {self.movie_vectors.shape[1]}")

    def recommend(self, movie_id: int, k: int = 5):

        if not self.is_trained:
            raise RuntimeError("Model has not been trained.")

        if movie_id not in self.movie_id_to_index:
            raise ValueError(f"Movie ID {movie_id} not found.")

        movie_index = self.movie_id_to_index[movie_id]

        # Find similar movies
        distances, indices = self.model.kneighbors(
            self.movie_vectors[movie_index],
            n_neighbors=min(k + 1, len(self.movies))
        )

        recommendations = []

        for distance, index in zip(distances[0], indices[0]):

            recommended_movie = self.movies.iloc[index]

            # Exclude the input movie itself
            if recommended_movie["movieId"] == movie_id:
                continue

            recommendations.append({
                "movie_id": int(recommended_movie["movieId"]),
                "title": recommended_movie["title"],
                "genres": recommended_movie["genres"],
                "similarity": round(float(1 - distance), 4)
            })

            if len(recommendations) == k:
                break

        return recommendations


    
    def recommend_for_user(
        self,
        user_ratings: pd.DataFrame,
        k: int = 10,
        rating_threshold: float = 4.0,
        candidate_movie_ids=None
    ):

        if not self.is_trained:
            raise RuntimeError("Model has not been trained.")

        if k <= 0:
            return []

        # Movies already watched or rated by the user
        seen_movie_ids = set(user_ratings["movie_id"])

        # Select positively rated movies
        liked_movies = user_ratings[
            user_ratings["rating"] >= rating_threshold
        ]

        if liked_movies.empty:
            return []

        # Keep only movies available in our content model
        liked_movies = liked_movies[
            liked_movies["movie_id"].isin(self.movie_id_to_index)
        ]

        if liked_movies.empty:
            return []

        # Get matrix positions of liked movies
        liked_indices = [
            self.movie_id_to_index[movie_id]
            for movie_id in liked_movies["movie_id"]
        ]

        # Give higher-rated movies more influence
        weights = liked_movies["rating"].to_numpy() - 3.0

        # Construct the user's genre profile
        user_profile = np.asarray(
            self.movie_vectors[liked_indices].multiply(
                weights.reshape(-1, 1)
            ).sum(axis=0)
        )

        # Define the recommendation candidate catalogue
        if candidate_movie_ids is None:
            candidate_set = set(self.movie_id_to_index)
        else:
            candidate_set = set(candidate_movie_ids)

        # Exclude movies already rated by the user
        candidate_set = candidate_set - seen_movie_ids

        # Keep only candidates available in the content model
        candidate_indices = [
            index
            for index, movie_id in enumerate(self.movies["movieId"])
            if movie_id in candidate_set
        ]

        if not candidate_indices:
            return []

        # Compare user profile only against eligible candidates
        candidate_vectors = self.movie_vectors[candidate_indices]

        scores = cosine_similarity(
            user_profile,
            candidate_vectors
        ).flatten()

        # Rank eligible candidates by similarity
        ranked_positions = scores.argsort()[::-1][:k]

        recommendations = []

        for position in ranked_positions:

            index = candidate_indices[position]
            movie = self.movies.iloc[index]

            recommendations.append({
                "movie_id": int(movie["movieId"]),
                "title": movie["title"],
                "genres": movie["genres"],
                "similarity": round(float(scores[position]), 4)
            })

        return recommendations

