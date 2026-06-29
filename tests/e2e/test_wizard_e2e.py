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


@pytest.mark.e2e
@pytest.mark.parametrize(
    "stem, endpoint, field_inputs, validated_id, success_text",
    [
        (
            "030-tautulli",
            "validate_tautulli",
            {"tautulli_url": "http://tautulli.local:8181", "tautulli_apikey": "k"},
            "tautulli_validated",
            "Tautulli server validated successfully!",
        ),
        (
            "080-gotify",
            "validate_gotify",
            {"gotify_url": "http://gotify.local", "gotify_token": "tok"},
            "gotify_validated",
            "Gotify credentials validated successfully!",
        ),
        (
            "085-ntfy",
            "validate_ntfy",
            {"ntfy_url": "http://ntfy.local", "ntfy_token": "tok", "ntfy_topic": "alerts"},
            "ntfy_validated",
            "ntfy credentials validated successfully!",
        ),
    ],
)
def test_multi_field_validator_wizard_success_flow(page, live_server, stem, endpoint, field_inputs, validated_id, success_text):
    """Multi-field wizards use the createApiKeyValidator factory's
    additionalFieldIds + 2-arg buildPayload (#1334 Step 6 PR 3). Each
    needs every field filled before validation can succeed.
    """

    def handle_validate(route):
        route.fulfill(status=200, json={"valid": True})

    page.route(f"**/{endpoint}", handle_validate)
    page.goto(f"{live_server}/step/{stem}", wait_until="domcontentloaded")

    for input_id, value in field_inputs.items():
        page.locator(f"#{input_id}").fill(value)
    page.locator("#validateButton").click()

    expect(page.locator("#statusMessage")).to_contain_text(success_text)
    expect(page.locator(f"#{validated_id}")).to_have_value("true")
    expect(page.locator("#validateButton")).to_be_disabled()


@pytest.mark.e2e
def test_multi_field_wizard_empty_check_across_fields(page, live_server):
    """Verify the multi-field empty-check on the rendered page: filling
    only the credential without the url should NOT trigger the fetch
    and should show the configured empty message.
    """

    fetch_calls = []

    def handle_validate(route):
        fetch_calls.append(route.request.url)
        route.fulfill(status=200, json={"valid": True})

    page.route("**/validate_gotify", handle_validate)
    page.goto(f"{live_server}/step/080-gotify", wait_until="domcontentloaded")

    page.locator("#gotify_token").fill("some-token")
    # gotify_url deliberately left empty
    page.locator("#validateButton").click()

    expect(page.locator("#statusMessage")).to_contain_text("Please enter both Gotify URL and Token.")
    expect(page.locator("#gotify_validated")).to_have_value("false")
    assert fetch_calls == [], f"expected no fetch but got {fetch_calls}"


@pytest.mark.e2e
@pytest.mark.parametrize(
    "stem, endpoint, field_inputs, validated_id, success_text, response_data, expected_options",
    [
        (
            "110-radarr",
            "validate_radarr",
            {"radarr_url": "http://radarr.local", "radarr_token": "k"},
            "radarr_validated",
            "Radarr API key is valid.",
            {
                "valid": True,
                "root_folders": [{"path": "/movies"}, {"path": "/four-k"}],
                "quality_profiles": [{"name": "HD-1080p"}, {"name": "4K"}],
            },
            {
                "radarr_root_folder_path": ["/movies", "/four-k"],
                "radarr_quality_profile": ["HD-1080p", "4K"],
            },
        ),
        (
            "120-sonarr",
            "validate_sonarr",
            {"sonarr_url": "http://sonarr.local", "sonarr_token": "k"},
            "sonarr_validated",
            "Sonarr API key is valid.",
            {
                "valid": True,
                "root_folders": [{"path": "/tv"}, {"path": "/anime"}],
                "quality_profiles": [{"name": "HD-720p"}, {"name": "HD-1080p"}],
                "language_profiles": [{"name": "English"}, {"name": "Japanese"}],
            },
            {
                "sonarr_root_folder_path": ["/tv", "/anime"],
                "sonarr_quality_profile": ["HD-720p", "HD-1080p"],
                "sonarr_language_profile": ["English", "Japanese"],
            },
        ),
    ],
)
def test_dropdown_populating_wizard_success_flow(
    page,
    live_server,
    stem,
    endpoint,
    field_inputs,
    validated_id,
    success_text,
    response_data,
    expected_options,
):
    """Radarr + Sonarr populate dropdowns from the validate response
    via onValidationSuccess (#1334 Step 6 PR 4a). Verify each dropdown
    receives the expected options after clicking Validate.
    """

    def handle_validate(route):
        route.fulfill(status=200, json=response_data)

    page.route(f"**/{endpoint}", handle_validate)
    page.goto(f"{live_server}/step/{stem}", wait_until="domcontentloaded")

    for input_id, value in field_inputs.items():
        page.locator(f"#{input_id}").fill(value)
    page.locator("#validateButton").click()

    expect(page.locator("#statusMessage")).to_contain_text(success_text)
    expect(page.locator(f"#{validated_id}")).to_have_value("true")

    # Each populated dropdown should contain the expected option values.
    for dropdown_id, expected_values in expected_options.items():
        dropdown = page.locator(f"#{dropdown_id}")
        actual_values = dropdown.evaluate("el => Array.from(el.options).map(o => o.value)")
        for expected in expected_values:
            assert expected in actual_values, f"{dropdown_id} missing option {expected!r}; got {actual_values}"


@pytest.mark.e2e
def test_radarr_pre_submit_blocks_navigation_when_dropdowns_unset(page, live_server):
    """Radarr's onPreSubmit guard should preventDefault on the form
    when validated=true but the root-folder/quality-profile dropdowns
    haven't been chosen. This is the load-bearing replacement for the
    legacy validateRadarrPage() function (#1334 Step 6 PR 4a).

    NOTE: the rendered template injects `initialRadarrQualityProfile`
    and `initialRadarrRootFolderPath` from the saved config. If the
    mock response contains options whose values match those initials,
    populateDropdown will auto-select them and the dropdowns won't be
    "unset" any more. To make the test deterministic regardless of
    saved config, the mock provides option values that won't match
    any plausible saved config ("NO_MATCH_*" prefixes).
    """

    def handle_validate(route):
        route.fulfill(
            status=200,
            json={
                "valid": True,
                "root_folders": [{"path": "NO_MATCH_ROOT_FOLDER"}],
                "quality_profiles": [{"name": "NO_MATCH_QUALITY_PROFILE"}],
            },
        )

    page.route("**/validate_radarr", handle_validate)
    page.goto(f"{live_server}/step/110-radarr", wait_until="domcontentloaded")

    # Validate succeeds, populating the dropdowns but leaving them on placeholder.
    page.locator("#radarr_url").fill("http://radarr.local")
    page.locator("#radarr_token").fill("k")
    page.locator("#validateButton").click()
    expect(page.locator("#radarr_validated")).to_have_value("true")

    # Sanity check: both dropdowns should be on their placeholder ("")
    # since the mock's option values don't match any saved initials.
    expect(page.locator("#radarr_root_folder_path")).to_have_value("")
    expect(page.locator("#radarr_quality_profile")).to_have_value("")

    # Trigger a form submit without selecting dropdowns. Use evaluate to
    # dispatch a real submit event and capture whether it was blocked.
    blocked = page.evaluate("""
        () => {
            const form = document.getElementById('configForm');
            const evt = new Event('submit', { cancelable: true });
            form.dispatchEvent(evt);
            return evt.defaultPrevented;
        }
    """)
    assert blocked is True, "expected form submit to be blocked by onPreSubmit"
    expect(page.locator("#statusMessage")).to_contain_text("Please select a valid Root Folder Path.")
    expect(page.locator("#statusMessage")).to_contain_text("Please select a valid Quality Profile.")


@pytest.mark.e2e
def test_radarr_revalidate_on_load_repopulates_dropdowns(page, live_server):
    """When the user returns to an already-validated Radarr page, the
    factory's revalidateOnLoad option should issue a silent POST and
    repopulate the dropdowns. This proves the silent fetch path.

    Instead of round-tripping through saved state (fragile in the e2e
    harness), this test directly mutates the in-memory wizard state to
    simulate "already validated", then triggers a manual reload of the
    factory module. The unit-level Vitest suite for revalidateOnLoad
    (8 tests) covers the option semantics in isolation; this test
    proves the option is correctly threaded through to the rendered
    wizard config.
    """

    fetch_count = {"n": 0}

    def handle_validate(route):
        fetch_count["n"] += 1
        route.fulfill(
            status=200,
            json={
                "valid": True,
                "root_folders": [{"path": "NO_MATCH_REVAL_FOLDER"}],
                "quality_profiles": [{"name": "NO_MATCH_REVAL_QUALITY"}],
            },
        )

    page.route("**/validate_radarr", handle_validate)
    page.goto(f"{live_server}/step/110-radarr", wait_until="domcontentloaded")

    # Simulate the "returning to a validated page" state by:
    # 1. Pre-filling the credential fields (revalidateOnLoad needs them)
    # 2. Setting radarr_validated='true' (the precondition for the silent fetch)
    # 3. Re-importing the wizard module to trigger the factory's init code
    #    with that state, the same way it would run on a fresh page load.
    page.evaluate("""
        () => {
            document.getElementById('radarr_url').value = 'http://radarr.local';
            document.getElementById('radarr_token').value = 'some-token';
            document.getElementById('radarr_validated').value = 'true';
        }
    """)
    # Re-import the wizard module with a cache buster so the factory's
    # top-level code runs again against the mutated DOM.
    page.evaluate("""
        () => import(`/static/local-js/110-radarr.js?revalidate-test=${Date.now()}`)
    """)
    # Give the silent fetch a moment to resolve.
    page.wait_for_timeout(500)

    # The dropdown should now contain the option from the mock response.
    dropdown_values = page.locator("#radarr_root_folder_path").evaluate("el => Array.from(el.options).map(o => o.value)")
    assert "NO_MATCH_REVAL_FOLDER" in dropdown_values, f"expected revalidateOnLoad to repopulate dropdown; got {dropdown_values}"
    assert fetch_count["n"] >= 1, f"expected at least one silent fetch; got count={fetch_count['n']}"


@pytest.mark.e2e
def test_plex_validator_success_populates_extra_state(page, live_server):
    """Plex's onValidationSuccess hook copies db_cache + 4 library lists
    into hidden form inputs and reveals the "hidden" section. Verify
    each piece of state lands where it should (#1334 Step 6 PR 4b).

    Plex's response shape is asymmetric: success returns
    `{validated: true, ...}` while failure returns `{valid: false, ...}`.
    The factory's `isValid` option lets the wizard configure
    `(data) => data.validated === true` for the success check.
    """

    def handle_validate(route):
        route.fulfill(
            status=200,
            json={
                "validated": True,
                "db_cache": 1024,
                "user_list": ["alice", "bob"],
                "music_libraries": ["Music"],
                "movie_libraries": ["Movies", "4K Movies"],
                "show_libraries": ["TV", "Anime"],
                "has_plex_pass": True,
            },
        )

    page.route("**/validate_plex", handle_validate)
    page.goto(f"{live_server}/step/010-plex", wait_until="domcontentloaded")

    page.locator("#plex_url").fill("http://plex.local:32400")
    page.locator("#plex_token").fill("some-token")
    page.locator("#validateButton").click()

    # Success status + validatedField flip + button disable.
    expect(page.locator("#statusMessage")).to_contain_text("Plex server validated successfully!")
    expect(page.locator("#plex_validated")).to_have_value("true")
    expect(page.locator("#validateButton")).to_be_disabled()

    # Hidden inputs populated by onValidationSuccess.
    # The legacy code copies arrays-as-strings (.value = arrayLiteral)
    # so the JS forms "alice,bob" etc. We just check that each value
    # contains the expected entries (substring match is the contract).
    user_list = page.locator("#tmp_user_list").evaluate("el => el.value")
    assert "alice" in user_list and "bob" in user_list, f"unexpected user_list: {user_list!r}"
    movie_libs = page.locator("#tmp_movie_libraries").evaluate("el => el.value")
    assert "Movies" in movie_libs and "4K Movies" in movie_libs, f"unexpected movies: {movie_libs!r}"
    show_libs = page.locator("#tmp_show_libraries").evaluate("el => el.value")
    assert "TV" in show_libs and "Anime" in show_libs, f"unexpected shows: {show_libs!r}"
    music_libs = page.locator("#tmp_music_libraries").evaluate("el => el.value")
    assert "Music" in music_libs, f"unexpected music: {music_libs!r}"

    # DB cache value pushed into the input.
    expect(page.locator("#plex_db_cache")).to_have_value("1024")

    # Plex Pass success banner visible, warning banner hidden.
    expect(page.locator("#plex-pass-status-success")).to_be_visible()
    expect(page.locator("#plex-pass-status-warning")).to_be_hidden()

    # Hidden section revealed for further config.
    expect(page.locator("#hidden")).to_be_visible()


@pytest.mark.e2e
def test_plex_validator_failure_uses_legacy_failure_message(page, live_server):
    """Plex's failure path: server returns `{valid: false, error: '...'}`.
    The factory's `isValid: (data) => data.validated === true` predicate
    correctly treats this as a failure. The configured static failure
    message is shown (not data.error -- the legacy plex wizard didn't
    forward that field either).
    """

    def handle_validate(route):
        route.fulfill(status=200, json={"valid": False, "error": "bad token"})

    page.route("**/validate_plex", handle_validate)
    page.goto(f"{live_server}/step/010-plex", wait_until="domcontentloaded")

    page.locator("#plex_url").fill("http://plex.local")
    page.locator("#plex_token").fill("badtoken")
    page.locator("#validateButton").click()

    expect(page.locator("#statusMessage")).to_contain_text("Failed to validate Plex server. Please check your URL and Token.")
    expect(page.locator("#plex_validated")).to_have_value("false")


@pytest.mark.e2e
def test_plex_db_cache_mismatch_warning(page, live_server):
    """When the user's db_cache input doesn't match what Plex reports,
    the plexDbCache element shows a warning in error color appended to
    the standard "value retrieved" message. Verifies the bespoke
    mismatch-detection logic survives the migration.
    """

    def handle_validate(route):
        # Server returns db_cache=2048 while the page's default input
        # is something different (1024 from the dummy data).
        route.fulfill(
            status=200,
            json={
                "validated": True,
                "db_cache": 2048,
                "user_list": [],
                "music_libraries": [],
                "movie_libraries": [],
                "show_libraries": [],
                "has_plex_pass": False,
            },
        )

    page.route("**/validate_plex", handle_validate)
    page.goto(f"{live_server}/step/010-plex", wait_until="domcontentloaded")

    # Force a mismatch: set the input to something other than 2048.
    page.evaluate("document.getElementById('plex_db_cache').value = '999'")
    page.locator("#plex_url").fill("http://plex.local")
    page.locator("#plex_token").fill("sometoken")
    page.locator("#validateButton").click()

    # The plexDbCache element should now contain the mismatch warning.
    expect(page.locator("#plexDbCache")).to_contain_text("Database cache value retrieved from server is: 2048 MB")
    expect(page.locator("#plexDbCache")).to_contain_text("Warning: The value in the input box (999 MB) does not match the value retrieved from the server (2048 MB).")
    # And the input value should now be overwritten with the server's value.
    expect(page.locator("#plex_db_cache")).to_have_value("2048")


@pytest.mark.e2e
def test_tmdb_validator_success_enables_navigation_when_dropdowns_chosen(page, live_server):
    """TMDB gates the Next/JumpTo buttons LIVE on (api key validated)
    AND (language chosen) AND (region chosen). After validate succeeds,
    pick both dropdowns and verify navigation is enabled.
    (#1334 Step 6 PR 4c)
    """

    def handle_validate(route):
        route.fulfill(status=200, json={"valid": True})

    page.route("**/validate_tmdb", handle_validate)
    page.goto(f"{live_server}/step/020-tmdb", wait_until="domcontentloaded")

    page.locator("#tmdb_apikey").fill("some-api-key")
    page.locator("#validateButton").click()
    expect(page.locator("#tmdb_validated")).to_have_value("true")
    expect(page.locator("#statusMessage")).to_contain_text("API key is valid!")

    # Pick both dropdowns. The languages/regions are server-rendered
    # from data['iso_639_1_languages'] / data['iso_3166_1_regions'];
    # any non-empty value will do.
    language_options = page.locator("#tmdb_language option").evaluate_all("els => els.map(el => el.value).filter(v => v)")
    region_options = page.locator("#tmdb_region option").evaluate_all("els => els.map(el => el.value).filter(v => v)")
    assert language_options, "tmdb_language dropdown should have non-empty options from server render"
    assert region_options, "tmdb_region dropdown should have non-empty options from server render"

    page.locator("#tmdb_language").select_option(language_options[0])
    page.locator("#tmdb_region").select_option(region_options[0])

    # Both dropdown status callouts should now read "is valid."
    expect(page.locator("#languageStatusMessage")).to_contain_text("Language is valid.")
    expect(page.locator("#regionStatusMessage")).to_contain_text("Region is valid.")

    # Navigation buttons should be enabled.
    expect(page.locator('button[onclick*="next"]')).to_be_enabled()
    expect(page.locator(".dropdown-toggle").first).to_be_enabled()


@pytest.mark.e2e
def test_tmdb_validator_failure_keeps_navigation_disabled(page, live_server):
    """After a failed TMDB validate, even if both dropdowns are picked,
    navigation should stay disabled because (api key validated) is false.
    This is the load-bearing proof that onValidationFailure correctly
    re-runs updateNavigationState. (#1334 Step 6 PR 4c)
    """

    def handle_validate(route):
        route.fulfill(status=200, json={"valid": False})

    page.route("**/validate_tmdb", handle_validate)
    page.goto(f"{live_server}/step/020-tmdb", wait_until="domcontentloaded")

    # Pick the dropdowns FIRST so they're not the gating factor.
    language_options = page.locator("#tmdb_language option").evaluate_all("els => els.map(el => el.value).filter(v => v)")
    region_options = page.locator("#tmdb_region option").evaluate_all("els => els.map(el => el.value).filter(v => v)")
    page.locator("#tmdb_language").select_option(language_options[0])
    page.locator("#tmdb_region").select_option(region_options[0])

    # Now run a failed validate.
    page.locator("#tmdb_apikey").fill("bad-key")
    page.locator("#validateButton").click()
    expect(page.locator("#tmdb_validated")).to_have_value("false")

    # Navigation should remain disabled.
    expect(page.locator('button[onclick*="next"]')).to_be_disabled()


@pytest.mark.e2e
def test_tmdb_dropdown_change_alone_does_not_enable_navigation(page, live_server):
    """Picking the dropdowns without ever validating the api key should
    NOT enable navigation. Tests the wizard-specific dropdown listeners
    correctly check isApiKeyValidated() as part of their gating logic.
    """

    page.goto(f"{live_server}/step/020-tmdb", wait_until="domcontentloaded")

    language_options = page.locator("#tmdb_language option").evaluate_all("els => els.map(el => el.value).filter(v => v)")
    region_options = page.locator("#tmdb_region option").evaluate_all("els => els.map(el => el.value).filter(v => v)")
    page.locator("#tmdb_language").select_option(language_options[0])
    page.locator("#tmdb_region").select_option(region_options[0])

    # Even though both dropdowns now have valid values, the api key was
    # never validated, so navigation must stay disabled.
    expect(page.locator('button[onclick*="next"]')).to_be_disabled()


# Trakt OAuth-PIN tests (#1334 Step 6 PR 4d). A real Trakt validate
# requires `trakt_client_id` to be exactly 64 chars for the
# updateTraktURL() function to generate a non-empty authorization URL.
TRAKT_CLIENT_ID_64 = "a" * 64


@pytest.mark.e2e
def test_trakt_pin_validator_success_populates_six_token_fields(page, live_server):
    """After a successful Trakt PIN validate, the six hidden
    authorization fields must contain the values from the response,
    the PIN+URL fields are cleared, the PIN-flow buttons disabled,
    and the Check Token button enabled.
    """

    def handle_validate(route):
        route.fulfill(
            status=200,
            json={
                "valid": True,
                "trakt_authorization_access_token": "AT-123",
                "trakt_authorization_token_type": "Bearer",
                "trakt_authorization_expires_in": 7200,
                "trakt_authorization_refresh_token": "RT-456",
                "trakt_authorization_scope": "public",
                "trakt_authorization_created_at": 1700000000,
            },
        )

    page.route("**/validate_trakt", handle_validate)
    page.goto(f"{live_server}/step/130-trakt", wait_until="domcontentloaded")

    page.locator("#trakt_client_id").fill(TRAKT_CLIENT_ID_64)
    page.locator("#trakt_client_secret").fill("my-secret")
    page.locator("#trakt_pin").fill("12345678")
    page.locator("#validate_trakt_pin").click()

    # All six access-token fields populated.
    expect(page.locator("#access_token")).to_have_value("AT-123")
    expect(page.locator("#token_type")).to_have_value("Bearer")
    expect(page.locator("#expires_in")).to_have_value("7200")
    expect(page.locator("#refresh_token")).to_have_value("RT-456")
    expect(page.locator("#scope")).to_have_value("public")
    expect(page.locator("#created_at")).to_have_value("1700000000")
    # PIN + URL cleared.
    expect(page.locator("#trakt_pin")).to_have_value("")
    expect(page.locator("#trakt_url")).to_have_value("")
    # PIN-flow buttons disabled, Check Token enabled.
    expect(page.locator("#trakt_open_url")).to_be_disabled()
    expect(page.locator("#validate_trakt_pin")).to_be_disabled()
    expect(page.locator("#trakt_check_token")).to_be_enabled()
    # Validated state flipped to true.
    expect(page.locator("#trakt_validated")).to_have_value("true")
    expect(page.locator("#statusMessage")).to_contain_text("Trakt credentials validated successfully!")


@pytest.mark.e2e
def test_trakt_pin_validator_missing_fields_shows_required_message(page, live_server):
    """With one of id/secret/pin missing, the client-side guard short-
    circuits before the network call and shows the static required-
    fields message.
    """
    requests_made = {"n": 0}

    def handle_validate(route):
        requests_made["n"] += 1
        route.fulfill(status=200, json={"valid": True})

    page.route("**/validate_trakt", handle_validate)
    page.goto(f"{live_server}/step/130-trakt", wait_until="domcontentloaded")

    page.locator("#trakt_client_id").fill(TRAKT_CLIENT_ID_64)
    page.locator("#trakt_client_secret").fill("my-secret")
    # PIN is intentionally empty. The pin field's checkPinField() will
    # have left the validate button disabled, so we force-enable it.
    page.evaluate("document.getElementById('validate_trakt_pin').disabled = false")
    page.locator("#validate_trakt_pin").click()

    expect(page.locator("#statusMessage")).to_contain_text("ID, secret, and PIN are all required.")
    assert requests_made["n"] == 0, "no network call should fire when fields are missing"


@pytest.mark.e2e
def test_trakt_url_button_enabled_when_client_id_is_exactly_64_chars(page, live_server):
    """Verifies the updateTraktURL() inline handler builds the
    authorization URL only when client_id.length === 64, and the
    Retrieve PIN button enables itself when the URL is non-empty.
    """
    page.goto(f"{live_server}/step/130-trakt", wait_until="domcontentloaded")

    # Initially disabled (page just loaded).
    expect(page.locator("#trakt_open_url")).to_be_disabled()

    # Wrong length: still disabled.
    page.locator("#trakt_client_id").fill("a" * 32)
    expect(page.locator("#trakt_url")).to_have_value("")
    expect(page.locator("#trakt_open_url")).to_be_disabled()

    # Right length: URL constructed, button enabled.
    page.locator("#trakt_client_id").fill(TRAKT_CLIENT_ID_64)
    expect(page.locator("#trakt_url")).to_contain_text("")  # readonly so use to_have_value
    trakt_url_value = page.locator("#trakt_url").input_value()
    assert "trakt.tv/oauth/authorize" in trakt_url_value
    assert TRAKT_CLIENT_ID_64 in trakt_url_value
    expect(page.locator("#trakt_open_url")).to_be_enabled()


@pytest.mark.e2e
def test_trakt_check_token_button_initially_disabled_when_no_access_token(page, live_server):
    """isBlankTokenValue treats blank/None/Null as blank. On a fresh
    page where access_token is empty (or the literal string 'None' from
    the persisted state), the Check Token button must start disabled.
    """
    page.goto(f"{live_server}/step/130-trakt", wait_until="domcontentloaded")
    expect(page.locator("#trakt_check_token")).to_be_disabled()


# MAL OAuth tests. MAL's client_id must be exactly 32 chars for the
# updateMALTargetURL() function to generate a non-empty URL.
MAL_CLIENT_ID_32 = "a" * 32


@pytest.mark.e2e
def test_mal_validator_success_populates_four_token_fields(page, live_server):
    """After a successful MAL validate, the four hidden authorization
    fields are populated, both auth-flow buttons disabled, and the
    Check Token button enabled. MAL has 4 fields vs Trakt's 6.
    """

    def handle_validate(route):
        route.fulfill(
            status=200,
            json={
                "valid": True,
                "mal_authorization_access_token": "MAL-AT",
                "mal_authorization_token_type": "Bearer",
                "mal_authorization_expires_in": 2592000,
                "mal_authorization_refresh_token": "MAL-RT",
            },
        )

    page.route("**/validate_mal", handle_validate)
    page.goto(f"{live_server}/step/140-mal", wait_until="domcontentloaded")

    page.locator("#mal_client_id").fill(MAL_CLIENT_ID_32)
    page.locator("#mal_client_secret").fill("mal-secret")
    # mal_code_verifier is a hidden field populated by the server. The
    # template renders {{ data['code_verifier'] }}, which may be empty
    # in test data. Force a value so the validate-payload guard passes.
    page.evaluate("document.getElementById('mal_code_verifier').value = 'V' + 'a'.repeat(42)")
    page.locator("#mal_localhost_url").fill("http://localhost/callback?code=xyz")
    page.locator("#validate_mal_url").click()

    # Four authorization fields populated.
    expect(page.locator("#access_token")).to_have_value("MAL-AT")
    expect(page.locator("#token_type")).to_have_value("Bearer")
    expect(page.locator("#expires_in")).to_have_value("2592000")
    expect(page.locator("#refresh_token")).to_have_value("MAL-RT")
    # Auth-flow buttons disabled, Check Token enabled.
    expect(page.locator("#mal_get_localhost_url")).to_be_disabled()
    expect(page.locator("#validate_mal_url")).to_be_disabled()
    expect(page.locator("#mal_check_token")).to_be_enabled()
    expect(page.locator("#mal_validated")).to_have_value("true")
    expect(page.locator("#statusMessage")).to_contain_text("MyAnimeList credentials validated successfully!")


@pytest.mark.e2e
def test_mal_validator_missing_fields_shows_required_message(page, live_server):
    """Mirror of the Trakt missing-fields test: client-side guard fires
    before any network call.
    """
    requests_made = {"n": 0}

    def handle_validate(route):
        requests_made["n"] += 1
        route.fulfill(status=200, json={"valid": True})

    page.route("**/validate_mal", handle_validate)
    page.goto(f"{live_server}/step/140-mal", wait_until="domcontentloaded")

    page.locator("#mal_client_id").fill(MAL_CLIENT_ID_32)
    page.locator("#mal_client_secret").fill("mal-secret")
    # mal_localhost_url is intentionally empty.
    page.evaluate("document.getElementById('validate_mal_url').disabled = false")
    page.locator("#validate_mal_url").click()

    expect(page.locator("#statusMessage")).to_contain_text("ID, secret, and localhost URL are all required.")
    assert requests_made["n"] == 0


@pytest.mark.e2e
def test_mal_authorize_button_enabled_when_client_id_is_exactly_32_chars(page, live_server):
    """Mirror of the Trakt URL-button test, with MAL's 32-char gate."""
    page.goto(f"{live_server}/step/140-mal", wait_until="domcontentloaded")

    # Initially disabled (URL is empty).
    expect(page.locator("#mal_get_localhost_url")).to_be_disabled()

    # Wrong length: still disabled.
    page.locator("#mal_client_id").fill("a" * 16)
    expect(page.locator("#mal_url")).to_have_value("")
    expect(page.locator("#mal_get_localhost_url")).to_be_disabled()

    # Right length: URL constructed, Authorize button enabled.
    page.locator("#mal_client_id").fill(MAL_CLIENT_ID_32)
    mal_url_value = page.locator("#mal_url").input_value()
    assert "myanimelist.net/v1/oauth2/authorize" in mal_url_value
    assert MAL_CLIENT_ID_32 in mal_url_value
    expect(page.locator("#mal_get_localhost_url")).to_be_enabled()


# These tests cover behaviors that USED to be wired via inline
# oninput="checkPinField" / oninput="checkURLField" attributes in
# the templates and are now driven by addEventListener('input', ...)
# in the JS modules. (Inline-handler-cleanup follow-up to Step 6 PR 4d.)


@pytest.mark.e2e
def test_trakt_validate_button_enables_when_user_types_in_pin_field(page, live_server):
    """Typing into the PIN field should enable the Validate PIN button;
    clearing it should disable it again. Previously wired via inline
    oninput="checkPinField(this)", now via addEventListener.
    """
    page.goto(f"{live_server}/step/130-trakt", wait_until="domcontentloaded")

    # Initially disabled (the page just loaded with no PIN entered).
    expect(page.locator("#validate_trakt_pin")).to_be_disabled()

    page.locator("#trakt_pin").fill("12345678")
    expect(page.locator("#validate_trakt_pin")).to_be_enabled()

    page.locator("#trakt_pin").fill("")
    expect(page.locator("#validate_trakt_pin")).to_be_disabled()


@pytest.mark.e2e
def test_mal_validate_button_enables_when_user_types_in_localhost_url(page, live_server):
    """Typing into the Localhost URL field should enable the Complete
    Authentication button. Previously wired via inline
    oninput="checkURLField(this)", now via addEventListener.
    """
    page.goto(f"{live_server}/step/140-mal", wait_until="domcontentloaded")

    # Initially disabled (no URL filled in).
    expect(page.locator("#validate_mal_url")).to_be_disabled()

    page.locator("#mal_localhost_url").fill("http://localhost/callback?code=xyz")
    expect(page.locator("#validate_mal_url")).to_be_enabled()

    page.locator("#mal_localhost_url").fill("")
    expect(page.locator("#validate_mal_url")).to_be_disabled()


# Webhooks page (#090) inline-handler cleanup. The previous inline
# onchange="showCustomInput(this)" was BROKEN on this page because
# 090-webhooks.js loads as a module, which means showCustomInput was
# module-scoped and not on window. The inline call silently no-op'd,
# leaving the custom-URL panel hidden when users picked 'Custom'.
# These tests pin the corrected addEventListener-based behaviour.


@pytest.mark.e2e
def test_webhooks_changing_to_custom_reveals_custom_url_input(page, live_server):
    """Picking 'Custom' from the dropdown should reveal the custom-URL
    input panel for that webhook. (Was BROKEN in production before this
    PR -- the inline onchange handler couldn't find the module-scoped
    showCustomInput function.)
    """
    page.goto(f"{live_server}/step/090-webhooks", wait_until="domcontentloaded")

    custom_panel = page.locator("#webhooks_error_custom")
    expect(custom_panel).to_be_hidden()

    page.locator("#webhooks_error").select_option("custom")
    expect(custom_panel).to_be_visible()

    # Switching back to 'None' should hide the panel again.
    page.locator("#webhooks_error").select_option("")
    expect(custom_panel).to_be_hidden()


@pytest.mark.e2e
def test_webhooks_validate_button_click_dispatches_to_validate_endpoint(page, live_server):
    """The .validate-button click handler should POST to /validate_webhook.
    Proves the click handler is wired correctly to the new addEventListener
    (was previously inline onclick='validateWebhook(...)' calling a
    window-exposed function).
    """
    captured = {"url": None, "body": None}

    def handle_validate(route, request):
        captured["url"] = request.url
        captured["body"] = request.post_data_json
        route.fulfill(status=200, json={"success": "Webhook OK"})

    page.route("**/validate_webhook", handle_validate)
    page.goto(f"{live_server}/step/090-webhooks", wait_until="domcontentloaded")

    page.locator("#webhooks_error").select_option("custom")
    page.locator("#webhooks_error_custom input.custom-webhook-url").fill("https://example.com/webhook")
    page.locator("#webhooks_error_custom .validate-button").click()

    expect(page.locator("#validation_message_error")).to_contain_text("Webhook OK")
    assert captured["url"] is not None and "validate_webhook" in captured["url"]
    assert captured["body"]["webhook_url"] == "https://example.com/webhook"
    assert "Error" in captured["body"]["message"]  # message includes formatted webhook type


@pytest.mark.e2e
def test_webhooks_typing_in_custom_url_re_enables_validate_button(page, live_server):
    """After a successful validation, the validate button is disabled.
    Editing the URL again should re-enable it so the user can re-validate.
    Replaces the previous inline oninput='setWebhookValidated(false, ...)'
    handler -- the inline handler called setWebhookValidated(false, key)
    which also sets `validateButton.disabled = false`. Verifying THIS
    side effect (rather than the brittle webhooks_validated value, which
    races with markTouched -> updateValidationState in both legacy and
    new code).
    """
    page.route("**/validate_webhook", lambda route: route.fulfill(status=200, json={"success": "OK"}))
    page.goto(f"{live_server}/step/090-webhooks", wait_until="domcontentloaded")

    page.locator("#webhooks_error").select_option("custom")
    url_input = page.locator("#webhooks_error_custom input.custom-webhook-url")
    validate_btn = page.locator("#webhooks_error_custom .validate-button")

    url_input.fill("https://example.com/webhook")
    validate_btn.click()
    # After success the button gets disabled.
    expect(validate_btn).to_be_disabled()

    # Editing the URL should re-enable the button via the new input listener.
    url_input.fill("https://different.example.com/webhook")
    expect(validate_btn).to_be_enabled()


# Config workspace modal (#_config_workspace_modal). The previous
# onchange="toggleConfigInput(this)" relied on a window-exposed
# function in 001-start.js. Now wired via addEventListener inside the
# existing configSelector change handler.


@pytest.mark.e2e
def test_config_workspace_modal_changing_selector_shows_new_config_input(page, live_server):
    """Opening the modal and selecting 'Add Config' from the dropdown
    should reveal the New Config Name input box (#newConfigInput).
    Selecting an existing config should hide it.
    """
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")

    # The modal is in the DOM but starts hidden behind a Bootstrap
    # modal toggle. Show it directly so we can interact with the select.
    page.evaluate("""
        const modalEl = document.getElementById('configSwitchModal')
        if (modalEl) {
            modalEl.classList.add('show')
            modalEl.style.display = 'block'
            modalEl.removeAttribute('aria-hidden')
        }
    """)

    selector = page.locator("#configSelector")
    selector.select_option("add_config")
    # The new-config input box loses the d-none class.
    classes_after_add = page.locator("#newConfigInput").get_attribute("class") or ""
    assert "d-none" not in classes_after_add, f"expected d-none REMOVED after picking 'add_config'; got class='{classes_after_add}'"

    # If there's another option available, picking it should re-add d-none.
    other_options = selector.evaluate("el => Array.from(el.options).map(o => o.value).filter(v => v !== 'add_config')")
    if other_options:
        selector.select_option(other_options[0])
        classes_after_other = page.locator("#newConfigInput").get_attribute("class") or ""
        assert "d-none" in classes_after_other, f"expected d-none ADDED after switching away from add_config; got class='{classes_after_other}'"
