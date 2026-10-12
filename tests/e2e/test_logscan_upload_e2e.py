import gzip
import hashlib
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 390])
def test_analytics_uploads_resolved_archive_and_restores_links(page, live_server, qs_module, monkeypatch, width):
    from blueprints import logscan_upload_routes as routes
    from modules import helpers

    archive = Path(helpers.CONFIG_DIR) / "cache" / "logscan" / "archive" / "kometa"
    archive.mkdir(parents=True, exist_ok=True)
    log = archive / "meta-previous.log.gz"
    log.write_bytes(gzip.compress(b"historical Kometa run\n"))
    run = {
        "run_key": "upload-history",
        "config_name": "Historical Movies",
        "tool_name": "kometa",
        "finished_at": "2026-10-12T10:00:00Z",
        "log_available": True,
        "log_location": "archive",
        "log_is_compressed": True,
    }
    monkeypatch.setattr(
        qs_module.database,
        "get_log_run",
        lambda key: run if key == run["run_key"] else None,
    )
    monkeypatch.setattr(
        qs_module,
        "_load_logscan_ingest_cache",
        lambda: {"logs": {str(log.resolve()): {"run_key": run["run_key"], "run_complete": True}}},
    )
    start = Mock(return_value="browser-job")
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    result = {
        "phase": "complete",
        "run_key": "upload-history",
        "result_url": "https://logscan.kometa.team/scan/browser-test",
        "management_url": "https://logscan.kometa.team/scan/browser-test#delete=private-token",
    }
    monkeypatch.setattr(
        routes.portal_uploader,
        "status",
        lambda job: dict(result) if job == "browser-job" else None,
    )
    monkeypatch.setattr(
        routes.portal_uploader,
        "saved_run_results",
        lambda: {run["run_key"]: result} if start.call_count else {},
    )
    page.route(
        "**/logscan/trends?*",
        lambda route: route.fulfill(json={"runs": [run], "total_runs": 1, "incomplete_runs": []}),
    )
    page.route(
        "**/logscan/trends/reingest/status",
        lambda route: route.fulfill(json={"status": "idle"}),
    )
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server}/step/905-analytics", wait_until="domcontentloaded")
    page.locator("#logscan-table-toggle").click()
    button = page.locator(".logscan-upload-log")
    expect(button).to_be_visible()
    expect(page.locator("#logscan-upload-links")).to_be_hidden()
    assert start.call_count == 0
    button.click()
    modal = page.locator("#qs-confirm-modal")
    expect(modal).to_be_visible()
    expect(modal).to_contain_text("Historical Movies")
    page.wait_for_function("() => getComputedStyle(document.getElementById('qs-confirm-modal')).opacity === '1'")
    assert modal.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    screenshot = Path("artifacts") / f"logscan-upload-modal-{width}.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot))
    page.locator("#qs-confirm-cancel").click()
    expect(modal).to_be_hidden()
    assert start.call_count == 0
    button.click()
    page.locator("#qs-confirm-confirm").click()
    expect(modal).to_be_hidden()
    expect(page.locator("#logscan-upload-result")).to_have_attribute("href", result["result_url"])
    expect(page.locator("#logscan-upload-result")).to_be_visible()
    start.assert_called_once_with(log.resolve(), config_name="Historical Movies", run_key="upload-history")
    expect(page.locator("#logscan-upload-result")).to_have_attribute("href", result["result_url"])
    expect(page.locator("#logscan-upload-management")).to_have_attribute("href", result["management_url"])
    feedback = page.locator('.logscan-upload-feedback[data-run-key="upload-history"]')
    expect(feedback).to_contain_text("Uploaded")
    expect(feedback.locator("a").first).to_have_attribute("href", result["result_url"])
    feedback.scroll_into_view_if_needed()
    page.screenshot(path=str(Path("artifacts") / f"logscan-upload-inline-{width}.png"))
    assert feedback.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    assert log.exists()
    assert button.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    page.locator("#logscan-upload-links").scroll_into_view_if_needed()
    screenshot = Path("artifacts") / f"logscan-upload-analytics-{width}.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot), full_page=True)
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("#logscan-upload-result")).to_have_attribute("href", result["result_url"])
    page.locator("#logscan-table-toggle").click()
    expect(page.locator('.logscan-upload-feedback[data-run-key="upload-history"]')).to_contain_text("Uploaded")
    assert start.call_count == 1


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 390])
def test_current_log_upload_controls(page, live_server, qs_module, monkeypatch, width):
    from blueprints import logscan_upload_routes as routes
    from modules import helpers

    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *args, **kwargs: {
            "stage": "kometa",
            "todo_count": 0,
            "todo_blockers": [],
            "dependency_cards": [],
            "setup_blockers": [],
            "bulk_validation_fresh": True,
            "bulk_validation_at": qs_module.utc_now_iso(),
            "validation_ttl_hours": 12,
            "can_build_config": True,
            "config_valid": True,
        },
    )
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *args, **kwargs: (True, None, {}, "test: true\n", []),
    )
    monkeypatch.setattr(qs_module, "_get_kometa_log_wait_payload", lambda path: None)
    start = Mock(return_value="current-browser-job")
    monkeypatch.setattr(routes.portal_uploader, "start", start)
    result = {
        "phase": "complete",
        "result_url": "https://logscan.kometa.team/scan/current-test",
        "management_url": "https://logscan.kometa.team/scan/current-test#delete=private-token",
    }
    monkeypatch.setattr(
        routes.portal_uploader,
        "status",
        lambda job: dict(result) if job == "current-browser-job" else None,
    )
    page.route("**/kometa-status", lambda route: route.fulfill(json={"status": "running"}))
    page.route(
        "**/logscan/analyze",
        lambda route: route.fulfill(json={"recommendations": [], "sections": []}),
    )
    page.route(
        "**/validate-kometa-root",
        lambda route: route.fulfill(
            json={
                "success": True,
                "kometa_root": str(helpers.get_kometa_root_path()),
                "venv_python": "python",
                "log": [],
            }
        ),
    )
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    page.locator('[data-bs-target="#logscan-accordion-collapse"]').click()
    button = page.locator("#logscan-upload")
    expect(button).to_be_visible()
    expect(page.locator("#logscan-upload-links")).to_be_hidden()
    assert start.call_count == 0
    button.click()
    expect(page.locator("#qs-confirm-modal")).to_contain_text("Current Kometa log")
    page.locator("#qs-confirm-confirm").click()
    expect(page.locator("#qs-confirm-modal")).to_be_hidden()
    expect(page.locator("#logscan-upload-result")).to_have_attribute("href", result["result_url"])
    assert start.call_count == 1
    assert start.call_args.args[0] == helpers.get_kometa_log_dir() / "meta.log"
    assert button.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    page.locator("#logscan-panel").scroll_into_view_if_needed()
    screenshot = Path("artifacts") / f"logscan-upload-current-{width}.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot))


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 390])
def test_saved_and_legacy_links_return_without_session_job_or_local_logs(page, live_server, qs_module, monkeypatch, tmp_path, width):
    from blueprints import logscan_upload_routes as routes
    from modules.logscan_upload import LogscanUploader

    path = tmp_path / "receipts.json"
    log = tmp_path / "saved-one.log.gz"
    content = b"previously uploaded archive\n"
    log.write_bytes(gzip.compress(content))
    manager = LogscanUploader(receipt_path=path)
    runs = []
    for index, key in enumerate(("saved-one", "saved-two")):
        manager._remember_receipt(
            hashlib.sha256(content).hexdigest() if index == 0 else str(index) * 64,
            {
                "result_url": f"https://logscan.kometa.team/scan/{key}",
                "delete_token": "private_management_token_123",
                "expires_at": 9999999999,
            },
            run_key=key if index else None,
        )
        runs.append(
            {
                "run_key": key,
                "config_name": key,
                "tool_name": "kometa",
                "finished_at": "2026-10-12T10:00:00Z",
                "log_available": False,
            }
        )
    restored = LogscanUploader(receipt_path=path)
    monkeypatch.setattr(routes, "portal_uploader", restored)
    monkeypatch.setattr(qs_module, "portal_uploader", restored)
    monkeypatch.setattr(
        qs_module,
        "_resolve_logscan_run_log_info",
        lambda key, **kwargs: ({"path": log, "location": "archive", "is_compressed": True} if key == "saved-one" and log.exists() else None),
    )
    start = Mock()
    monkeypatch.setattr(restored, "start", start)
    page.route(
        "**/logscan/trends?*",
        lambda route: route.fulfill(
            json={
                "runs": qs_module._annotate_logscan_runs(runs, context={"cache_entries": []}),
                "total_runs": 2,
                "incomplete_runs": [],
            }
        ),
    )
    page.route(
        "**/logscan/trends/reingest/status",
        lambda route: route.fulfill(json={"status": "idle"}),
    )
    page.set_viewport_size({"width": width, "height": 900})
    url = f"{live_server}/step/905-analytics"
    for visit in range(2):
        page.goto(url, wait_until="domcontentloaded")
        page.locator("#logscan-table-toggle").click()
        for run in runs:
            feedback = page.locator(f'.logscan-upload-feedback[data-run-key="{run["run_key"]}"]')
            expect(feedback).to_contain_text("Uploaded", timeout=15000)
            expect(feedback.locator("a").first).to_have_attribute("href", f'https://logscan.kometa.team/scan/{run["run_key"]}')
            expect(feedback.locator("a").last).to_have_attribute(
                "href",
                f'https://logscan.kometa.team/scan/{run["run_key"]}#delete=private_management_token_123',
            )
            assert feedback.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        expect(page.locator(".logscan-upload-log")).to_have_count(1 if visit == 0 else 0)
        if visit == 0:
            page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
            log.unlink()
            # Simulate a fresh server process with no remembered session job.
            restored = LogscanUploader(receipt_path=path)
            monkeypatch.setattr(routes, "portal_uploader", restored)
            monkeypatch.setattr(qs_module, "portal_uploader", restored)
            monkeypatch.setattr(restored, "start", start)
    page.screenshot(
        path=str(Path("artifacts") / f"logscan-upload-restored-{width}.png"),
        full_page=True,
    )
    feedback.scroll_into_view_if_needed()
    feedback.screenshot(path=str(Path("artifacts") / f"logscan-upload-restored-detail-{width}.png"))
    start.assert_not_called()


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 390])
def test_selected_upload_queue_deduplication_filters_and_navigation(page, live_server, qs_module, monkeypatch, tmp_path, width):
    from blueprints import logscan_upload_routes as routes
    from modules import helpers, logscan_upload as upload

    archive = Path(helpers.CONFIG_DIR) / "cache" / "logscan" / "archive" / "kometa"
    archive.mkdir(parents=True, exist_ok=True)
    paths = {}
    runs = []
    for key, content in (
        ("existing", b"same log"),
        ("copy", b"same log"),
        ("new", b"different log"),
        ("imagemaid", b"ImageMaid log"),
    ):
        path = archive / (key + ".log.gz")
        path.write_bytes(gzip.compress(content))
        paths[key] = path
        runs.append(
            {
                "run_key": key,
                "config_name": key,
                "tool_name": "imagemaid" if key == "imagemaid" else "kometa",
                "finished_at": "2026-10-12T10:00:00Z",
                "log_available": True,
                "log_location": "archive",
                "log_can_delete": True,
                "log_is_compressed": True,
            }
        )
    manager = upload.LogscanUploader(receipt_path=tmp_path / "receipts.json")
    manager._remember_receipt(
        hashlib.sha256(b"same log").hexdigest(),
        {
            "result_url": "https://logscan.kometa.team/scan/existing",
            "delete_token": "private_management_token_123",
            "expires_at": 9999999999,
        },
        run_key="existing",
    )
    monkeypatch.setattr(routes, "portal_uploader", manager)
    monkeypatch.setattr(qs_module, "portal_uploader", manager)
    monkeypatch.setattr(
        qs_module.database,
        "get_log_run",
        lambda key: next((run for run in runs if run["run_key"] == key), None),
    )
    monkeypatch.setattr(
        qs_module,
        "_resolve_logscan_run_log_info",
        lambda key, **kwargs: {
            "path": paths[key],
            "location": "archive",
            "is_compressed": True,
        },
    )
    started = threading.Event()
    release = threading.Event()
    posted = []

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def head(self, *args, **kwargs):
            return Mock(status_code=200)

        def post(self, url, **kwargs):
            posted.append(gzip.decompress(kwargs["data"].snapshot.read()))
            started.set()
            assert release.wait(timeout=60)
            return Mock(
                status_code=200,
                json=lambda: {
                    "result_url": "https://logscan.kometa.team/scan/new",
                    "delete_token": "private_management_token_456",
                    "expires_at": 9999999999,
                },
            )

    monkeypatch.setattr(upload.requests, "Session", Portal)
    page.route(
        "**/logscan/trends?*",
        lambda route: route.fulfill(
            json={
                "runs": qs_module._annotate_logscan_runs(runs, context={"cache_entries": []}),
                "total_runs": 4,
                "incomplete_runs": [],
            }
        ),
    )
    page.route(
        "**/logscan/trends/incomplete-runs?*",
        lambda route: route.fulfill(json={"incomplete_runs": [], "total_incomplete_runs": 0}),
    )
    page.route(
        "**/logscan/trends/reingest/status",
        lambda route: route.fulfill(json={"status": "idle"}),
    )
    page.set_viewport_size({"width": width, "height": 900})
    url = f"{live_server}/step/905-analytics"
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.locator("#logscan-table-toggle").click()
        upload_filter = page.locator("#logscan-table-upload-filter")
        expect(page.locator("#logscan-trends-table tbody tr")).to_have_count(4)
        upload_filter.select_option("uploaded")
        expect(page.locator("#logscan-trends-table tbody tr")).to_have_count(1)
        expect(page.locator("#logscan-trends-table tbody")).to_contain_text("existing")
        upload_filter.select_option("not_uploaded")
        expect(page.locator("#logscan-trends-table tbody tr")).to_have_count(2)
        expect(page.locator("#logscan-trends-table tbody")).not_to_contain_text("imagemaid")
        upload_filter.select_option("all")
        page.locator("#logscan-table-select-all").click()
        expect(page.locator("#logscan-table-selection-summary")).to_contain_text("3 uploadable")
        page.locator("#logscan-table-upload-selected").click()
        expect(page.locator("#qs-confirm-modal")).to_contain_text("3 selected logs")
        page.locator("#qs-confirm-cancel").click()
        expect(page.locator("#qs-confirm-modal")).to_be_hidden()
        assert not posted
        page.locator("#logscan-table-upload-selected").click()
        page.locator("#qs-confirm-confirm").click()
        expect(page.locator("#qs-confirm-modal")).to_be_hidden()
        expect(page.locator("#logscan-upload-cancel-batch")).to_be_visible(timeout=10000)
        expect(page.locator('.logscan-upload-feedback[data-run-key="new"]')).to_contain_text("Uploading", timeout=10000)
        assert started.is_set()
        expect(page.locator("#logscan-table-upload-selected")).to_be_disabled()
        page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
        page.goto(url, wait_until="domcontentloaded")
        expect(page.locator("#logscan-upload-cancel-batch")).to_be_visible()
        release.set()
        page.locator("#logscan-table-toggle").click()
        expect(page.locator("#logscan-upload-status")).to_contain_text("1 uploaded, 2 already uploaded", timeout=10000)
        for key in ("existing", "copy", "new"):
            feedback = page.locator(f'.logscan-upload-feedback[data-run-key="{key}"]')
            expect(feedback.locator("a").first).to_have_attribute(
                "href",
                "https://logscan.kometa.team/scan/" + ("new" if key == "new" else "existing"),
            )
            assert feedback.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        assert posted == [b"different log"]
        upload_filter.select_option("uploaded")
        expect(page.locator("#logscan-trends-table tbody tr")).to_have_count(3)
        upload_filter.screenshot(path=str(Path("artifacts") / f"logscan-upload-filter-{width}.png"))
        page.locator("#logscan-table-upload-selected").scroll_into_view_if_needed()
        page.screenshot(path=str(Path("artifacts") / f"logscan-upload-batch-{width}.png"))
        assert page.locator("#logscan-table-upload-selected").evaluate("el => el.scrollWidth <= el.clientWidth + 1")
        upload_filter.select_option("not_uploaded")
        expect(page.locator("#logscan-trends-table tbody")).to_contain_text("No runs match")
        page.reload(wait_until="domcontentloaded")
        page.locator("#logscan-table-toggle").click()
        upload_filter.select_option("uploaded")
        expect(page.locator("#logscan-trends-table tbody tr")).to_have_count(3)
        assert posted == [b"different log"]
    finally:
        release.set()
