import re
import io
import zipfile
from pathlib import Path

import pytest
from playwright.sync_api import expect


def _stub_validate_root(route):
    route.fulfill(
        status=200,
        json={
            "success": True,
            "kometa_root": "/config/kometa",
            "kometa_root_display": "/config/kometa",
            "venv_python": "python3",
            "venv_python_display": "python3",
            "kometa_version": "0.0.0",
            "local_version": "0.0.0",
            "remote_version": "0.0.0",
            "kometa_update_available": False,
            "log": [],
        },
    )


def _stub_status(route, **overrides):
    payload = {
        "status": "not started",
        "maintenance_active": False,
        "maintenance_paused": False,
        "maintenance_window": None,
        "maintenance_paused_since": None,
        "queued_started_at": None,
        "window_unavailable": False,
        "window_unavailable_since": None,
        "pending_start": False,
        "pending_requested_at": None,
    }
    payload.update(overrides)
    route.fulfill(status=200, json=payload)


def _wait_for_run_now_enabled(page):
    page.wait_for_function(
        "() => { const btn = document.getElementById('run-now'); return btn && !btn.disabled; }",
        timeout=15000,
    )


def _allow_final_gate(qs_module, monkeypatch):
    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *_args, **_kwargs: {
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


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1280, 390])
def test_integrity_refresh_warns_without_disabling_run(page, live_server, monkeypatch, qs_module, tmp_path, width):
    from blueprints import kometa_updates
    from modules import kometa_integrity as integrity

    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
    monkeypatch.setattr(qs_module.persistence, "check_minimum_settings", lambda: (True, True, True, True))
    root = tmp_path / "managed"
    shipped = {"kometa.py": b"vanilla", "requirements.txt": b"requests", "VERSION": b"1.0.0", "defaults/overlays/images/rating.png": b"original image"}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in shipped.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            archive.writestr(f"Kometa-test/{name}", content)
    commit = "a" * 40
    (root / ".kometa_sha").write_text(commit, encoding="utf-8")
    integrity.write_manifest(root, integrity.manifest_from_zip(buffer.getvalue(), commit, "develop"))
    monkeypatch.setattr(qs_module, "current_integrity", lambda: integrity.check_integrity(root))
    monkeypatch.setattr(kometa_updates, "current_integrity", lambda *_args, **_kwargs: integrity.check_integrity(root))
    page.set_viewport_size({"width": width, "height": 900})
    page.route("**/validate-kometa-root", _stub_validate_root)
    page.route("**/kometa-status", lambda route: _stub_status(route))
    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    _wait_for_run_now_enabled(page)
    panel = page.locator("#kometa-integrity-panel")
    expect(panel).to_contain_text("Kometa Integrity: CLEAN")
    (root / "defaults/overlays/images/rating.png").write_bytes(b"modified image")
    page.locator("#refresh-kometa-integrity").click()
    expect(panel).to_contain_text("Kometa Integrity: MODIFIED")
    expect(panel).to_contain_text("Modified: defaults/overlays/images/rating.png")
    expect(panel).to_contain_text("entire runtime config/ directory is preserved")
    expect(page.locator("#run-now")).to_be_enabled()
    expect(page.locator("#refresh-kometa-integrity")).to_be_enabled()
    assert panel.evaluate("el => el.scrollWidth <= el.clientWidth + 1")
    panel.scroll_into_view_if_needed()
    screenshot = Path("artifacts") / f"kometa-integrity-{width}.png"
    screenshot.parent.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot))
    (root / "defaults/overlays/images/rating.png").write_bytes(shipped["defaults/overlays/images/rating.png"])
    page.locator("#refresh-kometa-integrity").click()
    expect(panel).to_contain_text("Kometa Integrity: CLEAN")
    expect(panel).not_to_contain_text("Modified:")


@pytest.mark.e2e
def test_run_now_queued_toast(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []),
    )

    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    page.route("**/validate-kometa-root", _stub_validate_root)
    page.route("**/kometa-status", lambda route: _stub_status(route))
    page.route(
        "**/start-kometa",
        lambda route: route.fulfill(status=202, json={"status": "queued", "maintenance_window": "01:00-02:00"}),
    )

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")

    _wait_for_run_now_enabled(page)
    run_now = page.locator("#run-now")
    run_now.click()

    expect(run_now).to_have_text(re.compile("Waiting"))
    toast = page.locator(".toast .toast-body").filter(has_text="Quickstart will launch Kometa when it ends.")
    expect(toast).to_be_visible()


@pytest.mark.e2e
def test_stop_modal_and_state_reset(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []),
    )

    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    page.route("**/validate-kometa-root", _stub_validate_root)
    page.route("**/kometa-status", lambda route: _stub_status(route))
    page.route("**/start-kometa", lambda route: route.fulfill(status=200, json={"status": "Kometa started", "pid": 111}))
    page.route("**/stop-kometa", lambda route: route.fulfill(status=200, json={"success": True, "message": "Kometa stopped"}))

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")

    _wait_for_run_now_enabled(page)
    run_now = page.locator("#run-now")
    run_now.click()

    stop_btn = page.locator("#stop-now")
    expect(stop_btn).to_be_visible()
    stop_btn.click()

    modal = page.locator("#stop-kometa-modal")
    expect(modal).to_be_visible()
    page.locator("#confirm-stop-kometa").click()

    expect(stop_btn).to_be_hidden()
    expect(run_now).to_be_enabled()


@pytest.mark.e2e
def test_reconnect_after_refresh_shows_running(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []),
    )
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    page.route("**/validate-kometa-root", _stub_validate_root)
    page.route(
        "**/kometa-status",
        lambda route: route.fulfill(
            status=200,
            json={
                "status": "running",
                "pid": 999,
                "elapsed_seconds": 120,
                "maintenance_active": False,
                "maintenance_paused": False,
                "maintenance_window": None,
                "maintenance_paused_since": None,
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": False,
                "pending_requested_at": None,
            },
        ),
    )

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    stop_btn = page.locator("#stop-now")
    run_now = page.locator("#run-now")
    expect(stop_btn).to_be_visible()
    expect(run_now).to_be_disabled()

    page.reload()
    expect(stop_btn).to_be_visible()
    expect(run_now).to_be_disabled()


@pytest.mark.e2e
def test_maintenance_pause_resume_toasts(page, live_server):
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")

    page.evaluate("""() => {
          window.QS_handleMaintenanceStatus({
            status: 'running',
            maintenance_paused: true,
            maintenance_window: '01:00-02:00',
            maintenance_active: true,
            pending_start: false,
            queued_started_at: null,
            window_unavailable: false
          })
        }""")
    toast1 = page.locator(".toast .toast-body").filter(has_text="Kometa paused for Plex maintenance")
    expect(toast1).to_be_visible()

    page.evaluate("""() => {
          window.QS_handleMaintenanceStatus({
            status: 'running',
            maintenance_paused: false,
            maintenance_window: '01:00-02:00',
            maintenance_active: false,
            pending_start: false,
            queued_started_at: null,
            window_unavailable: false
          })
        }""")
    toast2 = page.locator(".toast .toast-body").filter(has_text="Plex maintenance ended")
    expect(toast2).to_be_visible()


@pytest.mark.e2e
def test_queued_run_auto_start_toast(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []),
    )
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    page.route("**/validate-kometa-root", _stub_validate_root)
    page.route(
        "**/start-kometa",
        lambda route: route.fulfill(status=202, json={"status": "queued", "maintenance_window": "01:00-02:00"}),
    )

    status_calls = {"count": 0}

    def handle_status(route):
        status_calls["count"] += 1
        if status_calls["count"] == 1:
            payload = {
                "status": "not started",
                "maintenance_active": False,
                "maintenance_paused": False,
                "maintenance_window": None,
                "maintenance_paused_since": None,
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": False,
                "pending_requested_at": None,
            }
        elif status_calls["count"] < 3:
            payload = {
                "status": "not started",
                "maintenance_active": True,
                "maintenance_paused": False,
                "maintenance_window": "01:00-02:00",
                "maintenance_paused_since": None,
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": True,
                "pending_requested_at": "2026-03-31T00:00:00Z",
            }
        else:
            payload = {
                "status": "running",
                "elapsed_seconds": 5,
                "maintenance_active": False,
                "maintenance_paused": False,
                "maintenance_window": "01:00-02:00",
                "maintenance_paused_since": None,
                "queued_started_at": "2026-03-31T00:10:00Z",
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": False,
                "pending_requested_at": None,
            }
        route.fulfill(status=200, json=payload)

    page.route("**/kometa-status", handle_status)

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    _wait_for_run_now_enabled(page)
    run_now = page.locator("#run-now")
    run_now.click()

    page.wait_for_function("() => typeof window.QS_handleMaintenanceStatus === 'function'")
    page.evaluate("""() => {
          window.QS_handleMaintenanceStatus({
            status: 'running',
            maintenance_active: false,
            maintenance_paused: false,
            maintenance_window: '01:00-02:00',
            maintenance_paused_since: null,
            queued_started_at: '2026-03-31T00:10:00Z',
            window_unavailable: false,
            window_unavailable_since: null,
            pending_start: false,
            pending_requested_at: null
          })
        }""")

    toast = page.locator(".toast .toast-body").filter(has_text="Kometa started from queued request")
    expect(toast).to_be_visible()


@pytest.mark.e2e
def test_validate_kometa_root_syncs_managed_assets_to_kometa(page, live_server, monkeypatch, qs_module):
    config_name = "pytest_e2e_kometa_copy"
    config_dir = Path(qs_module.helpers.CONFIG_DIR)
    kometa_root = Path(qs_module.app.config["KOMETA_ROOT"])
    source_yaml = Path("config") / f"{config_name}_config.yml"

    managed_dir = config_dir / config_name / "collection_files" / "mov-library_movies"
    managed_dir.mkdir(parents=True, exist_ok=True)
    (managed_dir / "collections.yml").write_text(
        "collections:\n  test:\n    plex_search:\n      any:\n        title: Example\n",
        encoding="utf-8",
    )
    source_yaml.write_text(
        f"libraries:\n  Movies:\n    collection_files:\n      - file: config/{config_name}/collection_files/mov-library_movies/collections.yml\n",
        encoding="utf-8",
    )

    (kometa_root / "kometa.py").write_text("print('kometa')\n", encoding="utf-8")
    (kometa_root / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (kometa_root / "VERSION").write_text("0.0.0\n", encoding="utf-8")
    venv_scripts = kometa_root / "kometa-venv" / "Scripts"
    venv_scripts.mkdir(parents=True, exist_ok=True)
    (venv_scripts / "python.exe").write_text("", encoding="utf-8")
    (venv_scripts / "pip.exe").write_text("", encoding="utf-8")

    stale_dir = kometa_root / "config" / config_name / "overlay_files" / "mov-library_movies"
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "stale.yml").write_text("overlays:\n  stale:\n    template:\n      - name: ribbon\n", encoding="utf-8")

    monkeypatch.setattr(qs_module.shutil, "which", lambda _cmd: "C:/Python/python.exe")
    monkeypatch.setattr(
        qs_module.subprocess,
        "check_output",
        lambda cmd, **_kwargs: "Python 3.12.0" if "--version" in cmd else "git version 2.45.0",
    )

    class _RunResult:
        def __init__(self, stdout):
            self.stdout = stdout

    monkeypatch.setattr(qs_module.subprocess, "run", lambda *args, **kwargs: _RunResult("Requirement already satisfied"))

    page.goto(f"{live_server}/static/favicon.png", wait_until="load")

    payload = page.evaluate(
        """async ({ path, configName }) => {
          const res = await fetch('/validate-kometa-root', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, config_name: configName })
          })
          return { status: res.status, body: await res.json() }
        }""",
        {"path": str(kometa_root), "configName": source_yaml.name},
    )

    assert payload["status"] == 200, payload
    assert payload["body"]["success"] is True
    assert any("YAML copied to Kometa config folder" in line for line in payload["body"]["log"])
    assert any("managed library artifact tree" in line for line in payload["body"]["log"])

    copied_yaml = kometa_root / "config" / source_yaml.name
    copied_collection = kometa_root / "config" / config_name / "collection_files" / "mov-library_movies" / "collections.yml"
    assert copied_yaml.exists()
    assert copied_collection.exists()
    assert copied_collection.read_text(encoding="utf-8") == (managed_dir / "collections.yml").read_text(encoding="utf-8")
    assert not stale_dir.exists()
    source_yaml.unlink(missing_ok=True)
