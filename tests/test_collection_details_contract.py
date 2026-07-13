from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS_PATH = ROOT / "templates" / "partials" / "_macros.html"
LIBRARIES_JS_PATH = ROOT / "static" / "local-js" / "025-libraries.js"
VALIDATION_JS_PATH = ROOT / "static" / "local-js" / "validationHandler.js"


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


def test_validation_handler_opens_hidden_detail_sections():
    script = VALIDATION_JS_PATH.read_text(encoding="utf-8")

    assert '[data-detail-section="true"]' in script
    assert "detailSection.style.display = 'block'" in script
    assert "btn.dataset.sectionId === sectionId" in script
