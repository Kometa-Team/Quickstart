from urllib.parse import parse_qs, urlparse

import pytest
import requests
from flask import Flask
from flask_session import Session
from cachelib.file import FileSystemCache

from blueprints import plex_auth_routes as auth
from modules import database, persistence


class PlexResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("provider response may contain secrets")

    def json(self):
        return self.data


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", SESSION_TYPE="cachelib", SESSION_CACHELIB=FileSystemCache(str(tmp_path / "sessions")), QS_DEBUG=False)
    Session(app)
    app.register_blueprint(auth.bp)
    monkeypatch.setattr(database, "get_database_path", lambda: str(tmp_path / "quickstart.sqlite"))
    client = app.test_client()
    with client.session_transaction() as session:
        session["config_name"] = "first"
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: PlexResponse({"id": 123, "code": "strong-code", "expiresIn": 60}))
    return client


def begin(client):
    response = client.post("/plex-auth/start", json={"config_name": "first"})
    assert response.status_code == 200
    return {"config_name": "first", "attempt_id": response.json["attempt_id"]}


def test_start_uses_strong_pin_and_stable_client_identifier(auth_client, monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return PlexResponse({"id": 123, "code": "code&with=special", "expiresIn": 60})

    monkeypatch.setattr(auth.requests, "post", post)
    response = auth_client.post("/plex-auth/start", json={"config_name": "first"})
    params = parse_qs(urlparse(response.json["auth_url"]).fragment.lstrip("?"))
    assert params["code"] == ["code&with=special"]
    assert params["context[device][product]"] == ["Kometa Quickstart"]
    assert calls[0][0] == "https://plex.tv/api/v2/pins"
    assert calls[0][1]["params"] == {"strong": "true"}
    assert calls[0][1]["timeout"] == 10
    assert calls[0][1]["allow_redirects"] is False
    assert params["clientID"] == [calls[0][1]["headers"]["X-Plex-Client-Identifier"]]
    for field, header in {
        "product": "Product",
        "version": "Version",
        "platform": "Platform",
        "platformVersion": "Platform-Version",
        "device": "Device",
        "deviceName": "Device-Name",
    }.items():
        assert params[f"context[device][{field}]"] == [calls[0][1]["headers"][f"X-Plex-{header}"]]
        assert params[f"context[device][{field}]"][0] not in ("", "undefined", "None")
    assert response.headers["Cache-Control"] == "no-store"
    auth_client.post("/plex-auth/start", json={"config_name": "first"})
    assert calls[0][1]["headers"] == calls[1][1]["headers"]
    with auth_client.session_transaction() as session:
        assert "code&with=special" not in str(session.get("plex_auth"))


def test_pending_pin_does_not_save_token(auth_client, monkeypatch):
    payload = begin(auth_client)
    monkeypatch.setattr(auth.requests, "get", lambda *args, **kwargs: PlexResponse({"authToken": None}))
    response = auth_client.post("/plex-auth/check", json=payload)
    assert response.json == {"authenticated": False}
    assert database.retrieve_section_data("first", "plex")[2] is None


def test_approval_after_ten_minutes_honors_provider_expiry(auth_client, monkeypatch):
    started = auth.time.time()
    monkeypatch.setattr(auth.time, "time", lambda: started)
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: PlexResponse({"id": 123, "code": "strong-code", "expiresIn": 1800}))
    response = auth_client.post("/plex-auth/start", json={"config_name": "first"})
    assert response.json["expires_in"] == 1800
    with auth_client.session_transaction() as sess:
        assert sess["plex_auth"]["expires_at"] == started + 1800
    monkeypatch.setattr(auth.time, "time", lambda: started + 601)
    monkeypatch.setattr(auth.requests, "get", lambda url, **kwargs: PlexResponse({"authToken": "approved-token"} if "/pins/" in url else {"username": "owner"}))
    response = auth_client.post("/plex-auth/check", json={"config_name": "first", "attempt_id": response.json["attempt_id"]})
    assert response.status_code == 200
    assert response.json["authenticated"] is True
    assert database.retrieve_section_data("first", "plex")[2]["plex"]["token"] == "approved-token"


def test_approved_token_is_verified_saved_and_retrievable_without_replacing_settings(auth_client, monkeypatch):
    database.save_section_data(
        "plex",
        True,
        True,
        {"plex": {"url": "http://plex:32400", "token": "old", "timeout": 90}, "validated": True, "validated_at": "old-date", "validation_status": "validated"},
        name="first",
    )
    database.save_section_data("plex", True, True, {"plex": {"token": "other"}}, name="second")
    payload = begin(auth_client)
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return PlexResponse({"authToken": "new-token"} if "/pins/" in url else {"username": "owner"})

    monkeypatch.setattr(auth.requests, "get", get)
    response = auth_client.post("/plex-auth/check", json=payload)
    assert response.json == {"authenticated": True, "token": "new-token", "username": "owner"}
    assert calls[1][0] == "https://plex.tv/api/v2/user"
    assert calls[1][1]["headers"]["X-Plex-Token"] == "new-token"
    validated, entered, data = database.retrieve_section_data("first", "plex")
    assert not validated and entered
    assert data["plex"] == {"url": "http://plex:32400", "token": "new-token", "timeout": 90}
    assert "validated_at" not in data and "validation_status" not in data
    assert database.retrieve_section_data("second", "plex")[2]["plex"]["token"] == "other"
    assert auth_client.post("/plex-auth/check", json=payload).json == response.json
    assert len(calls) == 2


def test_failed_user_verification_preserves_existing_token_and_redacts_errors(auth_client, monkeypatch):
    database.save_section_data("plex", True, True, {"plex": {"token": "old"}}, name="first")
    payload = begin(auth_client)
    monkeypatch.setattr(auth.requests, "get", lambda url, **kwargs: PlexResponse({"authToken": "secret-token"}) if "/pins/" in url else PlexResponse({}, 401))
    response = auth_client.post("/plex-auth/check", json=payload)
    assert response.status_code == 502
    assert "secret" not in response.get_data(as_text=True)
    assert database.retrieve_section_data("first", "plex")[2]["plex"]["token"] == "old"


def test_expiry_and_provider_expiry_stop_attempt(auth_client, monkeypatch):
    payload = begin(auth_client)
    with auth_client.session_transaction() as session:
        session["plex_auth"] = {**session["plex_auth"], "expires_at": 0}
    assert auth_client.post("/plex-auth/check", json=payload).status_code == 410
    payload = begin(auth_client)
    monkeypatch.setattr(auth.requests, "get", lambda *args, **kwargs: PlexResponse({}, 404))
    assert auth_client.post("/plex-auth/check", json=payload).status_code == 410
    assert auth_client.post("/plex-auth/check", json=payload).status_code == 409


def test_cancel_and_restart_reject_old_attempt_without_cancelling_new_one(auth_client):
    old = begin(auth_client)
    new = begin(auth_client)
    assert old != new
    auth_client.post("/plex-auth/cancel", json=old)
    assert auth_client.post("/plex-auth/check", json=old).status_code == 409
    with auth_client.session_transaction() as session:
        assert session["plex_auth"]["attempt_id"] == new["attempt_id"]
    auth_client.post("/plex-auth/cancel", json=new)
    assert auth_client.post("/plex-auth/check", json=new).status_code == 409


def test_attempt_is_bound_to_browser_and_config(auth_client):
    payload = begin(auth_client)
    other = auth_client.application.test_client()
    assert other.post("/plex-auth/check", json=payload).status_code == 409
    assert auth_client.post("/plex-auth/check", json={**payload, "config_name": "second"}).status_code == 409
    with auth_client.session_transaction() as session:
        session["config_name"] = "second"
    assert auth_client.post("/plex-auth/check", json=payload).status_code == 409
    assert auth_client.post("/plex-auth/start", json={"config_name": "first"}).status_code == 409
    assert database.retrieve_section_data("second", "plex")[2] is None


def test_provider_failure_and_malformed_pin_can_be_retried(auth_client, monkeypatch):
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: PlexResponse({}, 503))
    assert auth_client.post("/plex-auth/start", json={"config_name": "first"}).status_code == 502
    monkeypatch.setattr(auth.requests, "post", lambda *args, **kwargs: PlexResponse({"id": 123, "code": None}))
    assert auth_client.post("/plex-auth/start", json={"config_name": "first"}).status_code == 502


def test_routes_registered_in_quickstart(client):
    assert client.post("/plex-auth/start", json={}).status_code == 409


def test_first_token_save_uses_plex_defaults(auth_client):
    with auth_client.application.app_context():
        persistence.update_stored_plex_token("first", "approved")
    validated, entered, data = database.retrieve_section_data("first", "plex")
    assert not validated and entered
    assert data["plex"]["token"] == "approved"
    assert data["plex"]["timeout"]


@pytest.mark.parametrize("endpoint", ["servers", "connect"])
def test_server_discovery_routes_are_not_registered(auth_client, endpoint):
    assert auth_client.post(f"/plex-auth/{endpoint}", json=begin(auth_client)).status_code == 404
