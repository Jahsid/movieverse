"""HTTP client for the MovieVerse Streamlit application."""

import os
from typing import Any

import requests

API_BASE_URL = os.getenv("MOVIEVERSE_API_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_TIMEOUT = 10


class APIError(Exception):
    """A user-facing API error without transport or server internals."""


def request(method: str, path: str, *, params: dict | None = None,
            json: dict | None = None) -> dict[str, Any] | None:
    """Send one request and validate the expected JSON object response."""
    try:
        response = requests.request(method, f"{API_BASE_URL}{path}", params=params,
                                    json=json, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise APIError("Cannot reach the MovieVerse API. Start the backend and try again.") from exc
    if response.status_code >= 400:
        message = {
            400: "The request could not be processed.",
            404: "The requested user or movie was not found.",
            409: "This movie is already in the watchlist.",
            422: "Check the entered values and try again.",
            503: "The service is temporarily unavailable.",
        }.get(response.status_code, "The API could not complete the request.")
        raise APIError(message)
    if response.status_code == 204:
        return None
    try:
        data = response.json()
    except ValueError as exc:
        raise APIError("The API returned an unreadable response.") from exc
    if not isinstance(data, dict):
        raise APIError("The API returned an unexpected response.")
    return data


def get(path: str, params: dict | None = None) -> dict[str, Any]:
    return request("GET", path, params=params)


def post(path: str, payload: dict) -> dict[str, Any]:
    return request("POST", path, json=payload)


def patch(path: str, payload: dict) -> dict[str, Any]:
    return request("PATCH", path, json=payload)


def delete(path: str) -> None:
    request("DELETE", path)
