"""Real stylesheet and browser clicks for separator controls loaded after Attributes."""

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect


@pytest.mark.e2e
@pytest.mark.parametrize("kind,media_type", [("mov", "movie"), ("sho", "show")])
def test_separator_collections_are_clickable_after_lazy_load(page, app, kind, media_type):
    root = Path(__file__).resolve().parents[2]
    prefix = f"{kind}-library_clicks"
    definitions = json.loads((root / "static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    separators = [collection for group in definitions for collection in group["collections"] if collection["id"] in {"collection_separator_award", "collection_separator_chart"}]
    library = {"id": prefix, "name": "Library", "type": media_type}
    data = {"libraries": {f"{prefix}-template_variables[use_separator]": "gray"}}
    with app.test_request_context():
        macros = app.jinja_env.get_template("partials/_macros.html").module
        attributes = str(
            macros.select_section(library, data, "use_separator", "Separator Style", "Style", "#", [("none", "None"), ("gray", "Gray")], yml_location="template_variables")
        )
        collections = str(macros.collection_group_section(library, data, {}, {"accordion": "Separators", "collections": separators}, {}))
    stylesheet = (root / "static/css/styles.css").read_text(encoding="utf-8")
    html = f'<style>{stylesheet}</style><form id="configForm">{attributes}</form>'

    def serve(route):
        path = urlparse(route.request.url).path
        if path == "/":
            route.fulfill(body=html, content_type="text/html")
        elif path.startswith("/static/local-js/"):
            route.fulfill(body=(root / path.lstrip("/")).read_text(encoding="utf-8"), content_type="text/javascript")
        elif path.startswith("/get_top_imdb_items/"):
            route.fulfill(json={"status": "success", "items": []})
        else:
            route.fulfill(status=404, body="")

    page.route("http://127.0.0.1:8765/**", serve)
    page.goto("http://127.0.0.1:8765/")
    expect(page.get_by_text("Choose a separator style and placeholder here.", exact=False)).to_be_visible()
    page.evaluate(
        """async ({prefix, movie}) => {
        window.separatorModule = await import('/static/local-js/modules/separatorPreview.js');
        window.separatorModule.initializeOverlays(prefix, movie);
    }""",
        {"prefix": prefix, "movie": kind == "mov"},
    )
    # Real collection groups arrive after the Attributes controls are initialized.
    page.evaluate(
        """({html, prefix, movie}) => {
        document.getElementById('configForm').insertAdjacentHTML('beforeend', html);
        window.separatorModule.initializeOverlays(prefix, movie);
    }""",
        {"html": collections, "prefix": prefix, "movie": kind == "mov"},
    )
    chart = page.locator(f"#{prefix}-collection_separator_chart")
    award = page.locator(f"#{prefix}-collection_separator_award")
    assert chart.evaluate("node => getComputedStyle(node).pointerEvents") != "none"
    assert award.evaluate("node => getComputedStyle(node).pointerEvents") != "none"
    chart.check()
    expect(chart).to_be_checked()
    expect(award).not_to_be_checked()
    style = page.locator(f"#{prefix}-template_variables_use_separator")
    style.select_option("none")
    expect(chart).to_be_disabled()
    expect(award).to_be_disabled()
    style.select_option("gray")
    expect(chart).to_be_enabled()
    expect(award).to_be_enabled()
    expect(chart).to_be_checked()
    expect(award).not_to_be_checked()
    chart.uncheck()
    award.check()
    expect(chart).not_to_be_checked()
    expect(award).to_be_checked()
