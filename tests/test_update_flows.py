import requests

from modules import helpers


def test_cached_kometa_update_reuses_lookup(tmp_path, monkeypatch):
    root = tmp_path / "kometa"
    root.mkdir()
    (root / "VERSION").write_text("1.2.3", encoding="utf-8")

    helpers.invalidate_cached_kometa_update(root)
    calls = {"count": 0}

    def fake_remote(_branch):
        calls["count"] += 1
        return "1.2.4"

    monkeypatch.setattr(helpers, "detect_git_branch", lambda *_args, **_kwargs: "develop", raising=False)
    monkeypatch.setattr(helpers, "get_kometa_remote_version", fake_remote)

    first = helpers.get_cached_kometa_update(root)
    second = helpers.get_cached_kometa_update(root)

    assert first["update_available"] is True
    assert second["cached"] is True
    assert calls["count"] == 1


def test_update_quickstart_success(client, monkeypatch, qs_module):
    monkeypatch.setattr(
        helpers,
        "perform_quickstart_update",
        lambda *_args, **_kwargs: {"success": True, "log": ["ok"]},
    )

    resp = client.post("/update-quickstart", json={"branch": "master"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["branch"] == "master"


def test_update_quickstart_exception(client, monkeypatch):
    def raise_exc(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(helpers, "perform_quickstart_update", raise_exc)
    resp = client.post("/update-quickstart", json={"branch": "master"})
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["success"] is False


def test_check_quickstart_update_refreshes_cached_version(client, monkeypatch, qs_module):
    fake_info = {
        "local_version": "0.0.1",
        "remote_version": "9.9.9",
        "branch": "develop",
        "kometa_branch": "nightly",
        "update_available": True,
        "running_on": "Local-Windows",
        "file_ext": "",
    }
    monkeypatch.setattr(helpers, "check_for_update", lambda: fake_info)

    resp = client.post("/check-quickstart-update")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["version_info"] == fake_info
    assert qs_module.app.config["VERSION_CHECK"] == fake_info


def test_update_kometa_conflict_when_running(client, monkeypatch):
    monkeypatch.setattr(helpers, "is_kometa_running", lambda: True)
    monkeypatch.setattr(helpers, "get_kometa_pid", lambda: 1234)
    resp = client.post("/update-kometa", json={})
    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Kometa is currently running" in payload["error"]


def test_update_kometa_failure_result(client, monkeypatch, qs_module):
    monkeypatch.setattr(helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(helpers, "detect_git_branch", lambda *_: "master", raising=False)
    monkeypatch.setattr(
        helpers,
        "perform_kometa_update_zip_only",
        lambda *_args, **_kwargs: {"success": False, "log": ["fail"]},
    )

    resp = client.post("/update-kometa", json={"force": False})
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["success"] is False
    assert payload["kometa_branch"] == "master"


def test_check_kometa_update_not_installed_returns_install_needed(client, isolated_config_dir):
    kometa_root = isolated_config_dir / "kometa-missing"
    kometa_root.mkdir(parents=True, exist_ok=True)

    resp = client.post("/check-kometa-update", json={"path": str(kometa_root)})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["kometa_installed"] is False
    assert payload["update_check_completed"] is False
    assert payload["kometa_update_available"] is False


def test_check_kometa_update_installed_uses_cached_lookup(client, isolated_config_dir, monkeypatch):
    kometa_root = isolated_config_dir / "kometa-installed"
    kometa_root.mkdir(parents=True, exist_ok=True)
    (kometa_root / "kometa.py").write_text("# stub", encoding="utf-8")
    (kometa_root / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (kometa_root / "VERSION").write_text("1.0.0", encoding="utf-8")

    monkeypatch.setattr(helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(
        helpers,
        "get_cached_kometa_update",
        lambda *_args, **_kwargs: {
            "local_version": "1.0.0",
            "remote_version": "1.0.1",
            "update_available": True,
            "cached": True,
            "branch": "nightly",
        },
    )

    resp = client.post("/check-kometa-update", json={"path": str(kometa_root)})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["kometa_installed"] is True
    assert payload["update_check_completed"] is True
    assert payload["kometa_update_available"] is True
    assert payload["cached"] is True
    assert payload["local_version"] == "1.0.0"
    assert payload["remote_version"] == "1.0.1"


def test_update_kometa_invalidates_cached_update(client, monkeypatch, qs_module):
    monkeypatch.setattr(helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(helpers, "detect_git_branch", lambda *_: "develop", raising=False)
    monkeypatch.setattr(
        helpers,
        "perform_kometa_update_zip_only",
        lambda *_args, **_kwargs: {"success": True, "log": ["ok"], "up_to_date": False},
    )
    invalidated = {"path": None}
    monkeypatch.setattr(helpers, "invalidate_cached_kometa_update", lambda path=None: invalidated.__setitem__("path", path))

    resp = client.post("/update-kometa", json={"force": False})
    assert resp.status_code == 200
    assert invalidated["path"] == helpers.CONFIG_DIR


def test_get_upstream_sha_non_200(monkeypatch):
    class _Resp:
        status_code = 500

        def json(self):
            return {}

    monkeypatch.setattr(helpers.requests, "get", lambda *_args, **_kwargs: _Resp())
    logs = []
    sha = helpers._get_upstream_sha("nightly", logs)
    assert sha is None
    assert any("GitHub API" in line for line in logs)


def test_download_zip_timeout(monkeypatch):
    def raise_timeout(*_args, **_kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(helpers.requests, "get", raise_timeout)
    logs = []
    data = helpers._download_zip("nightly", logs)
    assert data is None
    assert any("Exception during ZIP download" in line for line in logs)


def test_extract_zip_bytes_invalid(isolated_config_dir):
    logs = []
    ok = helpers._extract_zip_bytes(b"not-a-zip", isolated_config_dir / "kometa", logs)
    assert ok is False
    assert any("Extraction failed" in line for line in logs)
