import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect
from ruamel.yaml import YAML

from modules import database


@pytest.mark.e2e
def test_ratings_preview_positions_survive_autosave_and_yaml(page, live_server, app, qs_module, monkeypatch, library_poster_preview_stub):
    # Keep CDN dependencies and rating badge downloads deterministic offline.
    badge = Path(__file__).resolve().parents[2] / "static/images/default-1000x1500.png"
    page.route("**/defaults/overlays/images/rating/**", lambda route: route.fulfill(path=str(badge)))
    page.add_init_script("""document.addEventListener('DOMContentLoaded', () => {
      const Tooltip = window.bootstrap.Tooltip;
      Tooltip.getInstance ||= () => null;
      Tooltip.getOrCreateInstance ||= () => ({setContent() {}, hide() {}, dispose() {}});
      window.Sortable ||= class { static create() { return new this(); } destroy() {} };
    })""")
    config_name = "ratings_position_yaml"
    library_id = "sho-library_1"
    database.save_section_data("start", True, True, {"start": {}}, name=config_name)
    database.save_section_data(
        "plex",
        False,
        True,
        {"plex": {"tmp_show_libraries": "1,2", "tmp_movie_libraries": "", "tmp_music_libraries": "", "tmp_library_names": json.dumps({"1": "TV Shows", "2": "Other Shows"})}},
        name=config_name,
    )
    database.save_section_data(
        "libraries",
        False,
        True,
        {
            "libraries": {
                f"{library_id}-library": "TV Shows",
                "sho-library_2-library": "Other Shows",
                f"{library_id}-collection_collectionless": True,
                f"{library_id}-show-overlay_ratings": True,
                f"{library_id}-show-template_overlay_ratings[horizontal_position]": "right",
                f"{library_id}-episode-overlay_ratings": True,
            }
        },
        name=config_name,
    )
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

    def open_overlays():
        expect(picker).to_be_enabled()
        picker.select_option(library_id)
        card = page.locator(f'.library-settings-card[data-library-id="{library_id}"]')
        expect(card).to_be_visible()
        expect(picker).to_be_enabled(timeout=45000)
        collapse = card.locator(f"#{library_id}-overlays")
        # Trigger the production lazy loader without depending on Bootstrap's CDN.
        collapse.evaluate("""element => {
          element.classList.add('show');
          element.dispatchEvent(new Event('shown.bs.collapse', {bubbles: true}));
        }""")
        expect(card.locator('[data-library-lazy-section="overlays"]')).to_have_count(0, timeout=45000)
        expect(collapse).to_have_class(re.compile(r"\bcollapse\s+show\b"))
        return card

    card = open_overlays()
    positions = {"show": "right", "episode": "right"}
    for level, position in positions.items():
        field = card.locator(f'select[name="{library_id}-{level}-template_overlay_ratings[horizontal_position]"]')
        # Leave episode's UI default untouched: this is the reproduction.
        expect(field).to_have_value(position)
        layer = page.locator(f'[data-overlay-id="{library_id}-{level}-template_overlay_ratings"]').first
        # Check the actual preview layer's horizontal anchor, normalized to its board.
        page.wait_for_function(
            """([id, position]) => {
          const layer = document.querySelector(`[data-overlay-id="${id}"]`);
          if (!layer || layer.style.display === 'none') return false;
          const board = layer.parentElement;
          const left = parseFloat(layer.style.left);
          const width = parseFloat(layer.style.width);
          const available = board.clientWidth - width;
          if (!(available > 0)) return false;
          const fraction = left / available;
          return position === 'right' ? fraction > 0.8 : position === 'left' ? fraction < 0.2 : Math.abs(fraction - 0.5) < 0.1;
        }""",
            arg=[f"{library_id}-{level}-template_overlay_ratings", position],
        )
        expect(layer).to_be_attached()

    with page.expect_response(lambda response: response.url.endswith(f"/autosave_library/{library_id}") and response.request.method == "POST") as saved:
        picker.select_option("sho-library_2")
    assert saved.value.json()["success"] is True
    with app.app_context():
        stored = database.retrieve_section_data(config_name, "libraries")[2]["libraries"]
    for level, position in positions.items():
        assert stored[f"{library_id}-{level}-template_overlay_ratings[horizontal_position]"] == position
        assert stored[f"{library_id}-{level}-template_overlay_ratings[vertical_position]"] == "center"

    # Build from the persisted browser payload, through the production YAML pipeline.
    with monkeypatch.context() as patch:
        patch.setattr(qs_module.output.helpers, "get_template_list", lambda: {"libraries": {"name": "Libraries", "stem": "025-libraries", "raw_name": "libraries"}})
        patch.setattr(qs_module.output.helpers, "get_plex_summary", lambda: "Plex summary unavailable")
        patch.setattr(qs_module.output.helpers, "get_quickstart_settings_summary", lambda: [])
        patch.setattr(qs_module.output.helpers, "get_library_summaries", lambda _names: "TV Shows")
        patch.setattr(
            qs_module.output.persistence, "retrieve_settings", lambda section: {"validated": True, "libraries": stored} if section == "025-libraries" else {"validated": False}
        )
        with app.app_context():
            _valid, _error, _data, yaml_text, _errors = qs_module.output.build_config(header_style="single line", config_name=config_name)
    parsed = YAML(typ="safe", pure=True).load(yaml_text)
    entries = parsed["libraries"]["TV Shows"]["overlay_files"]
    ratings = {entry.get("template_variables", {}).get("builder_level", "show"): entry["template_variables"] for entry in entries if entry.get("default") == "ratings"}
    assert set(ratings) == {"show", "episode"}
    for level, position in positions.items():
        assert ratings[level]["horizontal_position"] == position
        assert ratings[level]["vertical_position"] == "center"
    page.reload(wait_until="networkidle")
    card = open_overlays()
    for level, position in positions.items():
        expect(card.locator(f'select[name="{library_id}-{level}-template_overlay_ratings[horizontal_position]"]')).to_have_value(position)
