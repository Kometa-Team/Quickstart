import pytest
from dotenv import dotenv_values
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_browser_preference_persists_across_modal_reopen_and_reload(page, live_server, app, isolated_config_dir, monkeypatch):
    monkeypatch.setitem(app.config, "QS_AUTO_OPEN", True)
    for endpoint in ("workspace_status", "workspace_app_readiness", "background-jobs/active"):
        page.route(f"**/{endpoint}*", lambda route: route.fulfill(json={}))
    page.route("**/kometa-status", lambda route: route.fulfill(json={"status": "not_running"}))
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    modal = page.locator("#quickstartSettingsModal")
    toggle = page.get_by_role("switch", name="Open browser on startup")

    def open_settings():
        if not page.locator("#quickstart-settings-btn").is_visible():
            page.locator(".qs-sidebar-utility-toggle").click()
        page.locator("#quickstart-settings-btn").click()
        expect(modal).to_be_visible()

    open_settings()
    expect(toggle).to_be_checked()
    toggle.uncheck()
    with page.expect_response(lambda response: response.url.endswith("/update-quickstart-settings") and response.request.method == "POST") as saved:
        page.locator("#quickstart-settings-apply").click()
    assert saved.value.json()["auto_open"] is False
    assert saved.value.json()["restart"] is False
    expect(modal).to_be_hidden()
    assert dotenv_values(isolated_config_dir / ".env")["QS_AUTO_OPEN"] == "0"

    open_settings()
    expect(toggle).not_to_be_checked()
    modal.get_by_role("button", name="Close", exact=True).click()
    expect(modal).to_be_hidden()
    page.reload(wait_until="domcontentloaded")
    open_settings()
    expect(toggle).not_to_be_checked()
    toggle.check()
    with page.expect_response(lambda response: response.url.endswith("/update-quickstart-settings") and response.request.method == "POST") as saved:
        page.locator("#quickstart-settings-apply").click()
    assert saved.value.json()["auto_open"] is True
    expect(modal).to_be_hidden()
    assert dotenv_values(isolated_config_dir / ".env")["QS_AUTO_OPEN"] == "1"
