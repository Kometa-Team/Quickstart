"""Regression tests for two bugs found during the test-matrix expansion.

Bug 1: ``database.reset_data()`` crashed with ``OperationalError: no such
table: section_data`` on a fresh SQLite file because it issued a DELETE
without first running ``CREATE TABLE IF NOT EXISTS``.  Every other helper
in modules/database.py creates the table before use; reset_data was the
sole exception.

Bug 2: ``blueprints/validation_routes.validate_github()`` crashed with
``AttributeError: 'tuple' object has no attribute 'get_json'`` whenever
``modules.validations.validate_github_server()`` returned a
``(jsonify(payload), 400)`` tuple (which it does on an invalid GitHub
token).  The route called ``result.get_json()`` directly without first
unpacking the tuple.  The radarr and sonarr routes already handled this
pattern with ``isinstance(result, tuple)``; the other five routes (omdb,
github, tmdb, mdblist, notifiarr) did not.  All seven now go through the
new ``_unpack_validation_result`` helper.
"""

import pytest
from unittest.mock import MagicMock, patch

# ===========================================================================
# Bug 1: database.reset_data() on a fresh SQLite file
# ===========================================================================


def test_reset_data_does_not_crash_on_empty_db(isolated_config_dir):
    """reset_data() must not raise on a db file that has never had tables created."""
    from modules import database

    # Do NOT call any other database helper first -- this must be the very
    # first operation on the fresh SQLite file in isolated_config_dir.
    database.reset_data("nonexistent_config")  # should not raise


def test_reset_data_section_does_not_crash_on_empty_db(isolated_config_dir):
    from modules import database

    database.reset_data("nonexistent_config", section="010-plex")  # should not raise


def test_reset_data_removes_existing_rows(isolated_config_dir):
    """reset_data() should delete the named config's rows after they've been saved."""
    from modules import database

    config_name = "bug1_test"
    database.save_section_data(
        name=config_name,
        section="plex",
        validated=True,
        user_entered=True,
        data={"plex": {"url": "http://localhost:32400"}},
    )
    _, _, pre = database.retrieve_section_data(config_name, "plex")
    assert pre is not None, "pre-condition: data should be saved"

    database.reset_data(config_name)

    _, _, post = database.retrieve_section_data(config_name, "plex")
    assert post is None, "data should be gone after reset_data()"


def test_reset_data_section_removes_only_named_section(isolated_config_dir):
    """reset_data(name, section=X) must not disturb other sections for the same config."""
    from modules import database

    config_name = "bug1_section_test"
    for section in ("plex", "tmdb"):
        database.save_section_data(
            name=config_name,
            section=section,
            validated=True,
            user_entered=True,
            data={section: {"key": "val"}},
        )

    database.reset_data(config_name, section="plex")

    _, _, plex_post = database.retrieve_section_data(config_name, "plex")
    _, _, tmdb_post = database.retrieve_section_data(config_name, "tmdb")
    assert plex_post is None, "plex section should be deleted"
    assert tmdb_post is not None, "tmdb section should be untouched"


# ===========================================================================
# Bug 2: validate_github route crashed when validator returns a tuple
# ===========================================================================


def _err_tuple(message="Error"):
    """Return the form validate_github_server uses on invalid-token: (jsonify({...}), 400)."""
    mock = MagicMock()
    mock.get_json.return_value = {"valid": False, "message": message}
    return mock, 400  # tuple -- the form that previously crashed the route


def _ok_response():
    mock = MagicMock()
    mock.get_json.return_value = {"valid": True, "message": "OK"}
    return mock


def test_validate_github_returns_400_when_validator_returns_tuple(client):
    """validate_github must not crash when validate_github_server returns a tuple."""
    with patch("modules.validations.validate_github_server", return_value=_err_tuple("Invalid GitHub token")):
        resp = client.post("/validate_github", json={"github_token": "bad-token"})
    # Before the fix this would 500; after the fix it must be 400.
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["valid"] is False


def test_validate_github_returns_200_on_plain_success(client):
    """Ensure the success path still works after the refactor."""
    with patch("modules.validations.validate_github_server", return_value=_ok_response()):
        resp = client.post("/validate_github", json={"github_token": "valid-token"})
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True


def test_validate_github_plain_error_still_returns_400(client):
    """If the validator returns a plain error response (no tuple), route still returns 400."""
    err_mock = MagicMock()
    err_mock.get_json.return_value = {"valid": False, "message": "network error"}
    with patch("modules.validations.validate_github_server", return_value=err_mock):
        resp = client.post("/validate_github", json={"github_token": "anything"})
    assert resp.status_code == 400


# ===========================================================================
# _unpack_validation_result helper -- unit tests
# ===========================================================================


def test_unpack_validation_result_handles_plain_response():
    from blueprints.validation_routes import _unpack_validation_result

    mock = MagicMock()
    result, code = _unpack_validation_result(mock)
    assert result is mock
    assert code is None  # sentinel: caller uses ``code or 400`` to get the fallback


def test_unpack_validation_result_handles_tuple():
    from blueprints.validation_routes import _unpack_validation_result

    mock = MagicMock()
    result, code = _unpack_validation_result((mock, 400))
    assert result is mock
    assert code == 400


def test_unpack_validation_result_coerces_status_to_int():
    from blueprints.validation_routes import _unpack_validation_result

    mock = MagicMock()
    _, code = _unpack_validation_result((mock, "400"))
    assert isinstance(code, int)
    assert code == 400


# ===========================================================================
# The other five routes that were hardened (omdb, tmdb, mdblist, notifiarr,
# radarr, sonarr) -- verify they all also survive a tuple return from their
# respective validator, confirming _unpack_validation_result is wired in.
# ===========================================================================


@pytest.mark.parametrize(
    "route,mock_fn,payload",
    [
        ("/validate_omdb", "validate_omdb_server", {"apikey": "k"}),
        ("/validate_tmdb", "validate_tmdb_server", {"apikey": "k"}),
        ("/validate_mdblist", "validate_mdblist_server", {"apikey": "k"}),
        ("/validate_notifiarr", "validate_notifiarr_server", {"apikey": "k"}),
        ("/validate_radarr", "validate_radarr_server", {"radarr_url": "http://r", "api_key": "k"}),
        ("/validate_sonarr", "validate_sonarr_server", {"sonarr_url": "http://s", "api_key": "k"}),
    ],
)
def test_validate_route_survives_tuple_return_from_validator(client, route, mock_fn, payload):
    """All seven routes must return 400 cleanly when the validator returns a tuple."""
    err = MagicMock()
    err.get_json.return_value = {"valid": False, "message": "fail"}
    with patch(f"modules.validations.{mock_fn}", return_value=(err, 400)):
        resp = client.post(route, json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["valid"] is False
