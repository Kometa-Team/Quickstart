"""TMDb (The Movie Database) lookup helpers for the YAML validation flow.

These six small utilities used to live inline at module scope in
``quickstart.py`` (lines 3020-3195 on develop).  They are pure helpers --
no Flask app coupling, no global state -- so they belong in a focused
module instead of in the 7,000-line monolith.

The lone caller in ``quickstart.py`` is the
``/lookup_template_string_value`` route (``lookup_template_string_value``),
which uses these to verify TMDb IDs and IMDb IDs entered into YAML
config templates.  ``quickstart.py`` re-exports each helper under the
``_leading_underscore`` name it had before, so the route body and any
tests that reach in through ``qs_module._lookup_tmdb_*`` keep working
without changes.

External dependencies (kept):
    * ``requests`` -- HTTPS calls to the TMDb v3 API
    * ``modules.database`` -- read TMDb API key from the active config
    * ``flask.session`` -- pick the active config_name

This module is intentionally test-friendly: every TMDb HTTP call goes
through ``requests.get`` so callers can monkey-patch
``modules.tmdb_lookup.requests`` (or use ``responses`` / ``httpx-mock``)
without having to plumb through quickstart.
"""

from flask import session

import requests

from modules import database


def get_active_tmdb_api_key():
    """Return the TMDb API key for the currently-active config, or "" if none.

    Reads ``config_name`` from the Flask session, looks up the persisted
    ``tmdb`` section in the SQLite database, and digs out the API key
    under any of the keys we historically accept (``apikey``,
    ``api_key``, ``tmdb_apikey``, ``token``).
    """
    config_name = session.get("config_name")
    if not config_name:
        return ""
    try:
        _validated, _user_entered, stored = database.retrieve_section_data(config_name, "tmdb")
    except Exception:
        return ""
    if not isinstance(stored, dict):
        return ""
    tmdb_block = stored.get("tmdb", stored)
    if not isinstance(tmdb_block, dict):
        return ""
    api_key = tmdb_block.get("apikey") or tmdb_block.get("api_key") or tmdb_block.get("tmdb_apikey") or tmdb_block.get("token") or ""
    return str(api_key).strip()


def lookup_tmdb_by_imdb_id(imdb_id, media_type=""):
    """Resolve an IMDb ID to a TMDb movie or show via the ``/find`` endpoint.

    ``media_type`` is an optional hint (``"movie"`` or ``"show"``) used to
    pick the preferred result when TMDb returns matches in both buckets.
    """
    api_key = get_active_tmdb_api_key()
    if not api_key:
        return {"valid": False, "verified": False, "message": "TMDb is not configured for the active config."}

    try:
        response = requests.get(
            f"https://api.themoviedb.org/3/find/{imdb_id}",
            params={"api_key": api_key, "external_source": "imdb_id"},
            timeout=10,
        )
    except requests.RequestException as exc:
        return {"valid": False, "verified": False, "message": f"TMDb lookup failed: {exc}."}

    if response.status_code in {401, 403}:
        return {"valid": False, "verified": False, "message": "TMDb lookup could not be verified with the configured API key."}

    if response.status_code == 404:
        return {"valid": False, "verified": True, "message": "TMDb did not find a matching IMDb ID."}

    if response.status_code != 200:
        return {"valid": False, "verified": False, "message": f"TMDb lookup failed with status {response.status_code}."}

    payload = response.json() if response.content else {}
    movie_results = payload.get("movie_results") if isinstance(payload.get("movie_results"), list) else []
    tv_results = payload.get("tv_results") if isinstance(payload.get("tv_results"), list) else []

    preferred_media_type = str(media_type or "").strip().lower()
    ordered_results = []
    if preferred_media_type == "movie":
        ordered_results.extend(("movie", item) for item in movie_results)
        ordered_results.extend(("show", item) for item in tv_results)
    elif preferred_media_type == "show":
        ordered_results.extend(("show", item) for item in tv_results)
        ordered_results.extend(("movie", item) for item in movie_results)
    else:
        ordered_results.extend(("movie", item) for item in movie_results)
        ordered_results.extend(("show", item) for item in tv_results)

    for result_type, item in ordered_results:
        if not isinstance(item, dict):
            continue
        label = str(item.get("title") or item.get("name") or "").strip()
        if not label:
            continue
        tmdb_id = item.get("id")
        tmdb_suffix = f" (TMDb {tmdb_id})" if tmdb_id not in [None, ""] else ""
        media_label = "movie" if result_type == "movie" else "show"
        return {
            "valid": True,
            "verified": True,
            "label": label,
            "result_type": result_type,
            "message": f"TMDb {media_label}: {label}{tmdb_suffix}",
        }

    return {"valid": False, "verified": True, "message": "TMDb did not find a matching IMDb ID."}


def lookup_tmdb_external_ids(endpoint, tmdb_id, api_key):
    """Fetch the ``external_ids`` (IMDb, TVDb, etc.) for a given TMDb entry.

    Returns an empty dict on any failure -- callers are expected to treat
    the result as best-effort enrichment.
    """
    if endpoint not in {"movie", "tv"} or not tmdb_id or not api_key:
        return {}

    try:
        response = requests.get(
            f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}/external_ids",
            params={"api_key": api_key},
            timeout=10,
        )
    except requests.RequestException:
        return {}

    if response.status_code != 200:
        return {}

    payload = response.json() if response.content else {}
    return payload if isinstance(payload, dict) else {}


def lookup_tmdb_numeric_id(tmdb_id, media_type=""):
    """Resolve a numeric TMDb ID by trying movie / tv / collection / person endpoints.

    ``media_type`` is an optional hint to reorder the endpoint probe so a
    user-declared media type is tried first.
    """
    api_key = get_active_tmdb_api_key()
    if not api_key:
        return {"valid": False, "verified": False, "message": "TMDb is not configured for the active config."}

    preferred_media_type = str(media_type or "").strip().lower()
    endpoint_order = []
    if preferred_media_type == "movie":
        endpoint_order = [("movie", "movie"), ("tv", "show"), ("collection", "collection"), ("person", "person")]
    elif preferred_media_type == "show":
        endpoint_order = [("tv", "show"), ("movie", "movie"), ("collection", "collection"), ("person", "person")]
    else:
        endpoint_order = [("movie", "movie"), ("tv", "show"), ("collection", "collection"), ("person", "person")]

    for endpoint, result_type in endpoint_order:
        try:
            response = requests.get(
                f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}",
                params={"api_key": api_key},
                timeout=10,
            )
        except requests.RequestException as exc:
            return {"valid": False, "verified": False, "message": f"TMDb lookup failed: {exc}."}

        if response.status_code in {401, 403}:
            return {"valid": False, "verified": False, "message": "TMDb lookup could not be verified with the configured API key."}

        if response.status_code == 404:
            continue

        if response.status_code != 200:
            return {"valid": False, "verified": False, "message": f"TMDb lookup failed with status {response.status_code}."}

        payload = response.json() if response.content else {}
        label = str(payload.get("title") or payload.get("name") or "").strip()
        if not label:
            label = f"TMDb {result_type} {tmdb_id}"
        external_ids = lookup_tmdb_external_ids(endpoint, tmdb_id, api_key) if endpoint in {"movie", "tv"} else {}
        tvdb_id = external_ids.get("tvdb_id")
        id_suffix = f" (TMDb {tmdb_id})"
        if tvdb_id not in [None, "", 0, "0"]:
            id_suffix = f" (TMDb {tmdb_id}, TVDb {tvdb_id})"

        return {
            "valid": True,
            "verified": True,
            "label": label,
            "result_type": result_type,
            "tvdb_id": tvdb_id,
            "message": f"TMDb {result_type}: {label}{id_suffix}",
        }

    return {"valid": False, "verified": True, "message": "TMDb did not find a matching numeric ID."}


def normalize_tmdb_library_media_type(value):
    """Collapse Plex-style library media types into ``"movie"`` / ``"show"`` / pass-through."""
    normalized = str(value or "").strip().lower()
    if normalized in {"movie", "movies", "mov"}:
        return "movie"
    if normalized in {"show", "shows", "sho", "tv", "season", "seasons", "episode", "episodes"}:
        return "show"
    return normalized


def build_tmdb_library_type_warning(tmdb_message, tmdb_result_type, expected_media_type, value_label="ID"):
    """Compose a friendly warning when a TMDb result's media type clashes with the active library.

    Returns the empty string when the types agree or when either side is
    not a recognizable movie/show -- the caller can drop falsy returns
    without further checks.
    """
    resolved_type = normalize_tmdb_library_media_type(tmdb_result_type)
    expected_type = normalize_tmdb_library_media_type(expected_media_type)
    if not resolved_type or expected_type not in {"movie", "show"}:
        return ""
    if resolved_type == expected_type:
        return ""

    library_label = "movie library" if expected_type == "movie" else "show/season/episode library"
    readable_type = {
        "movie": "movie",
        "show": "show",
        "collection": "collection",
        "person": "person",
    }.get(resolved_type, resolved_type)
    return f"{tmdb_message}. This {value_label} resolves to a {readable_type}, but the active library is a {library_label}."
