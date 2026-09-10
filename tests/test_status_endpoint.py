from cachelib.file import FileSystemCache


def test_kometa_status_has_expected_fields(client):
    resp = client.get("/kometa-status")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in [
        "status",
        "maintenance_active",
        "maintenance_paused",
        "maintenance_window",
        "maintenance_paused_since",
        "queued_started_at",
        "window_unavailable",
        "window_unavailable_since",
        "pending_start",
        "pending_requested_at",
    ]:
        assert key in data


def test_kometa_status_healthcheck_does_not_create_session_files(tmp_path, app, monkeypatch, qs_module):
    session_dir = tmp_path / "flask_session"
    session_cache = FileSystemCache(cache_dir=str(session_dir), threshold=500, default_timeout=3600)
    monkeypatch.setattr(app.session_interface, "cache", session_cache)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: None)
    monkeypatch.setattr(qs_module, "_refresh_maintenance_window_availability", lambda **_: None)

    healthcheck_client = app.test_client(use_cookies=False)
    before_files = {path.relative_to(session_dir) for path in session_dir.rglob("*") if path.is_file()}
    responses = [healthcheck_client.get("/kometa-status", headers={"User-Agent": "Docker-Healthcheck"}) for _ in range(3)]
    after_files = {path.relative_to(session_dir) for path in session_dir.rglob("*") if path.is_file()}

    assert [resp.status_code for resp in responses] == [200, 200, 200]
    assert all("Set-Cookie" not in resp.headers for resp in responses)
    assert after_files == before_files
