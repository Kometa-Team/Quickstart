"""Tests for blueprints/validation_routes.py.

Each validate_* route is a thin wrapper that:
  1. Optionally validates the URL field (gotify, ntfy, plex).
  2. Delegates to a ``modules.validations.*_server(data)`` function.
  3. Returns the result JSON, promoting the status code to 400 on failure.

We mock at the ``modules.validations`` level (not the requests level) so
we're testing the route contract rather than the network logic -- that's
covered separately in test_tmdb_lookup.py and similar.

Token-exchange routes (validate_trakt_token, validate_mal_token) do
their own HTTP work, so they get a slightly different treatment.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _ok_response(extra=None):
    """Build a Flask-style response mock that returns a success payload."""
    data = {"valid": True, "message": "OK", **(extra or {})}
    mock = MagicMock()
    mock.get_json.return_value = data
    return mock


def _err_response(message="Error"):
    data = {"valid": False, "message": message}
    mock = MagicMock()
    mock.get_json.return_value = data
    return mock


# ---------------------------------------------------------------------------
# Simple pass-through routes (mock modules.validations.*_server)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route,mock_fn,payload", [
    ("/validate_tautulli",   "validate_tautulli_server",   {"tautulli_url": "http://t", "apikey": "k"}),
    ("/validate_trakt",      "validate_trakt_server",      {"client_id": "id", "client_secret": "sec"}),
    ("/validate_mal",        "validate_mal_server",        {"client_id": "id", "client_secret": "sec"}),
    ("/validate_webhook",    "validate_webhook_server",    {"webhook_url": "http://hook"}),
])
def test_validate_passthrough_route_proxies_success(client, route, mock_fn, payload):
    with patch(f"modules.validations.{mock_fn}", return_value=_ok_response()):
        resp = client.post(route, json=payload)
    # The route returns whatever validations returns -- for success we accept 200 or 302
    assert resp.status_code in (200, 201, 302)


@pytest.mark.parametrize("route,mock_fn,payload", [
    ("/validate_tautulli",   "validate_tautulli_server",   {"tautulli_url": "http://t", "apikey": "k"}),
    ("/validate_trakt",      "validate_trakt_server",      {"client_id": "id", "client_secret": "sec"}),
])
def test_validate_passthrough_route_proxies_failure_payload(client, route, mock_fn, payload):
    with patch(f"modules.validations.{mock_fn}", return_value=_err_response("Service unreachable")):
        resp = client.post(route, json=payload)
    # Route should forward the error; status may vary (the simple wrappers just return the result)
    assert resp.status_code in (200, 400, 500)


# ---------------------------------------------------------------------------
# Routes that use result.get_json().get("valid") to choose status code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route,mock_fn,payload", [
    ("/validate_radarr",   "validate_radarr_server",   {"radarr_url": "http://r", "api_key": "k"}),
    ("/validate_sonarr",   "validate_sonarr_server",   {"sonarr_url": "http://s", "api_key": "k"}),
    ("/validate_omdb",     "validate_omdb_server",     {"apikey": "k"}),
    ("/validate_github",   "validate_github_server",   {"token": "t"}),
    ("/validate_tmdb",     "validate_tmdb_server",     {"apikey": "k"}),
    ("/validate_mdblist",  "validate_mdblist_server",  {"apikey": "k"}),
    ("/validate_notifiarr","validate_notifiarr_server",{"apikey": "k"}),
])
def test_validate_route_returns_200_on_success(client, route, mock_fn, payload):
    with patch(f"modules.validations.{mock_fn}", return_value=_ok_response()):
        resp = client.post(route, json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True


# radarr / sonarr unpack ``(response, status_code)`` tuples from the validator;
# the others call result.get_json() directly and hardcode 400 on failure.

@pytest.mark.parametrize("route,mock_fn,payload", [
    ("/validate_radarr",   "validate_radarr_server",   {"radarr_url": "http://r", "api_key": "k"}),
    ("/validate_sonarr",   "validate_sonarr_server",   {"sonarr_url": "http://s", "api_key": "k"}),
])
def test_validate_arr_route_returns_400_on_failure_via_tuple(client, route, mock_fn, payload):
    # These routes do: if isinstance(result, tuple): result, status_code = result
    # so we must return a tuple to get the 400 propagated.
    with patch(f"modules.validations.{mock_fn}", return_value=(_err_response("Bad credentials"), 400)):
        resp = client.post(route, json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["valid"] is False


@pytest.mark.parametrize("route,mock_fn,payload", [
    ("/validate_omdb",     "validate_omdb_server",     {"apikey": "k"}),
    ("/validate_github",   "validate_github_server",   {"token": "t"}),
    ("/validate_tmdb",     "validate_tmdb_server",     {"apikey": "k"}),
    ("/validate_mdblist",  "validate_mdblist_server",  {"apikey": "k"}),
    ("/validate_notifiarr","validate_notifiarr_server",{"apikey": "k"}),
])
def test_validate_simple_route_returns_400_on_failure(client, route, mock_fn, payload):
    # These routes call result.get_json() directly and hardcode status 400.
    with patch(f"modules.validations.{mock_fn}", return_value=_err_response("Bad credentials")):
        resp = client.post(route, json=payload)
    assert resp.status_code == 400
    assert resp.get_json()["valid"] is False


# ---------------------------------------------------------------------------
# URL-validation gates (gotify, ntfy)
# ---------------------------------------------------------------------------

def test_validate_gotify_rejects_bad_url(client):
    resp = client.post("/validate_gotify", json={"gotify_url": "not-a-url"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["valid"] is False


def test_validate_gotify_accepts_valid_url(client):
    with patch("modules.validations.validate_gotify_server", return_value=_ok_response()):
        resp = client.post("/validate_gotify", json={"gotify_url": "http://localhost:8080"})
    assert resp.status_code == 200


def test_validate_ntfy_rejects_bad_url(client):
    resp = client.post("/validate_ntfy", json={"ntfy_url": "not-a-url"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["valid"] is False


def test_validate_ntfy_accepts_valid_url(client):
    with patch("modules.validations.validate_ntfy_server", return_value=_ok_response()):
        resp = client.post("/validate_ntfy", json={"ntfy_url": "http://localhost:8080"})
    assert resp.status_code == 200


def test_validate_gotify_missing_url_returns_400(client):
    resp = client.post("/validate_gotify", json={})
    assert resp.status_code == 400


def test_validate_ntfy_missing_url_returns_400(client):
    resp = client.post("/validate_ntfy", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# validate_trakt_token -- token exchange flow
# ---------------------------------------------------------------------------

def test_validate_trakt_token_missing_access_and_client_id_returns_400(client):
    resp = client.post("/validate_trakt_token", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["valid"] is False
    assert "Missing" in data.get("error", "")


def test_validate_trakt_token_valid_access_token_returns_200(client):
    import blueprints.validation_routes as vr
    ok_resp = MagicMock()
    ok_resp.status_code = 200

    with patch.object(vr.requests, "get", return_value=ok_resp):
        resp = client.post("/validate_trakt_token", json={
            "access_token": "valid-token",
            "client_id": "my-client-id",
            "client_secret": "my-secret",
            "refresh_token": "refresh",
        })
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True


def test_validate_trakt_token_401_without_refresh_returns_400(client):
    import blueprints.validation_routes as vr
    err_resp = MagicMock()
    err_resp.status_code = 401

    with patch.object(vr.requests, "get", return_value=err_resp):
        resp = client.post("/validate_trakt_token", json={
            "access_token": "expired-token",
            "client_id": "my-client-id",
            # no refresh_token or client_secret -- refresh can't be attempted
        })
    assert resp.status_code == 400
    assert resp.get_json()["valid"] is False


def test_validate_trakt_token_network_error_returns_400(client):
    import blueprints.validation_routes as vr
    import requests as req_lib

    with patch.object(vr.requests, "get", side_effect=req_lib.exceptions.RequestException("timeout")):
        resp = client.post("/validate_trakt_token", json={
            "access_token": "token",
            "client_id": "id",
            "client_secret": "secret",
            "refresh_token": "refresh",
        })
    assert resp.status_code == 400
    assert resp.get_json()["valid"] is False


# ---------------------------------------------------------------------------
# validate_mal_token -- token check flow
# ---------------------------------------------------------------------------

def test_validate_mal_token_missing_access_token_returns_400(client):
    resp = client.post("/validate_mal_token", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["valid"] is False
    assert "Missing" in data.get("error", "")


def test_validate_mal_token_valid_token_returns_200(client):
    import blueprints.validation_routes as vr
    ok_resp = MagicMock()
    ok_resp.status_code = 200

    with patch.object(vr.requests, "get", return_value=ok_resp):
        resp = client.post("/validate_mal_token", json={"access_token": "valid-mal-token"})
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True


def test_validate_mal_token_401_returns_400(client):
    import blueprints.validation_routes as vr
    err_resp = MagicMock()
    err_resp.status_code = 401

    with patch.object(vr.requests, "get", return_value=err_resp):
        resp = client.post("/validate_mal_token", json={"access_token": "expired"})
    assert resp.status_code == 400
    assert resp.get_json()["valid"] is False


# ---------------------------------------------------------------------------
# validate_library_service_overrides
# ---------------------------------------------------------------------------

def test_validate_library_service_overrides_returns_json(client, isolated_config_dir):
    resp = client.post(
        "/validate_library_service_overrides/mov-library_movies",
        json={"config_name": "pytest_config"},
    )
    # Route exists and responds (validation result may vary, but should not 404/500)
    assert resp.status_code in (200, 400)
    assert resp.is_json
