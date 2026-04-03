import os
import time
from pathlib import Path


class _FakeAnalyzer:
    def analyze_log_file(self, *args, **kwargs):
        return {
            "summary": {
                "run_key": "run-1",
                "finished_at": "2026-01-01T00:00:00Z",
                "run_complete": True,
            },
            "recommendations": [],
        }


def _write_log(kometa_root: Path, content: bytes):
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta.log"
    log_path.write_bytes(content)
    return log_path


def test_logscan_analyze_missing_log(client, isolated_config_dir):
    resp = client.get("/logscan/analyze")
    assert resp.status_code == 404
    payload = resp.get_json()
    assert "Log file not found" in payload["error"]


def test_logscan_analyze_caches_and_invalidates(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    _write_log(kometa_root, b"")

    qs_module.LOGSCAN_ANALYSIS_CACHE.update({"mtime": None, "size": None, "data": None})
    monkeypatch.setattr(qs_module.logscan, "LogscanAnalyzer", _FakeAnalyzer)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.database, "save_log_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(qs_module, "_archive_rotated_logs", lambda *_: None)
    monkeypatch.setattr(qs_module, "_logscan_needs_reingest", lambda *_: False)
    monkeypatch.setattr(qs_module, "_start_logscan_auto_reingest", lambda *_: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)

    resp1 = client.get("/logscan/analyze")
    assert resp1.status_code == 200
    assert resp1.get_json()["cached"] is False

    resp2 = client.get("/logscan/analyze")
    assert resp2.status_code == 200
    assert resp2.get_json()["cached"] is True

    # Grow log to invalidate cache
    time.sleep(1)
    _write_log(kometa_root, b"x" * 1024 * 1024)
    resp3 = client.get("/logscan/analyze")
    assert resp3.status_code == 200
    assert resp3.get_json()["cached"] is False


def test_logscan_analyze_malformed_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    _write_log(kometa_root, b"\xff\xfe\x00bad\n")

    qs_module.LOGSCAN_ANALYSIS_CACHE.update({"mtime": None, "size": None, "data": None})
    monkeypatch.setattr(qs_module.logscan, "LogscanAnalyzer", _FakeAnalyzer)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.database, "save_log_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(qs_module, "_archive_rotated_logs", lambda *_: None)
    monkeypatch.setattr(qs_module, "_logscan_needs_reingest", lambda *_: False)
    monkeypatch.setattr(qs_module, "_start_logscan_auto_reingest", lambda *_: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)

    resp = client.get("/logscan/analyze")
    assert resp.status_code == 200
    assert resp.get_json()["cached"] is False


def test_logscan_trends_empty(client, isolated_config_dir):
    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_runs"] == 0
    assert payload["runs"] == []


def test_logscan_progress_tracks_libraries(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta.log"
    log_path.write_text(
        "\n".join(
            [
                "[2026-04-01 01:13:24,670] [kometa.py:730] [INFO]     |================================== Mapping Movies Library ===================================|",
                "[2026-04-01 01:13:25,670] [kometa.py:730] [INFO]     |================================== Mapping TV Shows Library ===================================|",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return {
                "libraries": {
                    "mov-library_movies-library": "Movies",
                    "sho-library_tv_shows-library": "TV Shows",
                }
            }
        return {}

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    resp = client.get("/logscan/progress")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_count"] == 2
    statuses = {entry["name"]: entry["status"] for entry in payload["libraries"]}
    assert statuses["Movies"] == "Done"
    assert statuses["TV Shows"] == "In progress"
