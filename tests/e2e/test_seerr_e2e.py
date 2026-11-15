import json

import pytest
from flask import render_template
from playwright.sync_api import expect

from modules import database, seerr

pytestmark = pytest.mark.e2e


def test_seerr_browser_edits_preserve_false_tier_overrides_and_inheritance(page, live_server, app, monkeypatch):
    name = "seerrbrowser"
    library_id = "mov-library_1"
    for endpoint in ("workspace_status", "workspace_app_readiness", "background-jobs/active"):
        page.route(f"**/{endpoint}*", lambda route: route.fulfill(json={}))
    page.route("**/kometa-status", lambda route: route.fulfill(json={"status": "not_running"}))
    monkeypatch.setattr(seerr, "validate_connection", lambda connection: ({"valid": True}, 200))
    assert page.request.post(f"{live_server}/activate-config", data={"name": name}).ok
    database.save_section_data(section="seerr", validated=True, user_entered=True, name=name, data={"seerr": {"url": "http://seerr", "apikey": "test-key"}})
    database.save_section_data(section="libraries", validated=False, user_entered=True, name=name, data={"libraries": {f"{library_id}-library": "Movies"}})
    page.goto(f"{live_server}/step/125-seerr", wait_until="domcontentloaded")
    expect(page.locator("#seerr_apikey")).to_have_attribute("type", "password")
    values = {f"{library_id}-attribute_seerr_url": "http://override-seerr", f"{library_id}-attribute_seerr_apikey": "override-key"}
    with app.test_request_context():
        html = render_template("partials/_library_seerr.html", library={"id": library_id, "type": "movie"}, data={"libraries": values})
    page.evaluate(
        "html => { document.body.innerHTML = '<form id=seerr-browser-form>' + html + '</form>'; document.querySelector('[data-advanced-section]').classList.remove('d-none'); document.querySelector('.accordion-collapse').classList.add('show') }",
        html,
    )
    page.evaluate("() => import('/static/local-js/modules/seerrOptions.js')")
    page.locator("[data-seerr-inherit]").click()
    expect(page.locator(f'[name="{library_id}-attribute_seerr_url"]')).to_have_value("")
    expect(page.locator(f'[name="{library_id}-attribute_seerr_apikey"]')).to_have_value("")
    page.locator("[data-seerr-switch]").nth(1).locator("[data-seerr-explicit]").check()
    expect(page.locator("[data-seerr-switch]").nth(1).locator("[data-seerr-switch-output]")).to_have_value("false")
    page.locator('[name$="[seerr_instance]"]').select_option("both")
    page.locator("[data-seerr-overrides] > summary").click()
    page.locator('[data-seerr-tier="standard"][data-seerr-field="quality_profile"]').fill("HD-1080p")
    page.locator('[data-seerr-tier="4k"][data-seerr-field="quality_profile"]').fill("4")
    page.locator('[data-seerr-tier="4k"][data-seerr-field="server_id"]').fill("2")
    with page.expect_response(lambda response: "/validate_library_seerr/" in response.url, timeout=30000):
        page.locator("[data-seerr-validate]").click()
    expect(page.locator("[data-seerr-status]")).to_contain_text("validated")
    result = page.evaluate(
        """async libraryId => {
      const payload = Object.fromEntries(new FormData(document.querySelector('#seerr-browser-form')));
      payload[`${libraryId}-library`] = 'Movies';
      const response = await fetch(`/autosave_library/${libraryId}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      return {ok: response.ok, body: await response.json()};
    }""",
        library_id,
    )
    assert result["ok"], result
    _validated, _entered, saved = database.retrieve_section_data(name, "libraries")
    libraries = saved["libraries"]
    assert not libraries.get(f"{library_id}-attribute_seerr_url")
    assert libraries[f"{library_id}-template_variables[seerr_add_existing]"] is False
    assert libraries[f"{library_id}-template_variables[seerr_instance]"] == "both"
    overrides = json.loads(libraries[f"{library_id}-template_variables[seerr_overrides]"])
    assert overrides == {"standard": {"quality_profile": "HD-1080p"}, "4k": {"quality_profile": 4, "server_id": 2}}
