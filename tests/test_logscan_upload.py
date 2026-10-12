import io
import gzip
import json
from unittest.mock import Mock

import pytest
import requests

from modules import logscan_upload as upload


def response(code, payload):
    return Mock(status_code=code, json=lambda: payload)


def connection(monkeypatch, post, polls=()):
    client = Mock()
    client.post.return_value = post
    client.head.return_value = response(200, {})
    client.get.side_effect = list(polls)
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(upload.requests, "Session", lambda: client)
    monkeypatch.setattr(upload.time, "sleep", lambda _: None)
    return client


RESULT = {
    "result_url": "https://logscan.kometa.team/scan/abc123",
    "delete_token": "secret_management_token_123",
    "expires_at": 9999999999,
}


def worker(monkeypatch, post, polls=()):
    manager = upload.LogscanUploader()
    manager.jobs["test-job"] = {"phase": "uploading", "created_at": 0}
    manager.active = True
    client = connection(monkeypatch, post, polls)
    source = io.BytesIO(b"[kometa.py:1] [ERROR] test\n")
    manager._prepare_and_run("test-job", source, len(source.getvalue()), "qs-default-meta.gz")
    snapshot = client.post.call_args.kwargs["data"].snapshot
    return manager, client, snapshot


def test_upload_queued_then_complete_and_separates_public_private_links(monkeypatch):
    manager, client, snapshot = worker(
        monkeypatch,
        response(202, {"job_id": "test-job", "phase": "queued"}),
        [
            response(200, {"phase": "scanning"}),
            response(200, {"phase": "complete", "result": RESULT}),
        ],
    )
    data = manager.status("test-job")
    assert data["phase"] == "complete"
    assert data["result_url"] == RESULT["result_url"]
    assert "secret_management" not in data["result_url"]
    assert data["management_url"].endswith("#delete=" + RESULT["delete_token"])
    assert client.get.call_count == 2
    assert snapshot.closed
    assert manager.active is False
    assert client.post.call_args.args[0] == upload.PORTAL_URL + "/api/scan"
    assert "Authorization" not in client.post.call_args.kwargs["headers"]
    assert client.post.call_args.kwargs["allow_redirects"] is False


def test_synchronous_response_supported(monkeypatch):
    manager, client, _ = worker(monkeypatch, response(200, RESULT))
    assert manager.status("test-job")["phase"] == "complete"
    client.get.assert_not_called()


@pytest.mark.parametrize("code", [400, 413, 429, 500, 302])
def test_rejected_upload_does_not_return_result_or_retry(monkeypatch, code):
    manager, client, snapshot = worker(monkeypatch, response(code, {}))
    assert manager.status("test-job")["phase"] == "failed"
    assert str(code) in manager.status("test-job")["error"]
    assert "result_url" not in manager.status("test-job")
    assert snapshot.closed
    assert client.post.call_count == 1


def test_connection_failure_releases_lock_and_warns_about_ambiguous_upload(monkeypatch):
    client = connection(monkeypatch, response(200, RESULT))
    client.post.side_effect = requests.Timeout("private details")
    manager = upload.LogscanUploader()
    manager.jobs["test-job"] = {"phase": "uploading"}
    manager.active = True
    snapshot = io.BytesIO(b"log")
    manager._prepare_and_run("test-job", snapshot, 3, "qs-default-meta.gz")
    assert manager.status("test-job")["phase"] == "failed"
    assert "duplicate" in manager.status("test-job")["error"]
    assert "private details" not in manager.status("test-job")["error"]
    assert snapshot.closed and not manager.active


def test_failed_remote_job(monkeypatch):
    manager, _, _ = worker(
        monkeypatch,
        response(202, {"job_id": "test-job"}),
        [response(200, {"phase": "failed"})],
    )
    assert manager.status("test-job")["phase"] == "failed"


@pytest.mark.parametrize(
    "url",
    [
        "http://logscan.kometa.team/scan/abc",
        "https://evil.test/scan/abc",
        "https://logscan.kometa.team/other",
        "https://logscan.kometa.team@evil.test/scan/abc",
    ],
)
def test_untrusted_result_links_rejected(url):
    with pytest.raises(upload.UploadError):
        upload.result_links({**RESULT, "result_url": url})


def test_snapshot_is_independent_of_live_file(tmp_path):
    path = tmp_path / "meta.log"
    path.write_bytes(b"original\n")
    snapshot, size = upload.snapshot_log(path)
    try:
        path.write_bytes(b"replacement\n")
        data = snapshot.read()
        assert gzip.decompress(data) == b"original\n" and size == len(data)
    finally:
        snapshot.close()


def test_snapshot_rejects_empty_and_oversize(tmp_path, monkeypatch):
    path = tmp_path / "meta.log"
    path.write_bytes(b"")
    with pytest.raises(upload.UploadError, match="empty"):
        upload.snapshot_log(path)
    path.write_bytes(b"1234")
    monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 3)
    with pytest.raises(upload.UploadError, match="limit"):
        upload.snapshot_log(path)


def test_multipart_body_is_sized_stream_and_contains_only_log():
    compressed = gzip.compress(b"contents")
    body = upload.MultipartLog(io.BytesIO(compressed), len(compressed), upload.upload_filename("Movies"))
    prepared = requests.Request("POST", upload.PORTAL_URL + "/api/scan", data=body).prepare()
    assert prepared.headers["Content-Length"] == str(len(body))
    assert "Transfer-Encoding" not in prepared.headers
    data = b"".join(body)
    assert len(data) == len(body)
    assert b'filename="qs-Movies-meta.gz"' in data and compressed in data
    assert b"contents" not in data
    assert b"Content-Type: application/gzip" in data
    assert b"config_name" not in data


def test_confirmation_required_before_any_upload(client, monkeypatch):
    from blueprints import logscan_upload_routes as routes

    start = Mock()
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    assert client.post("/logscan/upload", json={}).status_code == 400
    assert client.post("/logscan/upload", json=["confirm"]).status_code == 400
    assert client.post("/logscan/upload", data={"confirm": True}).status_code == 400
    start.assert_not_called()


def test_route_uses_only_current_log_and_status_is_session_scoped(client, qs_module, monkeypatch, tmp_path):
    from blueprints import logscan_upload_routes as routes

    monkeypatch.setattr(qs_module, "_get_kometa_log_wait_payload", lambda _: None)
    monkeypatch.setattr(routes.helpers, "get_kometa_log_dir", lambda: tmp_path)
    start = Mock(return_value="local-job")
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    monkeypatch.setattr(
        routes.portal_uploader,
        "status",
        lambda job: {"phase": "queued"} if job == "local-job" else None,
    )
    result = client.post("/logscan/upload", json={"confirm": True, "path": "/private/config.yml"})
    assert result.status_code == 202
    start.assert_called_once_with(tmp_path / "meta.log", config_name=None)
    assert client.get("/logscan/upload/status").get_json()["phase"] == "queued"
    assert qs_module.app.test_client().get("/logscan/upload/status").get_json()["phase"] == "idle"
    client.post("/logscan/upload", json={"confirm": True})
    assert start.call_count == 1


def test_route_rejects_previous_run_log(client, qs_module, monkeypatch):
    from blueprints import logscan_upload_routes as routes

    monkeypatch.setattr(qs_module, "_get_kometa_log_wait_payload", lambda _: {"waiting": True})
    monkeypatch.setattr(routes.portal_uploader, "status", lambda _: None)
    start = Mock()
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    assert client.post("/logscan/upload", json={"confirm": True}).status_code == 409
    start.assert_not_called()


def test_config_name_is_used_in_filename_without_paths_or_header_injection():
    assert upload.upload_filename("Movies Test") == "qs-Movies_Test-meta.gz"
    assert upload.upload_filename("../../private\r\nheader") == "qs-private_header-meta.gz"
    assert upload.upload_filename(None) == "qs-default-meta.gz"
    assert len(upload.upload_filename("x" * 200)) < 110


def test_background_compression_captures_initial_size_and_uses_config_name(monkeypatch, tmp_path):
    path = tmp_path / "meta.log"
    path.write_bytes(b"initial log\n")
    pending = {}

    def thread(**kwargs):
        pending.update(kwargs)
        return Mock()

    monkeypatch.setattr(upload.threading, "Thread", thread)
    manager = upload.LogscanUploader()
    job = manager.start(path, "Movie Config")
    assert manager.status(job)["phase"] == "compressing"
    assert manager.status(job)["filename"] == "qs-Movie_Config-meta.gz"
    with path.open("ab") as live:
        live.write(b"later appended log\n")
    captured = {}

    def run(job_id, snapshot, size, filename):
        with snapshot:
            captured.update(data=gzip.decompress(snapshot.read()), filename=filename)

    monkeypatch.setattr(manager, "_run", run)
    pending["target"](*pending["args"])
    assert captured == {"data": b"initial log\n", "filename": "qs-Movie_Config-meta.gz"}
    assert pending["args"][1].closed


def test_start_failures_release_busy_state_without_network(tmp_path):
    manager = upload.LogscanUploader()
    with pytest.raises(FileNotFoundError):
        manager.start(tmp_path / "missing.log")
    assert not manager.active
    path = tmp_path / "meta.log"
    path.write_bytes(b"")
    with pytest.raises(upload.UploadError, match="empty"):
        manager.start(path)
    assert not manager.active
    assert manager.jobs == {}


def test_gzip_archive_is_uploaded_without_double_compression(monkeypatch, tmp_path):
    path = tmp_path / "meta-previous.log.gz"
    original = gzip.compress(b"historical run\n")
    path.write_bytes(original)
    pending = {}
    monkeypatch.setattr(upload.threading, "Thread", lambda **kwargs: pending.update(kwargs) or Mock())
    manager = upload.LogscanUploader()
    job = manager.start(path, "Previous Config", run_key="previous-run")
    assert manager.status(job)["phase"] == "preparing"
    captured = {}

    def run(job_id, snapshot, size, filename):
        captured.update(data=snapshot.read(), size=size)

    monkeypatch.setattr(manager, "_run", run)
    pending["target"](*pending["args"])
    assert captured == {"data": original, "size": len(original)}
    assert path.read_bytes() == original
    assert manager.status(job)["run_key"] == "previous-run"
    assert not manager.active


@pytest.mark.parametrize("contents", [b"not gzip", gzip.compress(b"log")[:-5], gzip.compress(b"")])
def test_invalid_gzip_is_rejected_before_network(monkeypatch, contents):
    manager = upload.LogscanUploader()
    manager.jobs["job"] = {"phase": "preparing"}
    manager.active = True
    run = Mock()
    monkeypatch.setattr(manager, "_run", run)
    source = io.BytesIO(contents)
    manager._prepare_and_run("job", source, len(contents), "qs-test-meta.gz", True)
    assert manager.status("job")["phase"] == "failed"
    assert not manager.active and source.closed
    run.assert_not_called()


def test_gzip_decoded_size_limit_is_enforced(monkeypatch):
    contents = gzip.compress(b"a" * 4096)
    monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 100)
    with pytest.raises(upload.UploadError, match="limit"):
        upload.snapshot_gzip(io.BytesIO(contents), len(contents))


def test_unexpected_worker_failure_releases_busy_state(monkeypatch):
    manager = upload.LogscanUploader()
    manager.jobs["job"] = {"phase": "compressing"}
    manager.active = True
    run = Mock(side_effect=RuntimeError("private worker details"))
    monkeypatch.setattr(manager, "_run", run)
    source = io.BytesIO(b"log")
    manager._prepare_and_run("job", source, 3, "qs-test-meta.gz")
    assert manager.status("job")["phase"] == "failed"
    assert "private worker details" not in manager.status("job")["error"]
    assert source.closed and run.call_args.args[1].closed
    assert not manager.active


def historical_route(monkeypatch, qs_module, path, tool_name="kometa"):
    from blueprints import logscan_upload_routes as routes

    run = {"run_key": "old-run", "config_name": "Old Movies", "tool_name": tool_name}
    monkeypatch.setattr(qs_module, "_get_logscan_incomplete_run", lambda key: None)
    monkeypatch.setattr(qs_module.database, "get_log_run", lambda key: run if key == "old-run" else None)
    monkeypatch.setattr(
        qs_module,
        "_resolve_logscan_run_log_info",
        lambda *args, **kwargs: {"path": path} if path else None,
    )
    monkeypatch.setattr(qs_module, "_classify_logscan_file_location", lambda _: "archive")
    monkeypatch.setattr(routes.portal_uploader, "status", lambda _: None)
    start = Mock(return_value="historical-job")
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    return start


def test_historical_upload_resolves_run_and_uses_its_config(client, qs_module, monkeypatch, tmp_path):
    path = tmp_path / "meta-old.log.gz"
    start = historical_route(monkeypatch, qs_module, path)
    with client.session_transaction() as browser:
        browser["config_name"] = "Current Config"
    result = client.post(
        "/logscan/upload",
        json={"confirm": True, "run_key": "old-run", "path": "/private/config.yml"},
    )
    assert result.status_code == 202
    start.assert_called_once_with(path, config_name="Old Movies", run_key="old-run")


def test_incomplete_historical_run_can_be_uploaded_without_db_record(client, qs_module, monkeypatch, tmp_path):
    path = tmp_path / "meta-incomplete.log.gz"
    start = historical_route(monkeypatch, qs_module, path)
    monkeypatch.setattr(qs_module.database, "get_log_run", lambda key: None)
    monkeypatch.setattr(
        qs_module,
        "_get_logscan_incomplete_run",
        lambda key: {
            "run_key": key,
            "config_name": "Stopped Movies",
            "is_incomplete": True,
        },
    )
    assert client.post("/logscan/upload", json={"confirm": True, "run_key": "old-run"}).status_code == 202
    start.assert_called_once_with(path, config_name="Stopped Movies", run_key="old-run")


@pytest.mark.parametrize("run_key", [None, "", [], {}, 1])
def test_invalid_historical_run_id_is_rejected(client, monkeypatch, run_key):
    from blueprints import logscan_upload_routes as routes

    start = Mock()
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    assert client.post("/logscan/upload", json={"confirm": True, "run_key": run_key}).status_code == 400
    start.assert_not_called()


@pytest.mark.parametrize(
    "case, expected",
    [("missing_run", 404), ("missing_log", 404), ("outside", 400), ("imagemaid", 400)],
)
def test_unavailable_or_unsupported_historical_logs_are_not_uploaded(client, qs_module, monkeypatch, tmp_path, case, expected):
    if case == "imagemaid":
        from blueprints import logscan_upload_routes as routes

        monkeypatch.setattr(routes.portal_uploader, "supports_tool", lambda tool: False)
    start = historical_route(
        monkeypatch,
        qs_module,
        None if case == "missing_log" else tmp_path / "meta-old.log.gz",
        "imagemaid" if case == "imagemaid" else "kometa",
    )
    if case == "outside":
        monkeypatch.setattr(qs_module, "_classify_logscan_file_location", lambda _: "other")
    result = client.post(
        "/logscan/upload",
        json={
            "confirm": True,
            "run_key": "unknown" if case == "missing_run" else "old-run",
        },
    )
    assert result.status_code == expected
    start.assert_not_called()


def test_historical_imagemaid_upload_when_portal_supports_it(client, qs_module, monkeypatch, tmp_path):
    from blueprints import logscan_upload_routes as routes

    path = tmp_path / "imagemaid-old.log.gz"
    start = historical_route(monkeypatch, qs_module, path, tool_name="imagemaid")
    monkeypatch.setattr(routes.portal_uploader, "supports_tool", lambda tool: tool == "imagemaid")
    assert client.post("/logscan/upload", json={"confirm": True, "run_key": "old-run"}).status_code == 202
    start.assert_called_once_with(path, config_name="Old Movies", run_key="old-run")


def test_portal_capabilities_cached_and_kometa_needs_no_probe(monkeypatch):
    get = Mock(return_value=response(200, {"tools": ["kometa", "imagemaid"]}))
    monkeypatch.setattr(upload.requests, "get", get)
    manager = upload.LogscanUploader()
    assert manager.supports_tool("kometa")
    get.assert_not_called()
    assert manager.supports_tool("imagemaid") and manager.supports_tool("imagemaid")
    get.assert_called_once_with(upload.PORTAL_URL + "/api/capabilities", timeout=(10, 15), allow_redirects=False)


@pytest.mark.parametrize("code,payload", [(404, {}), (302, {}), (200, {}), (200, {"tools": "imagemaid"}), (200, {"tools": [1]})])
def test_unconfirmed_imagemaid_capability_does_not_enable_upload(monkeypatch, code, payload):
    get = Mock(return_value=response(code, payload))
    monkeypatch.setattr(upload.requests, "get", get)
    manager = upload.LogscanUploader()
    assert not manager.supports_tool("imagemaid")
    assert not manager.supports_tool("imagemaid")
    get.assert_called_once()


def test_imagemaid_live_log_not_blocked_by_kometa_startup(client, qs_module, monkeypatch, tmp_path):
    from blueprints import logscan_upload_routes as routes

    start = historical_route(monkeypatch, qs_module, tmp_path / "meta.log", tool_name="imagemaid")
    monkeypatch.setattr(routes.portal_uploader, "supports_tool", lambda tool: True)
    wait = Mock(return_value={"status": "waiting_for_kometa_log"})
    monkeypatch.setattr(qs_module, "_get_kometa_log_wait_payload", wait)
    assert client.post("/logscan/upload", json={"confirm": True, "run_key": "old-run"}).status_code == 202
    start.assert_called_once()
    wait.assert_not_called()


def test_portal_capability_is_rechecked_after_short_negative_cache(monkeypatch):
    get = Mock(side_effect=[response(200, {"tools": ["kometa"]}), response(200, {"tools": ["kometa", "imagemaid"]})])
    monkeypatch.setattr(upload.requests, "get", get)
    manager = upload.LogscanUploader()
    assert not manager.supports_tool("imagemaid")
    monkeypatch.setattr(upload.time, "monotonic", lambda: manager.capabilities_checked_at + 31)
    assert manager.supports_tool("imagemaid")
    assert get.call_count == 2


def test_server_duplicate_response_reuses_remote_result(monkeypatch):
    manager, client, _ = worker(monkeypatch, response(200, {**RESULT, "already_uploaded": True}))
    assert manager.status("test-job")["already_uploaded"]
    client.post.assert_called_once()


def prepare_job(manager, job_id, content, compressed=False, run_key=None):
    manager.jobs[job_id] = {"phase": "preparing", "created_at": 0, "run_key": run_key}
    manager.active = True
    manager._prepare_and_run(job_id, io.BytesIO(content), len(content), "qs-test-meta.gz", compressed)
    return manager.status(job_id)


def test_identical_plain_and_gzip_logs_reuse_successful_result(monkeypatch):
    client = connection(monkeypatch, response(200, RESULT))
    manager = upload.LogscanUploader()
    first = prepare_job(manager, "first", b"same historical log\n")
    second = prepare_job(manager, "second", gzip.compress(b"same historical log\n", mtime=123), True)
    assert first["already_uploaded"] is False
    assert second["already_uploaded"] is True
    assert second["result_url"] == first["result_url"]
    assert second["management_url"] == first["management_url"]
    assert first["content_sha256"] == second["content_sha256"]
    assert client.post.call_count == 1
    assert not manager.active


def test_all_run_links_survive_restart_without_jobs_or_original_logs(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    path = tmp_path / "receipts.json"
    manager = upload.LogscanUploader(receipt_path=path)
    prepare_job(manager, "one", b"first log", run_key="first-run")
    client.post.return_value = response(200, {**RESULT, "result_url": upload.PORTAL_URL + "/scan/second"})
    prepare_job(manager, "two", b"second log", run_key="second-run")
    restored = upload.LogscanUploader(receipt_path=path)
    results = restored.saved_run_results()
    assert not restored.jobs
    assert set(results) == {"first-run", "second-run"}
    assert results["first-run"]["result_url"] == RESULT["result_url"]
    assert results["second-run"]["management_url"].endswith("#delete=" + RESULT["delete_token"])
    assert client.post.call_count == 2


def test_duplicate_binds_receipt_to_both_runs_without_resetting_expiry(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, {**RESULT, "expires_at": None}))
    path = tmp_path / "receipts.json"
    manager = upload.LogscanUploader(receipt_path=path)
    first = prepare_job(manager, "one", b"same log", run_key="one")
    uploaded_at = manager.receipts[first["content_sha256"]]["uploaded_at"]
    second = prepare_job(manager, "two", gzip.compress(b"same log"), True, run_key="two")
    assert second["already_uploaded"]
    results = upload.LogscanUploader(receipt_path=path).saved_run_results()
    assert set(results) == {"one", "two"}
    assert results["two"]["uploaded_at"] == uploaded_at
    assert client.post.call_count == 1


@pytest.mark.parametrize("compressed", [False, True])
def test_legacy_receipt_recovers_from_local_log_without_upload(monkeypatch, tmp_path, compressed):
    client = connection(monkeypatch, response(200, RESULT))
    receipt_path = tmp_path / "receipts.json"
    content = b"previously uploaded log\n"
    fingerprint = upload.hashlib.sha256(content).hexdigest()
    receipt_path.write_text(
        json.dumps(
            {
                "version": 1,
                "receipts": {fingerprint: {**RESULT, "uploaded_at": upload.time.time()}},
            }
        )
    )
    path = tmp_path / ("old.log.gz" if compressed else "old.log")
    path.write_bytes(gzip.compress(content) if compressed else content)
    manager = upload.LogscanUploader(receipt_path=receipt_path)
    assert manager.restore_run_result("old-run", path)
    with manager.receipt_lock:
        thread = manager.restore_thread
    if thread:
        thread.join(timeout=5)
        assert not thread.is_alive()
    results = upload.LogscanUploader(receipt_path=receipt_path).saved_run_results()
    assert results["old-run"]["result_url"] == RESULT["result_url"]
    assert not manager.restoring_results()
    client.post.assert_not_called()


def test_expired_run_result_is_not_restored(monkeypatch, tmp_path):
    connection(monkeypatch, response(200, {**RESULT, "expires_at": 1}))
    path = tmp_path / "receipts.json"
    prepare_job(upload.LogscanUploader(receipt_path=path), "one", b"expired", run_key="one")
    assert upload.LogscanUploader(receipt_path=path).saved_run_results() == {}


def test_analytics_annotation_and_status_restore_all_receipts(client, qs_module, monkeypatch, tmp_path):
    from blueprints import logscan_upload_routes as routes

    connection(monkeypatch, response(200, RESULT))
    path = tmp_path / "receipts.json"
    manager = upload.LogscanUploader(receipt_path=path)
    for key in ("one", "two"):
        prepare_job(manager, key, key.encode(), run_key=key)
    restored = upload.LogscanUploader(receipt_path=path)
    monkeypatch.setattr(routes, "portal_uploader", restored)
    monkeypatch.setattr(qs_module, "portal_uploader", restored)
    monkeypatch.setattr(qs_module, "_resolve_logscan_run_log_info", lambda *args, **kwargs: None)
    rows = qs_module._annotate_logscan_runs(
        [{"run_key": key, "tool_name": "kometa"} for key in ("one", "two")],
        context={"cache_entries": []},
    )
    assert all(not row["log_available"] and row["portal_upload"]["phase"] == "complete" for row in rows)
    result = client.get("/logscan/upload/status?history=1")
    assert result.headers["Cache-Control"] == "no-store"
    assert result.json["phase"] == "idle"
    assert set(result.json["run_results"]) == {"one", "two"}
    assert result.json["restoring"] is False


def test_successful_receipts_survive_restart(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    path = tmp_path / "upload_receipts.json"
    first = prepare_job(upload.LogscanUploader(receipt_path=path), "first", b"saved log")
    stored = json.loads(path.read_text())
    assert stored["receipts"][first["content_sha256"]]["result_url"] == RESULT["result_url"]
    restored = prepare_job(upload.LogscanUploader(receipt_path=path), "restored", b"saved log")
    assert restored["already_uploaded"] is True
    assert restored["management_url"] == first["management_url"]
    assert client.post.call_count == 1


def test_changed_content_is_uploaded_even_with_same_length(monkeypatch):
    client = connection(monkeypatch, response(200, RESULT))
    manager = upload.LogscanUploader()
    first = prepare_job(manager, "first", b"old log")
    second = prepare_job(manager, "second", b"new log")
    assert first["content_sha256"] != second["content_sha256"]
    assert second["already_uploaded"] is False
    assert client.post.call_count == 2


@pytest.mark.parametrize("expires_at", [1, "2000-01-01T00:00:00Z"])
def test_expired_receipts_allow_new_upload(monkeypatch, expires_at):
    client = connection(monkeypatch, response(200, {**RESULT, "expires_at": expires_at}))
    manager = upload.LogscanUploader()
    prepare_job(manager, "first", b"expired log")
    client.post.return_value = response(200, RESULT)
    second = prepare_job(manager, "second", b"expired log")
    assert second["already_uploaded"] is False
    assert client.post.call_count == 2


def test_failed_upload_is_not_saved_as_successful_receipt(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(500, {}))
    path = tmp_path / "upload_receipts.json"
    manager = upload.LogscanUploader(receipt_path=path)
    assert prepare_job(manager, "failed", b"retry log")["phase"] == "failed"
    assert not path.exists()
    client.post.return_value = response(200, RESULT)
    assert prepare_job(manager, "retry", b"retry log")["already_uploaded"] is False
    assert client.post.call_count == 2


def test_receipt_write_failure_does_not_hide_confirmed_upload(monkeypatch, tmp_path):
    connection(monkeypatch, response(200, RESULT))
    parent = tmp_path / "not-a-directory"
    parent.write_text("occupied")
    manager = upload.LogscanUploader(receipt_path=parent / "upload_receipts.json")
    data = prepare_job(manager, "confirmed", b"confirmed log")
    assert data["phase"] == "complete"
    assert data["result_url"] == RESULT["result_url"]
    assert not manager.active


def test_bad_cached_receipt_cannot_return_untrusted_link(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    content = b"cached log"
    fingerprint = upload.hashlib.sha256(content).hexdigest()
    path = tmp_path / "upload_receipts.json"
    path.write_text(
        json.dumps(
            {
                "receipts": {
                    fingerprint: {
                        **RESULT,
                        "result_url": "https://evil.test/scan/abc",
                        "uploaded_at": 1,
                    }
                }
            }
        )
    )
    data = prepare_job(upload.LogscanUploader(receipt_path=path), "safe", content)
    assert data["phase"] == "complete" and data["already_uploaded"] is False
    assert data["result_url"] == RESULT["result_url"]
    assert client.post.call_count == 1


def queued_batch(monkeypatch, manager, keys, resolve):
    pending = {}
    monkeypatch.setattr(upload.threading, "Thread", lambda **kwargs: pending.update(kwargs) or Mock())
    batch_id = manager.start_batch(keys, resolve)
    return batch_id, lambda: pending["target"](*pending["args"])


def test_batch_deduplicates_ids_and_contents_sequentially(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    paths = {}
    for key, content in (
        ("one", b"same log"),
        ("copy", gzip.compress(b"same log")),
        ("different", b"new log"),
    ):
        path = tmp_path / (key + (".log.gz" if key == "copy" else ".log"))
        path.write_bytes(content)
        paths[key] = path
    manager = upload.LogscanUploader(receipt_path=tmp_path / "receipts.json")
    checked = []

    def resolve(key):
        assert manager.active
        checked.append(key)
        return paths[key], key

    batch_id, run = queued_batch(monkeypatch, manager, ["one", "copy", "one", "different"], resolve)
    assert manager.active
    with pytest.raises(upload.UploadError):
        manager.start(paths["one"])
    with pytest.raises(upload.UploadError):
        manager.start_batch(["one"], resolve)
    run()
    result = manager.status(batch_id)
    assert result["phase"] == "complete"
    assert checked == ["one", "copy", "different"]
    assert [item["already_uploaded"] for item in result["items"]] == [
        False,
        True,
        False,
    ]
    assert client.post.call_count == 2
    assert not manager.active and not manager.jobs
    result["items"][0]["phase"] = "tampered"
    assert manager.status(batch_id)["items"][0]["phase"] == "complete"
    assert set(upload.LogscanUploader(receipt_path=tmp_path / "receipts.json").saved_run_results()) == set(paths)


def test_batch_stops_after_uncertain_upload_without_retrying(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    client.post.side_effect = requests.Timeout()
    path = tmp_path / "meta.log"
    path.write_bytes(b"log")
    manager = upload.LogscanUploader()
    resolve = Mock(return_value=(path, "test"))
    batch_id, run = queued_batch(monkeypatch, manager, ["one", "two"], resolve)
    run()
    result = manager.status(batch_id)
    assert result["phase"] == "failed"
    assert [item["phase"] for item in result["items"]] == ["failed", "not_uploaded"]
    assert result["items"][0]["uncertain"]
    assert resolve.call_count == client.post.call_count == 1
    assert not manager.active and not manager.saved_run_results()


@pytest.mark.parametrize("status", [404, 410])
def test_deleted_or_expired_remote_result_allows_reupload(monkeypatch, tmp_path, status):
    client = connection(monkeypatch, response(200, RESULT))
    path = tmp_path / "receipts.json"
    manager = upload.LogscanUploader(receipt_path=path)
    prepare_job(manager, "one", b"same log", run_key="one")
    client.head.return_value = response(status, {})
    result = prepare_job(manager, "two", b"same log", run_key="one")
    assert result["phase"] == "complete" and not result["already_uploaded"]
    assert client.post.call_count == 2
    client.head.assert_called_once_with(RESULT["result_url"], timeout=(10, 30), allow_redirects=False)


@pytest.mark.parametrize("status", [302, 403, 500])
def test_uncertain_receipt_check_never_reuploads(monkeypatch, status):
    client = connection(monkeypatch, response(200, RESULT))
    manager = upload.LogscanUploader()
    prepare_job(manager, "one", b"same log", run_key="one")
    client.head.return_value = response(status, {})
    result = prepare_job(manager, "two", b"same log", run_key="one")
    assert result["phase"] == "failed" and result["uncertain"]
    assert client.post.call_count == 1


def test_receipt_check_timeout_never_reuploads(monkeypatch):
    client = connection(monkeypatch, response(200, RESULT))
    manager = upload.LogscanUploader()
    prepare_job(manager, "one", b"same log", run_key="one")
    client.head.side_effect = requests.Timeout()
    assert prepare_job(manager, "two", b"same log", run_key="one")["uncertain"]
    assert client.post.call_count == 1


def test_batch_continues_after_definitive_missing_log(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    path = tmp_path / "available.log"
    path.write_bytes(b"log")
    manager = upload.LogscanUploader()
    resolve = Mock(side_effect=[upload.UploadError("Log is no longer available."), (path, "test")])
    batch_id, run = queued_batch(monkeypatch, manager, ["missing", "available"], resolve)
    run()
    assert [item["phase"] for item in manager.status(batch_id)["items"]] == [
        "failed",
        "complete",
    ]
    assert client.post.call_count == 1
    assert not manager.active


def test_cancel_batch_finishes_current_and_skips_remaining(monkeypatch, tmp_path):
    client = connection(monkeypatch, response(200, RESULT))
    path = tmp_path / "meta.log"
    path.write_bytes(b"log")
    manager = upload.LogscanUploader()
    batch_id, run = queued_batch(monkeypatch, manager, ["one", "two"], lambda key: (path, key))

    def accepted(*args, **kwargs):
        assert manager.cancel_batch(batch_id)
        return response(200, RESULT)

    client.post.side_effect = accepted
    run()
    result = manager.status(batch_id)
    assert result["phase"] == "complete" and result["cancel_requested"]
    assert [item["phase"] for item in result["items"]] == ["complete", "not_uploaded"]
    assert client.post.call_count == 1
    assert not manager.active


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"confirm": True},
        {"confirm": True, "run_keys": []},
        {"confirm": True, "run_keys": [None]},
        {"confirm": True, "run_keys": [" "]},
        {"confirm": True, "run_keys": ["x" * 257]},
        {"confirm": True, "run_keys": ["x"] * 501},
    ],
)
def test_batch_route_requires_confirmation_and_bounded_run_ids(client, monkeypatch, payload):
    from blueprints import logscan_upload_routes as routes

    start = Mock()
    monkeypatch.setattr(routes.portal_uploader, "start_batch", start)
    assert client.post("/logscan/upload/batch", json=payload).status_code == 400
    start.assert_not_called()


def test_batch_route_resolves_only_managed_runs_and_restores_session_queue(client, qs_module, monkeypatch, tmp_path):
    from blueprints import logscan_upload_routes as routes

    path = tmp_path / "old.log.gz"
    historical_route(monkeypatch, qs_module, path)
    pending = {}
    manager = upload.LogscanUploader()
    monkeypatch.setattr(routes, "portal_uploader", manager)
    monkeypatch.setattr(upload.threading, "Thread", lambda **kwargs: pending.update(kwargs) or Mock())
    result = client.post(
        "/logscan/upload/batch",
        json={"confirm": True, "run_keys": [" old-run ", "old-run"]},
    )
    assert result.status_code == 202
    assert result.json["kind"] == "batch"
    assert len(result.json["items"]) == 1
    assert client.post("/logscan/upload/batch", json={"confirm": True, "run_keys": ["old-run"]}).status_code == 202
    assert client.post("/logscan/upload/batch", json={"confirm": True, "run_keys": ["different"]}).status_code == 409
    assert client.post("/logscan/upload", json={"confirm": True, "run_key": "old-run"}).status_code == 409
    resolve = pending["args"][1]
    assert resolve("old-run") == (path, "Old Movies")
    monkeypatch.setattr(qs_module, "_classify_logscan_file_location", lambda path: "other")
    with pytest.raises(upload.UploadError, match="managed"):
        resolve("old-run")
    assert client.get("/logscan/upload/status").json["kind"] == "batch"
    assert qs_module.app.test_client().get("/logscan/upload/status").json["phase"] == "idle"
    assert client.post("/logscan/upload/batch/cancel", json={}).json["cancel_requested"]
    assert qs_module.app.test_client().post("/logscan/upload/batch/cancel", json={}).status_code == 404
