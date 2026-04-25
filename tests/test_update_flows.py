import io
import zipfile

import requests

from modules import helpers


def test_cached_kometa_update_reuses_lookup(tmp_path, monkeypatch):
    root = tmp_path / "kometa"
    root.mkdir()
    (root / "VERSION").write_text("1.2.3", encoding="utf-8")
    (root / ".kometa_sha").write_text("localsha", encoding="utf-8")
    (root / ".kometa_branch").write_text("nightly", encoding="utf-8")

    helpers.invalidate_cached_kometa_update(root)
    calls = {"count": 0}

    def fake_remote(_branch):
        calls["count"] += 1
        return "1.2.4"

    monkeypatch.setattr(helpers, "detect_git_branch", lambda *_args, **_kwargs: "develop", raising=False)
    monkeypatch.setattr(helpers, "get_kometa_remote_version", fake_remote)
    monkeypatch.setattr(helpers, "get_kometa_remote_sha", lambda _branch: "remotesha")

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
    assert any("Remote VERSION source" in line for line in payload["log"])
    assert any("Using cached Kometa update lookup." in line for line in payload["log"])


def test_check_kometa_update_branch_override_uses_selected_branch(client, isolated_config_dir, monkeypatch):
    kometa_root = isolated_config_dir / "kometa-override"
    kometa_root.mkdir(parents=True, exist_ok=True)
    (kometa_root / "kometa.py").write_text("# stub", encoding="utf-8")
    (kometa_root / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (kometa_root / "VERSION").write_text("1.0.0", encoding="utf-8")

    monkeypatch.setattr(helpers, "is_kometa_running", lambda: False)
    captured = {"branch_override": None}

    def fake_cached(_root, force_refresh=False, branch_override=None):
        captured["branch_override"] = branch_override
        return {
            "local_version": "1.0.0",
            "local_branch": "nightly",
            "local_sha": "abc123nightly",
            "remote_version": "1.1.0-develop5",
            "remote_sha": "def456develop",
            "update_available": True,
            "cached": False,
            "branch": "develop",
            "comparison_basis": "sha",
        }

    monkeypatch.setattr(helpers, "get_cached_kometa_update", fake_cached)

    resp = client.post("/check-kometa-update", json={"path": str(kometa_root), "branch_override": "develop"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert captured["branch_override"] == "develop"
    assert any("Kometa branch override selected: develop" in line for line in payload["log"])
    assert any("/develop/VERSION" in line for line in payload["log"])
    assert any("Local Kometa SHA" in line for line in payload["log"])
    assert any("Remote Kometa SHA" in line for line in payload["log"])


def test_check_kometa_update_detects_sha_difference_even_when_versions_match(monkeypatch, tmp_path):
    root = tmp_path / "kometa"
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text("2.3.1", encoding="utf-8")
    (root / ".kometa_sha").write_text("mastersha", encoding="utf-8")
    (root / ".kometa_branch").write_text("master", encoding="utf-8")

    monkeypatch.setattr(helpers, "get_kometa_remote_version", lambda _branch: "2.3.1")
    monkeypatch.setattr(helpers, "get_kometa_remote_sha", lambda _branch: "developsha")

    result = helpers.check_kometa_update(root, branch_override="develop")
    assert result["update_available"] is True
    assert result["comparison_basis"] == "sha"
    assert result["local_branch"] == "master"
    assert result["branch"] == "develop"
    assert result["local_sha"] == "mastersha"
    assert result["remote_sha"] == "developsha"


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


def test_update_kometa_branch_override_uses_selected_branch(client, monkeypatch, qs_module):
    monkeypatch.setattr(helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(helpers, "detect_git_branch", lambda *_: "master", raising=False)
    captured = {"branch": None}

    def fake_update(_config_root, branch="nightly", force=False):
        captured["branch"] = branch
        return {"success": True, "log": ["ok"], "up_to_date": False}

    monkeypatch.setattr(helpers, "perform_kometa_update_zip_only", fake_update)

    resp = client.post("/update-kometa", json={"branch_override": "develop", "force": False})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["kometa_branch"] == "develop"
    assert captured["branch"] == "develop"
    assert any("Kometa branch override selected: develop" in line for line in payload["log"])


def test_get_upstream_sha_non_200(monkeypatch):
    class _Resp:
        status_code = 500

        def json(self):
            return {}

    monkeypatch.setattr(helpers.requests, "get", lambda *_args, **_kwargs: _Resp())
    logs = []
    sha = helpers._get_upstream_sha("nightly", logs)
    assert sha is None
    assert any("Resolving upstream SHA from:" in line for line in logs)
    assert any("GitHub API" in line for line in logs)


def test_download_zip_timeout(monkeypatch):
    def raise_timeout(*_args, **_kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(helpers.requests, "get", raise_timeout)
    logs = []
    data = helpers._download_zip("nightly", logs)
    assert data is None
    assert any("Downloading nightly.zip from:" in line for line in logs)
    assert any("Exception during ZIP download" in line for line in logs)


def test_extract_zip_bytes_invalid(isolated_config_dir):
    logs = []
    ok = helpers._extract_zip_bytes(b"not-a-zip", isolated_config_dir / "kometa", logs)
    assert ok is False
    assert any("Extraction failed" in line for line in logs)


def test_extract_zip_bytes_replaces_existing_contents(isolated_config_dir):
    dest_dir = isolated_config_dir / "kometa"
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "old.txt").write_text("stale", encoding="utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Kometa-develop/VERSION", "9.9.9-develop1")
        zf.writestr("Kometa-develop/kometa.py", "# stub")

    logs = []
    ok = helpers._extract_zip_bytes(buf.getvalue(), dest_dir, logs)

    assert ok is True
    assert not (dest_dir / "old.txt").exists()
    assert (dest_dir / "VERSION").read_text(encoding="utf-8").strip() == "9.9.9-develop1"
    assert any("Removing existing Kometa contents" in line for line in logs)
    assert any("Extracted VERSION file: 9.9.9-develop1" in line for line in logs)


def test_perform_kometa_update_zip_only_writes_branch_metadata(tmp_path, monkeypatch):
    config_root = tmp_path / "config"
    kometa_dir = config_root / "kometa"
    kometa_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(helpers, "_get_upstream_sha", lambda branch, logs: "sha123")
    monkeypatch.setattr(helpers, "_download_zip", lambda branch, logs: b"zip-bytes")
    monkeypatch.setattr(helpers, "_extract_zip_bytes", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(helpers, "_backup_kometa_runtime_assets", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(helpers, "_restore_kometa_runtime_assets", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(helpers, "_cleanup_kometa_backup", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(helpers, "_ensure_venv", lambda *_args, **_kwargs: (kometa_dir / "python", kometa_dir / "pip"))
    monkeypatch.setattr(helpers, "_pip_install", lambda *_args, **_kwargs: True)

    result = helpers.perform_kometa_update_zip_only(config_root, branch="develop", force=False)
    assert result["success"] is True
    assert (kometa_dir / ".kometa_sha").read_text(encoding="utf-8").strip() == "sha123"
    assert (kometa_dir / ".kometa_branch").read_text(encoding="utf-8").strip() == "develop"
