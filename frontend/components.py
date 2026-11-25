"""Reusable visual components for MovieVerse pages."""

from collections.abc import Callable
from html import escape

import streamlit as st


def section(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="mv-section"><h2>{escape(title)}</h2>'
        f'<p>{escape(subtitle)}</p></div>',
        unsafe_allow_html=True,
    )


def empty(message: str) -> None:
    st.markdown(f'<div class="mv-empty">{escape(message)}</div>',
                unsafe_allow_html=True)


def stat(label: str, value: str) -> None:
    st.markdown(
        f'<div class="mv-stat"><div class="mv-stat-value">{escape(value)}</div>'
        f'<div class="mv-stat-label">{escape(label)}</div></div>',
        unsafe_allow_html=True,
    )


def movie_year(movie: dict) -> str:
    """Use the API year, with a title suffix as a display fallback."""
    year = movie.get("release_year")
    if isinstance(year, int):
        return str(year)
    title = movie.get("title", "")
    if isinstance(title, str) and len(title) >= 6 and title[-6:-5] == "(" and title[-1] == ")":
        candidate = title[-5:-1]
        if candidate.isdigit():
            return candidate
    return "Year unknown"


def poster(movie: dict) -> None:
    """Render a real poster when supplied, otherwise use neutral brand artwork."""
    title = str(movie.get("title") or "Movie")
    url = movie.get("poster_url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        inside = f'<img src="{escape(url, quote=True)}" alt="Poster for {escape(title, quote=True)}">'
    else:
        initial = next((character.upper() for character in title if character.isalpha()), "M")
        inside = (f'<div class="mv-poster-mark">MOVIEVERSE</div>'
                  f'<div class="mv-poster-initial">{escape(initial)}</div>'
                  f'<div class="mv-poster-bottom"></div>')
    st.markdown(f'<div class="mv-poster">{inside}</div>', unsafe_allow_html=True)


def movie_card(movie: dict, *, key: str, action: str | None = None,
               note: str | None = None) -> bool:
    """Render a compact movie card and return whether its action was clicked."""
    if not isinstance(movie, dict) or not isinstance(movie.get("title"), str):
        empty("This movie could not be displayed.")
        return False
    poster(movie)
    genres = movie.get("genres")
    first_genres = ", ".join(genres.split("|")[:2]) if isinstance(genres, str) else "Genres unknown"
    st.markdown(f'<div class="mv-card-title">{escape(movie["title"])}</div>'
                f'<div class="mv-card-meta">{escape(movie_year(movie))} · '
                f'{escape(first_genres)}</div>', unsafe_allow_html=True)
    if note:
        st.markdown(f'<div class="mv-card-note">{escape(note)}</div>', unsafe_allow_html=True)
    return st.button(action, key=key, use_container_width=True) if action else False


def movie_grid(movies: list[dict], *, key: str, action: str = "View details",
               note_for: Callable[[dict], str | None] | None = None) -> int | None:
    """Render a responsive grid and return the selected movie ID."""
    selected = None
    for start in range(0, len(movies), 4):
        for column, movie in zip(st.columns(4), movies[start:start + 4]):
            with column:
                movie_id = movie.get("movie_id") if isinstance(movie, dict) else None
                note = note_for(movie) if note_for and isinstance(movie, dict) else None
                if movie_card(movie, key=f"{key}_{movie_id}", action=action, note=note):
                    selected = movie_id
    return selected
