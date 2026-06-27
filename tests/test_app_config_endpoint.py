"""Tests for blueprints.app_config_routes.

Covers the read-only ``GET /api/app-config`` endpoint that exposes the
11 app-level config keys to the front end (roadmap #1334 Step 5,
Phase A).

Two layers of testing here:

1. ``collect_app_config`` is tested directly via the app context so we
   can isolate the "which keys, with which fallbacks" contract from
   request handling. This is the layer the front-end migration PR
   (Phase B) will pin its expectations against.

2. The endpoint itself is tested via the Flask test client to confirm
   the route is wired and returns ``200 OK`` with the expected JSON
   shape.
"""

from __future__ import annotations

import pytest

from blueprints.app_config_routes import APP_CONFIG_KEYS, collect_app_config

# The exact 11 keys we expect, in declaration order. Pinning this
# explicitly catches accidental additions/removals in a code review.
EXPECTED_KEYS = (
    "QS_DEBUG",
    "QS_THEME",
    "QS_OPTIMIZE_DEFAULTS",
    "QS_CONFIG_HISTORY",
    "QS_KOMETA_LOG_KEEP",
    "QS_IMAGEMAID_LOG_KEEP",
    "QS_TEST_LIBS_PATH",
    "QS_TEST_LIBS_TMP",
    "QS_SESSION_LIFETIME_DAYS",
    "QS_FLASK_SESSION_DIR",
    "QS_RESTART_NOTICE",
)


def test_app_config_keys_constant_matches_expected_set():
    """The blueprint declares the canonical key list. The follow-up PR
    that deletes the matching ``<script>`` injections in
    ``templates/000-base.html`` will use this same constant as its
    source of truth, so locking it down here is load-bearing.
    """
    assert tuple(key for key, _ in APP_CONFIG_KEYS) == EXPECTED_KEYS


def test_collect_app_config_returns_dict_with_all_expected_keys(app):
    with app.app_context():
        result = collect_app_config()
    assert set(result.keys()) == set(EXPECTED_KEYS)


def test_collect_app_config_uses_fallback_when_key_missing(app, monkeypatch):
    # Force one key to be absent and confirm the declared fallback is
    # returned. We pop the key from a copy of app.config to keep the
    # session-scoped fixture intact.
    saved = {key: app.config.get(key) for key in EXPECTED_KEYS}
    monkeypatch.setitem(app.config, "QS_KOMETA_LOG_KEEP", None)
    app.config.pop("QS_KOMETA_LOG_KEEP", None)
    try:
        with app.app_context():
            result = collect_app_config()
        # APP_CONFIG_KEYS declares the fallback for QS_KOMETA_LOG_KEEP as 0.
        assert result["QS_KOMETA_LOG_KEEP"] == 0
    finally:
        # Restore so the session-scoped app fixture isn't polluted for
        # downstream tests.
        for key, value in saved.items():
            if value is None:
                app.config.pop(key, None)
            else:
                app.config[key] = value


def test_collect_app_config_returns_live_app_config(app, monkeypatch):
    monkeypatch.setitem(app.config, "QS_THEME", "test-theme-xyz")
    monkeypatch.setitem(app.config, "QS_KOMETA_LOG_KEEP", 42)
    with app.app_context():
        result = collect_app_config()
    assert result["QS_THEME"] == "test-theme-xyz"
    assert result["QS_KOMETA_LOG_KEEP"] == 42


def test_api_app_config_endpoint_returns_200(client):
    resp = client.get("/api/app-config")
    assert resp.status_code == 200
    assert resp.is_json


def test_api_app_config_endpoint_returns_all_expected_keys(client):
    resp = client.get("/api/app-config")
    data = resp.get_json()
    assert set(data.keys()) == set(EXPECTED_KEYS)


def test_api_app_config_endpoint_reflects_live_config_changes(app, client, monkeypatch):
    """Confirm there's no stale caching: each request reads ``app.config``
    afresh. This matters because the existing settings save flow mutates
    ``app.config`` in place and Phase B will rely on this endpoint
    returning the new values immediately.
    """
    monkeypatch.setitem(app.config, "QS_DEBUG", True)
    monkeypatch.setitem(app.config, "QS_THEME", "dracula")
    resp = client.get("/api/app-config")
    data = resp.get_json()
    assert data["QS_DEBUG"] is True
    assert data["QS_THEME"] == "dracula"


@pytest.mark.parametrize(
    ("key", "expected_default"),
    [
        ("QS_DEBUG", False),
        ("QS_THEME", "kometa"),
        ("QS_OPTIMIZE_DEFAULTS", True),
        ("QS_CONFIG_HISTORY", 0),
        ("QS_KOMETA_LOG_KEEP", 0),
        ("QS_IMAGEMAID_LOG_KEEP", 0),
        ("QS_TEST_LIBS_PATH", ""),
        ("QS_TEST_LIBS_TMP", ""),
        ("QS_SESSION_LIFETIME_DAYS", 30),
        ("QS_FLASK_SESSION_DIR", ""),
        ("QS_RESTART_NOTICE", None),
    ],
)
def test_app_config_keys_declared_defaults(key, expected_default):
    """Pin each fallback default so a refactor doesn't silently change
    the contract the front end will rely on.
    """
    declared = dict(APP_CONFIG_KEYS)
    assert declared[key] == expected_default
