import json
from pathlib import Path
import re

import pytest
from playwright.sync_api import expect

from modules import database


@pytest.mark.e2e
@pytest.mark.parametrize(
    "viewport,label",
    [
        ({"width": 1440, "height": 1000}, "desktop"),
        ({"width": 390, "height": 844}, "mobile"),
    ],
)
@pytest.mark.parametrize("library_type,prefix", [("movie", "mov"), ("show", "sho")])
def test_operation_counts_survive_lazy_loading_and_save(page, live_server, app, viewport, label, library_type, prefix):
    config_name = f"operation_counts_{library_type}_{label}"
    library_id = f"{prefix}-library_1"
    other_library_id = f"{prefix}-library_2"
    operation = "mass_user_rating_update"
    field_prefix = f"{library_id}-attribute_{operation}"
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
    database.save_section_data(
        "libraries",
        False,
        True,
        {
            "libraries": {
                f"{library_id}-library": "true",
                f"{other_library_id}-library": "true",
                f"{field_prefix}_mdb_tomatoes": "true",
            }
        },
        name=config_name,
    )
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
    page.locator("#libraryPicker").select_option(library_id)
    card = page.locator(f'.library-settings-card[data-library-id="{library_id}"]')
    expect(card).to_be_visible(timeout=15000)
    section = card.locator(f"#{library_id}-{operation}-body")
    badge = card.locator(f"#{library_id}-{operation}-header [data-accordion-override-summary]")
    order = card.locator(f"#{field_prefix}_order")
    expect(order).to_have_value('["mdb_tomatoes"]')
    expect(section).to_have_attribute("data-override-count", "1")
    expect(badge).to_have_text("1 modification")
    for rating_type in ("critic", "audience"):
        expect(card.locator(f"#{library_id}-mass_{rating_type}_rating_update-body")).to_have_attribute("data-override-count", "0")

    for lazy_section in ("collections", "overlays"):
        expect(card.locator(f'[data-library-lazy-section="{lazy_section}"]')).to_have_count(1)
        card.locator(f'[data-bs-target="#{library_id}-{lazy_section}"]').click()
        expect(card.locator(f'[data-library-lazy-section="{lazy_section}"]')).to_have_count(0, timeout=15000)
        collapse = card.locator(f"#{library_id}-{lazy_section}")
        expect(collapse).to_have_class(re.compile(r"\bcollapse\s+show\b"))
        expect(section).to_have_attribute("data-override-count", "1")
        expect(badge).to_have_text("1 modification")
        button = card.locator(f'[data-bs-target="#{library_id}-{lazy_section}"]')
        button.click()
        expect(collapse).to_have_class(re.compile(r"\bcollapse$"))
        button.click()
        expect(collapse).to_have_class(re.compile(r"\bcollapse\s+show\b"))
        expect(badge).to_have_text("1 modification")

    ratings = card.locator('.template-toggle-group[data-overlay-id="overlay_ratings"]').first
    collapsed_parents = ratings.evaluate("""element => {
      const ids = [];
      for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        if (parent.matches('.accordion-collapse:not(.show)')) ids.unshift(parent.id);
      }
      return ids;
    }""")
    for collapse_id in collapsed_parents:
        card.locator(f'[data-bs-target="#{collapse_id}"]').click()
        expect(card.locator(f"#{collapse_id}")).to_have_class(re.compile(r"\bcollapse\s+show\b"))
    ratings.locator(".overlay-toggle").check()
    for rating_type in ("user", "critic", "audience"):
        expect(card.locator(f"#{library_id}-mass_{rating_type}_rating_update-body")).to_have_attribute("data-override-count", "1")
        expect(card.locator(f"#{library_id}-mass_{rating_type}_rating_update-header [data-accordion-override-summary]")).to_have_text("1 modification")
    expect(card.locator(f"#{library_id}-collapseLibrary")).to_have_attribute("data-override-count", "3")

    card.locator(f'[data-bs-target="#{library_id}-attributes"]').click()
    card.locator(f'[data-bs-target="#{library_id}-collapseLibrary"]').click()
    card.locator(f'[data-bs-target="#{library_id}-{operation}-body"]').click()
    source = section.locator(f"#{field_prefix}_tmdb")
    source.check()
    expect(section).to_have_attribute("data-override-count", "2")
    expect(badge).to_have_text("2 modifications")
    expect(order).to_have_value('["mdb_tomatoes","tmdb"]')
    source.uncheck()
    expect(badge).to_have_text("1 modification")
    source.check()
    expect(badge).to_have_text("2 modifications")
    expect(order).to_have_value('["mdb_tomatoes","tmdb"]')
    sortable = section.locator(f"#{field_prefix}_sortable")
    last = sortable.locator('[data-value="tmdb"]')
    last.scroll_into_view_if_needed()
    sortable.locator('[data-value="mdb_tomatoes"] .drag-handle').drag_to(last, target_position={"x": 20, "y": last.bounding_box()["height"] - 2})
    expect(order).to_have_value('["tmdb","mdb_tomatoes"]')
    expect(badge).to_have_text("2 modifications")
    custom = section.locator(f"#{field_prefix}_custom_input")
    custom.fill("7.5")
    expect(badge).to_have_text("3 modifications")
    custom.fill("")
    expect(badge).to_have_text("2 modifications")

    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    header = card.locator(f"#{library_id}-{operation}-header")
    header.scroll_into_view_if_needed()
    header.evaluate("element => window.scrollBy({top: element.getBoundingClientRect().top - 200, behavior: 'instant'})")
    badge_box = badge.bounding_box()
    header_box = header.bounding_box()
    assert badge_box and header_box
    assert header_box["x"] <= badge_box["x"]
    assert badge_box["x"] + badge_box["width"] <= header_box["x"] + header_box["width"] + 1
    page.screenshot(path=str(artifacts / f"operation-counts-{library_type}-{label}.png"))

    with page.expect_response(
        lambda response: response.url.endswith(f"/autosave_library/{library_id}") and response.request.method == "POST",
        timeout=15000,
    ) as saved:
        page.locator("#libraryPicker").select_option(other_library_id)
    assert saved.value.json()["success"] is True
    with app.app_context():
        saved_fields = database.retrieve_section_data(config_name, "libraries")[2]["libraries"]
    assert json.loads(saved_fields[f"{field_prefix}_order"]) == ["tmdb", "mdb_tomatoes"]
    expect(page.locator(f'.library-settings-card[data-library-id="{other_library_id}"]')).to_be_visible(timeout=15000)
    page.locator("#libraryPicker").select_option(library_id)
    expect(card).to_be_visible(timeout=15000)
    expect(badge).to_have_text("2 modifications")
    expect(order).to_have_value('["tmdb","mdb_tomatoes"]')

    page.reload(wait_until="networkidle")
    page.locator("#libraryPicker").select_option(library_id)
    expect(card).to_be_visible(timeout=15000)
    expect(section).to_have_attribute("data-override-count", "2")
    expect(badge).to_have_text("2 modifications")
    expect(order).to_have_value('["tmdb","mdb_tomatoes"]')
    card.locator(f'[data-bs-target="#{library_id}-attributes"]').click()
    card.locator(f'[data-bs-target="#{library_id}-collapseLibrary"]').click()
    card.locator(f'[data-bs-target="#{library_id}-{operation}-body"]').click()
    section.locator("[data-library-override-reset]").click()
    expect(section).to_have_attribute("data-override-count", "0")
    expect(badge).to_be_hidden()
    expect(order).to_have_value("[]")
    expect(section.locator('input[type="checkbox"]:checked')).to_have_count(0)
