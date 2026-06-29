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
