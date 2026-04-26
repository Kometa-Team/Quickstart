import copy
from datetime import datetime
import gzip
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
    monkeypatch.setattr(qs_module, "_archive_finished_live_meta_log_if_idle", lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr(qs_module, "_archive_finished_live_meta_log_if_idle", lambda *_args, **_kwargs: None)
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
    assert payload["archive_storage"]["archived_bytes"] == 0
    assert payload["archive_storage"]["archived_files"] == 0
    assert payload["archive_storage"]["extra_archived_files"] == 0
    assert payload["archive_storage"]["retention_label"] == "Keep all archived logs"


def test_logscan_trends_includes_archive_storage_and_run_file_metadata(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-2026-04-23.log"
    extra_path = archive_dir / "meta-2026-04-22.log"
    log_bytes = b"archived log contents\n"
    extra_bytes = b"extra archived log\n"
    log_path.write_bytes(log_bytes)
    extra_path.write_bytes(extra_bytes)
    stats = log_path.stat()
    monkeypatch.setitem(qs_module.app.config, "QS_KOMETA_LOG_KEEP", 7)
    qs_module.database.save_log_run(
        {
            "run_key": "run-archive-1",
            "finished_at": "2026-04-23T10:00:00Z",
            "config_name": "demo",
            "created_at": "2026-04-23T10:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-archive-1", "run_complete": True}}},
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["archive_storage"]["archived_files"] == 1
    assert payload["archive_storage"]["archived_bytes"] == len(log_bytes)
    assert payload["archive_storage"]["extra_archived_files"] == 1
    assert payload["archive_storage"]["extra_archived_bytes"] == len(extra_bytes)
    assert payload["archive_storage"]["disk_archived_files"] == 2
    assert payload["archive_storage"]["retention_label"] == "Keep last 7 archived logs"
    assert payload["runs"][0]["log_location"] == "archive"
    assert payload["runs"][0]["log_available"] is True
    assert payload["runs"][0]["log_can_delete"] is True
    assert payload["runs"][0]["log_resolved_size"] == len(log_bytes)


def test_logscan_trends_returns_maintenance_summary_for_saved_runs(client, isolated_config_dir, qs_module):
    qs_module.database.save_log_run(
        {
            "run_key": "run-maint-1",
            "finished_at": "2026-04-23T10:00:00Z",
            "config_name": "demo",
            "created_at": "2026-04-23T10:00:00Z",
            "maintenance_summary": {
                "had_pause": True,
                "pause_count": 1,
                "pause_seconds": 300,
                "open_pause": False,
                "window": "01:00-02:00",
                "events": [],
            },
            "quiet_period_summary": {
                "longest_gap_seconds": 1200,
                "longest_gap_started_at": "2026-04-23T01:00:00",
                "longest_gap_ended_at": "2026-04-23T01:20:00",
                "gaps_over_300": 2,
                "gaps_over_900": 1,
                "gaps_over_1800": 0,
                "longest_gap_maintenance_overlap": "confirmed",
            },
        }
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    row = payload["runs"][0]
    assert row["maintenance_had_pause"] is True
    assert row["maintenance_summary"]["had_pause"] is True
    assert row["maintenance_summary"]["pause_count"] == 1
    assert row["maintenance_summary"]["pause_seconds"] == 300
    assert row["maintenance_summary"]["window"] == "01:00-02:00"
    assert row["quiet_period_summary"]["longest_gap_seconds"] == 1200
    assert row["quiet_period_summary"]["gaps_over_900"] == 1
    assert row["quiet_period_summary"]["longest_gap_maintenance_overlap"] == "confirmed"


def test_logscan_trends_does_not_bind_historical_run_to_live_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    live_path = log_dir / "meta.log"
    log_bytes = b"same sized log\n"
    live_path.write_bytes(log_bytes)
    stats = live_path.stat()
    qs_module.database.save_log_run(
        {
            "run_key": "run-historical-1",
            "finished_at": "2026-04-23T09:00:00Z",
            "config_name": "demo",
            "created_at": "2026-04-23T09:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: {"version": 1, "logs": {}})

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["runs"][0]["log_available"] is False
    assert payload["runs"][0]["log_location"] == "missing"


def test_logscan_trends_includes_incomplete_runs_in_table_payload(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    incomplete_path = archive_dir / "meta-20260423-120000Z-10.log"
    incomplete_path.write_text("incomplete log\n", encoding="utf-8")

    monkeypatch.setattr(
        qs_module,
        "_get_logscan_incomplete_runs",
        lambda limit=100, config_name=None: [
            {
                "run_key": "run-incomplete-1",
                "config_name": "demo",
                "created_at": "2026-04-23T12:00:00Z",
                "log_mtime": incomplete_path.stat().st_mtime,
                "log_size": incomplete_path.stat().st_size,
                "run_complete": False,
                "is_incomplete": True,
                "resume_reason": "Run appears incomplete.",
                "recommendations_count": 2,
            }
        ],
    )
    monkeypatch.setattr(
        qs_module, "_load_logscan_ingest_cache", lambda: {"version": 1, "logs": {str(incomplete_path.resolve()): {"run_key": "run-incomplete-1", "run_complete": False}}}
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_incomplete_runs"] == 1
    assert len(payload["incomplete_runs"]) == 1
    assert payload["incomplete_runs"][0]["is_incomplete"] is True
    assert payload["incomplete_runs"][0]["log_location"] == "archive"
    assert payload["incomplete_runs"][0]["log_can_delete"] is True
    assert payload["archive_storage"]["archived_files"] == 1


def test_logscan_trends_includes_incomplete_fallback_when_detailed_parse_fails(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    incomplete_path = archive_dir / "meta-fallback.log"
    incomplete_path.write_text("cannot parse this fully\n", encoding="utf-8")
    monkeypatch.setattr(qs_module, "_analyze_incomplete_log_for_resume", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(incomplete_path.resolve()): {
                    "run_key": "run-fallback-1",
                    "run_complete": False,
                    "mtime": incomplete_path.stat().st_mtime,
                    "size": incomplete_path.stat().st_size,
                }
            },
        },
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_incomplete_runs"] == 1
    assert payload["incomplete_runs"][0]["run_key"] == "run-fallback-1"
    assert payload["incomplete_runs"][0]["is_incomplete"] is True
    assert "preserved for investigation" in payload["incomplete_runs"][0]["resume_reason"].lower()


def test_logscan_trends_uses_cached_incomplete_summary_without_reparse(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    incomplete_path = archive_dir / "meta-cached.log"
    incomplete_path.write_text("cached incomplete\n", encoding="utf-8")
    monkeypatch.setattr(
        qs_module,
        "_analyze_incomplete_log_for_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not reparse cached incomplete entries")),
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(incomplete_path.resolve()): {
                    "run_key": "run-cached-1",
                    "run_complete": False,
                    "mtime": incomplete_path.stat().st_mtime,
                    "size": incomplete_path.stat().st_size,
                    "updated_at": "2026-04-23T22:00:00Z",
                    "summary": {
                        "run_key": "run-cached-1",
                        "finished_at": "2026-04-23T21:59:00Z",
                        "run_time_seconds": 123,
                        "config_name": "demo",
                        "run_command": "kometa.py --run --collections-only",
                        "command_signature": "--run --collections-only",
                        "log_counts": {"warning": 2, "error": 1},
                        "analysis_counts": {"playlist_errors": 1},
                    },
                    "recommendations": [{"first_line": "INFO - Run incomplete", "message": "Review the log"}],
                }
            },
        },
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_incomplete_runs"] == 1
    row = payload["incomplete_runs"][0]
    assert row["run_key"] == "run-cached-1"
    assert row["config_name"] == "demo"
    assert row["warning_count"] == 2
    assert row["error_count"] == 1
    assert row["recommendations_count"] == 1


def test_logscan_trends_recommendations_support_incomplete_run(client, isolated_config_dir, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.database, "get_log_run_recommendations", lambda run_key: [])
    monkeypatch.setattr(
        qs_module,
        "_get_logscan_incomplete_run",
        lambda run_key, config_name=None: {
            "run_key": run_key,
            "recommendations": [{"first_line": "INFO - Run incomplete", "summary": "Needs review"}],
        },
    )

    resp = client.get("/logscan/trends/recommendations?run_key=run-incomplete-1")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert len(payload["recommendations"]) == 1


def test_logscan_trends_log_delete_supports_incomplete_run_without_db(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-incomplete.log"
    log_path.write_text("delete incomplete\n", encoding="utf-8")
    monkeypatch.setattr(qs_module.database, "get_log_run", lambda run_key: None)
    monkeypatch.setattr(
        qs_module,
        "_get_logscan_incomplete_run",
        lambda run_key, config_name=None: {
            "run_key": run_key,
            "log_mtime": log_path.stat().st_mtime,
            "log_size": log_path.stat().st_size,
            "is_incomplete": True,
        },
    )
    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-incomplete-1", "run_complete": False}}})

    resp = client.post("/logscan/trends/log/delete", json={"run_key": "run-incomplete-1"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted_run"] is False
    assert not log_path.exists()


def test_logscan_trends_log_delete_supports_bulk_delete(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    first_log = archive_dir / "meta-bulk-1.log"
    second_log = archive_dir / "meta-bulk-2.log"
    first_log.write_text("bulk one\n", encoding="utf-8")
    second_log.write_text("bulk two\n", encoding="utf-8")
    first_stats = first_log.stat()
    second_epoch = int(first_stats.st_mtime) + 2
    os.utime(second_log, (second_epoch, second_epoch))

    run_map = {
        "bulk-run-1": {
            "run_key": "bulk-run-1",
            "log_mtime": first_log.stat().st_mtime,
            "log_size": first_log.stat().st_size,
            "config_name": "demo",
            "created_at": "2026-04-23T10:00:00Z",
        },
        "bulk-run-2": {
            "run_key": "bulk-run-2",
            "log_mtime": second_log.stat().st_mtime,
            "log_size": second_log.stat().st_size,
            "config_name": "demo",
            "created_at": "2026-04-23T10:05:00Z",
        },
    }
    deleted_run_keys = []

    monkeypatch.setattr(qs_module.database, "get_log_run", lambda run_key: run_map.get(run_key))
    monkeypatch.setattr(qs_module.database, "delete_log_run", lambda run_key: deleted_run_keys.append(run_key) or True)
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(first_log.resolve()): {"run_key": "bulk-run-1", "run_complete": True},
                str(second_log.resolve()): {"run_key": "bulk-run-2", "run_complete": True},
            },
        },
    )
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: None)

    resp = client.post("/logscan/trends/log/delete", json={"run_keys": ["bulk-run-1", "bulk-run-2"]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["deleted"] == 2
    assert payload["success"] is True
    assert set(deleted_run_keys) == {"bulk-run-1", "bulk-run-2"}
    assert not first_log.exists()
    assert not second_log.exists()


def test_logscan_trends_log_compress_supports_bulk_compress(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    first_log = archive_dir / "meta-bulk-1.log"
    second_log = archive_dir / "meta-bulk-2.log"
    first_log.write_text("bulk one\n", encoding="utf-8")
    second_log.write_text("bulk two\n", encoding="utf-8")

    run_map = {
        "bulk-run-1": {
            "run_key": "bulk-run-1",
            "log_mtime": first_log.stat().st_mtime,
            "log_size": first_log.stat().st_size,
            "config_name": "demo",
            "created_at": "2026-04-23T10:00:00Z",
        },
        "bulk-run-2": {
            "run_key": "bulk-run-2",
            "log_mtime": second_log.stat().st_mtime,
            "log_size": second_log.stat().st_size,
            "config_name": "demo",
            "created_at": "2026-04-23T10:05:00Z",
        },
    }
    saved_cache = {}
    cache = {
        "version": 1,
        "logs": {
            str(first_log.resolve()): {"run_key": "bulk-run-1", "run_complete": True},
            str(second_log.resolve()): {"run_key": "bulk-run-2", "run_complete": True},
        },
    }

    monkeypatch.setattr(qs_module.database, "get_log_run", lambda run_key: run_map.get(run_key))
    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: copy.deepcopy(cache))
    monkeypatch.setattr(
        qs_module,
        "_save_logscan_ingest_cache",
        lambda updated_cache: (
            saved_cache.__setitem__("cache", copy.deepcopy(updated_cache)),
            cache.clear(),
            cache.update(copy.deepcopy(updated_cache)),
        ),
    )

    resp = client.post("/logscan/trends/log/compress", json={"run_keys": ["bulk-run-1", "bulk-run-2"]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["compressed"] == 2
    assert payload["success"] is True
    assert not first_log.exists()
    assert not second_log.exists()
    compressed_paths = sorted(archive_dir.glob("*.log.gz"))
    assert len(compressed_paths) == 2
    for path in compressed_paths:
        assert str(path.resolve()) in saved_cache["cache"]["logs"]


def test_logscan_trends_log_download(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta-1.log"
    log_path.write_text("hello from meta log\n", encoding="utf-8")

    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-123", "run_complete": True}}},
    )

    resp = client.get("/logscan/trends/log?run_key=run-123")
    assert resp.status_code == 200
    assert resp.data.replace(b"\r\n", b"\n") == b"hello from meta log\n"


def test_logscan_trends_log_delete_removes_archived_log_and_run(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-delete-me.log"
    log_path.write_text("delete me\n", encoding="utf-8")
    stats = log_path.stat()
    qs_module.database.save_log_run(
        {
            "run_key": "run-delete-1",
            "finished_at": "2026-04-23T11:00:00Z",
            "config_name": "cleanup",
            "created_at": "2026-04-23T11:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-delete-1", "run_complete": True}}},
    )

    resp = client.post("/logscan/trends/log/delete", json={"run_key": "run-delete-1"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted_file"] is True
    assert not log_path.exists()
    assert qs_module.database.get_log_run("run-delete-1") is None


def test_logscan_trends_log_compress_compresses_archived_log_and_updates_cache(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-compress-me.log"
    log_path.write_text("compress me\n", encoding="utf-8")
    stats = log_path.stat()
    qs_module.database.save_log_run(
        {
            "run_key": "run-compress-1",
            "finished_at": "2026-04-23T11:00:00Z",
            "config_name": "cleanup",
            "created_at": "2026-04-23T11:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    saved_cache = {}
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-compress-1", "run_complete": True}}},
    )
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: saved_cache.__setitem__("cache", cache))

    resp = client.post("/logscan/trends/log/compress", json={"run_key": "run-compress-1"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["compressed_file"] is True
    compressed_path = Path(payload["compressed_path"])
    assert compressed_path.exists()
    assert not log_path.exists()
    with gzip.open(compressed_path, "rt", encoding="utf-8") as handle:
        assert handle.read() == "compress me\n"
    assert str(compressed_path.resolve()) in saved_cache["cache"]["logs"]
    assert str(log_path.resolve()) not in saved_cache["cache"]["logs"]


def test_logscan_trends_log_delete_rejects_live_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta.log"
    log_path.write_text("still live\n", encoding="utf-8")
    stats = log_path.stat()
    qs_module.database.save_log_run(
        {
            "run_key": "run-live-1",
            "finished_at": "2026-04-23T12:00:00Z",
            "config_name": "live",
            "created_at": "2026-04-23T12:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-live-1", "run_complete": True}}},
    )

    resp = client.post("/logscan/trends/log/delete", json={"run_key": "run-live-1"})
    assert resp.status_code == 409
    assert log_path.exists()
    assert qs_module.database.get_log_run("run-live-1") is not None


def test_archive_log_file_uses_canonical_timestamp_size_name(isolated_config_dir, qs_module):
    log_dir = isolated_config_dir / "kometa" / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta-3.log"
    log_path.write_bytes(b"abc123\n")
    fixed_epoch = 1766595600  # 2025-12-24T17:00:00Z
    os.utime(log_path, (fixed_epoch, fixed_epoch))

    archived = qs_module._archive_log_file(log_path, archive_dir, log_dir=log_dir)

    assert archived is not None
    assert archived.name == "meta-20251224-170000Z-7.log.gz"
    assert archived.exists()
    assert not log_path.exists()
    assert int(archived.stat().st_mtime) == fixed_epoch
    with gzip.open(archived, "rt", encoding="utf-8") as handle:
        assert handle.read() == "abc123\n"


def test_archive_finished_live_meta_log_if_idle_moves_live_file_and_cache(isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    live_path = log_dir / "meta.log"
    live_path.write_text("finished live run\n", encoding="utf-8")

    cache = {
        "version": 1,
        "logs": {
            str(live_path.resolve()): {
                "mtime": live_path.stat().st_mtime,
                "size": live_path.stat().st_size,
                "run_key": "run-live-finished-1",
                "run_complete": True,
                "updated_at": "2026-04-23T20:00:00Z",
            }
        },
    }
    saved = {}

    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: cache)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: saved.setdefault("cache", value))

    archived = qs_module._archive_finished_live_meta_log_if_idle(log_dir=log_dir)

    assert archived is not None
    assert archived.exists()
    assert archived.parent == archive_dir
    assert not live_path.exists()
    saved_cache = saved["cache"]
    assert str(live_path.resolve()) not in saved_cache["logs"]
    assert str(archived.resolve()) in saved_cache["logs"]
    assert saved_cache["logs"][str(archived.resolve())]["run_key"] == "run-live-finished-1"
    assert archived.suffixes[-2:] == [".log", ".gz"]


def test_classify_rotated_log_in_live_dir_as_archive(isolated_config_dir, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    rotated_path = log_dir / "meta-2.log"
    rotated_path.write_text("stale rotated log\n", encoding="utf-8")

    assert qs_module._classify_logscan_file_location(rotated_path, log_dir=log_dir) == "archive"
    assert qs_module._classify_logscan_file_location(log_dir / "meta.log", log_dir=log_dir) == "live"


def test_normalize_logscan_archive_filenames_renames_legacy_files_and_updates_cache(isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = archive_dir / "meta-1.log"
    legacy_path.write_bytes(b"legacy\n")
    fixed_epoch = 1766595600  # 2025-12-24T17:00:00Z
    os.utime(legacy_path, (fixed_epoch, fixed_epoch))
    cache = {"version": 1, "logs": {str(legacy_path.resolve()): {"run_key": "run-legacy", "run_complete": True}}}
    saved = {}

    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: cache)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: saved.setdefault("cache", value))

    result = qs_module._normalize_logscan_archive_filenames(archive_dir=archive_dir)

    assert result["renamed"] == 1
    renamed_path = archive_dir / "meta-20251224-170000Z-7.log"
    assert renamed_path.exists()
    assert not legacy_path.exists()
    saved_cache = saved["cache"]
    assert str(renamed_path.resolve()) in saved_cache["logs"]
    assert str(legacy_path.resolve()) not in saved_cache["logs"]


def test_logscan_trends_log_download_supports_gzip_archive(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-download.log.gz"
    with gzip.open(log_path, "wt", encoding="utf-8") as handle:
        handle.write("hello from compressed log\n")

    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-gz-download", "run_complete": True}}},
    )

    resp = client.get("/logscan/trends/log?run_key=run-gz-download")
    assert resp.status_code == 200
    assert resp.mimetype == "application/gzip"
    assert gzip.decompress(resp.data).replace(b"\r\n", b"\n") == b"hello from compressed log\n"


def test_logscan_trends_log_delete_removes_gzip_archived_log_and_run(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-delete-me.log.gz"
    with gzip.open(log_path, "wt", encoding="utf-8") as handle:
        handle.write("delete me compressed\n")
    stats = log_path.stat()
    qs_module.database.save_log_run(
        {
            "run_key": "run-delete-gz-1",
            "finished_at": "2026-04-23T11:00:00Z",
            "config_name": "cleanup",
            "created_at": "2026-04-23T11:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"version": 1, "logs": {str(log_path.resolve()): {"run_key": "run-delete-gz-1", "run_complete": True}}},
    )

    resp = client.post("/logscan/trends/log/delete", json={"run_key": "run-delete-gz-1"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted_file"] is True
    assert not log_path.exists()
    assert qs_module.database.get_log_run("run-delete-gz-1") is None


def test_prune_logscan_archive_counts_gzip_archives(isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    older = archive_dir / "meta-older.log.gz"
    newer = archive_dir / "meta-newer.log.gz"
    with gzip.open(older, "wt", encoding="utf-8") as handle:
        handle.write("older\n")
    with gzip.open(newer, "wt", encoding="utf-8") as handle:
        handle.write("newer\n")
    os.utime(older, (1766595600, 1766595600))
    os.utime(newer, (1766599200, 1766599200))
    monkeypatch.setitem(qs_module.app.config, "QS_KOMETA_LOG_KEEP", 1)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: None)

    removed = qs_module._prune_logscan_archive(archive_dir)

    assert removed == 1
    assert not older.exists()
    assert newer.exists()


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


def test_logscan_progress_cached_running_payload_keeps_live_elapsed(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta.log"
    log_path.write_text("still running\n", encoding="utf-8")
    stats = log_path.stat()

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: True)
    monkeypatch.setattr(qs_module, "_load_progress_config", lambda *_args, **_kwargs: {})

    started_at = "2026-04-24T21:00:00"
    phase_started_at = "2026-04-24T21:05:00"
    playlist_started_at = "2026-04-24T21:10:00"
    qs_module.LOGSCAN_PROGRESS_CACHE.update(
        {
            "mtime": stats.st_mtime,
            "size": stats.st_size,
            "data": {
                "current_library": "Movies",
                "phase_current": "collections",
                "phase_starts": {"Movies||collections": phase_started_at},
                "libraries": [{"name": "Movies", "type": "movie", "status": "In progress", "durations": {"collections": 12}}],
                "playlist_running": True,
                "playlist_started_at": playlist_started_at,
                "playlist_total_seconds": 5,
                "preparation_seconds": None,
                "preparation_elapsed_seconds": None,
                "run_started_at": started_at,
            },
        }
    )
    with qs_module.RUN_CONTEXT_LOCK:
        qs_module.RUN_CONTEXT["started_at"] = datetime.fromisoformat(started_at)
        qs_module.RUN_CONTEXT["selected_libraries"] = ["Movies"]
        qs_module.RUN_CONTEXT["config_path"] = None
        qs_module.RUN_CONTEXT["run_mode"] = "all"
        qs_module.RUN_CONTEXT["stop_requested_at"] = None

    class _FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = cls(2026, 4, 24, 21, 15, 0)
            if tz is not None:
                return fixed.replace(tzinfo=tz)
            return fixed

    monkeypatch.setattr(qs_module, "datetime", _FakeDateTime)

    resp = client.get("/logscan/progress")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["preparation_elapsed_seconds"] == 900
    assert payload["current_phase_elapsed_seconds"] == 612
    assert payload["playlist_elapsed_seconds"] == 305


def test_logscan_reingest_ingests_day_runtime_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta-1.log"
    log_path.write_text(
        "\n".join(
            [
                "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |====================================================================================================|",
                "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |                                            Finished Run                                            |",
                "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |                                       Version: 2.3.1-build4                                        |",
                "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |   Start Time: 07:16:22 2026-04-13     Finished: 09:36:53 2026-04-14     Run Time: 1 day, 2:20:31   |",
                "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |====================================================================================================|",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["ingested"] >= 1
    assert payload["skipped_incomplete"] == 0


def test_logscan_reingest_archives_incomplete_rotated_live_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta-2.log"
    log_path.write_text("incomplete rotated log\n", encoding="utf-8")
    saved = {}

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(
        qs_module.logscan.LogscanAnalyzer,
        "analyze_content",
        lambda self, *_args, **_kwargs: {
            "summary": {
                "run_key": "run-incomplete-rotated-1",
                "run_complete": False,
            },
            "recommendations": [],
        },
    )
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: saved.__setitem__("cache", copy.deepcopy(cache)))

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["skipped_incomplete"] == 1
    assert not log_path.exists()

    archived_paths = list(archive_dir.glob("*.log.gz"))
    assert len(archived_paths) == 1
    archived_path = archived_paths[0]
    assert archived_path.exists()

    saved_cache = saved["cache"]["logs"]
    assert str(log_path.resolve()) not in saved_cache
    assert str(archived_path.resolve()) in saved_cache
    assert saved_cache[str(archived_path.resolve())]["run_complete"] is False
    assert saved_cache[str(archived_path.resolve())]["run_key"] == "run-incomplete-rotated-1"


def test_logscan_reingest_ingests_gzip_archived_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-1.log.gz"
    with gzip.open(log_path, "wt", encoding="utf-8") as handle:
        handle.write(
            "\n".join(
                [
                    "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |====================================================================================================|",
                    "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |                                            Finished Run                                            |",
                    "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |                                       Version: 2.3.1-build4                                        |",
                    "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |   Start Time: 07:16:22 2026-04-13     Finished: 09:36:53 2026-04-14     Run Time: 1 day, 2:20:31   |",
                    "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |====================================================================================================|",
                ]
            )
        )

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["ingested"] >= 1
    assert payload["skipped_incomplete"] == 0
