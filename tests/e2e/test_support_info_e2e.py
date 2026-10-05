from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

SUMMARY = "# System Information\n# Quickstart: test\n# Libraries configured with Quickstart: 1 movie, 1 show"
WITH_LOGS = SUMMARY + "\n# Quickstart log tail (last 200 lines)\n\nPlex user: Jane Example"


def open_support_info(page):
    page.evaluate("bootstrap.Modal.getOrCreateInstance(document.getElementById('supportInfoModal')).show()")
    expect(page.locator("#supportInfoModal")).to_be_visible()


@pytest.mark.parametrize("viewport", [(1366, 900), (390, 844)], ids=["desktop", "mobile"])
@pytest.mark.parametrize("clipboard", [True, False], ids=["clipboard", "fallback"])
def test_support_info_opt_in_preview_copy_and_reset(page, live_server, viewport, clipboard):
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.add_init_script(f"""
            window.copiedSupportInfo = [];
            Object.defineProperty(window, 'isSecureContext', {{ value: {str(clipboard).lower()} }});
            Object.defineProperty(navigator, 'clipboard', {{ value: {{
                writeText: async text => window.copiedSupportInfo.push(text)
            }}}});
        """)
    requests = []

    def support_response(route):
        include_logs = parse_qs(urlparse(route.request.url).query).get("include_logs") == ["1"]
        requests.append(include_logs)
        route.fulfill(json={"text": WITH_LOGS if include_logs else SUMMARY, "generated_at": "test"})

    page.route("**/support-info**", support_response)
    page.goto(f"{live_server}/step/001-start", wait_until="networkidle")
    page.wait_for_function("typeof bootstrap.Modal.getOrCreateInstance === 'function'")
    open_support_info(page)
    toggle = page.locator("#supportInfoIncludeLogs")
    output = page.locator("#supportInfoOutput")
    expect(toggle).not_to_be_checked()
    expect(output).to_contain_text("Quickstart: test")
    expect(output).not_to_contain_text("Jane Example")

    def assert_copy(text):
        page.locator("#supportInfoCopy").click()
        if clipboard:
            page.wait_for_function("expected => window.copiedSupportInfo.at(-1) === expected", arg=text)
        else:
            expect(page.locator("#supportInfoCopyText")).to_have_value(text)

    assert_copy(SUMMARY)
    toggle.check()
    expect(output).to_contain_text("Jane Example")
    assert_copy(WITH_LOGS)
    page.locator("#supportInfoRefresh").click()
    expect(output).to_contain_text("Jane Example")
    toggle.uncheck()
    expect(output).to_contain_text("Quickstart: test")
    expect(output).not_to_contain_text("Jane Example")
    assert_copy(SUMMARY)

    artifact_dir = Path(__file__).resolve().parents[2] / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    page.screenshot(path=str(artifact_dir / f"support-info-{viewport[0]}-{'clipboard' if clipboard else 'fallback'}.png"))
    toggle.check()
    expect(output).to_contain_text("Jane Example")
    page.locator("#supportInfoModal .btn-close").click()
    expect(page.locator("#supportInfoModal")).not_to_be_visible()
    open_support_info(page)
    expect(toggle).not_to_be_checked()
    expect(output).to_contain_text("Quickstart: test")
    expect(output).not_to_contain_text("Jane Example")
    assert_copy(SUMMARY)
    assert requests == [False, True, True, False, True, False]


def test_support_info_ignores_late_log_response_after_opt_out(page, live_server):
    pending = []

    def support_response(route):
        if parse_qs(urlparse(route.request.url).query).get("include_logs") == ["1"]:
            pending.append(route)
        else:
            route.fulfill(json={"text": SUMMARY})

    page.route("**/support-info**", support_response)
    page.goto(f"{live_server}/step/001-start", wait_until="networkidle")
    page.wait_for_function("typeof bootstrap.Modal.getOrCreateInstance === 'function'")
    open_support_info(page)
    output = page.locator("#supportInfoOutput")
    expect(output).to_contain_text("Quickstart: test")
    with page.expect_request("**/support-info?include_logs=1"):
        page.locator("#supportInfoIncludeLogs").check()
    expect(page.locator("#supportInfoCopy")).to_be_disabled()
    page.locator("#supportInfoIncludeLogs").uncheck()
    expect(output).to_contain_text("Quickstart: test")
    with page.expect_response("**/support-info?include_logs=1") as response:
        pending[0].fulfill(json={"text": WITH_LOGS})
    response.value.finished()
    page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
    expect(output).not_to_contain_text("Jane Example")
    expect(page.locator("#supportInfoIncludeLogs")).not_to_be_checked()
