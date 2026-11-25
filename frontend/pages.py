"""Page flows for the cinematic MovieVerse Streamlit interface."""

import math

import pandas as pd
import streamlit as st

try:
    from frontend import api_client as api
    from frontend import components as ui
    from frontend.config import demo_user_id
except ModuleNotFoundError:
    import api_client as api
    import components as ui
    from config import demo_user_id


MOVIES = "/api/v1/movies"
ANALYTICS = "/api/v1/analytics"
WATCHLIST = "/api/v1/watchlist"
STATUSES = ("PLANNED", "WATCHING", "COMPLETED", "DROPPED")
PAGE_SIZE = 20


def fetch(path: str, params: dict | None = None) -> dict | None:
    """Fetch one API response with a visible loading indicator."""
    try:
        with st.spinner("Loading movies..."):
            data = api.get(path, params)
    except api.APIError as exc:
        st.error(str(exc))
        return None
    if not isinstance(data, dict):
        st.error("The API returned an unexpected response.")
        return None
    return data


def items(data: dict | None, field: str) -> list | None:
    if data is None:
        return None
    value = data.get(field)
    if not isinstance(value, list):
        st.error("The API returned an unexpected response.")
        return None
    return value


def navigate(page: str, **state) -> None:
    """Switch the radio page on the next rerun without changing a live widget."""
    st.session_state.update(state)
    st.session_state.pending_page = page
    st.rerun()


def rating_note(movie: dict) -> str | None:
    average = movie.get("average_rating")
    count = movie.get("rating_count")
    if isinstance(average, (int, float)) and isinstance(count, int):
        return f"★ {average:.2f} · {count:,} ratings"
    return None


def render_featured(title: str, endpoint: str, key: str) -> None:
    data = fetch(f"{ANALYTICS}/{endpoint}", {"limit": 8})
    movies = items(data, "movies")
    ui.section(title)
    if movies is None:
        return
    if not movies:
        ui.empty("No movies are available in this collection yet.")
        return
    selected = ui.movie_grid(movies[:8], key=key, note_for=rating_note)
    if selected is not None:
        navigate("Discover", selected_movie_id=selected)


def home() -> None:
    st.markdown(
        '<div class="mv-hero"><div class="mv-eyebrow">A universe of stories</div>'
        '<h1>Find your next favourite movie.</h1>'
        '<p>Explore the catalogue, follow the films you love, and uncover a great next watch.</p>'
        '</div>', unsafe_allow_html=True,
    )
    with st.form("hero_search"):
        search_col, button_col = st.columns((4, 1))
        query = search_col.text_input("Search for a movie", placeholder="Search movie titles...",
                                      label_visibility="collapsed")
        searched = button_col.form_submit_button("Discover movies", type="primary",
                                                 use_container_width=True)
    if searched:
        navigate("Discover", discover_query=query.strip(), discover_search_input=query.strip(),
                 discover_page=1)
    if st.button("Browse the catalogue", key="home_browse"):
        navigate("Discover")

    overview = fetch(f"{ANALYTICS}/overview")
    if overview and isinstance(overview.get("total_movies"), int):
        st.caption(f"Explore {overview['total_movies']:,} movies across the MovieVerse catalogue.")
    render_featured("Popular right now", "popular", "home_popular")
    render_featured("Top-rated favourites", "top-rated", "home_top")

    suggestions = fetch(f"{MOVIES}/", {"page": 1, "page_size": 8})
    movies = items(suggestions, "movies")
    ui.section("Start discovering", "A few titles from the catalogue")
    if movies:
        selected = ui.movie_grid(movies, key="home_discover")
        if selected is not None:
            navigate("Discover", selected_movie_id=selected)
    elif movies is not None:
        ui.empty("The catalogue is empty for now.")

    genres = items(fetch(f"{ANALYTICS}/genres"), "genres")
    ui.section("Explore by genre")
    if genres:
        for start in range(0, min(len(genres), 12), 4):
            for column, genre in zip(st.columns(4), genres[start:start + 4]):
                if not isinstance(genre, dict) or not isinstance(genre.get("genre"), str):
                    continue
                name = genre["genre"]
                if column.button(name, key=f"home_genre_{name}", use_container_width=True):
                    navigate("Discover", discover_genre=name, discover_page=1)
    elif genres is not None:
        ui.empty("Genres will appear when movies are available.")


def movie_details() -> None:
    movie_id = st.session_state.get("selected_movie_id")
    if movie_id is None:
        return
    st.divider()
    data = fetch(f"{MOVIES}/{movie_id}")
    if data is None or not isinstance(data.get("title"), str):
        return
    poster_col, detail_col = st.columns((1, 2))
    with poster_col:
        ui.poster(data)
    with detail_col:
        st.markdown('<div class="mv-eyebrow">Movie details</div>', unsafe_allow_html=True)
        st.header(data["title"])
        st.write(ui.movie_year(data))
        genres = data.get("genres")
        st.write(genres.replace("|", " · ") if isinstance(genres, str) else "Genres unknown")
        similar_col, save_col, close_col = st.columns(3)
        if similar_col.button("Find similar", key="detail_similar", type="primary"):
            navigate("For You", recommendation_seed=data, recommendation_result=None)
        if save_col.button("Add to watchlist", key="detail_save"):
            try:
                api.post(f"{WATCHLIST}/", {"user_id": demo_user_id(), "movie_id": movie_id,
                                          "status": "PLANNED"})
            except api.APIError as exc:
                st.error(str(exc))
            else:
                st.success("Added to your watchlist.")
        if close_col.button("Close", key="detail_close"):
            st.session_state.selected_movie_id = None
            st.rerun()


def discover() -> None:
    st.title("Discover")
    st.write("Find a film by name, or browse the catalogue at your own pace.")
    st.session_state.setdefault("discover_query", "")
    st.session_state.setdefault("discover_search_input", st.session_state.discover_query)
    st.session_state.setdefault("discover_page", 1)
    with st.form("discover_search_form"):
        search_col, button_col = st.columns((4, 1))
        search_col.text_input("Movie title", placeholder="Search movie titles...",
                              key="discover_search_input", label_visibility="collapsed")
        searched = button_col.form_submit_button("Search", type="primary",
                                                 use_container_width=True)
    if searched:
        st.session_state.discover_query = st.session_state.discover_search_input.strip()
        st.session_state.discover_page = 1
        st.session_state.selected_movie_id = None
    page = st.session_state.discover_page
    params = {"page": page, "page_size": PAGE_SIZE}
    endpoint = f"{MOVIES}/"
    if st.session_state.discover_query:
        endpoint = f"{MOVIES}/search"
        params["q"] = st.session_state.discover_query
    data = fetch(endpoint, params)
    movies = items(data, "movies")
    if movies is None:
        return
    total = data.get("total")
    if not isinstance(total, int):
        st.error("The API returned an unexpected response.")
        return
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    genres = items(fetch(f"{ANALYTICS}/genres"), "genres")
    genre_names = [entry["genre"] for entry in genres or []
                   if isinstance(entry, dict) and isinstance(entry.get("genre"), str)]
    genre_options = ["All genres", *genre_names]
    if st.session_state.get("discover_genre") not in genre_options:
        st.session_state.discover_genre = "All genres"
    filter_col, year_col = st.columns(2)
    genre = filter_col.selectbox("Genre on this page", genre_options, key="discover_genre")
    years = sorted({ui.movie_year(movie) for movie in movies
                    if isinstance(movie, dict) and ui.movie_year(movie) != "Year unknown"},
                   reverse=True)
    year = year_col.selectbox("Release year on this page", ["All years", *years])
    st.caption(f"{total:,} catalogue results · Page {page} of {total_pages}. "
               "Genre and year filters apply to the current page.")
    visible = [movie for movie in movies if isinstance(movie, dict)
               and (genre == "All genres" or genre in (movie.get("genres") or "").split("|"))
               and (year == "All years" or ui.movie_year(movie) == year)]
    if visible:
        selected = ui.movie_grid(visible, key=f"discover_{page}")
        if selected is not None:
            st.session_state.selected_movie_id = selected
            st.rerun()
    else:
        ui.empty("No movies match these filters on this page. Try another page or search.")
    previous, next_page = st.columns(2)
    if previous.button("← Previous", disabled=page <= 1, key="discover_previous"):
        st.session_state.discover_page = page - 1
        st.rerun()
    if next_page.button("Next →", disabled=page >= total_pages, key="discover_next"):
        st.session_state.discover_page = page + 1
        st.rerun()
    movie_details()


def search_movie_choices(prefix: str) -> list[dict] | None:
    """Search titles for the recommendation and watchlist pickers."""
    st.session_state.setdefault(f"{prefix}_query", "")
    with st.form(f"{prefix}_search_form"):
        query = st.text_input("Find a movie by title", key=f"{prefix}_search_input",
                              placeholder="Start with a movie title...")
        submitted = st.form_submit_button("Find movies", type="primary")
    if submitted:
        st.session_state[f"{prefix}_query"] = query.strip()
        if prefix == "recommend":
            st.session_state.recommendation_result = None
    active_query = st.session_state[f"{prefix}_query"]
    if not active_query:
        return []
    movies = items(fetch(f"{MOVIES}/search", {"q": active_query,
                                             "page": 1, "page_size": 20}), "movies")
    if movies == []:
        ui.empty("No titles match that search. Try another name.")
    return movies


def for_you() -> None:
    st.title("For You")
    st.write("Choose a movie you enjoy, and we’ll find similar titles using MovieVerse’s KNN model.")
    seed = st.session_state.get("recommendation_seed")
    if isinstance(seed, dict) and isinstance(seed.get("title"), str):
        st.caption(f"Current movie: {seed['title']}")
    movies = search_movie_choices("recommend")
    if movies:
        choices = {movie["movie_id"]: movie for movie in movies
                   if isinstance(movie, dict) and isinstance(movie.get("movie_id"), int)}
        if choices:
            chosen_id = st.selectbox("Choose a title", list(choices),
                                     format_func=lambda movie_id: choices[movie_id]["title"],
                                     key=f"recommend_choice_{st.session_state.recommend_query}")
            seed = choices[chosen_id]
    if not isinstance(seed, dict) or not isinstance(seed.get("movie_id"), int):
        ui.empty("Search for a movie above to start your recommendations.")
        return
    count = st.slider("How many similar movies?", 1, 20, 6, key="recommend_count")
    if st.button("Show similar movies", type="primary", key="recommend_submit"):
        st.session_state.recommendation_seed = seed
        st.session_state.recommendation_result = fetch(
            f"/api/v1/recommendations/similar/{seed['movie_id']}", {"k": count})
    result = st.session_state.get("recommendation_result")
    if result is None:
        return
    recommended = items(result, "recommendations")
    if recommended is None:
        return
    ui.section(f"Because you liked {result.get('title', seed['title'])}")
    if not recommended:
        ui.empty("We don’t have similar movies for this title yet. Try another one.")
        return
    selected = ui.movie_grid(
        recommended, key="similar", action="View movie",
        note_for=lambda movie: f"{movie['similarity']:.0%} similar"
        if isinstance(movie.get("similarity"), (int, float)) else None,
    )
    if selected is not None:
        navigate("Discover", selected_movie_id=selected)


def watchlist() -> None:
    st.title("My Watchlist")
    st.write("Keep your next watches together and track what you’ve finished.")
    if notice := st.session_state.pop("watchlist_notice", None):
        st.success(notice)
    user_id = demo_user_id()
    ui.section("Add a movie")
    choices = search_movie_choices("watchlist")
    if choices:
        by_id = {movie["movie_id"]: movie for movie in choices
                 if isinstance(movie, dict) and isinstance(movie.get("movie_id"), int)}
        if by_id:
            chosen_id = st.selectbox("Choose a title to save", list(by_id),
                                     format_func=lambda movie_id: by_id[movie_id]["title"],
                                     key=f"watchlist_choice_{st.session_state.watchlist_query}")
            initial_status = st.selectbox("Starting status", STATUSES,
                                          format_func=str.title, key="watchlist_start_status")
            if st.button("Add to watchlist", type="primary", key="watchlist_add"):
                try:
                    api.post(f"{WATCHLIST}/", {"user_id": user_id, "movie_id": chosen_id,
                                              "status": initial_status})
                except api.APIError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.watchlist_notice = "Movie added to your watchlist."
                    st.rerun()
    ui.section("Saved movies")
    st.session_state.setdefault("watchlist_page", 1)
    page = st.session_state.watchlist_page
    data = fetch(f"{WATCHLIST}/{user_id}", {"page": page, "page_size": PAGE_SIZE})
    movies = items(data, "watchlist")
    if movies is None:
        return
    total = data.get("total")
    if not isinstance(total, int):
        st.error("The API returned an unexpected response.")
        return
    if total > 0 and page > math.ceil(total / PAGE_SIZE):
        st.session_state.watchlist_page = max(1, math.ceil(total / PAGE_SIZE))
        st.rerun()
    st.caption(f"{total:,} saved movies · Page {page} of {max(1, math.ceil(total / PAGE_SIZE))}")
    st.caption("Status filters apply to this page of your watchlist.")
    status_filter = st.selectbox("Show", ("All", *STATUSES), format_func=str.title,
                                 key="watchlist_filter")
    visible = [movie for movie in movies if isinstance(movie, dict)
               and (status_filter == "All" or movie.get("status") == status_filter)]
    if not visible:
        ui.empty("No movies here yet. Search above to add one, or choose another status or page.")
    for start in range(0, len(visible), 4):
        for column, movie in zip(st.columns(4), visible[start:start + 4]):
            with column:
                movie_id = movie.get("movie_id")
                ui.movie_card(movie, key=f"saved_{movie_id}",
                              note=movie.get("status", "").title())
                current_status = movie.get("status")
                status = st.selectbox("Status", STATUSES,
                                      index=STATUSES.index(current_status)
                                      if current_status in STATUSES else 0,
                                      format_func=str.title,
                                      key=f"saved_status_{user_id}_{movie_id}")
                if st.button("Update status", key=f"saved_update_{movie_id}",
                             use_container_width=True):
                    try:
                        api.patch(f"{WATCHLIST}/{user_id}/{movie_id}", {"status": status})
                    except api.APIError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.watchlist_notice = "Watchlist updated."
                        st.rerun()
                if st.button("Remove", key=f"saved_remove_{movie_id}",
                             use_container_width=True):
                    try:
                        api.delete(f"{WATCHLIST}/{user_id}/{movie_id}")
                    except api.APIError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.watchlist_notice = "Movie removed from your watchlist."
                        st.rerun()
    previous, next_page = st.columns(2)
    if previous.button("← Previous", disabled=page <= 1, key="watchlist_previous"):
        st.session_state.watchlist_page = page - 1
        st.rerun()
    if next_page.button("Next →", disabled=page * PAGE_SIZE >= total,
                        key="watchlist_next"):
        st.session_state.watchlist_page = page + 1
        st.rerun()


def insights() -> None:
    st.title("Insights")
    st.write("A closer look at the films, ratings, and watchlists shaping MovieVerse.")
    overview = fetch(f"{ANALYTICS}/overview")
    if overview:
        fields = (("Films", "total_movies"), ("Members", "total_users"),
                  ("Ratings", "total_ratings"), ("Average score", "average_rating"))
        for column, (label, field) in zip(st.columns(4), fields):
            value = overview.get(field)
            if isinstance(value, (int, float)):
                display = f"{value:.2f} / 5" if field == "average_rating" else f"{value:,}"
            else:
                display = "—"
            with column:
                ui.stat(label, display)
    left, right = st.columns(2)
    with left:
        ui.section("Genres", "Films may appear in several genres")
        genres = items(fetch(f"{ANALYTICS}/genres"), "genres")
        if genres:
            frame = pd.DataFrame(genres)
            if {"genre", "movie_count"} <= set(frame.columns):
                st.bar_chart(frame.set_index("genre")["movie_count"])
            else:
                ui.empty("Genre data is unavailable.")
        elif genres is not None:
            ui.empty("No genre data yet.")
    with right:
        ui.section("Rating distribution")
        ratings = items(fetch(f"{ANALYTICS}/ratings"), "distribution")
        if ratings:
            frame = pd.DataFrame(ratings)
            if {"rating", "count"} <= set(frame.columns):
                st.bar_chart(frame.set_index("rating")["count"])
            else:
                ui.empty("Rating data is unavailable.")
        elif ratings is not None:
            ui.empty("No ratings yet.")
    left, right = st.columns(2)
    for column, label, endpoint in ((left, "Top-rated films", "top-rated"),
                                    (right, "Most-rated films", "popular")):
        with column:
            ui.section(label)
            movies = items(fetch(f"{ANALYTICS}/{endpoint}"), "movies")
            if movies:
                frame = pd.DataFrame(movies)
                if {"title", "average_rating", "rating_count"} <= set(frame.columns):
                    frame = frame[["title", "average_rating", "rating_count"]].copy()
                    frame.columns = ["Movie", "Average", "Ratings"]
                    frame["Average"] = frame["Average"].round(2)
                    st.dataframe(frame, hide_index=True, use_container_width=True)
                else:
                    ui.empty("This collection is unavailable.")
            elif movies is not None:
                ui.empty("No films qualify yet.")
    ui.section("Watchlist activity")
    data = fetch(f"{ANALYTICS}/watchlist")
    if data:
        first, second = st.columns(2)
        with first:
            ui.stat("Saved films", str(data.get("total_watchlist_items", 0)))
        with second:
            ui.stat("Members with watchlists", str(data.get("users_with_watchlist_items", 0)))
        statuses = items(data, "status_distribution")
        if statuses:
            frame = pd.DataFrame(statuses)
            if {"status", "count"} <= set(frame.columns):
                st.bar_chart(frame.set_index("status")["count"])
        elif statuses is not None:
            ui.empty("No watchlist activity yet.")
        most_added = items(data, "most_added_movies")
        if most_added:
            st.caption("Most saved films")
            frame = pd.DataFrame(most_added)
            if {"title", "watchlist_count"} <= set(frame.columns):
                frame = frame[["title", "watchlist_count"]]
                frame.columns = ["Movie", "Saves"]
                st.dataframe(frame, hide_index=True, use_container_width=True)
