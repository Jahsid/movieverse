
import pandas as pd

from scipy.sparse import csr_matrix
from sklearn.neighbors import NearestNeighbors


class MovieRecommender:

    def __init__(self):

        self.model = NearestNeighbors(
            metric="cosine",
            algorithm="brute"
        )

        self.movie_matrix = None
        self.movie_mapper = {}
        self.movie_inverse_mapper = {}
        self.is_trained = False

    def train(self, ratings: pd.DataFrame):

        """
        Train an item-based collaborative filtering model.

        Rows    = Movies
        Columns = Users
        Values  = User ratings
        """

        if ratings.empty:
            raise ValueError("Ratings dataset is empty")

        required_columns = ["user_id", "movie_id", "rating"]

        missing = [
            column for column in required_columns
            if column not in ratings.columns
        ]

        if missing:
            raise ValueError(f"Missing columns: {missing}")

        # Build movie-user matrix.
        movie_user_matrix = ratings.pivot(
            index="movie_id",
            columns="user_id",
            values="rating"
        ).fillna(0)

        # Create movie ID mappings.
        self.movie_mapper = {
            movie_id: index
            for index, movie_id in enumerate(movie_user_matrix.index)
        }

        self.movie_inverse_mapper = {
            index: movie_id
            for movie_id, index in self.movie_mapper.items()
        }

        # Convert dense matrix into sparse matrix.
        self.movie_matrix = csr_matrix(
            movie_user_matrix.values
        )

        # Train nearest neighbors model.
        self.model.fit(self.movie_matrix)

        self.is_trained = True

        print("KNN model trained successfully!")
        print(f"Movies: {self.movie_matrix.shape[0]}")
        print(f"Users: {self.movie_matrix.shape[1]}")

    def recommend(self, movie_id: int, k: int = 5):

        """
        Recommend k similar movies for a given movie ID.
        """

        if not self.is_trained:
            raise RuntimeError("Train the model before recommending")

        if k < 1:
            raise ValueError("k must be at least 1")

        if movie_id not in self.movie_mapper:
            return []

        total_movies = self.movie_matrix.shape[0]

        if total_movies <= 1:
            return []

        movie_index = self.movie_mapper[movie_id]

        number_of_neighbors = min(k + 1, total_movies)

        distances, indices = self.model.kneighbors(
            self.movie_matrix[movie_index],
            n_neighbors=number_of_neighbors
        )

        recommendations = []

        for distance, index in zip(
            distances[0],
            indices[0]
        ):

            recommended_movie_id = (
                self.movie_inverse_mapper[index]
            )

            # Exclude the input movie itself.
            if recommended_movie_id == movie_id:
                continue

            recommendations.append({
                "movie_id": int(recommended_movie_id),
                "similarity": float(1 - distance)
            })

            if len(recommendations) == k:
                break

        return recommendations
