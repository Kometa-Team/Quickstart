"""Real form submissions: unset sorting cannot discard asset-directory edits."""

import json

import pytest
from playwright.sync_api import expect


@pytest.fixture
def hub_settings_browser(page, live_server, qs_module):
    # Bootstrap/CDN availability is unrelated to the save contract.
    page.add_init_script("""
    (() => {
      class Component {
        constructor(el) { this.el = el }
        show() { if (this.el) { this.el.style.display = 'block'; this.el.classList.add('show') } }
        hide() { if (this.el) { this.el.style.display = 'none'; this.el.classList.remove('show') } }
        dispose() {}
        static getInstance(el) { return new Component(el) }
        static getOrCreateInstance(el) { return new Component(el) }
      }
      window.bootstrap = { Tooltip: Component, Toast: Component, Modal: Component, Collapse: Component, Popover: Component, Dropdown: Component };
    })();
    """)
    page.route("https://cdn.jsdelivr.net/**/*.js", lambda route: route.fulfill(body="", content_type="application/javascript"))
    page.set_viewport_size({"width": 1500, "height": 1100})
    for name in ("issue1944_other", "issue1944_browser"):
        response = page.request.post(f"{live_server}/activate-config", data={"name": name})
        assert response.ok, response.text()
    from modules import database

    database.save_section_data(
        "plex",
        False,
        True,
        {
            "plex": {
                "tmp_movie_libraries": "1",
                "tmp_show_libraries": "2",
                "tmp_music_libraries": "",
                "tmp_library_names": json.dumps({"1": "Movies", "2": "TV Shows"}),
                "telemetry": {"plex_pass": False},
            }
        },
        name="issue1944_browser",
    )
    database.save_section_data("libraries", False, True, {"libraries": {"mov-library_1-library": "Movies", "sho-library_2-library": "TV Shows"}}, name="issue1944_browser")
    return "issue1944_browser"


def open_assets(page):
    page.locator("#collapseOne").evaluate("el => el.classList.add('show')")
    return page.locator('[name="asset_directory[movies]"]').first, page.locator('[name="asset_directory[shows]"]').first


@pytest.mark.e2e
def test_fresh_settings_navigation_reload_and_config_switch_autosave(page, live_server, hub_settings_browser):
    from modules import database

    name = hub_settings_browser
    page.goto(f"{live_server}/step/150-settings", wait_until="networkidle")
    expect(page.locator("#auto_sort_hubs")).to_be_disabled()
    expect(page.locator('[name="auto_sort_hubs"]')).to_have_value("")
    movies, shows = open_assets(page)
    movies.fill("/config/assets/movies")
    shows.fill("/config/assets/shows")
    with page.expect_response(lambda r: r.request.method == "POST" and "/step/" in r.url) as saved:
        page.locator('.qs-step-link[data-jumpto-page="020-tmdb"]').first.evaluate("el => el.click()")
    assert saved.value.ok
    assert "auto_sort_hubs=" in saved.value.request.post_data
    assert "auto_sort_hubs=None" not in saved.value.request.post_data
    assert not page.locator("#qs-save-error").count()
    assert database.retrieve_section_data(name, "settings")[2]["settings"]["asset_directory"]["movies"] == ["/config/assets/movies"]
    for reload in (False, True):
        if reload:
            page.reload(wait_until="networkidle")
        else:
            page.goto(f"{live_server}/step/150-settings", wait_until="networkidle")
        movies, shows = open_assets(page)
        expect(movies).to_have_value("/config/assets/movies")
        expect(shows).to_have_value("/config/assets/shows")
        expect(page.locator('[name="auto_sort_hubs"]')).to_have_value("")
    movies.fill("/config/assets/edited")
    page.locator("#configSwitchModal").evaluate("el => { el.style.display = 'block'; el.classList.add('show') }")
    page.locator("#configSwitchSelect").select_option("issue1944_other")
    with page.expect_response(lambda r: r.request.headers.get("x-qs-autosave-only") == "1") as saved:
        page.locator("#configSwitchConfirm").click()
    assert saved.value.status == 200, saved.value.text()
    assert saved.value.json()["success"] is True
    page.wait_for_url("**config_name=issue1944_other")
    assert database.retrieve_section_data(name, "settings")[2]["settings"]["asset_directory"]["movies"] == ["/config/assets/edited"]
    page.goto(f"{live_server}/step/150-settings?config_name={name}", wait_until="networkidle")
    movies, shows = open_assets(page)
    expect(movies).to_have_value("/config/assets/edited")
    expect(shows).to_have_value("/config/assets/shows")


@pytest.mark.e2e
@pytest.mark.parametrize("value", ["bogus", "alpha"])
def test_no_plex_pass_can_clear_saved_value_without_losing_assets(page, live_server, hub_settings_browser, qs_module, value):
    from modules import database

    name = hub_settings_browser
    database.save_section_data(
        "settings",
        False,
        True,
        {"settings": {**qs_module.persistence.get_dummy_data("settings"), "auto_sort_hubs": value, "asset_directory": {"movies": ["/assets/original"]}}},
        name=name,
    )
    page.goto(f"{live_server}/step/150-settings", wait_until="networkidle")
    expect(page.locator("#auto_sort_hubs")).to_be_disabled()
    expect(page.locator('[name="auto_sort_hubs"]')).to_have_value(value)
    if value == "bogus":
        expect(page.locator("#auto_sort_hubs option:checked")).to_have_text("Invalid saved value: bogus")
    page.locator('[data-clear-auto-sort-hubs="auto_sort_hubs"]').evaluate("el => el.closest('.accordion-collapse').classList.add('show')")
    page.locator('[data-clear-auto-sort-hubs="auto_sort_hubs"]').click()
    expect(page.locator('[name="auto_sort_hubs"]')).to_have_value("")
    movies, _shows = open_assets(page)
    movies.fill("/assets/after-clear")
    with page.expect_response(lambda r: r.request.method == "POST" and "/step/" in r.url):
        page.locator('.qs-step-link[data-jumpto-page="020-tmdb"]').first.evaluate("el => el.click()")
    assert not page.locator("#qs-save-error").count()
    stored = database.retrieve_section_data(name, "settings")[2]["settings"]
    assert stored["auto_sort_hubs"] is None
    assert stored["asset_directory"]["movies"] == ["/assets/after-clear"]


@pytest.mark.e2e
def test_config_switch_reports_rejected_save_and_keeps_edits(page, live_server, hub_settings_browser, qs_module):
    from modules import database

    name = hub_settings_browser
    database.save_section_data(
        "settings",
        False,
        True,
        {"settings": {**qs_module.persistence.get_dummy_data("settings"), "auto_sort_hubs": "bogus", "asset_directory": {"movies": ["/assets/original"]}}},
        name=name,
    )
    page.goto(f"{live_server}/step/150-settings", wait_until="networkidle")
    movies, _shows = open_assets(page)
    movies.fill("/assets/unsaved")
    page.locator("#configSwitchModal").evaluate("el => { el.style.display = 'block'; el.classList.add('show') }")
    page.locator("#configSwitchSelect").select_option("issue1944_other")
    with page.expect_response(lambda r: r.request.headers.get("x-qs-autosave-only") == "1") as rejected:
        page.locator("#configSwitchConfirm").click()
    assert rejected.value.status == 400
    assert rejected.value.json()["success"] is False
    expect(page.locator(".toast").filter(has_text="Current page could not be saved")).to_be_visible()
    assert "issue1944_other" not in page.url
    expect(movies).to_have_value("/assets/unsaved")
    assert database.retrieve_section_data(name, "settings")[2]["settings"]["asset_directory"]["movies"] == ["/assets/original"]
