import gzip
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 390])
def test_automatic_upload_settings_results_and_navigation(page, live_server, qs_module, monkeypatch, tmp_path, width):
    from blueprints import logscan_upload_routes as routes
    from modules import helpers, logscan_auto_upload as automatic, logscan_upload as upload

    writes = {}
    monkeypatch.setattr(helpers, "update_env_variable", lambda key, value: writes.update({key: value}))
    for key in automatic.AUTO_UPLOAD_KEYS.values():
        monkeypatch.setitem(qs_module.app.config, key, False)
        monkeypatch.setitem(qs_module.app.config, f"{key}_SINCE", 0)
    manager = upload.LogscanUploader(receipt_path=tmp_path / "receipts.json")
    monkeypatch.setattr(manager, "supports_tool", lambda tool: True)
    monkeypatch.setattr(routes, "portal_uploader", manager)
    monkeypatch.setattr(automatic, "portal_uploader", manager)
    monkeypatch.setattr(qs_module, "portal_uploader", manager)
    posted = []
    ready = threading.Event()

    class Portal:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            content = gzip.decompress(kwargs["data"].snapshot.read())
            posted.append(content)
            tool = "imagemaid" if b"ImageMaid" in content else "kometa"
            ready.set()
            return Mock(
                status_code=200, json=lambda: {"result_url": f"https://logscan.kometa.team/scan/{tool}", "delete_token": "private_management_token_123", "expires_at": 9999999999}
            )

    monkeypatch.setattr(upload.requests, "Session", Portal)
    runs = []
    page.route("**/logscan/trends?*", lambda route: route.fulfill(json={"runs": runs, "total_runs": len(runs), "incomplete_runs": []}))
    page.route("**/logscan/trends/incomplete-runs?*", lambda route: route.fulfill(json={"incomplete_runs": [], "total_incomplete_runs": 0}))
    page.route("**/logscan/trends/reingest/status", lambda route: route.fulfill(json={"status": "idle"}))
    page.set_viewport_size({"width": width, "height": 900})
    url = f"{live_server}/step/905-analytics"
    page.goto(url, wait_until="networkidle")
    if not page.locator("#quickstart-settings-btn").is_visible():
        page.locator(".qs-sidebar-utility-toggle").click()
    page.locator("#quickstart-settings-btn").click()
    page.locator('[data-bs-target="#qs-settings-logscan"]').click()
    kometa = page.locator("#quickstart-settings-auto-upload-kometa")
    imagemaid = page.locator("#quickstart-settings-auto-upload-imagemaid")
    expect(kometa).not_to_be_checked()
    expect(imagemaid).not_to_be_checked()
    kometa.check()
    imagemaid.check()
    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    page.locator("#quickstartSettingsModal .modal-content").screenshot(path=str(artifacts / f"automatic-upload-settings-{width}.png"))
    with page.expect_response(lambda response: response.url.endswith("/update-quickstart-settings") and response.request.method == "POST") as saved:
        page.locator("#quickstart-settings-apply").click()
    assert saved.value.json()["restart"] is False
    expect(page.locator("#quickstartSettingsModal")).to_be_hidden()
    assert all(writes[key] == "1" for key in automatic.AUTO_UPLOAD_KEYS.values())
    assert not posted

    for tool in ("kometa", "imagemaid"):
        path = tmp_path / f"{tool}.log.gz"
        path.write_bytes(gzip.compress(b"ImageMaid completed" if tool == "imagemaid" else b"Kometa completed"))
        summary = {"run_key": tool, "run_complete": True, "config_name": tool, "finished_at": datetime.now(timezone.utc).isoformat()}
        runs.append({**summary, "tool_name": tool, "log_available": True, "log_location": "archive", "log_is_compressed": True})
        with qs_module.app.app_context():
            assert automatic.queue_completed_log(path, summary, tool)
    thread = manager.auto_thread
    if thread is not None:
        thread.join(timeout=15)
        assert not thread.is_alive()
    assert ready.is_set() and len(posted) == 2

    page.reload(wait_until="networkidle")
    page.locator("#logscan-table-toggle").click()
    for tool in ("kometa", "imagemaid"):
        feedback = page.locator(f'.logscan-upload-feedback[data-run-key="{tool}"]')
        expect(feedback).to_contain_text("Uploaded")
        expect(feedback.locator("a").first).to_have_attribute("href", f"https://logscan.kometa.team/scan/{tool}")
    page.locator("#logscan-table-upload-filter").select_option("uploaded")
    expect(page.locator("#logscan-trends-table tbody tr")).to_have_count(2)
    page.locator("#logscan-table-upload-filter").select_option("not_uploaded")
    expect(page.locator("#logscan-trends-table tbody tr .logscan-upload-feedback")).to_have_count(0)
    page.goto(f"{live_server}/step/001-start", wait_until="networkidle")
    page.goto(url, wait_until="networkidle")
    if not page.locator("#quickstart-settings-btn").is_visible():
        page.locator(".qs-sidebar-utility-toggle").click()
    page.locator("#quickstart-settings-btn").click()
    page.locator('[data-bs-target="#qs-settings-logscan"]').click()
    expect(kometa).to_be_checked()
    expect(imagemaid).to_be_checked()
    page.locator('#quickstartSettingsModal [data-bs-dismiss="modal"]').first.click()
    expect(page.locator("#quickstartSettingsModal")).to_be_hidden()
    page.locator("#logscan-table-toggle").click()
    expect(page.locator('.logscan-upload-feedback[data-run-key="imagemaid"] a').first).to_have_attribute("href", "https://logscan.kometa.team/scan/imagemaid")
    assert len(posted) == 2
