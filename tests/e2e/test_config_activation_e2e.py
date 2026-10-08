from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect

from modules import database


@pytest.mark.e2e
@pytest.mark.parametrize("step", ["001-start", "020-tmdb"])
@pytest.mark.parametrize("stale_query", [True, False], ids=["previous-config-url", "session-only"])
@pytest.mark.parametrize("viewport,label", [({"width": 1440, "height": 1000}, "desktop"), ({"width": 390, "height": 844}, "mobile")])
def test_save_and_activate_selects_new_config_after_navigation(page, live_server, app, step, stale_query, viewport, label):
    source = f"activation_source_{step[:3]}_{label}_{stale_query}".lower()
    target = f"activation_target_{step[:3]}_{label}_{stale_query}".lower()
    database.save_section_data("start", True, True, {"start": {"config_name": source}}, name=source)
    database.save_section_data("tmdb", True, True, {"tmdb": {"apikey": "source-only-key"}}, name=source)
    page.set_viewport_size(viewport)
    page.goto(f"{live_server}/step/{step}?config_name={source}", wait_until="networkidle")
    if not stale_query:
        page.goto(f"{live_server}/step/{step}?keep=1#config", wait_until="networkidle")
    else:
        page.goto(f"{live_server}/step/{step}?config_name={source}&keep=1#config", wait_until="networkidle")

    page.locator(".config-badge-button").click()
    expect(page.locator("#configSwitchModal")).to_be_visible()
    page.locator("#configSelector").select_option("add_config")
    page.locator("#newConfigName").fill(target)
    expect(page.locator("#saveConfigButton")).to_be_enabled()
    with page.expect_navigation(wait_until="domcontentloaded"):
        page.locator("#saveConfigButton").click()

    parsed = urlparse(page.url)
    assert parse_qs(parsed.query) == {"config_name": [target], "keep": ["1"]}
    assert parsed.fragment == "config"
    expect(page.locator("#qs-active-config-input")).to_have_value(target)
    expect(page.locator(".qs-main-page-meta-value").first).to_have_text(target)
    if step == "020-tmdb":
        expect(page.locator("#tmdb_apikey")).not_to_have_value("source-only-key")
    with app.app_context():
        assert target in database.get_unique_config_names()
        assert database.retrieve_section_data(target, "tmdb")[2] is None
        assert database.retrieve_section_data(source, "tmdb")[2]["tmdb"]["apikey"] == "source-only-key"

    page.goto(f"{live_server}/step/010-plex", wait_until="domcontentloaded")
    expect(page.locator("#qs-active-config-input")).to_have_value(target)
