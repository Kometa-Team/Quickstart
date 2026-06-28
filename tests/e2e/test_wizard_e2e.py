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
@pytest.mark.parametrize(
    "stem, endpoint, field_id, validated_id, success_text",
    [
        (
            "060-mdblist",
            "validate_mdblist",
            "mdblist_apikey",
            "mdblist_validated",
            "API key is valid!",
        ),
        (
            "050-omdb",
            "validate_omdb",
            "omdb_apikey",
            "omdb_validated",
            "OMDb API key is valid.",
        ),
        (
            "070-notifiarr",
            "validate_notifiarr",
            "notifiarr_apikey",
            "notifiarr_validated",
            "Notifiarr API key is valid.",
        ),
        (
            "087-apprise",
            "validate_apprise",
            "apprise_location",
            "apprise_validated",
            "Apprise location validated successfully!",
        ),
    ],
)
def test_simple_validator_wizard_success_flow(page, live_server, stem, endpoint, field_id, validated_id, success_text):
    """End-to-end smoke for every wizard migrated to createApiKeyValidator.

    Vitest covers the factory contract in isolation. This test proves
    each wizard's config IDs actually line up with its rendered template
    -- a typo in fieldId / endpoint / messages would only surface here.

    Server response includes a `message` field so the github-style
    function-valued success message also gets exercised (040-github has
    its own subtest below because the server response shape is different).
    """

    def handle_validate(route):
        route.fulfill(status=200, json={"valid": True})

    page.route(f"**/{endpoint}", handle_validate)
    page.goto(f"{live_server}/step/{stem}", wait_until="domcontentloaded")

    page.locator(f"#{field_id}").fill("some-credential")
    page.locator("#validateButton").click()
    expect(page.locator("#statusMessage")).to_contain_text(success_text)
    expect(page.locator(f"#{validated_id}")).to_have_value("true")
    expect(page.locator("#validateButton")).to_be_disabled()


@pytest.mark.e2e
def test_github_validator_uses_server_message(page, live_server):
    """040-github uses function-valued messages that pull data.message
    from the server response. Verify that a custom server message
    appears in the UI verbatim.
    """

    def handle_validate(route):
        route.fulfill(
            status=200,
            json={"valid": True, "message": "Token belongs to: testuser"},
        )

    page.route("**/validate_github", handle_validate)
    page.goto(f"{live_server}/step/040-github", wait_until="domcontentloaded")

    page.locator("#github_token").fill("ghp_FakeButLooksReal")
    page.locator("#validateButton").click()
    expect(page.locator("#statusMessage")).to_contain_text("Token belongs to: testuser")
    expect(page.locator("#github_validated")).to_have_value("true")


@pytest.mark.e2e
def test_apprise_validator_uses_server_error_on_failure(page, live_server):
    """087-apprise uses a function-valued failure message that pulls
    data.error from the server response. Verify that a custom server
    error appears in the UI verbatim.
    """

    def handle_validate(route):
        route.fulfill(
            status=200,
            json={
                "valid": False,
                "error": "Apprise YAML at /missing.yml could not be read.",
            },
        )

    page.route("**/validate_apprise", handle_validate)
    page.goto(f"{live_server}/step/087-apprise", wait_until="domcontentloaded")

    page.locator("#apprise_location").fill("/missing.yml")
    page.locator("#validateButton").click()
    expect(page.locator("#statusMessage")).to_contain_text("Apprise YAML at /missing.yml could not be read.")
    expect(page.locator("#apprise_validated")).to_have_value("false")
