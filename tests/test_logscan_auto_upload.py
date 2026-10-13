import gzip
import io
import json
import copy
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from modules import logscan_auto_upload as automatic, logscan_upload as upload

RESULT = {"result_url": "https://logscan.kometa.team/scan/automatic", "delete_token": "private_management_token_123", "expires_at": 9999999999}


@pytest.fixture
def manager(monkeypatch, tmp_path):
    uploader = upload.LogscanUploader(receipt_path=tmp_path / "receipts.json")
    monkeypatch.setattr(upload.threading, "Thread", Mock())
    monkeypatch.setattr(uploader, "supports_tool", lambda tool: True)
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.head.return_value = Mock(status_code=200)
    connection.post.return_value = Mock(status_code=200, json=lambda: RESULT)
    monkeypatch.setattr(upload.requests, "Session", lambda: connection)

    def synchronous_start(path, config_name=None, run_key=None):
        job_id = f"job-{run_key}"
        uploader.active = True
        uploader.jobs[job_id] = {"phase": "preparing", "created_at": 0, "run_key": run_key}
        source = io.BytesIO(path.read_bytes())
        uploader._prepare_and_run(job_id, source, len(source.getvalue()), upload.upload_filename(config_name), path.suffix == ".gz")
        return job_id

    monkeypatch.setattr(uploader, "start", synchronous_start)
    uploader.connection = connection
    return uploader


@pytest.mark.parametrize("tool", ["kometa", "imagemaid"])
def test_opt_in_defaults_to_off_and_environment_enable_has_safe_baseline(app, monkeypatch, tool):
    key = automatic.AUTO_UPLOAD_KEYS[tool]
    for setting in automatic.AUTO_UPLOAD_KEYS.values():
        monkeypatch.delenv(setting, raising=False)
        monkeypatch.delenv(f"{setting}_SINCE", raising=False)
        monkeypatch.setitem(app.config, setting, False)
        monkeypatch.setitem(app.config, f"{setting}_SINCE", 0)
    monkeypatch.setattr(automatic.time, "time", lambda: 1000)
    automatic.initialize_auto_upload_settings(app)
    assert all(app.config[setting] is False for setting in automatic.AUTO_UPLOAD_KEYS.values())
    monkeypatch.setenv(key, "true")
    monkeypatch.setenv(f"{key}_SINCE", "nan")
    automatic.initialize_auto_upload_settings(app)
    assert app.config[key] is True
    assert app.config[f"{key}_SINCE"] == 1000
    monkeypatch.setenv(f"{key}_SINCE", "900")
    automatic.initialize_auto_upload_settings(app)
    assert app.config[f"{key}_SINCE"] == 900


@pytest.mark.parametrize("tool", ["kometa", "imagemaid"])
def test_setting_is_independent_persisted_and_applies_without_restart(client, app, monkeypatch, tool):
    writes = Mock()
    monkeypatch.setattr(automatic.helpers, "update_env_variable", writes)
    monkeypatch.setattr(automatic.time, "time", lambda: 1000)
    for key in automatic.AUTO_UPLOAD_KEYS.values():
        monkeypatch.setitem(app.config, key, False)
        monkeypatch.setitem(app.config, f"{key}_SINCE", 0)
    field = f"logscan_auto_upload_{tool}"
    key = automatic.AUTO_UPLOAD_KEYS[tool]
    reply = client.post("/update-quickstart-settings", json={field: True})
    assert reply.status_code == 200
    assert reply.json[field] is True and reply.json["restart"] is False
    assert app.config[key] is True and app.config[f"{key}_SINCE"] == 1000
    assert sum(app.config[setting] for setting in automatic.AUTO_UPLOAD_KEYS.values()) == 1
    writes.assert_any_call(key, "1")
    writes.assert_any_call(f"{key}_SINCE", "1000")
    assert client.get("/api/app-config").json[key] is True
    writes.reset_mock()
    assert client.post("/update-quickstart-settings", json={field: True}).json[field] is True
    writes.assert_not_called()
    assert client.post("/update-quickstart-settings", json={field: False}).json[field] is False
    writes.assert_called_once_with(key, "0")


@pytest.mark.parametrize("value", ["true", "false", 1, None, []])
def test_setting_requires_explicit_boolean_consent(client, monkeypatch, value):
    writes = Mock()
    monkeypatch.setattr(automatic.helpers, "update_env_variable", writes)
    reply = client.post("/update-quickstart-settings", json={"logscan_auto_upload_kometa": value})
    assert reply.status_code == 400
    writes.assert_not_called()


@pytest.mark.parametrize("tool", ["kometa", "imagemaid"])
@pytest.mark.parametrize("enabled,complete,finished,expected", [(True, True, 1001, True), (False, True, 1001, False), (True, False, 1001, False), (True, True, 999, False)])
def test_only_new_completed_opted_in_runs_are_queued(app, monkeypatch, tmp_path, tool, enabled, complete, finished, expected):
    key = automatic.AUTO_UPLOAD_KEYS[tool]
    monkeypatch.setitem(app.config, key, enabled)
    monkeypatch.setitem(app.config, f"{key}_SINCE", 1000)
    uploader = Mock()
    uploader.enqueue_auto.return_value = True
    monkeypatch.setattr(automatic, "portal_uploader", uploader)
    summary = {"run_key": "new-run", "run_complete": complete, "config_name": "movies", "finished_at": datetime.fromtimestamp(finished, timezone.utc).isoformat()}
    with app.app_context():
        assert automatic.queue_completed_log(tmp_path / "archive.log.gz", summary, tool) is expected
    assert uploader.enqueue_auto.called is expected
    if expected:
        kwargs = uploader.enqueue_auto.call_args.kwargs
        assert kwargs["run_key"] == "new-run" and kwargs["tool_name"] == tool and kwargs["config_name"] == "movies"
        app.config[key] = False
        assert kwargs["enabled"]() is False


def test_background_checks_enabled_tools_without_browser(app, qs_module, monkeypatch):
    check = Mock()
    monkeypatch.setattr(qs_module, "_start_logscan_live_ingest", check)
    for tool, key in automatic.AUTO_UPLOAD_KEYS.items():
        monkeypatch.setitem(app.config, key, tool == "imagemaid")
    with app.app_context():
        automatic.ingest_auto_upload_logs()
    check.assert_called_once_with("imagemaid")


def test_status_requests_cannot_archive_during_background_ingest(qs_module, monkeypatch):
    analyze = Mock()
    monkeypatch.setattr(qs_module, "_ingest_completed_live_logs_unlocked", analyze)
    qs_module.logscan_ingest_lock.acquire()
    try:
        assert qs_module._ingest_completed_live_logs("imagemaid") == {"ingested": 0, "archived": 0}
        assert qs_module._archive_finished_live_meta_log_if_idle() is None
        analyze.assert_not_called()
    finally:
        qs_module.logscan_ingest_lock.release()


def test_failed_local_ingest_releases_shared_lock(qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_ingest_completed_live_logs_unlocked", Mock(side_effect=RuntimeError("test")))
    with pytest.raises(RuntimeError):
        qs_module._ingest_completed_live_logs("kometa")
    assert not qs_module.logscan_ingest_lock.locked()


def test_automatic_queue_reuses_content_receipts_for_both_tools_and_keeps_links(manager, tmp_path):
    paths = [tmp_path / "kometa.log.gz", tmp_path / "imagemaid.log.gz"]
    for path in paths:
        path.write_bytes(gzip.compress(b"identical log content"))
    for tool, path in zip(("kometa", "imagemaid"), paths):
        assert manager.enqueue_auto(path, config_name="test", run_key=tool, tool_name=tool, enabled=lambda: True)
    assert manager.automatic_pending()
    manager._run_automatic()
    assert manager.connection.post.call_count == 1
    assert manager.connection.head.call_count == 1
    results = manager.automatic_results()
    assert results["kometa"]["result_url"] == results["imagemaid"]["result_url"] == RESULT["result_url"]
    assert all(result["management_url"].endswith(RESULT["delete_token"]) for result in results.values())
    restored = upload.LogscanUploader(receipt_path=manager.receipt_path)
    assert set(restored.saved_run_results()) == {"kometa", "imagemaid"}
    assert not manager.automatic_pending()
    assert not restored.enqueue_auto(paths[0], config_name="test", run_key="kometa", tool_name="kometa", enabled=lambda: True)


def test_turning_off_while_waiting_for_manual_upload_skips_remaining_queue(manager, monkeypatch, tmp_path):
    path = tmp_path / "meta.log"
    path.write_bytes(b"log")
    enabled = {"value": True}
    manager.enqueue_auto(path, config_name=None, run_key="waiting", tool_name="kometa", enabled=lambda: enabled["value"])
    manager.active = True
    monkeypatch.setattr(upload.time, "sleep", lambda seconds: enabled.update(value=False))
    manager._run_automatic()
    assert manager.automatic_results()["waiting"]["phase"] == "not_uploaded"
    manager.connection.post.assert_not_called()


def test_uncertain_auto_upload_is_saved_and_not_retried_on_restart(manager, tmp_path):
    path = tmp_path / "meta.log"
    path.write_bytes(b"log")
    manager.connection.post.side_effect = requests.Timeout()
    manager.enqueue_auto(path, config_name=None, run_key="failed", tool_name="kometa", enabled=lambda: True)
    manager._run_automatic()
    assert manager.automatic_results()["failed"]["uncertain"] is True
    restored = upload.LogscanUploader(receipt_path=manager.receipt_path)
    assert restored.automatic_results()["failed"]["phase"] == "failed"
    assert not restored.enqueue_auto(path, config_name=None, run_key="failed", tool_name="kometa", enabled=lambda: True)
    assert manager.connection.post.call_count == 1
    assert path.read_bytes() == b"log"


def test_restart_marks_pending_upload_uncertain_without_resubmitting(tmp_path):
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps({"receipts": {}, "automatic": {"pending": {"phase": "uploading"}}}))
    result = upload.LogscanUploader(receipt_path=path).automatic_results()["pending"]
    assert result["phase"] == "failed" and result["uncertain"] is True


def test_unsupported_imagemaid_upload_does_not_contact_scan_endpoint(manager, monkeypatch, tmp_path):
    monkeypatch.setattr(manager, "supports_tool", lambda tool: False)
    manager.enqueue_auto(tmp_path / "imagemaid.log", config_name=None, run_key="unsupported", tool_name="imagemaid", enabled=lambda: True)
    manager._run_automatic()
    assert manager.automatic_results()["unsupported"]["phase"] == "failed"
    manager.connection.post.assert_not_called()


def test_auto_failure_and_pending_status_available_to_analytics(client, monkeypatch, manager):
    from blueprints import logscan_upload_routes as routes

    manager.automatic["failed"] = {"phase": "failed", "error": "Online Logscan unavailable."}
    manager.receipts_loaded = True
    monkeypatch.setattr(routes, "portal_uploader", manager)
    reply = client.get("/logscan/upload/status?history=1")
    assert reply.json["automatic_results"]["failed"]["phase"] == "failed"
    assert reply.json["run_results"] == {} and reply.json["automatic_pending"] is False


@pytest.mark.parametrize("tool", ["kometa", "imagemaid"])
@pytest.mark.parametrize("complete,saved", [(True, True), (True, False), (False, False)])
def test_completion_pipeline_saves_and_archives_before_automatic_upload(app, qs_module, monkeypatch, tmp_path, tool, complete, saved):
    live = tmp_path / "live"
    live.mkdir()
    archive = tmp_path / "archive"
    path = live / ("meta.log" if tool == "kometa" else "imagemaid.log")
    path.write_bytes(b"local completed run log")
    key = automatic.AUTO_UPLOAD_KEYS[tool]
    monkeypatch.setitem(app.config, key, True)
    monkeypatch.setitem(app.config, f"{key}_SINCE", 1)
    summary = {"run_key": "completed", "run_complete": complete, "config_name": "test", "finished_at": datetime.now(timezone.utc).isoformat()}
    result = {"summary": summary, "recommendations": []}
    analyzer = Mock()
    analyzer.analyze_content.return_value = result
    monkeypatch.setattr(qs_module.logscan, "LogscanAnalyzer", lambda: analyzer)
    monkeypatch.setattr(qs_module, "_analyze_imagemaid_log_content", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(qs_module, "_get_logscan_live_dir", lambda *_args, **_kwargs: live)
    monkeypatch.setattr(qs_module, "_get_logscan_archive_dir", lambda *_args, **_kwargs: archive)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module, "_flush_quickstart_pending_markers", lambda *_args, **_kwargs: {"flushed": True})
    monkeypatch.setattr(qs_module, "_flush_imagemaid_pending_markers", lambda *_args, **_kwargs: {"flushed": True})
    monkeypatch.setattr(qs_module, "_build_completed_log_progress_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(qs_module, "_build_incomplete_resume_cache_fields", lambda *_args, **_kwargs: {})
    cache = {"logs": {}}
    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: copy.deepcopy(cache))
    monkeypatch.setattr(qs_module, "_save_logscan_ingest_cache", lambda value: (cache.clear(), cache.update(copy.deepcopy(value))))
    monkeypatch.setattr(qs_module, "_prune_logscan_archive", lambda *_args, **_kwargs: 0)
    events = []

    def save(*_args, **_kwargs):
        events.append("saved")
        return saved

    def queue(archived, **_kwargs):
        assert archived.is_file() and archived.suffix == ".gz"
        assert gzip.decompress(archived.read_bytes()) == b"local completed run log"
        events.append("queued")
        return True

    monkeypatch.setattr(qs_module.database, "save_log_run", save)
    uploader = Mock()
    uploader.enqueue_auto.side_effect = queue
    monkeypatch.setattr(automatic, "portal_uploader", uploader)
    with app.app_context():
        qs_module._ingest_completed_live_logs(tool)
        qs_module._ingest_completed_live_logs(tool)
    assert events == (["saved", "queued"] if complete and saved else ["saved"] if complete else [])
