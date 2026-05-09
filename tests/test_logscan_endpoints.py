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
    assert payload["archive_storage"]["retention_label"] == "Kometa: Keep all archived logs | ImageMaid: Keep all archived logs"
    assert payload["archive_storage"]["kometa_retention_label"] == "Keep all archived logs"
    assert payload["archive_storage"]["imagemaid_retention_label"] == "Keep all archived logs"


def test_logscan_trends_limit_all_returns_all_saved_runs(client, isolated_config_dir, qs_module):
    for idx in range(3):
        timestamp = f"2026-04-2{idx}T10:00:00Z"
        qs_module.database.save_log_run(
            {
                "run_key": f"run-all-{idx}",
                "finished_at": timestamp,
                "config_name": "demo",
                "created_at": timestamp,
            }
        )

    resp = client.get("/logscan/trends?limit=all")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert len(payload["runs"]) == 3
    assert payload["total_runs"] == 3


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
    monkeypatch.setitem(qs_module.app.config, "QS_IMAGEMAID_LOG_KEEP", 3)
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
    assert payload["archive_storage"]["retention_label"] == "Kometa: Keep last 7 archived logs | ImageMaid: Keep last 3 archived logs"
    assert payload["archive_storage"]["kometa_keep_limit"] == 7
    assert payload["archive_storage"]["imagemaid_keep_limit"] == 3
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
                "longest_gap_start_line": 1842,
                "longest_gap_end_line": 1843,
                "longest_gap_last_line": "[2026-04-23 01:00:00,000] [operations.py:100] [INFO] | Working before gap |",
                "longest_gap_first_line": "[2026-04-23 01:20:00,000] [operations.py:101] [INFO] | Working after gap |",
                "gaps_over_300": 2,
                "gaps_over_900": 1,
                "gaps_over_1800": 0,
                "longest_gap_maintenance_overlap": "confirmed",
                "longest_unexplained_gap_seconds": 420,
                "longest_unexplained_gap_started_at": "2026-04-23T03:10:00",
                "longest_unexplained_gap_ended_at": "2026-04-23T03:17:00",
                "longest_unexplained_gap_start_line": 2110,
                "longest_unexplained_gap_end_line": 2111,
                "longest_unexplained_gap_last_line": "[2026-04-23 03:10:00,000] [operations.py:200] [INFO] | Before unexplained gap |",
                "longest_unexplained_gap_first_line": "[2026-04-23 03:17:00,000] [operations.py:201] [INFO] | After unexplained gap |",
                "longest_unexplained_gap_maintenance_overlap": "none",
                "confirmed_maintenance_gaps_over_300": 1,
                "unexplained_gaps_over_300": 1,
                "notable_gaps": [],
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
    assert row["quiet_period_summary"]["longest_gap_start_line"] == 1842
    assert row["quiet_period_summary"]["longest_gap_end_line"] == 1843
    assert row["quiet_period_summary"]["longest_unexplained_gap_seconds"] == 420
    assert row["quiet_period_summary"]["confirmed_maintenance_gaps_over_300"] == 1
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
                    "resume_progress_snapshot": {
                        "columns": [{"key": "collections", "label": "Collections"}],
                        "rows": [{"name": "Movies", "type": "movie", "status": "Done", "phase_cells": [{"label": "4m 11s", "tone": "primary"}]}],
                    },
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
    assert row["progress_snapshot"]["rows"][0]["name"] == "Movies"


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
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
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


def test_logscan_trends_log_compress_compresses_imagemaid_archive_in_place(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "imagemaid"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "imagemaid-compress-me.log"
    log_path.write_text("compress imagemaid\n", encoding="utf-8")
    stats = log_path.stat()
    qs_module.database.save_log_run(
        {
            "run_key": "run-imagemaid-compress-1",
            "tool_name": "imagemaid",
            "finished_at": "2026-04-23T11:00:00Z",
            "config_name": "imagemaid",
            "created_at": "2026-04-23T11:00:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
        }
    )
    saved_cache = {}
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(log_path.resolve()): {
                    "run_key": "run-imagemaid-compress-1",
                    "tool_name": "imagemaid",
                    "run_complete": True,
                }
            },
        },
    )
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: saved_cache.__setitem__("cache", copy.deepcopy(cache)))

    resp = client.post("/logscan/trends/log/compress", json={"run_key": "run-imagemaid-compress-1"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["compressed_file"] is True
    compressed_path = Path(payload["compressed_path"])
    assert compressed_path.exists()
    assert compressed_path.parent == archive_dir
    assert not log_path.exists()
    with gzip.open(compressed_path, "rt", encoding="utf-8") as handle:
        assert handle.read() == "compress imagemaid\n"
    assert str(compressed_path.resolve()) in saved_cache["cache"]["logs"]
    assert saved_cache["cache"]["logs"][str(compressed_path.resolve())]["tool_name"] == "imagemaid"
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
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
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
    legacy_archive_dir = isolated_config_dir / "cache" / "logscan" / "archive"
    archive_dir = legacy_archive_dir / "kometa"
    legacy_archive_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = legacy_archive_dir / "meta-1.log"
    legacy_path.write_bytes(b"legacy\n")
    fixed_epoch = 1766595600  # 2025-12-24T17:00:00Z
    os.utime(legacy_path, (fixed_epoch, fixed_epoch))
    cache = {"version": 1, "logs": {str(legacy_path.resolve()): {"run_key": "run-legacy", "run_complete": True}}}
    saved = {}

    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: cache)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: saved.setdefault("cache", value))

    result = qs_module._normalize_logscan_archive_filenames()

    assert result["renamed"] == 1
    renamed_path = archive_dir / "meta-20251224-170000Z-7.log.gz"
    assert renamed_path.exists()
    assert not legacy_path.exists()
    saved_cache = saved["cache"]
    assert str(renamed_path.resolve()) in saved_cache["logs"]
    assert str(legacy_path.resolve()) not in saved_cache["logs"]


def test_normalize_logscan_archive_filenames_removes_archived_maintenance_sidecar(isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
    archive_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = archive_dir / "meta.quickstart-maintenance.log"
    sidecar_path.write_text("sidecar marker\n", encoding="utf-8")
    cache = {"version": 1, "logs": {str(sidecar_path.resolve()): {"run_key": "run-sidecar", "run_complete": False}}}
    saved = {}

    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: cache)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: saved.setdefault("cache", value))

    result = qs_module._normalize_logscan_archive_filenames()

    assert result["renamed"] == 1
    assert not sidecar_path.exists()


def test_normalize_logscan_archive_filenames_collapses_repeated_kometa_archive_stem(isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
    archive_dir.mkdir(parents=True, exist_ok=True)
    bad_path = archive_dir / "meta-20260411-170312z-425057-log-20260411-170312z-23892.log.gz"
    with gzip.open(bad_path, "wt", encoding="utf-8") as handle:
        handle.write("legacy repeated archive name\n")
    fixed_epoch = 1766595600  # 2025-12-24T17:00:00Z
    os.utime(bad_path, (fixed_epoch, fixed_epoch))
    cache = {"version": 1, "logs": {str(bad_path.resolve()): {"run_key": "run-repeat", "run_complete": True}}}
    saved = {}

    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: cache)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: saved.setdefault("cache", value))

    result = qs_module._normalize_logscan_archive_filenames()

    assert result["renamed"] == 1
    renamed_matches = list(archive_dir.glob("meta-20251224-170000Z-*.log.gz"))
    assert len(renamed_matches) == 1
    renamed_path = renamed_matches[0]
    assert renamed_path.name.count("20251224-170000Z") == 1
    assert not bad_path.exists()
    saved_cache = saved["cache"]
    assert str(renamed_path.resolve()) in saved_cache["logs"]
    assert str(bad_path.resolve()) not in saved_cache["logs"]


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


def test_prune_logscan_archive_uses_imagemaid_keep_limit(isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "imagemaid"
    archive_dir.mkdir(parents=True, exist_ok=True)
    older = archive_dir / "imagemaid-older.log.gz"
    newer = archive_dir / "imagemaid-newer.log.gz"
    with gzip.open(older, "wt", encoding="utf-8") as handle:
        handle.write("older\n")
    with gzip.open(newer, "wt", encoding="utf-8") as handle:
        handle.write("newer\n")
    os.utime(older, (1766595600, 1766595600))
    os.utime(newer, (1766599200, 1766599200))
    monkeypatch.setitem(qs_module.app.config, "QS_KOMETA_LOG_KEEP", 0)
    monkeypatch.setitem(qs_module.app.config, "QS_IMAGEMAID_LOG_KEEP", 1)
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
                "[Quickstart] Run marker: started=2026-04-13T07:16:22Z config=demo quickstart=1.0.0 branch=develop maintenance_markers=1 start_mode=recovery",
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
    runs = qs_module.database.get_log_runs(limit=10)
    assert runs
    assert runs[0]["start_mode"] == "recovery"


def test_logscan_reingest_archives_incomplete_rotated_live_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
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


def test_logscan_reingest_ingests_imagemaid_log(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "imagemaid.log"
    log_path.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-04-28T20:13:55Z config=demo tool=imagemaid mode=report",
                "[2026-04-28 20:13:56,001] [imagemaid.py:93]           [DEBUG]    | --photo-transcoder (PHOTO_TRANSCODER): True                                                         |",
                "| Running in Report Mode with Empty Trash, Clean Bundles, Optimize DB, and PhotoTrancoder set to True |",
                "[2026-04-28 20:16:58,010] [imagemaid.py:214]          [WARNING]  | Example warning before finish                                                                       |",
                "[2026-04-28 20:16:59,010] [imagemaid.py:214]          [CRITICAL] | Example critical before finish                                                                      |",
                "[2026-04-28 20:17:00,274] [imagemaid.py:453]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-28 20:17:00,275] [imagemaid.py:453]          [INFO]     | Total Runtime      | 0:03:05                                                                       |",
                "[2026-04-28 20:17:00,275] [imagemaid.py:453]          [INFO]     |====================================================================================================|",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["ingested"] >= 1

    runs = qs_module.database.get_log_runs(limit=10)
    imagemaid_runs = [run for run in runs if run.get("tool_name") == "imagemaid"]
    assert imagemaid_runs
    assert imagemaid_runs[0]["kometa_version"] == qs_module.helpers.get_imagemaid_local_version()
    assert imagemaid_runs[0]["debug_count"] == 1
    assert imagemaid_runs[0]["info_count"] == 3
    assert imagemaid_runs[0]["warning_count"] == 1
    assert imagemaid_runs[0]["critical_count"] == 1


def test_logscan_reingest_archives_completed_imagemaid_live_log(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "imagemaid"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "imagemaid.log"
    log_path.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-04-28T20:13:55Z config=demo tool=imagemaid mode=restore",
                "[2026-04-28 20:17:00,274] [imagemaid.py:453]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-28 20:17:00,275] [imagemaid.py:453]          [INFO]     | Total Runtime      | 0:03:05                                                                       |",
            ]
        ),
        encoding="utf-8",
    )
    saved = {}

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: saved.__setitem__("cache", copy.deepcopy(cache)))

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert not log_path.exists()

    archived_paths = list(archive_dir.glob("imagemaid-*.log.gz"))
    assert len(archived_paths) == 1
    saved_cache = saved["cache"]["logs"]
    assert str(archived_paths[0].resolve()) in saved_cache
    assert saved_cache[str(archived_paths[0].resolve())]["tool_name"] == "imagemaid"


def test_logscan_reingest_ingests_imagemaid_runtime_log_with_parsed_details(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = log_dir / "imagemaid.log"
    runtime_log.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-04-29T00:32:44.827109 config=demo tool=imagemaid mode=report",
                "|     Version: 1.1.1 (Python 3.12.1)                                                                 |",
                "| Run Command: C:\\Quickstart\\config\\imagemaid\\imagemaid.py --url (redacted) --token (redacted) --plex p:\\ --mode report --photo-transcoder --empty-trash --clean-bundles --optimize-db --timeout 600 --sleep 60 |",
                "| Running in Report Mode with Empty Trash, Clean Bundles, Optimize DB, and PhotoTrancoder set to True |",
                "| Downloading Database via the Plex API. First Plex will make a backup of your database.             |",
                "| Metadata Error: File Error: Database File Could not Downloaded                                     |",
                "| Scanning Complete: Found 0 PhotoTranscoder Images to Remove                                        |",
                "| Runtime: 0:00:00                                                                                   |",
                "| Remove Complete: Removed 0 PhotoTranscoder Images                                                  |",
                "| Space Recovered: 0 Bytes                                                                           |",
                "| Runtime: 0:00:00                                                                                   |",
                "|======================================== ImageMaid Finished ========================================|",
                "| Total Runtime      | 0:03:05                                                                       |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_local_version", lambda: "1.1.1")
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["ingested"] >= 1

    runs = qs_module.database.get_log_runs(limit=10)
    imagemaid_runs = [run for run in runs if run.get("tool_name") == "imagemaid"]
    assert imagemaid_runs
    run = imagemaid_runs[0]
    assert run["config_name"] == "demo"
    assert run["kometa_version"] == "1.1.1"
    assert run["analysis_counts"]["imagemaid_database_download_failed"] == 1
    assert run["analysis_counts"]["imagemaid_photo_recovered_bytes"] == 0
    assert run["section_runtimes"]["photo_transcoder_scan"] == 0
    assert run["section_runtimes"]["photo_transcoder_remove"] == 0
    assert run["analysis_counts"]["imagemaid_empty_trash_enabled"] == 1
    assert run["analysis_counts"]["imagemaid_clean_bundles_enabled"] == 1
    assert run["analysis_counts"]["imagemaid_optimize_db_enabled"] == 1
    assert run["analysis_counts"]["imagemaid_completed_with_errors"] == 1


def test_logscan_reingest_ingests_imagemaid_clear_runtime_log_with_restore_stats(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = log_dir / "imagemaid.log"
    runtime_log.write_text(
        "\n".join(
            [
                "[2026-04-29 21:53:15,701] [imagemaid.py:93]           [INFO]     |====================================================================================================|",
                "[2026-04-29 21:53:16,088] [imagemaid.py:93]           [INFO]     |     Version: 1.1.1-build8 (Python 3.12.1)                                                          |",
                "[2026-04-29 21:53:16,716] [imagemaid.py:93]           [DEBUG]    | Run Command: C:\\Users\\bullmoose20\\Quickstart\\config\\imagemaid\\imagemaid.py --url (redacted) --token (redacted) --plex P:\\plex --mode clear --photo-transcoder --local --timeout 600 --sleep 60 |",
                "[2026-04-29 21:53:16,717] [imagemaid.py:93]           [DEBUG]    | --empty-trash (EMPTY_TRASH): False                                                                 |",
                "[2026-04-29 21:53:16,718] [imagemaid.py:93]           [DEBUG]    | --clean-bundles (CLEAN_BUNDLES): False                                                             |",
                "[2026-04-29 21:53:16,719] [imagemaid.py:93]           [DEBUG]    | --optimize-db (OPTIMIZE_DB): False                                                                 |",
                "[2026-04-29 21:53:16,726] [imagemaid.py:118]          [INFO]     | Running in Clear Mode with PhotoTrancoder set to True                                              |",
                "[2026-04-29 21:53:16,739] [imagemaid.py:385]          [INFO]     | Scanning ImageMaid Restore for Bloat Images to Remove                                              |",
                "[2026-04-29 22:05:43,127] [imagemaid.py:387]          [INFO]     | Scanning Complete: Found 93440 Bloat Images in the ImageMaid Directory to Remove                   |",
                "[2026-04-29 22:05:43,128] [imagemaid.py:388]          [INFO]     | Runtime: 0:12:26                                                                                   |",
                "[2026-04-29 22:05:43,129] [imagemaid.py:392]          [INFO]     | Removing ImageMaid Restore Bloat Images                                                            |",
                "[2026-04-29 23:08:07,043] [imagemaid.py:401]          [INFO]     | Removing Complete: Removed 93440 ImageMaid Restore Bloat Images                                    |",
                "[2026-04-29 23:08:07,044] [imagemaid.py:403]          [INFO]     | Space Recovered: 23.79 GBs                                                                         |",
                "[2026-04-29 23:08:07,045] [imagemaid.py:404]          [INFO]     | Runtime: 1:02:23                                                                                   |",
                "[2026-04-29 23:08:07,047] [imagemaid.py:415]          [INFO]     | Scanning for PhotoTranscoder Images                                                                |",
                "[2026-04-29 23:08:08,098] [imagemaid.py:417]          [INFO]     | Scanning Complete: Found 126 PhotoTranscoder Images to Remove                                      |",
                "[2026-04-29 23:08:08,099] [imagemaid.py:418]          [INFO]     | Runtime: 0:00:01                                                                                   |",
                "[2026-04-29 23:08:08,100] [imagemaid.py:421]          [INFO]     | Removing PhotoTranscoder Images                                                                    |",
                "[2026-04-29 23:08:09,311] [imagemaid.py:432]          [INFO]     | Remove Complete: Removed 126 PhotoTranscoder Images                                                |",
                "[2026-04-29 23:08:09,312] [imagemaid.py:434]          [INFO]     | Space Recovered: 6.43 MBs                                                                          |",
                "[2026-04-29 23:08:09,312] [imagemaid.py:435]          [INFO]     | Runtime: 0:00:01                                                                                   |",
                "[2026-04-29 23:08:09,319] [imagemaid.py:473]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-29 23:08:09,320] [imagemaid.py:473]          [INFO]     | Total Runtime      | 1:14:52                                                                       |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["ingested"] >= 1

    runs = qs_module.database.get_log_runs(limit=10)
    imagemaid_runs = [run for run in runs if run.get("tool_name") == "imagemaid"]
    assert imagemaid_runs
    run = imagemaid_runs[0]
    assert run["started_at"] == "2026-04-29 21:53:15"
    assert run["finished_at"] == "2026-04-29 23:08:09"
    assert run["run_time_seconds"] == 4492
    assert "--mode clear" in run["command_signature"]
    assert run["kometa_version"] == "1.1.1-build8"
    assert run["analysis_counts"]["imagemaid_restore_found_files"] == 93440
    assert run["analysis_counts"]["imagemaid_restore_removed_files"] == 93440
    assert run["analysis_counts"]["imagemaid_photo_found_files"] == 126
    assert run["analysis_counts"]["imagemaid_photo_removed_files"] == 126
    assert run["analysis_counts"]["imagemaid_total_removed_files"] == 93566
    assert run["analysis_counts"]["imagemaid_restore_recovered_bytes"] == 25544317992
    assert run["analysis_counts"]["imagemaid_photo_recovered_bytes"] == 6742343
    assert run["analysis_counts"]["imagemaid_total_recovered_bytes"] == 25551060335
    assert run["analysis_counts"]["imagemaid_empty_trash_enabled"] == 0
    assert run["analysis_counts"]["imagemaid_clean_bundles_enabled"] == 0
    assert run["analysis_counts"]["imagemaid_optimize_db_enabled"] == 0
    assert run["section_runtimes"]["restore_dir_scan"] == 746
    assert run["section_runtimes"]["restore_dir_action"] == 3743
    assert run["section_runtimes"]["photo_transcoder_scan"] == 1
    assert run["section_runtimes"]["photo_transcoder_remove"] == 1
    assert run["progress_snapshot"]["name_label"] == "Operation"
    assert run["progress_snapshot"]["type_label"] == "Area"
    assert run["progress_snapshot"]["total_label"] == "1h 14m 52s"
    progress_rows = {row["name"]: row for row in run["progress_snapshot"]["rows"]}
    assert progress_rows["Restore Cache"]["phase_cells"][0]["label"] == "12m 26s"
    assert progress_rows["Restore Cache"]["phase_cells"][1]["label"] == "1h 2m 23s"
    assert progress_rows["Restore Cache"]["phase_cells"][2]["label"] == "Removed 93.4K"
    assert progress_rows["PhotoTranscoder"]["phase_cells"][2]["label"] == "Removed 126"


def test_analyze_imagemaid_log_content_uses_first_runtime_timestamp_for_started_at(qs_module):
    result = qs_module._analyze_imagemaid_log_content(
        "\n".join(
            [
                "[2026-04-29 15:08:28,897] [imagemaid.py:93]           [INFO]     |====================================================================================================|",
                "[2026-04-29 15:08:35,001] [imagemaid.py:453]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-29 15:08:35,002] [imagemaid.py:453]          [INFO]     | Total Runtime      | 0:00:05                                                                       |",
            ]
        ),
        log_path="imagemaid.log",
    )

    assert result is not None
    summary = result["summary"]
    assert summary["started_at"] == "2026-04-29 15:08:28"
    assert summary["finished_at"] == "2026-04-29 15:08:35"
    assert summary["run_time_seconds"] == 5
    assert summary["config_name"] == "unknown"


def test_analyze_imagemaid_log_content_parses_summary_section_runtimes(qs_module):
    result = qs_module._analyze_imagemaid_log_content(
        "\n".join(
            [
                "[2026-05-06 07:45:19,459] [imagemaid.py:244]          [INFO]     | Downloading Database via the Plex API. First Plex will make a backup of your database.             |",
                "[2026-05-06 07:50:48,649] [imagemaid.py:290]          [INFO]     | Runtime: 0:05:29                                                                                   |",
                "[2026-05-06 07:50:48,779] [imagemaid.py:297]          [INFO]     | Database Opened Querying For In-Use Images                                                         |",
                "[2026-05-06 07:50:49,327] [imagemaid.py:304]          [INFO]     | Runtime: 0:00:00                                                                                   |",
                "[2026-05-06 07:50:49,330] [imagemaid.py:311]          [INFO]     | Scanning Metadata Directory For Bloat Images: p:\\Plex\\Metadata                                     |",
                "[2026-05-06 07:56:08,253] [imagemaid.py:317]          [INFO]     | Runtime: 0:05:18                                                                                   |",
                "[2026-05-06 07:56:08,253] [imagemaid.py:322]          [INFO]     | Reporting Bloat Images                                                                             |",
                "[2026-05-06 07:56:08,404] [imagemaid.py:354]          [INFO]     | Runtime: 0:00:00                                                                                   |",
                "[2026-05-06 07:56:08,407] [imagemaid.py:415]          [INFO]     | Scanning for PhotoTranscoder Images                                                                |",
                "[2026-05-06 07:56:09,910] [imagemaid.py:418]          [INFO]     | Runtime: 0:00:01                                                                                   |",
                "[2026-05-06 07:56:09,911] [imagemaid.py:421]          [INFO]     | Removing PhotoTranscoder Images                                                                    |",
                "[2026-05-06 07:56:09,913] [imagemaid.py:435]          [INFO]     | Runtime: 0:00:00                                                                                   |",
                "[2026-05-06 07:56:09,914] [imagemaid.py:473]          [INFO]     |============================================= Database =============================================|",
                "[2026-05-06 07:56:09,916] [imagemaid.py:473]          [INFO]     | Downloaded         | 0:05:29                                                                       |",
                "[2026-05-06 07:56:09,917] [imagemaid.py:473]          [INFO]     | Query              | 0:00:00                                                                       |",
                "[2026-05-06 07:56:09,917] [imagemaid.py:473]          [INFO]     |====================================== Reporting Bloat Images ======================================|",
                "[2026-05-06 07:56:09,918] [imagemaid.py:473]          [INFO]     | Scan Time          | 0:05:18                                                                       |",
                "[2026-05-06 07:56:09,918] [imagemaid.py:473]          [INFO]     | Report Time        | 0:00:00                                                                       |",
                "[2026-05-06 07:56:09,919] [imagemaid.py:473]          [INFO]     |================================== Remove PhotoTranscoder Images ===================================|",
                "[2026-05-06 07:56:09,920] [imagemaid.py:473]          [INFO]     | Scan Time          | 0:00:01                                                                       |",
                "[2026-05-06 07:56:09,920] [imagemaid.py:473]          [INFO]     | Remove Time        | 0:00:00                                                                       |",
                "[2026-05-06 07:56:09,922] [imagemaid.py:473]          [INFO]     | Total Runtime      | 0:10:50                                                                       |",
            ]
        ),
        log_path="imagemaid.log",
    )

    assert result is not None
    section_runtimes = result["summary"]["section_runtimes"]
    assert section_runtimes["database_download"] == 329
    assert section_runtimes["database_query"] == 0
    assert section_runtimes["report_bloat_scan"] == 318
    assert section_runtimes["report_bloat_action"] == 0
    assert section_runtimes["photo_transcoder_scan"] == 1
    assert section_runtimes["photo_transcoder_remove"] == 0
    progress_snapshot = result["summary"]["progress_snapshot"]
    assert progress_snapshot["name_label"] == "Operation"
    assert progress_snapshot["type_label"] == "Area"
    assert progress_snapshot["columns"][0]["label"] == "Scan Time"
    assert progress_snapshot["columns"][2]["label"] == "Observed"
    row_names = [row["name"] for row in progress_snapshot["rows"]]
    assert "Database Prep" in row_names
    assert "Bloat Report" in row_names
    assert "PhotoTranscoder" in row_names


def test_logscan_reingest_preserves_incomplete_imagemaid_progress_snapshot(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = log_dir / "imagemaid.log"
    runtime_log.write_text(
        "\n".join(
            [
                "[2026-05-06 07:45:19,459] [imagemaid.py:244]          [INFO]     | Downloading Database via the Plex API. First Plex will make a backup of your database.             |",
                "[2026-05-06 07:50:48,649] [imagemaid.py:290]          [INFO]     | Runtime: 0:05:29                                                                                   |",
                "[2026-05-06 07:50:48,779] [imagemaid.py:297]          [INFO]     | Database Opened Querying For In-Use Images                                                         |",
                "[2026-05-06 07:50:49,327] [imagemaid.py:304]          [INFO]     | Runtime: 0:00:00                                                                                   |",
                "[2026-05-06 07:50:49,330] [imagemaid.py:311]          [INFO]     | Scanning Metadata Directory For Bloat Images: p:\\Plex\\Metadata                                     |",
                "[2026-05-06 07:56:08,253] [imagemaid.py:317]          [INFO]     | Runtime: 0:05:18                                                                                   |",
                "[2026-05-06 07:56:08,253] [imagemaid.py:322]          [INFO]     | Reporting Bloat Images                                                                             |",
                "[2026-05-06 07:56:08,404] [imagemaid.py:354]          [INFO]     | Runtime: 0:00:00                                                                                   |",
                "[2026-05-06 07:56:08,407] [imagemaid.py:415]          [INFO]     | Scanning for PhotoTranscoder Images                                                                |",
                "[2026-05-06 07:56:09,910] [imagemaid.py:418]          [INFO]     | Runtime: 0:00:01                                                                                   |",
                "[2026-05-06 07:56:09,911] [imagemaid.py:421]          [INFO]     | Removing PhotoTranscoder Images                                                                    |",
                "[2026-05-06 07:56:09,913] [imagemaid.py:435]          [INFO]     | Runtime: 0:00:00                                                                                   |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: isolated_config_dir / "kometa")
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200

    incomplete_runs = qs_module._get_logscan_incomplete_runs(limit=10)
    imagemaid_runs = [run for run in incomplete_runs if run.get("tool_name") == "imagemaid"]
    assert imagemaid_runs
    snapshot = imagemaid_runs[0]["progress_snapshot"]
    assert snapshot["name_label"] == "Operation"
    assert snapshot["type_label"] == "Area"
    assert snapshot["rows"]
    row_names = [row["name"] for row in snapshot["rows"]]
    assert "Database Prep" in row_names
    assert "Bloat Report" in row_names
    assert "PhotoTranscoder" in row_names


def test_analyze_incomplete_kometa_log_for_resume_uses_first_runtime_timestamp_for_started_at(qs_module, isolated_config_dir, monkeypatch):
    log_path = isolated_config_dir / "kometa" / "config" / "logs" / "meta.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                "[2026-04-29 15:08:28,897] [kometa.py:93] [INFO] | Starting work |",
                "[2026-04-29 15:08:35,001] [collections.py:453] [INFO] | Running Demo Collection in Library |",
            ]
        ),
        encoding="utf-8",
    )

    class _IncompleteAnalyzer:
        def analyze_content(self, content, log_path=None, config_name=None, include_people_scan=False):
            return {
                "summary": {
                    "run_key": "run-incomplete-kometa-1",
                    "tool_name": "kometa",
                    "run_complete": False,
                    "started_at": None,
                    "finished_at": None,
                    "config_name": config_name or "demo",
                    "run_command": "python kometa.py --run --config C:\\Quickstart\\config\\demo.yml",
                    "log_size": len(content or ""),
                },
                "recommendations": [],
            }

        def extract_progress(self, *_args, **_kwargs):
            return {}

        def _strip_divider_wrappers(self, value):
            return value

    monkeypatch.setattr(qs_module.logscan, "LogscanAnalyzer", _IncompleteAnalyzer)
    monkeypatch.setattr(qs_module, "_build_recovery_suggestions", lambda *_args, **_kwargs: [])

    result = qs_module._analyze_incomplete_log_for_resume(log_path, config_name="demo")

    assert result is not None
    assert result["started_at"] == "2026-04-29 15:08:28"


def test_build_incomplete_run_from_cache_entry_uses_first_runtime_timestamp_for_started_at(qs_module, isolated_config_dir):
    log_path = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa" / "meta-cached.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                "[2026-04-29 15:08:28,897] [kometa.py:93] [INFO] | Starting work |",
                "[2026-04-29 15:08:35,001] [collections.py:453] [INFO] | Running Demo Collection in Library |",
            ]
        ),
        encoding="utf-8",
    )

    result = qs_module._build_incomplete_run_from_cache_entry(
        log_path,
        cache_entry={
            "run_key": "run-incomplete-cached-1",
            "tool_name": "kometa",
            "run_complete": False,
            "summary": {
                "run_key": "run-incomplete-cached-1",
                "tool_name": "kometa",
                "started_at": None,
                "config_name": "demo",
                "run_command": "python kometa.py --run",
            },
        },
        config_name="demo",
    )

    assert result["started_at"] == "2026-04-29 15:08:28"


def test_analyze_imagemaid_log_content_infers_saved_config_name(qs_module, isolated_config_dir):
    qs_module.database.save_section_data(
        name="demo_report",
        section="imagemaid",
        validated=True,
        user_entered=True,
        data={
            "imagemaid": {
                "plex_path": "P:\\plex",
                "mode": "report",
                "photo_transcoder": True,
                "local_db": True,
                "timeout": "600",
                "sleep": "60",
            }
        },
    )
    qs_module.database.save_section_data(
        name="demo_restore",
        section="imagemaid",
        validated=True,
        user_entered=True,
        data={
            "imagemaid": {
                "plex_path": "P:\\plex",
                "mode": "restore",
                "photo_transcoder": True,
                "local_db": True,
                "timeout": "600",
                "sleep": "60",
            }
        },
    )

    result = qs_module._analyze_imagemaid_log_content(
        "\n".join(
            [
                "[2026-04-29 21:53:15,701] [imagemaid.py:93]           [INFO]     |     Version: 1.1.1-build8 (Python 3.12.1)                                                          |",
                "[2026-04-29 21:53:16,716] [imagemaid.py:93]           [DEBUG]    | Run Command: C:\\Quickstart\\config\\imagemaid\\imagemaid.py --url (redacted) --token (redacted) --plex P:\\plex --mode report --photo-transcoder --local --timeout 600 --sleep 60 |",
                "[2026-04-29 21:53:16,726] [imagemaid.py:118]          [INFO]     | Running in Report Mode with PhotoTrancoder set to True                                              |",
                "[2026-04-29 21:53:35,001] [imagemaid.py:453]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-29 21:53:35,002] [imagemaid.py:453]          [INFO]     | Total Runtime      | 0:00:19                                                                       |",
            ]
        ),
        log_path="imagemaid.log",
    )

    assert result is not None
    assert result["summary"]["config_name"] == "demo_report"


def test_logscan_reingest_archives_completed_imagemaid_runtime_log_into_imagemaid_archive(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "imagemaid"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = log_dir / "imagemaid.log"
    runtime_log.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-04-29T00:32:44.827109 config=demo tool=imagemaid mode=restore",
                "| Run Command: C:\\Quickstart\\config\\imagemaid\\imagemaid.py --url (redacted) --token (redacted) --plex p:\\ --mode restore |",
                "|======================================== ImageMaid Finished ========================================|",
                "| Total Runtime      | 0:03:05                                                                       |",
            ]
        ),
        encoding="utf-8",
    )
    saved = {}

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda cache: saved.__setitem__("cache", copy.deepcopy(cache)))

    resp = client.post("/logscan/trends/reingest", json={"reset": True})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert not runtime_log.exists()

    archived_paths = list(archive_dir.glob("imagemaid-*.log.gz"))
    assert len(archived_paths) == 1
    saved_cache = saved["cache"]["logs"]
    assert str(archived_paths[0].resolve()) in saved_cache
    assert saved_cache[str(archived_paths[0].resolve())]["tool_name"] == "imagemaid"


def test_logscan_trends_auto_ingests_completed_imagemaid_live_log(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "imagemaid"
    log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = log_dir / "imagemaid.log"
    runtime_log.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-04-29T00:32:44.827109 config=demo tool=imagemaid mode=report",
                "[2026-04-29 15:08:35,001] [imagemaid.py:453]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-29 15:08:35,002] [imagemaid.py:453]          [INFO]     | Total Runtime      | 0:00:05                                                                       |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["total_runs"] == 1
    assert payload["runs"][0]["tool_name"] == "imagemaid"
    assert payload["runs"][0]["config_name"] == "demo"
    assert not runtime_log.exists()
    assert len(list(archive_dir.glob("imagemaid-*.log.gz"))) == 1


def test_ingest_completed_live_logs_caches_unchanged_incomplete_live_kometa_log(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = isolated_config_dir / "kometa"
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = log_dir / "meta.log"
    runtime_log.write_text("incomplete log\n", encoding="utf-8")

    cache = {"version": 1, "logs": {}}
    analyze_calls = {"count": 0}

    class _IncompleteAnalyzer:
        def analyze_content(self, content, log_path=None, include_people_scan=False):
            analyze_calls["count"] += 1
            return {
                "summary": {
                    "run_key": "run-incomplete-live-1",
                    "tool_name": "kometa",
                    "run_complete": False,
                    "config_name": "demo",
                    "start_mode": "logged",
                    "run_command": "python kometa.py --config config/demo.yml",
                    "log_counts": {},
                    "analysis_counts": {},
                    "library_counts": {},
                    "section_runtimes": {},
                    "maintenance_summary": {},
                    "quiet_period_summary": {},
                    "quickstart_run_marker": False,
                    "created_at": "2026-04-30T18:00:00Z",
                    "log_size": runtime_log.stat().st_size,
                },
                "recommendations": [],
            }

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module, "_archive_finished_live_meta_log_if_idle", lambda *args, **kwargs: None)
    monkeypatch.setattr(qs_module.logscan, "LogscanAnalyzer", _IncompleteAnalyzer)
    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: copy.deepcopy(cache))
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: (cache.clear(), cache.update(copy.deepcopy(value))))

    first = qs_module._ingest_completed_live_logs("kometa")
    assert first == {"ingested": 0, "archived": 0}
    assert str(runtime_log.resolve()) in cache["logs"]
    assert cache["logs"][str(runtime_log.resolve())]["run_complete"] is False
    assert cache["logs"][str(runtime_log.resolve())]["summary"]["start_mode"] == "logged"
    assert analyze_calls["count"] == 1

    second = qs_module._ingest_completed_live_logs("kometa")
    assert second == {"ingested": 0, "archived": 0}
    assert analyze_calls["count"] == 1


def test_logscan_reingest_reset_false_scans_only_delta_files(client, isolated_config_dir, monkeypatch, qs_module):
    kometa_root = isolated_config_dir / "kometa"
    kometa_log_dir = kometa_root / "config" / "logs"
    kometa_log_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
    archive_dir.mkdir(parents=True, exist_ok=True)

    cached_path = archive_dir / "meta-20260428-120000Z-10.log"
    cached_path.write_text("cached complete log\n", encoding="utf-8")
    cached_stats = cached_path.stat()

    imagemaid_root = isolated_config_dir / "imagemaid"
    imagemaid_log_dir = imagemaid_root / "config" / "logs"
    imagemaid_log_dir.mkdir(parents=True, exist_ok=True)
    delta_path = imagemaid_log_dir / "imagemaid.log"
    delta_path.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-04-29T00:32:44.827109 config=demo tool=imagemaid mode=report",
                "[2026-04-29 15:08:35,001] [imagemaid.py:453]          [INFO]     |======================================== ImageMaid Finished ========================================|",
                "[2026-04-29 15:08:35,002] [imagemaid.py:453]          [INFO]     | Total Runtime      | 0:00:05                                                                       |",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.logscan.LogscanAnalyzer, "preload_people_index", lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(cached_path.resolve()): {
                    "mtime": cached_stats.st_mtime,
                    "size": cached_stats.st_size,
                    "run_key": "cached-run-1",
                    "tool_name": "kometa",
                    "run_complete": True,
                }
            },
        },
    )

    resp = client.post("/logscan/trends/reingest", json={"reset": False})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["scanned"] == 1
    assert payload["ingested"] >= 1


def test_logscan_trends_includes_imagemaid_runs(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "imagemaid"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "imagemaid-20260428.log"
    log_path.write_text("imagemaid archived log\n", encoding="utf-8")
    stats = log_path.stat()

    qs_module.database.save_log_run(
        {
            "run_key": "run-imagemaid-1",
            "tool_name": "imagemaid",
            "finished_at": "2026-04-28T20:17:00Z",
            "config_name": "demo",
            "created_at": "2026-04-28T20:17:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
            "run_command": "imagemaid --mode report",
            "kometa_version": "1.0.0",
        }
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(log_path.resolve()): {
                    "run_key": "run-imagemaid-1",
                    "tool_name": "imagemaid",
                    "run_complete": True,
                }
            },
        },
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["runs"]
    assert payload["runs"][0]["tool_name"] == "imagemaid"
    assert payload["runs"][0]["log_location"] == "archive"


def test_logscan_trends_returns_kometa_start_mode(client, isolated_config_dir, monkeypatch, qs_module):
    archive_dir = isolated_config_dir / "cache" / "logscan" / "archive" / "kometa"
    archive_dir.mkdir(parents=True, exist_ok=True)
    log_path = archive_dir / "meta-20260504.log"
    log_path.write_text("kometa archived log\n", encoding="utf-8")
    stats = log_path.stat()

    qs_module.database.save_log_run(
        {
            "run_key": "run-kometa-start-mode-1",
            "tool_name": "kometa",
            "finished_at": "2026-05-04T20:17:00Z",
            "config_name": "demo",
            "created_at": "2026-05-04T20:17:00Z",
            "log_mtime": stats.st_mtime,
            "log_size": stats.st_size,
            "run_command": "python kometa.py --run",
            "kometa_version": "2.3.1",
            "start_mode": "recovery",
        }
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {
            "version": 1,
            "logs": {
                str(log_path.resolve()): {
                    "run_key": "run-kometa-start-mode-1",
                    "tool_name": "kometa",
                    "run_complete": True,
                }
            },
        },
    )

    resp = client.get("/logscan/trends")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["runs"]
    assert payload["runs"][0]["tool_name"] == "kometa"
    assert payload["runs"][0]["start_mode"] == "recovery"


def test_logscan_startup_migration_defers_without_logs(isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setenv(qs_module.LOGSCAN_STARTUP_MIGRATIONS_ENV, "1")
    monkeypatch.setenv(qs_module.LOGSCAN_MIGRATION_LEVEL_DONE_ENV, "0")
    monkeypatch.setattr(qs_module, "REQUIRED_LOGSCAN_MIGRATION_LEVEL", 4)

    state = qs_module._get_pending_logscan_startup_migration()

    assert state["should_run"] is False
    assert state["reason"] == "waiting_for_logs"
    assert state["required_level"] == 4
    assert state["completed_level"] == 0


def test_logscan_startup_migration_runs_when_level_pending(isolated_config_dir, monkeypatch, qs_module):
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "meta-1.log").write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setenv(qs_module.LOGSCAN_STARTUP_MIGRATIONS_ENV, "1")
    monkeypatch.setenv(qs_module.LOGSCAN_MIGRATION_LEVEL_DONE_ENV, "1")
    monkeypatch.setattr(qs_module, "REQUIRED_LOGSCAN_MIGRATION_LEVEL", 3)

    state = qs_module._get_pending_logscan_startup_migration()

    assert state["should_run"] is True
    assert state["reason"] == "pending"
    assert state["required_level"] == 3
    assert state["completed_level"] == 1
    assert state["candidate_files"] >= 1


def test_run_logscan_startup_migration_persists_completed_level(monkeypatch, qs_module):
    updates = {}
    monkeypatch.setenv(qs_module.LOGSCAN_MIGRATION_LEVEL_DONE_ENV, "0")
    monkeypatch.setattr(
        qs_module.helpers,
        "update_env_variable",
        lambda key, value: updates.__setitem__(key, value),
    )
    monkeypatch.setattr(
        qs_module.helpers,
        "ts_log",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        qs_module,
        "_perform_logscan_reingest",
        lambda reset, job_id=None, update_state=True: {"success": True, "ingested": 2},
    )

    result = qs_module._run_logscan_startup_migration(qs_module.app, required_level=5, completed_level=0)

    assert result["success"] is True
    assert updates[qs_module.LOGSCAN_MIGRATION_LEVEL_DONE_ENV] == "5"
    assert os.environ[qs_module.LOGSCAN_MIGRATION_LEVEL_DONE_ENV] == "5"


def test_logscan_reingest_route_conflict_returns_active_job_metadata(client, monkeypatch, qs_module):
    qs_module._reset_logscan_reingest_state()
    qs_module._update_logscan_reingest_state(
        status="running",
        job_id="startup-logscan-migration",
        trigger="startup_migration",
        migration_level=6,
    )
    acquired = qs_module.logscan_ingest_lock.acquire(blocking=False)
    assert acquired is True
    try:
        resp = client.post("/logscan/trends/reingest", json={"reset": False, "background": True})
    finally:
        qs_module.logscan_ingest_lock.release()
        qs_module._reset_logscan_reingest_state()

    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["job_id"] == "startup-logscan-migration"
    assert payload["trigger"] == "startup_migration"
    assert payload["migration_level"] == 6
