import requests

from modules import helpers


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
