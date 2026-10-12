import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from modules import database
from test_ratings_source_selection_e2e import _open_collapsed_parents


@pytest.mark.e2e
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("builder", ["movie", "show", "episode"])
def test_default_rating_slots_survive_view_autosave_clear_and_mirror(page, live_server, app, library_poster_preview_stub, builder, width):
    prefix = "mov" if builder == "movie" else "sho"
    config_name = f"ratings_mirror_{builder}_{width}"
    library_ids = [f"{prefix}-library_{index}" for index in range(1, 5)]
    source_id = library_ids[0]
    template = f"{source_id}-{builder}-template_overlay_ratings"
    original = {"rating1": "user", "rating1_image": "letterboxd", "rating2": "critic", "rating2_image": "imdb"}
    if builder == "episode":
        original["rating1_image"] = "tmdb"
    else:
        original.update(rating3="audience", rating3_image="imdb")
    libraries = {f"{library_id}-library": True for library_id in library_ids}
    libraries[f"{source_id}-{builder}-overlay_ratings"] = True
    libraries.update({f"{template}[{key}]": value for key, value in original.items()})
    database.save_section_data("start", True, True, {"start": {}}, name=config_name)
    database.save_section_data(
        "plex",
        False,
        True,
        {
            "plex": {
                "tmp_movie_libraries": "1,2,3,4" if prefix == "mov" else "",
                "tmp_show_libraries": "1,2,3,4" if prefix == "sho" else "",
                "tmp_music_libraries": "",
                "tmp_library_names": json.dumps({str(index): f"Library {index}" for index in range(1, 5)}),
            }
        },
        name=config_name,
    )
    database.save_section_data("libraries", False, True, {"libraries": libraries}, name=config_name)
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.evaluate(
        """async name => {
      const response = await fetch('/switch-config', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})});
      if (!response.ok) throw new Error('Unable to select test config');
    }""",
        config_name,
    )
    page.goto(f"{live_server}/step/025-libraries", wait_until="networkidle")
    picker = page.locator("#libraryPicker")

    def open_source():
        expect(picker).to_be_enabled(timeout=45000)
        picker.select_option(source_id)
        card = page.locator(f'.library-settings-card[data-library-id="{source_id}"]')
        expect(card).to_be_visible(timeout=45000)
        expect(picker).to_be_enabled(timeout=45000)
        collapse = card.locator(f"#{source_id}-overlays")
        if not collapse.evaluate("element => element.classList.contains('show')"):
            card.locator(f'[data-bs-target="#{source_id}-overlays"]').click()
        expect(card.locator('[data-library-lazy-section="overlays"]')).to_have_count(0, timeout=45000)
        expect(collapse).to_have_class(re.compile(r"\bcollapse\s+show\b"))
        ratings = card.locator(f'.template-toggle-group[data-overlay-id="overlay_ratings"][data-overlay-type="{builder}"]')
        _open_collapsed_parents(ratings, card)
        first = ratings.locator(f'select[name="{template}[rating1]"]')
        if not first.is_visible():
            ratings.locator(".overlay-details-toggle").click()
        if not first.is_visible():
            first.locator('xpath=ancestor::*[@data-overlay-variable-section="true"]').locator(".overlay-variable-section-toggle").click()
        expect(first).to_be_visible()
        return card, ratings

    def assert_saved(expected, ids):
        with app.app_context():
            stored = database.retrieve_section_data(config_name, "libraries")[2]["libraries"]
        for library_id in ids:
            for key, value in expected.items():
                assert stored.get(f"{library_id}-{builder}-template_overlay_ratings[{key}]") == value

    _card, ratings = open_source()
    for key, value in original.items():
        expect(ratings.locator(f'select[name="{template}[{key}]"]')).to_have_value(value)
    with page.expect_response(lambda response: response.url.endswith(f"/autosave_library/{source_id}") and response.request.method == "POST") as saved:
        picker.select_option(library_ids[1])
    assert saved.value.json()["success"] is True
    expect(page.locator(f'.library-settings-card[data-library-id="{library_ids[1]}"]')).to_be_visible(timeout=45000)
    expect(picker).to_be_enabled(timeout=45000)
    assert_saved(original, [source_id])

    _card, ratings = open_source()
    cleared_slot = "rating2" if builder == "episode" else "rating3"
    ratings.locator(f'select[name="{template}[{cleared_slot}]"]').select_option("")
    image = ratings.locator(f'select[name="{template}[{cleared_slot}_image]"]')
    image_group = image.locator("xpath=..")
    image_group.locator(".rating-image-dropdown-toggle").click()
    image_group.locator('.rating-image-dropdown-item[data-value=""]').click()
    expected = {**original, cleared_slot: "none", f"{cleared_slot}_image": "none"}
    for key, value in original.items():
        if not key.startswith(cleared_slot):
            expect(ratings.locator(f'select[name="{template}[{key}]"]')).to_have_value(value)
    page.locator(f'.copy-library-btn[data-library-id="{source_id}"]').click()
    expect(page.locator("#copyLibraryModal")).to_be_visible()
    page.locator("#copySelectAll").click()
    with page.expect_response(lambda response: response.url.endswith("/copy_library_settings") and response.request.method == "POST") as copied:
        page.locator("#copyLibraryConfirm").click()
    assert copied.value.ok
    assert copied.value.json()["success"] is True
    assert_saved(expected, library_ids)
    page.reload(wait_until="networkidle")
    _card, ratings = open_source()
    for key, value in expected.items():
        expect(ratings.locator(f'select[name="{template}[{key}]"]')).to_have_value("" if value == "none" else value)
    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    ratings.screenshot(path=str(artifacts / f"ratings-autosave-mirror-{builder}-{width}.png"))
