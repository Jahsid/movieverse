
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

    
    def recommend_for_user(
        self,
        user_ratings: pd.DataFrame,
        k: int = 10,
        seed_count: int = 5,
        candidates_per_seed: int = 50
    ):
        """
        Generate personalized recommendations using
        multiple highly rated movies from one user.
        """

        if not self.is_trained:
            raise RuntimeError("Train the model first")

        if k < 1 or seed_count < 1:
            raise ValueError("k and seed_count must be positive")

        required_columns = ["movie_id", "rating"]

        if not all(col in user_ratings.columns for col in required_columns):
            raise ValueError("user_ratings must contain movie_id and rating")

        # Movies already rated by the user.
        seen_movies = set(
            user_ratings["movie_id"].astype(int)
        )

        # Select highly rated movies that exist in the model.
        liked_movies = user_ratings[
            (user_ratings["rating"] >= 4.0) &
            (user_ratings["movie_id"].isin(self.movie_mapper))
        ].copy()

        if liked_movies.empty:
            return []

        # Select the user's top-rated seed movies.
        seed_movies = liked_movies.sort_values(
            ["rating", "movie_id"],
            ascending=[False, True]
        ).head(seed_count)

        # Aggregate recommendations from all seed movies.
        scores = {}

        total_seed_weight = 0.0

        for _, row in seed_movies.iterrows():

            seed_movie_id = int(row["movie_id"])
            rating = float(row["rating"])

            # Higher-rated seed movies receive more weight.
            weight = rating / 5.0
            total_seed_weight += weight

            similar_movies = self.recommend(
                movie_id=seed_movie_id,
                k=candidates_per_seed
            )

            for item in similar_movies:

                candidate_id = item["movie_id"]

                # Do not recommend movies the user has rated.
                if candidate_id in seen_movies:
                    continue

                weighted_score = (
                    item["similarity"] * weight
                )

                scores[candidate_id] = (
                    scores.get(candidate_id, 0.0)
                    + weighted_score
                )

        if not scores or total_seed_weight == 0:
            return []

        # Normalize scores and rank candidates.
        ranked_movies = [
            {
                "movie_id": movie_id,
                "similarity": score / total_seed_weight
            }
            for movie_id, score in scores.items()
        ]

        ranked_movies.sort(
            key=lambda item: item["similarity"],
            reverse=True
        )

        return ranked_movies[:k]

    
def evaluate_multi_seed_model(
    ratings: pd.DataFrame,
    k: int = 10,
    rating_threshold: float = 4.0,
    test_fraction: float = 0.2,
    seed_count: int = 5
):

    # Split ratings per user.
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

    # Train model only on training data.
    recommender = MovieRecommender()
    recommender.train(train_data)

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

        if not relevant_movies:
            continue

        if user_train.empty:
            continue

        # Generate recommendations from multiple liked movies.
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

