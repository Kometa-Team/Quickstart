import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS_PATH = ROOT / "templates" / "partials" / "_macros.html"
STYLES_PATH = ROOT / "static" / "css" / "styles.css"
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
    assert "template-variable-section-has-overrides" in script
    assert "configuredCount > 0" in script
    assert "updateTemplateGroupOverrideSummary(section)" in script
    assert "updateAncestorOverrideSummaries(group)" in script
    assert "function refreshTemplateOverrideState" in script
    assert "refreshTemplateOverrideState(group.closest('.template-toggle-group') || group)" in script
    assert "function updateTemplateVariableFieldOverrideStates" in script
    assert "data-template-variable-field-override" in script
    assert "[data-collection-field-wrapper]" in script


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
    assert "overlay.id == 'overlay_ratings'" in macros
    assert "'rating_slots'" in macros


def test_libraries_script_wires_overlay_variable_sections():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "function wireOverlayVariableSectionToggles" in script
    assert "function wireOverlayVariableSections" in script
    assert "function updateOverlayVariableSectionSummary" in script
    assert "wireOverlayVariableSectionToggles(card)" in script
    assert "wireOverlayVariableSections(card)" in script
    assert "btn.dataset.overlayVariableSectionReset === 'true'" in script
    assert "template-variable-section-has-overrides" in script
    assert "configuredCount > 0" in script
    assert "data-template-group-override-summary" in script
    assert "data-accordion-override-summary" in script
    assert "findTemplateVariableFieldRow(field)" in script
    assert "refreshTemplateOverrideState(group)" in script


def test_libraries_script_replaces_mirror_confirm_handler():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "copyConfirmBtn.onclick = onConfirm" in script
    assert "copyConfirmBtn.addEventListener('click', onConfirm)" not in script


def test_template_variable_sections_show_override_rail():
    styles = STYLES_PATH.read_text(encoding="utf-8")

    assert ".collection-variable-section.template-variable-section-has-overrides" in styles
    assert ".overlay-variable-section.template-variable-section-has-overrides" in styles
    assert ".template-toggle-group.template-variable-section-has-overrides" in styles
    assert ".accordion-header.template-variable-section-has-overrides" in styles
    assert ".template-variable-field-has-override" in styles
    assert "[data-template-string-list].template-variable-field-has-override" in styles
    assert "background: linear-gradient(90deg, rgba(var(--accent-color), 0.08), transparent 34%);" in styles
    assert "background: var(--theme-primary);" in styles


def test_common_overlay_template_variables_have_sections():
    overlay_config = json.loads(OVERLAYS_PATH.read_text(encoding="utf-8"))
    overlays = [overlay for group in overlay_config for overlay in group.get("overlays", [])]
    section_ids = {"basics", "included_items", "font", "background", "placement"}
    rating_section_ids = {"basics", "rating_slots", "font", "background", "placement"}

    for overlay in overlays:
        template_variables = overlay.get("template_variables")
        if not template_variables:
            continue
        if overlay.get("id") == "overlay_ratings":
            assert {section["id"] for section in overlay["template_variable_sections"]} == rating_section_ids
            assert all(section.get("default_open") is False for section in overlay["template_variable_sections"])
            continue

        assert {section["id"] for section in overlay["template_variable_sections"]} == section_ids
        assert all(section.get("default_open") is False for section in overlay["template_variable_sections"])
        values = template_variables.values() if isinstance(template_variables, dict) else [item for item in template_variables if isinstance(item, dict)]
        for details in values:
            assert details.get("section") in section_ids


def test_validation_handler_opens_hidden_detail_sections():
    script = VALIDATION_JS_PATH.read_text(encoding="utf-8")

    assert '[data-detail-section="true"]' in script
    assert "detailSection.style.display = 'block'" in script
    assert "btn.dataset.sectionId === sectionId" in script
