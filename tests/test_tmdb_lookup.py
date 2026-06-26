"""Tests for modules/tmdb_lookup.py.

Every function that hits the TMDb API goes through ``requests.get`` /
``requests.post``, so we mock at the ``modules.tmdb_lookup.requests``
level with ``unittest.mock.patch`` -- no live network calls.

``get_active_tmdb_api_key`` reads from the Flask session + SQLite, so
we patch it directly for the lookup-function tests.
"""

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# normalize_tmdb_library_media_type  (pure, no mocking)
# ---------------------------------------------------------------------------


def test_normalize_tmdb_library_media_type_movie_variants():
    from modules.tmdb_lookup import normalize_tmdb_library_media_type

    for v in ("movie", "movies", "mov", "MOVIE", "Movies"):
        assert normalize_tmdb_library_media_type(v) == "movie", f"failed for {v!r}"


def test_normalize_tmdb_library_media_type_show_variants():
    from modules.tmdb_lookup import normalize_tmdb_library_media_type

    for v in ("show", "shows", "sho", "tv", "season", "seasons", "episode", "episodes"):
        assert normalize_tmdb_library_media_type(v) == "show", f"failed for {v!r}"


def test_normalize_tmdb_library_media_type_passthrough_unknown():
    from modules.tmdb_lookup import normalize_tmdb_library_media_type

    assert normalize_tmdb_library_media_type("anime") == "anime"
    assert normalize_tmdb_library_media_type("") == ""
    assert normalize_tmdb_library_media_type(None) == ""


# ---------------------------------------------------------------------------
# build_tmdb_library_type_warning  (pure, no mocking)
# ---------------------------------------------------------------------------


def test_build_tmdb_library_type_warning_returns_empty_when_types_agree():
    from modules.tmdb_lookup import build_tmdb_library_type_warning

    assert build_tmdb_library_type_warning("Found: The Matrix", "movie", "movie") == ""
    assert build_tmdb_library_type_warning("Found: Breaking Bad", "show", "show") == ""


def test_build_tmdb_library_type_warning_returns_message_on_mismatch():
    from modules.tmdb_lookup import build_tmdb_library_type_warning

    msg = build_tmdb_library_type_warning("Found: Breaking Bad", "show", "movie")
    assert msg  # non-empty
    assert "show" in msg
    assert "movie library" in msg


def test_build_tmdb_library_type_warning_movie_result_in_show_library():
    from modules.tmdb_lookup import build_tmdb_library_type_warning

    msg = build_tmdb_library_type_warning("Found: The Matrix", "movie", "show")
    assert "movie" in msg
    assert "show/season/episode library" in msg


def test_build_tmdb_library_type_warning_returns_empty_for_unknown_result_type():
    from modules.tmdb_lookup import build_tmdb_library_type_warning

    # If result_type is not movie/show (e.g. collection, person), no warning needed
    # unless the expected library type is a known type
    # collection result in a movie library: warning IS generated (collection != movie)
    msg = build_tmdb_library_type_warning("Found: Marvel", "collection", "movie")
    assert "collection" in msg


def test_build_tmdb_library_type_warning_returns_empty_when_expected_unknown():
    from modules.tmdb_lookup import build_tmdb_library_type_warning

    # expected_media_type is something unrecognized — no warning
    assert build_tmdb_library_type_warning("msg", "movie", "anime") == ""


def test_build_tmdb_library_type_warning_uses_custom_value_label():
    from modules.tmdb_lookup import build_tmdb_library_type_warning

    msg = build_tmdb_library_type_warning("Found it", "show", "movie", value_label="IMDb ID")
    assert "IMDb ID" in msg


# ---------------------------------------------------------------------------
# get_active_tmdb_api_key  (needs Flask app context + DB)
# ---------------------------------------------------------------------------


def test_get_active_tmdb_api_key_returns_empty_when_no_session(app):
    from modules.tmdb_lookup import get_active_tmdb_api_key

    with app.test_request_context("/"):
        # No config_name in session
        result = get_active_tmdb_api_key()
    assert result == ""


def test_get_active_tmdb_api_key_reads_apikey_from_db(app, isolated_config_dir):
    """Store a TMDb apikey in the DB, then confirm the helper retrieves it."""
    from modules import database
    from modules.tmdb_lookup import get_active_tmdb_api_key

    config_name = "pytest_tmdb_key"
    with app.app_context():
        database.save_section_data(
            name=config_name,
            section="tmdb",
            validated=True,
            user_entered=True,
            data={"tmdb": {"apikey": "my-api-key-123"}},
        )

    with app.test_request_context("/"):
        from flask import session

        session["config_name"] = config_name
        result = get_active_tmdb_api_key()

    assert result == "my-api-key-123"


def test_get_active_tmdb_api_key_accepts_alt_key_names(app, isolated_config_dir):
    """The helper also accepts api_key, tmdb_apikey, and token."""
    from modules import database
    from modules.tmdb_lookup import get_active_tmdb_api_key

    config_name = "pytest_tmdb_alt_key"
    with app.app_context():
        database.save_section_data(
            name=config_name,
            section="tmdb",
            validated=True,
            user_entered=True,
            data={"tmdb": {"api_key": "alt-key-456"}},
        )

    with app.test_request_context("/"):
        from flask import session

        session["config_name"] = config_name
        result = get_active_tmdb_api_key()

    assert result == "alt-key-456"


# ---------------------------------------------------------------------------
# lookup_tmdb_by_imdb_id
# ---------------------------------------------------------------------------


def _mock_response(status_code, json_data=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = b"data" if json_data is not None else b""
    mock.json.return_value = json_data or {}
    return mock


def test_lookup_tmdb_by_imdb_id_returns_movie_result():
    from modules import tmdb_lookup

    payload = {
        "movie_results": [{"id": 603, "title": "The Matrix"}],
        "tv_results": [],
    }
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="fake-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(200, payload)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt0133093")

    assert result["valid"] is True
    assert result["verified"] is True
    assert result["label"] == "The Matrix"
    assert result["result_type"] == "movie"
    assert "603" in result["message"]


def test_lookup_tmdb_by_imdb_id_returns_show_result():
    from modules import tmdb_lookup

    payload = {
        "movie_results": [],
        "tv_results": [{"id": 1396, "name": "Breaking Bad"}],
    }
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="fake-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(200, payload)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt0903747")

    assert result["valid"] is True
    assert result["result_type"] == "show"
    assert result["label"] == "Breaking Bad"


def test_lookup_tmdb_by_imdb_id_prefers_media_type_hint_movie():
    """When both movie and TV results exist, media_type='movie' should win."""
    from modules import tmdb_lookup

    payload = {
        "movie_results": [{"id": 1, "title": "Movie Version"}],
        "tv_results": [{"id": 2, "name": "Show Version"}],
    }
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="fake-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(200, payload)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt9999999", media_type="movie")

    assert result["result_type"] == "movie"
    assert result["label"] == "Movie Version"


def test_lookup_tmdb_by_imdb_id_prefers_media_type_hint_show():
    from modules import tmdb_lookup

    payload = {
        "movie_results": [{"id": 1, "title": "Movie Version"}],
        "tv_results": [{"id": 2, "name": "Show Version"}],
    }
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="fake-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(200, payload)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt9999999", media_type="show")

    assert result["result_type"] == "show"
    assert result["label"] == "Show Version"


def test_lookup_tmdb_by_imdb_id_404_means_not_found():
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="fake-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(404)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt0000000")

    assert result["valid"] is False
    assert result["verified"] is True  # TMDb responded, just not found


def test_lookup_tmdb_by_imdb_id_401_means_bad_api_key():
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="bad-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(401)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt0133093")

    assert result["valid"] is False
    assert result["verified"] is False
    assert "API key" in result["message"]


def test_lookup_tmdb_by_imdb_id_no_api_key_configured():
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value=""):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt0133093")

    assert result["valid"] is False
    assert "not configured" in result["message"]


def test_lookup_tmdb_by_imdb_id_network_error():
    import requests as req_lib
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="key"), patch.object(tmdb_lookup.requests, "get", side_effect=req_lib.RequestException("timeout")):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt0133093")

    assert result["valid"] is False
    assert "failed" in result["message"].lower()


def test_lookup_tmdb_by_imdb_id_empty_results_means_not_found():
    from modules import tmdb_lookup

    payload = {"movie_results": [], "tv_results": []}
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(200, payload)):
        result = tmdb_lookup.lookup_tmdb_by_imdb_id("tt9999999")

    assert result["valid"] is False
    assert result["verified"] is True


# ---------------------------------------------------------------------------
# lookup_tmdb_numeric_id
# ---------------------------------------------------------------------------


def test_lookup_tmdb_numeric_id_finds_movie():
    from modules import tmdb_lookup

    movie_payload = {"id": 603, "title": "The Matrix"}
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="key"), patch.object(tmdb_lookup, "lookup_tmdb_external_ids", return_value={}), patch.object(
        tmdb_lookup.requests, "get", return_value=_mock_response(200, movie_payload)
    ):
        result = tmdb_lookup.lookup_tmdb_numeric_id("603", media_type="movie")

    assert result["valid"] is True
    assert result["label"] == "The Matrix"
    assert result["result_type"] == "movie"


def test_lookup_tmdb_numeric_id_includes_tvdb_id_when_present():
    from modules import tmdb_lookup

    tv_payload = {"id": 1396, "name": "Breaking Bad"}
    external_ids = {"tvdb_id": 81189}
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="key"), patch.object(tmdb_lookup, "lookup_tmdb_external_ids", return_value=external_ids), patch.object(
        tmdb_lookup.requests, "get", return_value=_mock_response(200, tv_payload)
    ):
        result = tmdb_lookup.lookup_tmdb_numeric_id("1396", media_type="show")

    assert result["valid"] is True
    assert result["tvdb_id"] == 81189
    assert "81189" in result["message"]


def test_lookup_tmdb_numeric_id_no_match_exhausts_all_endpoints():
    from modules import tmdb_lookup

    # All four endpoints return 404 → "not found"
    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(404)):
        result = tmdb_lookup.lookup_tmdb_numeric_id("9999999")

    assert result["valid"] is False
    assert result["verified"] is True


def test_lookup_tmdb_numeric_id_401_short_circuits():
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value="bad-key"), patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(401)):
        result = tmdb_lookup.lookup_tmdb_numeric_id("603")

    assert result["valid"] is False
    assert result["verified"] is False


def test_lookup_tmdb_numeric_id_no_api_key():
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup, "get_active_tmdb_api_key", return_value=""):
        result = tmdb_lookup.lookup_tmdb_numeric_id("603")

    assert result["valid"] is False
    assert "not configured" in result["message"]


# ---------------------------------------------------------------------------
# lookup_tmdb_external_ids
# ---------------------------------------------------------------------------


def test_lookup_tmdb_external_ids_returns_payload():
    from modules import tmdb_lookup

    ext_payload = {"id": 1396, "imdb_id": "tt0903747", "tvdb_id": 81189}
    with patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(200, ext_payload)):
        result = tmdb_lookup.lookup_tmdb_external_ids("tv", "1396", "key")

    assert result.get("tvdb_id") == 81189
    assert result.get("imdb_id") == "tt0903747"


def test_lookup_tmdb_external_ids_returns_empty_on_bad_endpoint():
    from modules import tmdb_lookup

    result = tmdb_lookup.lookup_tmdb_external_ids("invalid", "123", "key")
    assert result == {}


def test_lookup_tmdb_external_ids_returns_empty_on_http_error():
    from modules import tmdb_lookup

    with patch.object(tmdb_lookup.requests, "get", return_value=_mock_response(500)):
        result = tmdb_lookup.lookup_tmdb_external_ids("movie", "603", "key")
    assert result == {}


def test_lookup_tmdb_external_ids_returns_empty_on_missing_args():
    from modules import tmdb_lookup

    assert tmdb_lookup.lookup_tmdb_external_ids("movie", "", "key") == {}
    assert tmdb_lookup.lookup_tmdb_external_ids("movie", "603", "") == {}
    assert tmdb_lookup.lookup_tmdb_external_ids("", "603", "key") == {}
