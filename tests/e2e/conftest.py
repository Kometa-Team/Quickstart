import threading
import sys
from urllib.parse import urlparse

import pytest
from werkzeug.serving import make_server


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

    server = make_server("127.0.0.1", 0, app)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
