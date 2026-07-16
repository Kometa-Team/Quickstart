import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS_PATH = ROOT / "templates" / "partials" / "_macros.html"
LIBRARIES_JS_PATH = ROOT / "static" / "local-js" / "025-libraries.js"
VALIDATION_JS_PATH = ROOT / "static" / "local-js" / "validationHandler.js"
OVERLAYS_PATH = ROOT / "static" / "json" / "quickstart_overlays.json"


def test_collection_macros_render_collapsible_detail_section():
    macros = MACROS_PATH.read_text(encoding="utf-8")

    assert "collection-details-toggle" in macros
    assert "collection-detail-actions" in macros
    assert 'class="collection-template-section mt-2"' in macros
    assert 'data-detail-section="true"' in macros
    assert 'data-collection-variable-section="true"' in macros
    assert "collection-variable-section-toggle" in macros
    assert "data-collection-section-summary" in macros


def test_libraries_script_wires_collection_detail_toggles():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "function toggleCollectionTemplateSection" in script
    assert "function wireCollectionDetailToggles" in script
    assert "function wireCollectionTemplateSections" in script
    assert "wireCollectionDetailToggles(card)" in script
    assert "wireCollectionTemplateSections(card)" in script
    assert "function wireCollectionVariableSectionToggles" in script
    assert "function wireCollectionVariableSections" in script
    assert "function updateCollectionVariableSectionSummary" in script
    assert "wireCollectionVariableSectionToggles(card)" in script
    assert "wireCollectionVariableSections(card)" in script
    assert "section.dataset.defaultOpen === 'true'" in script


def test_overlay_macros_render_collapsible_variable_sections():
    macros = MACROS_PATH.read_text(encoding="utf-8")

    assert 'class="border rounded p-2 mb-3 collection-variable-section overlay-variable-section"' in macros
    assert 'data-overlay-variable-section="true"' in macros
    assert "overlay-variable-section-toggle" in macros
    assert "data-overlay-section-summary" in macros
    assert 'data-show-label="Show"' in macros
    assert 'data-hide-label="Hide"' in macros
    assert 'data-overlay-variable-section-reset="true"' in macros
    assert "Reset {{ render_group.label }}" in macros
    assert "overlay.id != 'overlay_ratings'" in macros


def test_libraries_script_wires_overlay_variable_sections():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "function wireOverlayVariableSectionToggles" in script
    assert "function wireOverlayVariableSections" in script
    assert "function updateOverlayVariableSectionSummary" in script
    assert "wireOverlayVariableSectionToggles(card)" in script
    assert "wireOverlayVariableSections(card)" in script
    assert "btn.dataset.overlayVariableSectionReset === 'true'" in script


def test_common_overlay_template_variables_have_sections_except_ratings():
    overlay_config = json.loads(OVERLAYS_PATH.read_text(encoding="utf-8"))
    overlays = [overlay for group in overlay_config for overlay in group.get("overlays", [])]
    section_ids = {"basics", "included_items", "font", "background", "placement"}

    for overlay in overlays:
        template_variables = overlay.get("template_variables")
        if not template_variables:
            continue
        if overlay.get("id") == "overlay_ratings":
            assert "template_variable_sections" not in overlay
            continue

        assert {section["id"] for section in overlay["template_variable_sections"]} == section_ids
        values = template_variables.values() if isinstance(template_variables, dict) else [item for item in template_variables if isinstance(item, dict)]
        for details in values:
            assert details.get("section") in section_ids


def test_validation_handler_opens_hidden_detail_sections():
    script = VALIDATION_JS_PATH.read_text(encoding="utf-8")

    assert '[data-detail-section="true"]' in script
    assert "detailSection.style.display = 'block'" in script
    assert "btn.dataset.sectionId === sectionId" in script
