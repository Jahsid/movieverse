
from sqlalchemy import text
from app.database.connection import engine

queries = {
    "Movies": "SELECT COUNT(*) FROM movies",
    "Users": "SELECT COUNT(*) FROM users",
    "Ratings": "SELECT COUNT(*) FROM ratings",
    "Watchlist": "SELECT COUNT(*) FROM watchlist",
    "Ingestion Jobs": "SELECT COUNT(*) FROM ingestion_jobs",
}

with engine.connect() as connection:

    print("MOVIEVERSE DATABASE SUMMARY")

    for name, query in queries.items():
        count = connection.execute(text(query)).scalar()
        print(f"{name}: {count}")

    print("\nSAMPLE MOVIES")

    result = connection.execute(
        text("SELECT movie_id, title, genres FROM movies LIMIT 5")
    )

    for row in result:
        print(row)
