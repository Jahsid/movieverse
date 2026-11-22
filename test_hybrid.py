import pandas as pd

from app.recommender.hybrid import calculate_popularity_scores
from app.recommender.hybrid import normalize_scores

knn_scores = {
    1: 0.60,
    2: 0.75,
    3: 0.90
}

normalized = normalize_scores(knn_scores)

print("Original scores:", knn_scores)
print("Normalized scores:", normalized)

assert normalized[1] == 0.0
assert normalized[2] == 0.5
assert normalized[3] == 1.0

print("All tests passed!")


from app.recommender.hybrid import (
    normalize_scores,
    calculate_hybrid_scores
)

# Test 1: Normalization
scores = {1: 0.60, 2: 0.75, 3: 0.90}
normalized = normalize_scores(scores)

assert normalized[1] == 0.0
assert normalized[2] == 0.5
assert normalized[3] == 1.0

# Test 2: Hybrid scoring
knn_scores = {
    1: 0.90,
    2: 0.60,
    3: 0.30
}

content_scores = {
    1: 0.30,
    2: 0.95,
    3: 0.70
}

popularity_scores = {
    1: 0.80,
    2: 0.40,
    3: 1.00
}

hybrid = calculate_hybrid_scores(
    knn_scores,
    content_scores,
    popularity_scores
)

print("Hybrid recommendations:")

for movie_id, score in hybrid.items():
    print(f"Movie {movie_id}: {score:.4f}")

assert list(hybrid.keys())[0] == 1

assert abs(hybrid[1] - 0.6333) < 0.001
assert abs(hybrid[2] - 0.5500) < 0.001
assert abs(hybrid[3] - 0.3846) < 0.001

print("Hybrid scoring tests passed!")

print("All tests passed!")

sample_ratings = pd.DataFrame({
    "user_id": [1, 2, 3, 1, 2, 3],
    "movie_id": [101, 101, 101, 102, 102, 103],
    "rating": [5.0, 4.5, 3.0, 4.0, 5.0, 2.0]
})

popularity = calculate_popularity_scores(
    sample_ratings,
    rating_threshold=4.0
)

print("Popularity scores:", popularity)

assert popularity[101] == 2.0
assert popularity[102] == 2.0
assert 103 not in popularity

print("Popularity tests passed!")