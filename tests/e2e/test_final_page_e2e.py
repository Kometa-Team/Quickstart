import re

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

    page.goto(f"{live_server}/step/900-final", wait_until="domcontentloaded")

    _wait_for_run_now_enabled(page)
    run_now = page.locator("#run-now")
    run_now.click()

    expect(run_now).to_have_text(re.compile("Waiting"))
    toast = page.locator(".toast .toast-body").filter(has_text="Kometa will start automatically")
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

    page.goto(f"{live_server}/step/900-final", wait_until="domcontentloaded")

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

    page.goto(f"{live_server}/step/900-final", wait_until="domcontentloaded")
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

    page.goto(f"{live_server}/step/900-final", wait_until="domcontentloaded")
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
