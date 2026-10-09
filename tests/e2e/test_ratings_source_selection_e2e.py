import json
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from modules import database


def _open_collapsed_parents(element, card):
    ids = element.evaluate("""element => {
      const ids = [];
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        if (parent.matches('.accordion-collapse:not(.show)')) ids.unshift(parent.id);
      }
      return ids;
    }""")
    for collapse_id in ids:
        card.locator(f'[data-bs-target="#{collapse_id}"]').click()
        expect(card.locator(f"#{collapse_id}")).to_have_class(re.compile(r"\bcollapse\s+show\b"))


@pytest.mark.e2e
@pytest.mark.parametrize("viewport,label", [({"width": 1440, "height": 1000}, "desktop"), ({"width": 390, "height": 844}, "mobile")])
@pytest.mark.parametrize("library_type,prefix,builder", [("movie", "mov", "movie"), ("show", "sho", "show"), ("show", "sho", "episode")])
def test_rating_sources_and_none_survive_lazy_loading_and_save(page, live_server, app, library_poster_preview_stub, viewport, label, library_type, prefix, builder):
    config_name = f"ratings_sources_{builder}_{label}"
    library_id = f"{prefix}-library_1"
    other_library_id = f"{prefix}-library_2"
    template_name = f"{library_id}-{builder}-template_overlay_ratings"
    database.save_section_data("start", True, True, {"start": {}}, name=config_name)
    database.save_section_data(
        "plex",
        False,
        True,
        {
            "plex": {
                "tmp_movie_libraries": "1,2" if library_type == "movie" else "",
                "tmp_show_libraries": "1,2" if library_type == "show" else "",
                "tmp_music_libraries": "",
                "tmp_library_names": json.dumps({"1": "Test Library", "2": "Other Library"}),
            }
        },
        name=config_name,
    )
    database.save_section_data("libraries", False, True, {"libraries": {f"{library_id}-library": "true", f"{other_library_id}-library": "true"}}, name=config_name)
    page.set_viewport_size(viewport)
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.evaluate(
        """async name => {
      const response = await fetch('/switch-config', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name})
      });
      if (!response.ok) throw new Error('Unable to select test config');
    }""",
        config_name,
    )
    page.goto(f"{live_server}/step/025-libraries", wait_until="networkidle")
    picker = page.locator("#libraryPicker")
    picker.select_option(library_id)
    card = page.locator(f'.library-settings-card[data-library-id="{library_id}"]')
    expect(card).to_be_visible(timeout=15000)
    card.locator(f'[data-bs-target="#{library_id}-overlays"]').click()
    expect(card.locator('[data-library-lazy-section="overlays"]')).to_have_count(0, timeout=45000)
    expect(card.locator(f"#{library_id}-overlays")).to_have_class(re.compile(r"\bcollapse\s+show\b"))
    ratings = card.locator(f'.template-toggle-group[data-overlay-id="overlay_ratings"][data-overlay-type="{builder}"]')
    _open_collapsed_parents(ratings, card)
    ratings.locator(".overlay-toggle").check()
    ratings.locator(".overlay-details-toggle").click()
    first = ratings.locator(f'select[name="{template_name}[rating1]"]')
    second = ratings.locator(f'select[name="{template_name}[rating2]"]')
    third = ratings.locator(f'select[name="{template_name}[rating3]"]')
    slots = (first, second) if builder == "episode" else (first, second, third)
    section = first.locator('xpath=ancestor::*[@data-overlay-variable-section="true"]')
    if not first.is_visible():
        section.locator(".overlay-variable-section-toggle").click()
    expect(first).to_be_visible()
    for field in slots:
        field.select_option("")
    for field in slots:
        expect(field.locator('option[value="critic"]')).not_to_be_disabled()
        expect(field.locator('option[value="audience"]')).not_to_be_disabled()
        expect(field.locator('option[value="user"]')).not_to_be_disabled()
    first.select_option("critic")
    second.select_option("user")
    if builder != "episode":
        third.select_option("audience")
    expect(second.locator('option[value="critic"]')).to_be_disabled()
    first.select_option("")
    expect(second.locator('option[value="critic"]')).not_to_be_disabled()
    expect(second).to_have_value("user")

    values = first.locator("option").evaluate_all("options => options.map(option => option.value)")
    assert {"", "critic", "audience", "user", "imdb", "tmdb", "floppy"} <= set(values)
    if builder == "episode":
        assert "serializd" in values
        assert "omdb_tomatoes" not in values
        assert "mdb_tomatoes" not in values
        direct_source = "imdb"
    else:
        assert {"omdb_tomatoes", "mdb_tomatoes", "plex_tomatoes", "mdb_letterboxd", "anidb", "mal"} <= set(values)
        assert ("serializd" in values) is (builder == "show")
        direct_source = "plex_tomatoes"
        plex_source = card.locator(f"#{library_id}-attribute_mass_user_rating_update_plex_tomatoes")
        mdb_source = card.locator(f"#{library_id}-attribute_mass_user_rating_update_mdb_tomatoes")
        expect(plex_source).to_be_checked()
        _open_collapsed_parents(plex_source, card)
        plex_source.uncheck()
        mdb_source.check()
        image = ratings.locator(f'select[name="{template_name}[rating2_image]"]')
        _open_collapsed_parents(image, card)
        image.select_option("imdb")
        image.select_option("rt_tomato")
        expect(mdb_source).to_be_checked()
        expect(plex_source).not_to_be_checked()

    first.select_option(direct_source)
    second.select_option("")
    if builder != "episode":
        third.select_option("tmdb")
    expect(first.locator('option[value="user"]')).not_to_be_disabled()
    expect(first).to_have_value(direct_source)
    card.locator(f'[data-bs-target="#{library_id}-collections"]').click()
    expect(card.locator(f"#{library_id}-collections")).to_have_class(re.compile(r"\bcollapse\s+show\b"), timeout=15000)
    expect(card.locator('[data-library-lazy-section="collections"]')).to_have_count(0, timeout=45000)
    expect(first).to_have_value(direct_source)
    expect(second).to_have_value("")
    if builder != "episode":
        expect(third).to_have_value("tmdb")
    expect(first.locator('option[value="user"]')).not_to_be_disabled()

    _open_collapsed_parents(first, card)
    if not first.is_visible():
        ratings.locator(".overlay-details-toggle").click()
    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    section.scroll_into_view_if_needed()
    section.evaluate("element => window.scrollBy({top: element.getBoundingClientRect().top - 200, behavior: 'instant'})")
    page.screenshot(path=str(artifacts / f"ratings-sources-{builder}-{label}.png"))

    with page.expect_response(lambda response: response.url.endswith(f"/autosave_library/{library_id}") and response.request.method == "POST", timeout=15000) as saved:
        picker.select_option(other_library_id)
    assert saved.value.json()["success"] is True
    with app.app_context():
        saved_fields = database.retrieve_section_data(config_name, "libraries")[2]["libraries"]
    assert saved_fields[f"{template_name}[rating1]"] == direct_source
    assert saved_fields[f"{template_name}[rating2]"] == "none"
    if builder != "episode":
        assert saved_fields[f"{template_name}[rating3]"] == "tmdb"
    picker.select_option(library_id)
    expect(card).to_be_visible(timeout=15000)
    expect(first).to_have_value(direct_source)
    expect(second).to_have_value("")
    page.reload(wait_until="networkidle")
    picker.select_option(library_id)
    expect(card).to_be_visible(timeout=15000)
    card.locator(f'[data-bs-target="#{library_id}-overlays"]').click()
    expect(card.locator('[data-library-lazy-section="overlays"]')).to_have_count(0, timeout=45000)
    expect(first).to_have_value(direct_source)
    expect(second).to_have_value("")
    if builder != "episode":
        expect(third).to_have_value("tmdb")
    expect(first.locator('option[value="user"]')).not_to_be_disabled()
