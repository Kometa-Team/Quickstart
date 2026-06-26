import threading
import sys
from urllib.parse import urlparse

import pytest
from werkzeug.serving import make_server

# Chromium/Playwright will refuse to navigate to these ports.
# Keep the E2E live server off the browser's unsafe-port list.
BROWSER_UNSAFE_PORTS = {
    1,
    7,
    9,
    11,
    13,
    15,
    17,
    19,
    20,
    21,
    22,
    23,
    25,
    37,
    42,
    43,
    53,
    69,
    77,
    79,
    87,
    95,
    101,
    102,
    103,
    104,
    109,
    110,
    111,
    113,
    115,
    117,
    119,
    123,
    135,
    137,
    139,
    143,
    161,
    179,
    389,
    427,
    465,
    512,
    513,
    514,
    515,
    526,
    530,
    531,
    532,
    540,
    548,
    554,
    556,
    563,
    587,
    601,
    636,
    989,
    990,
    993,
    995,
    1719,
    1720,
    1723,
    2049,
    3659,
    4045,
    5060,
    5061,
    6000,
    6566,
    6665,
    6666,
    6667,
    6668,
    6669,
    6697,
    10080,
}


def _make_safe_live_server(app, host="127.0.0.1", attempts=25):
    last_port = None
    for _ in range(attempts):
        server = make_server(host, 0, app)
        port = server.server_port
        if port not in BROWSER_UNSAFE_PORTS:
            return server, port
        last_port = port
        server.server_close()
    raise RuntimeError(f"Could not allocate a browser-safe test server port after {attempts} attempts; last rejected port was {last_port}.")


def _can_create_overlapped_pipe():
    if not sys.platform.startswith("win"):
        return True
    try:
        import asyncio.windows_utils as win_utils

        read_handle, write_handle = win_utils.pipe(overlapped=(False, True), duplex=True)
        win_utils._winapi.CloseHandle(read_handle)
        win_utils._winapi.CloseHandle(write_handle)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def playwright():
    if not _can_create_overlapped_pipe():
        pytest.skip("Playwright blocked by Windows pipe permissions. Try running as Administrator or adjusting security policy.")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - dependency missing
        pytest.skip(f"Playwright not available: {exc}")

    try:
        pw = sync_playwright().start()
    except PermissionError as exc:
        pytest.skip(f"Playwright not permitted on this host: {exc}")
    except Exception as exc:
        pytest.skip(f"Playwright failed to start: {exc}")

    yield pw
    pw.stop()


@pytest.fixture(autouse=True)
def _configure_page(page):
    page.set_default_timeout(45000)
    page.set_default_navigation_timeout(45000)

    page.add_init_script("""
(() => {
  if (!window.bootstrap) {
    window.bootstrap = {
      Tooltip: function () {},
      Toast: function () { this.show = function () {}; },
      Modal: function () { this.show = function () {}; this.hide = function () {}; }
    };
  }

  const attachTooltip = () => {
    const jq = window.jQuery || window.$;
    if (jq && jq.fn && !jq.fn.tooltip) {
      jq.fn.tooltip = function () { return this; };
    }
  };

  attachTooltip();
  window.addEventListener('DOMContentLoaded', attachTooltip);
})();
""")

    def _block_external(route):
        parsed = urlparse(route.request.url)
        if parsed.scheme not in {"http", "https"}:
            route.continue_()
            return
        allowed_hosts = {
            "127.0.0.1",
            "localhost",
            "cdn.jsdelivr.net",
            "code.jquery.com",
        }
        if parsed.hostname in allowed_hosts:
            route.continue_()
            return
        route.abort()

    page.route("**/*", _block_external)
    yield


@pytest.fixture()
def live_server(app, tmp_path, monkeypatch):
    import modules.helpers as helpers
    import quickstart

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    kometa_root = tmp_path / "kometa"
    kometa_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(helpers, "CONFIG_DIR", str(config_dir))
    app.config["KOMETA_ROOT"] = str(kometa_root)
    # Avoid slow network calls during E2E page rendering.
    monkeypatch.setattr(quickstart, "refresh_plex_libraries", lambda: None)

    server, port = _make_safe_live_server(app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
