from unittest.mock import Mock

import pytest
from dotenv import dotenv_values

from modules import helpers
from modules.helpers import _settings


@pytest.mark.parametrize(
    "config,expected_open",
    [
        ({}, True),
        ({"QS_AUTO_OPEN": True}, True),
        ({"QS_AUTO_OPEN": False}, False),
        ({"QS_AUTO_OPEN": True, "QS_SKIP_AUTO_OPEN": True}, False),
        ({"QS_AUTO_OPEN": False, "QS_SKIP_AUTO_OPEN": True}, False),
    ],
)
def test_browser_open_respects_preference_and_update_restart(monkeypatch, config, expected_open):
    browser_open = Mock()
    monkeypatch.setattr(_settings.webbrowser, "open", browser_open)
    helpers.auto_open_browser("http://localhost:7171", config)
    if expected_open:
        browser_open.assert_called_once_with("http://localhost:7171")
    else:
        browser_open.assert_not_called()


def test_browser_preference_is_saved_and_can_be_reenabled(client, app, isolated_config_dir, monkeypatch):
    monkeypatch.setitem(app.config, "QS_AUTO_OPEN", True)
    monkeypatch.setitem(app.config, "QS_SKIP_AUTO_OPEN", False)
    for enabled, stored in [(False, "0"), (True, "1")]:
        reply = client.post("/update-quickstart-settings", json={"auto_open": enabled})
        assert reply.status_code == 200
        assert reply.json["auto_open"] is enabled
        assert reply.json["restart"] is False
        assert app.config["QS_AUTO_OPEN"] is enabled
        assert dotenv_values(isolated_config_dir / ".env")["QS_AUTO_OPEN"] == stored
        assert client.get("/api/app-config").json["QS_AUTO_OPEN"] is enabled
        with app.app_context():
            assert f"# Quickstart Open Browser on Startup: {'Enabled' if enabled else 'Disabled'}" in helpers.get_quickstart_settings_summary()


def test_unchanged_or_omitted_browser_preference_does_not_write(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "QS_AUTO_OPEN", False)
    writes = Mock()
    monkeypatch.setattr(helpers, "update_env_variable", writes)
    for payload in [{"auto_open": False}, {}]:
        reply = client.post("/update-quickstart-settings", json=payload)
        assert reply.status_code == 200
        assert reply.json["auto_open"] is False
        assert reply.json["message"] == "No changes applied."
    writes.assert_not_called()


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, [], {}])
def test_browser_preference_rejects_invalid_values_without_saving(client, app, monkeypatch, value):
    monkeypatch.setitem(app.config, "QS_AUTO_OPEN", True)
    writes = Mock()
    monkeypatch.setattr(helpers, "update_env_variable", writes)
    reply = client.post("/update-quickstart-settings", json={"auto_open": value, "config_history": 5})
    assert reply.status_code == 400
    assert "Open browser on startup" in reply.json["message"]
    assert app.config["QS_AUTO_OPEN"] is True
    writes.assert_not_called()


def test_browser_preference_does_not_clear_update_suppression(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "QS_AUTO_OPEN", False)
    monkeypatch.setitem(app.config, "QS_SKIP_AUTO_OPEN", True)
    monkeypatch.setattr(helpers, "update_env_variable", Mock())
    browser_open = Mock()
    monkeypatch.setattr(_settings.webbrowser, "open", browser_open)
    assert client.post("/update-quickstart-settings", json={"auto_open": True}).json["auto_open"] is True
    helpers.auto_open_browser("http://localhost:7171", app.config)
    browser_open.assert_not_called()
