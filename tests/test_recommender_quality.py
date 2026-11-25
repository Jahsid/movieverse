"""Small, deterministic tests for the three recommendation strategies."""

import pandas as pd
import pytest

from app.recommender.content_based import ContentBasedRecommender
from app.recommender.hybrid import calculate_hybrid_scores
from app.recommender.hybrid_service import recommend_hybrid_for_user
from app.recommender.model import MovieRecommender


@pytest.fixture
def ratings():
    return pd.DataFrame([
        (1, 1, 5.0), (2, 1, 4.0), (1, 2, 4.0), (2, 2, 5.0),
        (3, 2, 4.0), (3, 3, 5.0), (2, 3, 3.0),
    ], columns=["user_id", "movie_id", "rating"])


@pytest.fixture
def movies():
    return pd.DataFrame([
        (1, "One", "Drama|Comedy"), (2, "Two", "Drama"),
        (3, "Three", "Comedy"), (4, "Four", "Action"),
    ], columns=["movieId", "title", "genres"])


def test_knn_training_similar_and_sparse(ratings):
    model = MovieRecommender()
    with pytest.raises(ValueError):
        model.train(pd.DataFrame(columns=ratings.columns))
    model.train(ratings)
    assert model.is_trained
    assert model.recommend(999) == []
    assert model.recommend(1, k=10)
    assert all(item["movie_id"] != 1 for item in model.recommend(1, k=10))
    assert len(model.recommend(1, k=10)) == 2
    with pytest.raises(ValueError):
        model.recommend(1, k=0)
    one_movie = MovieRecommender()
    one_movie.train(ratings[ratings.movie_id == 1])
    assert one_movie.recommend(1) == []


def test_knn_user_excludes_seen_and_handles_no_candidates(ratings):
    model = MovieRecommender()
    model.train(ratings)
    user = ratings[ratings.user_id == 1]
    results = model.recommend_for_user(user, k=5)
    assert all(item["movie_id"] not in {1, 2} for item in results)
    assert len(results) <= 1
    assert model.recommend_for_user(ratings[ratings.user_id == 999]) == []
    assert model.recommend_for_user(ratings[ratings.user_id == 2]) == []


def test_content_based_similar_and_user(movies):
    model = ContentBasedRecommender()
    model.fit(movies)
    assert model.is_trained
    with pytest.raises(ValueError, match="not found"):
        model.recommend(999)
    assert len(model.recommend(1, k=10)) == 3
    assert all(item["movie_id"] != 1 for item in model.recommend(1, k=10))
    user = pd.DataFrame([{"movie_id": 1, "rating": 5.0}])
    results = model.recommend_for_user(user, candidate_movie_ids={1, 2}, k=5)
    assert [item["movie_id"] for item in results] == [2]
    assert model.recommend_for_user(user, candidate_movie_ids={1}) == []
    assert model.recommend_for_user(pd.DataFrame([{"movie_id": 1, "rating": 2.0}])) == []


def test_hybrid_excludes_seen_and_respects_candidates(ratings, movies):
    knn = MovieRecommender()
    knn.train(ratings)
    content = ContentBasedRecommender()
    content.fit(movies)
    user = ratings[ratings.user_id == 1]
    result = recommend_hybrid_for_user(knn, content, user,
                                       popularity_scores={1: 10, 3: 3, 4: 2},
                                       candidate_movie_ids={1, 3, 4}, k=10)
    assert result
    assert {item["movie_id"] for item in result} <= {3, 4}
    assert all(0 <= item["hybrid_score"] <= 1 for item in result)
    assert recommend_hybrid_for_user(knn, content, user, {},
                                     candidate_movie_ids={1, 2}) == []
    assert recommend_hybrid_for_user(knn, content, ratings[ratings.user_id == 999], {}) == []
    with pytest.raises(ValueError):
        calculate_hybrid_scores({}, {}, {}, knn_weight=-1)
