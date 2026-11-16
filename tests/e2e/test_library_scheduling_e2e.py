import json

import pytest
from playwright.sync_api import expect

from modules import database, library_scheduling

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("width", [1440, 390])
def test_ordered_library_rules_survive_real_autosave_and_reload(page, live_server, app, isolated_config_dir, qs_module, monkeypatch, library_poster_preview_stub, width):
    name, library_id = f"scheduling_browser_{width}", "mov-library_1"
    rules = [{"schedule": "weekly(monday)", "mode": "added(7)"}, {"schedule": "weekly(tuesday)", "mode": "index(A-F#)"}, {"schedule": "weekly.not(monday|tuesday)", "mode": "full"}]
    database.save_section_data("start", True, True, {"start": {}}, name=name)
    database.save_section_data(
        "plex",
        False,
        True,
        {"plex": {"tmp_movie_libraries": "1,2", "tmp_show_libraries": "", "tmp_music_libraries": "", "tmp_library_names": json.dumps({"1": "Movies", "2": "Other Movies"})}},
        name=name,
    )
    database.save_section_data(
        "libraries", False, True, {"libraries": {f"{library_id}-library": "true", "mov-library_2-library": "true", f"{library_id}-top_level_schedule": rules}}, name=name
    )
    monkeypatch.setattr(library_scheduling, "runtime_support", lambda: {"supported": True, "message": ""})
    for endpoint in ("workspace_status", "workspace_app_readiness", "background-jobs/active"):
        page.route(f"**/{endpoint}*", lambda route: route.fulfill(json={}))
    page.route("**/kometa-status", lambda route: route.fulfill(json={"status": "not_running"}))
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    assert page.request.post(f"{live_server}/switch-config", data={"name": name}).ok
    page.goto(f"{live_server}/step/025-libraries", wait_until="networkidle")
    page.locator("#libraryPicker").select_option(library_id)
    card = page.locator(f'.library-settings-card[data-library-id="{library_id}"]')
    expect(card).to_be_visible()
    card.locator(f'[data-bs-target="#{library_id}-scheduling"]').click()
    section = card.locator("[data-library-scheduling]")
    rows = section.locator("[data-library-schedule-row]")
    expect(rows).to_have_count(3)
    expect(rows.nth(0).locator("[data-processing-kind]")).to_have_value("added")
    rows.nth(0).get_by_role("button", name="Move rule down", exact=True).click()
    expect(rows.nth(1).locator("[data-processing-kind]")).to_have_value("added")
    rows.nth(1).locator("[data-schedule-frequency]").select_option("monthly")
    rows.nth(1).locator("[data-schedule-dates]").fill("1,15,last")
    rows.nth(1).locator("[data-schedule-not]").check()
    rows.nth(1).locator("[data-processing-amount]").fill("30")
    rows.nth(1).locator("[data-processing-unit]").select_option("m")
    rows.nth(2).locator("[data-processing-kind]").select_option("diff")
    section.get_by_role("button", name="Add scheduling rule").click()
    expect(rows).to_have_count(4)
    rows.nth(3).locator("[data-processing-kind]").select_option("index")
    rows.nth(3).locator("[data-processing-first]").fill("G")
    rows.nth(3).locator("[data-processing-last]").fill("Z")
    rows.nth(3).locator("[data-processing-symbols]").check()
    rows.nth(3).get_by_role("button", name="Move rule up", exact=True).click()
    rows.nth(0).get_by_role("button", name="Remove rule", exact=True).click()
    expected = [
        {"schedule": "monthly.not(1|15|last)", "mode": "added(30m)"},
        {"schedule": "daily", "mode": "index(G-Z#)"},
        {"schedule": "weekly.not(monday|tuesday)", "mode": "diff"},
    ]
    assert json.loads(section.locator("[data-library-schedule-value]").input_value()) == expected
    section.get_by_text("YAML preview for this library", exact=True).click()
    expect(section.locator("[data-library-schedule-preview]")).to_contain_text('mode: "added(30m)"')
    with page.expect_response(lambda response: response.url.endswith(f"/autosave_library/{library_id}")) as saved:
        page.locator("#libraryPicker").select_option("mov-library_2")
    assert saved.value.ok, saved.value.text()
    assert database.retrieve_section_data(name, "libraries")[2]["libraries"][f"{library_id}-top_level_schedule"] == expected
    page.reload(wait_until="networkidle")
    page.locator("#libraryPicker").select_option(library_id)
    expect(card).to_be_visible()
    card.locator(f'[data-bs-target="#{library_id}-scheduling"]').click()
    expect(rows).to_have_count(3)
    assert json.loads(section.locator("[data-library-schedule-value]").input_value()) == expected
    expect(rows.nth(0).locator("[data-processing-unit]")).to_have_value("m")
    expect(rows.nth(1).locator("[data-processing-symbols]")).to_be_checked()
    expect(rows.nth(2).locator("[data-processing-kind]")).to_have_value("diff")
