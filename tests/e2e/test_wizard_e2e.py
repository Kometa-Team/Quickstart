import re
from pathlib import Path

import pytest
from playwright.sync_api import expect


def _seed_config(name):
    import modules.database as database
    import quickstart

    database.save_section_data(
        name=name,
        section="start",
        validated=True,
        user_entered=True,
        data={"start": {"config_name": name}, "validated_at": quickstart.utc_now_iso()},
    )


def _ordered_stems():
    import modules.helpers as helpers
    import quickstart

    with quickstart.app.app_context():
        return [Path(file).stem for file, _display_name in helpers.get_menu_list()]


def _goto_step(page, live_server, stem):
    page.goto(f"{live_server}/step/{stem}", wait_until="domcontentloaded")


def _step_shell(page):
    return page.locator("#configForm").first


@pytest.mark.e2e
def test_config_switch_auto_saves_current_page(page, live_server, app):
    import modules.database as database

    source_config = "pytest_switch_source"
    target_config = "pytest_switch_target"
    _seed_config(source_config)
    _seed_config(target_config)

    page.goto(f"{live_server}/step/020-tmdb", wait_until="domcontentloaded")
    page.evaluate(
        """async (name) => {
          const res = await fetch('/switch-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
          })
          if (!res.ok) throw new Error('failed to set source config')
        }""",
        source_config,
    )
    page.reload(wait_until="domcontentloaded")

    page.locator("#tmdb_apikey").fill("autosave-before-switch")
    page.locator(".config-badge-button").click()
    page.locator("#configSwitchSelect").select_option(target_config)
    page.locator("#configSwitchConfirm").click()

    expect(page.locator(".qs-main-page-meta-value")).to_contain_text(target_config)
    with app.app_context():
        _validated, user_entered, data = database.retrieve_section_data(source_config, "tmdb")
    assert user_entered is True
    assert data["tmdb"]["apikey"] == "autosave-before-switch"


@pytest.mark.e2e
def test_wizard_happy_path_all_steps(page, live_server):
    stems = _ordered_stems()
    assert stems

    for stem in stems:
        _goto_step(page, live_server, stem)
        expect(_step_shell(page)).to_be_visible()


@pytest.mark.e2e
def test_back_forward_navigation(page, live_server):
    stems = _ordered_stems()
    assert len(stems) >= 2

    first, second = stems[0], stems[1]
    _goto_step(page, live_server, first)
    _goto_step(page, live_server, second)

    page.go_back()
    expect(page).to_have_url(re.compile(f"/step/{re.escape(first)}$"))
    expect(_step_shell(page)).to_be_visible()

    page.go_forward()
    expect(page).to_have_url(re.compile(f"/step/{re.escape(second)}$"))
    expect(_step_shell(page)).to_be_visible()


@pytest.mark.e2e
def test_maintenance_badge_visible_on_any_page(page, live_server):
    def handle_status(route):
        route.fulfill(
            status=200,
            json={
                "status": "running",
                "elapsed_seconds": 90,
                "maintenance_active": True,
                "maintenance_paused": True,
                "maintenance_window": "01:00-02:00",
                "maintenance_paused_since": "2026-03-31T00:00:00Z",
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": False,
                "pending_requested_at": None,
            },
        )

    page.route("**/kometa-status", handle_status)
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.wait_for_timeout(1600)
    badge = page.locator("#qs-maintenance-badge")
    expect(badge).not_to_have_class(re.compile(r"\bd-none\b"))


@pytest.mark.e2e
def test_running_pill_visible(page, live_server):
    def handle_status(route):
        route.fulfill(
            status=200,
            json={
                "status": "running",
                "elapsed_seconds": 75,
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
        )

    page.route("**/kometa-status", handle_status)
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.wait_for_timeout(1600)
    badge = page.locator("#qs-running-badge")
    expect(badge).not_to_have_class(re.compile(r"\bd-none\b"))
    expect(badge).to_contain_text("Kometa running")


@pytest.mark.e2e
def test_mdblist_validate_button_uses_factory(page, live_server):
    """Smoke test for the createApiKeyValidator factory on a real page.

    060-mdblist.js was migrated to the shared factory under #1334 Step 6
    PR 1. The Vitest suite for the factory locks in the contract in
    isolation, but only an actual rendered page proves that the
    factory's IDs (validateButton, statusMessage, toggleApikeyVisibility)
    line up with the wizard template.
    """

    def handle_validate(route):
        route.fulfill(status=200, json={"valid": True})

    page.route("**/validate_mdblist", handle_validate)
    page.goto(f"{live_server}/step/060-mdblist", wait_until="domcontentloaded")

    page.locator("#mdblist_apikey").fill("some-key")
    page.locator("#validateButton").click()
    expect(page.locator("#statusMessage")).to_contain_text("API key is valid!")
    expect(page.locator("#mdblist_validated")).to_have_value("true")
    expect(page.locator("#validateButton")).to_be_disabled()
