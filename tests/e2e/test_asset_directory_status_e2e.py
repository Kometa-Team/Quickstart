from copy import deepcopy
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.parametrize("viewport,label", [({"width": 1440, "height": 1000}, "desktop"), ({"width": 390, "height": 844}, "mobile")])
@pytest.mark.parametrize("library_type,prefix", [("movie", "mov"), ("show", "sho")])
def test_asset_directory_status_tracks_entered_paths(page, live_server, monkeypatch, qs_module, viewport, label, library_type, prefix):
    library_id = f"{prefix}-library_1"
    plex_settings = {
        "validated": False,
        "user_entered": True,
        "plex": {
            "tmp_movie_libraries": "1" if library_type == "movie" else "",
            "tmp_show_libraries": "1" if library_type == "show" else "",
            "tmp_music_libraries": "",
            "tmp_library_names": json.dumps({"1": "Test Library"}),
        },
    }
    libraries_settings = {"validated": False, "user_entered": True, "libraries": {f"{library_id}-library": "Test Library"}}
    original_retrieve = qs_module.persistence.retrieve_settings

    def retrieve_settings(section):
        if section in ("010-plex", "plex"):
            return deepcopy(plex_settings)
        if section in ("025-libraries", "libraries"):
            return deepcopy(libraries_settings)
        return original_retrieve(section)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", retrieve_settings)
    page.set_viewport_size(viewport)
    response = page.goto(f"{live_server}/step/025-libraries", wait_until="networkidle")
    assert response.status == 200
    page.locator("#libraryPicker").select_option(library_id)
    card = page.locator(f'.library-settings-card[data-library-id="{library_id}"]')
    expect(card).to_be_visible()
    card.locator(f'[data-bs-target="#{library_id}-attributes"]').click()
    card.locator(f'[data-bs-target="#{library_id}-collapseLibrary"]').click()
    container = card.locator("[data-library-asset-directory-container]")
    field = container.locator('input[data-path-rule="asset_directory"]').first
    hint = container.locator('[data-path-hint="platform-status"]').first
    expect(field).to_be_visible()
    expect(field).to_have_attribute("data-path-validation-bound", "true")
    expect(field).to_have_value("")
    expect(hint).to_be_hidden()
    expect(hint).to_have_text("")
    section = container.locator("..")
    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    section.screenshot(path=str(artifacts / f"asset-directory-{library_type}-{label}-blank.png"))

    field.fill("/var/\\0assets")
    expect(hint).to_be_visible()
    expect(hint).to_contain_text("Contains an invalid null sequence.")
    expect(field).to_have_class("form-control is-invalid")
    field.fill("C:/assets")
    expect(hint).to_contain_text("Windows: OK")
    expect(hint).to_contain_text("Windows-style paths are not valid on Linux/macOS/Docker.")
    field.fill("/var/assets")
    expect(hint).to_contain_text("Linux/macOS/Docker: OK")
    section.screenshot(path=str(artifacts / f"asset-directory-{library_type}-{label}-entered.png"))

    section.locator("[data-add-asset-directory]").click()
    expect(container.locator('input[data-path-rule="asset_directory"]')).to_have_count(2)
    new_hint = container.locator('[data-path-hint="platform-status"]').nth(1)
    expect(new_hint).to_be_hidden()
    expect(new_hint).to_have_text("")
    expect(hint).to_be_visible()

    for empty_value in ("", "   ", "none", "NULL"):
        field.fill(empty_value)
        field.blur()
        expect(hint).to_be_hidden()
        expect(hint).to_have_text("")
        expect(field).not_to_have_class("form-control is-invalid")
    assert page.evaluate("window.PathValidation.validateAll(document)") is True
    expect(hint).to_be_hidden()
    expect(new_hint).to_be_hidden()
    box = section.bounding_box()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"] + 1
