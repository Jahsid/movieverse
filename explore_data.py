import pandas as pd

movies = pd.read_csv("data/raw/movies.csv")
ratings = pd.read_csv("data/raw/ratings.csv")

print("MOVIES DATASET")
print(movies.head())

print("\nRATINGS DATASET")
print(ratings.head())

print("\nMOVIE INFORMATION")
print(movies.info())

print("\nRATINGS INFORMATION")
print(ratings.info())

print("\nMOVIE SHAPE")
print(movies.shape)

print("\nRATINGS SHAPE")
print(ratings.shape)

print("\nMISSING VALUES")
print(movies.isnull().sum())

print("\nDUPLICATE MOVIES")
print(movies.duplicated(subset=["movieId"]).sum())

print("\nRATING DISTRIBUTION")
print(ratings["rating"].value_counts().sort_index())