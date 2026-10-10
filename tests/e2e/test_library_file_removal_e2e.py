import json

import pytest
from playwright.sync_api import expect

from modules import database


@pytest.mark.e2e
@pytest.mark.parametrize("action", ["remove", "reset"])
@pytest.mark.parametrize("width", [1440, 390])
def test_cleared_collection_files_stay_cleared(
    page,
    live_server,
    app,
    isolated_config_dir,
    qs_module,
    monkeypatch,
    library_poster_preview_stub,
    action,
    width,
):
    name = f"file_removal_{action}_{width}"
    library_id = "mov-library_1"
    field = f"{library_id}-collection_files"
    database.save_section_data("start", True, True, {"start": {}}, name=name)
    database.save_section_data(
        "plex",
        False,
        True,
        {
            "plex": {
                "tmp_movie_libraries": "1,2",
                "tmp_show_libraries": "",
                "tmp_music_libraries": "",
                "tmp_library_names": json.dumps({"1": "Movies", "2": "Other Movies"}),
            }
        },
        name=name,
    )
    database.save_section_data(
        "libraries",
        False,
        True,
        {
            "libraries": {
                f"{library_id}-library": "true",
                "mov-library_2-library": "true",
                field: json.dumps([{"type": "url", "location": "https://example.test/missing.yml"}]),
            }
        },
        name=name,
    )
    monkeypatch.setattr(qs_module, "_normalize_library_file_entries_payload", lambda data, *a, **kw: (data, [], False))
    for kind in ("collection_files", "metadata_files", "overlay_files"):
        monkeypatch.setattr(qs_module, f"_validate_library_{kind}", lambda *_: [])
    monkeypatch.setattr(qs_module, "_validate_library_auto_sort_hubs", lambda *_: [])
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.evaluate(
        """async name => {
      const response = await fetch('/switch-config', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})
      });
      if (!response.ok) throw new Error('Unable to select config');
    }""",
        name,
    )
    page.goto(f"{live_server}/step/025-libraries", wait_until="networkidle")
    page.locator("#libraryPicker").select_option(library_id)
    card = page.locator(f'.library-settings-card[data-library-id="{library_id}"]')
    expect(card).to_be_visible()
    card.locator(".library-advanced-toggle").check()
    card.locator(f'[data-bs-target="#{library_id}-collection-files"]').click()
    section = card.locator(f"#{library_id}-collection-files")
    expect(section.locator("[data-collection-file-row]")).to_have_count(1)
    if action == "remove":
        section.locator("[data-remove-collection-file]").click()
    else:
        section.locator("[data-library-override-reset]").click()
    expect(card.locator(f'input[name="{field}"]')).to_have_value("[]")
    with page.expect_response(lambda response: response.url.endswith(f"/autosave_library/{library_id}")) as saved:
        page.locator("#libraryPicker").select_option("mov-library_2")
    assert saved.value.ok
    _, _, data = database.retrieve_section_data(name, "libraries")
    assert data["libraries"][field] == "[]"
    page.reload(wait_until="networkidle")
    page.locator("#libraryPicker").select_option(library_id)
    expect(card.locator(f'input[name="{field}"]')).to_have_value("[]")
