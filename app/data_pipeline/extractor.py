
import pandas as pd


def extract_movies(file_path):

    movies = pd.read_csv(file_path)

    print(f"Extracted {len(movies)} movies")

    return movies


def extract_ratings(file_path):

    ratings = pd.read_csv(file_path)

    print(f"Extracted {len(ratings)} ratings")

    return ratings
