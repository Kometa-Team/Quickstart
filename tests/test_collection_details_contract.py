import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS_PATH = ROOT / "templates" / "partials" / "_macros.html"
STYLES_PATH = ROOT / "static" / "css" / "styles.css"
LIBRARIES_JS_PATH = ROOT / "static" / "local-js" / "025-libraries.js"
VALIDATION_JS_PATH = ROOT / "static" / "local-js" / "validationHandler.js"
OVERLAYS_PATH = ROOT / "static" / "json" / "quickstart_overlays.json"
LIBRARIES_TEMPLATE_PATH = ROOT / "templates" / "025-libraries.html"
PLAYLIST_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_playlists.html"


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


def test_mirror_modal_explains_targets_stay_excluded():
    template = LIBRARIES_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "does not include target libraries in the final YAML automatically" in template
    assert "runs the normal library validation flow" in template
    assert "placeholder IDs" in template
    assert "enable <strong>Include in YAML</strong>" in template


def test_playlist_toggle_preserves_mirrored_state_when_excluded():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    partial = PLAYLIST_PARTIAL_PATH.read_text(encoding="utf-8")

    assert "{% if playlist_checked %}checked{% endif %}" in partial
    assert "playlistToggle.checked = false" not in script
    assert "payload[el.name] = el.checked ? (el.value || 'true') : 'false'" in script


def test_parent_collection_toggle_does_not_clear_child_toggles():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "child.checked = false" not in script
    assert "child.checked = child.dataset.lastChecked === 'true'" not in script
    assert "child.checked = child.dataset.initialChecked === 'true'" not in script


def test_library_fragment_load_failure_preserves_current_card():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    load_body = script.split("function loadLibrary (libraryId, context = 'switch')", 1)[1].split(
        "if (libraryPicker) {\n  libraryPicker.addEventListener",
        1,
    )[0]

    assert "function fetchLibraryFragment (libraryId, attempt = 0)" in script
    assert "attempt < 1" in script
    assert "credentials: 'same-origin'" in script
    assert "function restorePreviousLibrarySelection (previousLibraryId)" in script
    assert "restorePreviousLibrarySelection(previousLibraryId)" in load_body

    cached_swap = (
        'const cached = libraryCache.querySelector(`[data-library-id="${libraryId}"]`)\n'
        "      if (cached) {\n"
        "        if (requestId !== loadRequestId) return\n"
        "        moveCurrentToCache()\n"
        "        mountCard(cached, libraryId)"
    )
    fetched_swap = "fetchLibraryFragment(libraryId)\n" "        .then(html => {\n" "          if (requestId !== loadRequestId) return\n" "          const parser = new DOMParser()"
    assert cached_swap in load_body
    assert fetched_swap in load_body
    assert load_body.index("fetchLibraryFragment(libraryId)") < load_body.index(
        "if (!card) throw new Error('Empty fragment response')\n" "          moveCurrentToCache()\n" "          mountCard(card, libraryId)"
    )
    assert "Your current library stayed open" in load_body


def test_cached_library_cards_do_not_submit_stale_form_fields():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "function setCachedCardFormSubmission" in script
    assert "el.dataset.qsCachedDisabled = el.disabled ? 'true' : 'false'" in script
    assert "el.disabled = true" in script
    assert "el.disabled = el.dataset.qsCachedDisabled === 'true'" in script
    assert "setCachedCardFormSubmission(current, true)" in script
    assert "setCachedCardFormSubmission(card, false)" in script


def test_schedule_builder_allows_clearing_weekly_days():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "nextValue = buildValueFromInputs(mode) || ''" in script
    assert "const nextRaw = String(hidden.value || '').trim()" in script
    assert "nextValue = buildValueFromInputs(mode) || defaultValue || ''" not in script
    assert "const nextRaw = String(hidden.value || defaultValue || '').trim()" not in script


def test_attributes_and_playlists_have_override_scope_counts_and_resets():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    movie_settings = (ROOT / "templates" / "partials" / "_movie_library_settings.html").read_text(encoding="utf-8")
    show_settings = (ROOT / "templates" / "partials" / "_show_library_settings.html").read_text(encoding="utf-8")
    movie_attributes = (ROOT / "templates" / "partials" / "_movie_attributes.html").read_text(encoding="utf-8")
    show_attributes = (ROOT / "templates" / "partials" / "_show_attributes.html").read_text(encoding="utf-8")
    playlists = PLAYLIST_PARTIAL_PATH.read_text(encoding="utf-8")
    macros = MACROS_PATH.read_text(encoding="utf-8")
    playlist_vars = (ROOT / "templates" / "partials" / "_library_playlist_template_variables.html").read_text(encoding="utf-8")

    assert "function wireLibraryOverrideScopes" in script
    assert "function updateLibraryOverrideScopeSummary" in script
    assert "function getLibraryOverrideScopes" in script
    assert "function clearTemplateVariableFieldOverrideStates" in script
    assert "clearTemplateVariableFieldOverrideStates(root)" in script
    assert "root.matches?.('[data-library-override-scope=\"true\"]')" in script
    assert "refreshTemplateOverrideState(section.closest('.library-settings-card') || section)" in script
    assert 'data-library-override-reset="true"' in script
    assert "wireLibraryOverrideScopes(card)" in script
    assert "name.endsWith('_hidden')" in script

    assert 'data-library-override-label="Attributes"' in movie_settings
    assert 'data-library-override-label="Attributes"' in show_settings
    assert 'data-library-override-label="Playlists"' in playlists
    for label in ("Separators", "Overlay Operations", "Library Operations", "Miscellaneous"):
        assert f'data-library-override-label="{label}"' in movie_attributes
        assert f'data-library-override-label="{label}"' in show_attributes

    assert 'data-default=""' in macros
    assert 'data-default="false"' in macros
    assert 'data-default="false"' in playlists
    assert 'data-default="false"' in playlist_vars


def test_analytics_page_checks_reingest_status_before_loading_trends():
    script = (ROOT / "static" / "local-js" / "905-analytics.js").read_text(encoding="utf-8")

    assert "fetchReingestStatus()\n    .then(data => {" in script
    assert "if (data && (data.status === 'running' || data.status === 'complete')) return" in script
    assert "fetchRuns({ suppressStatus })" in script
    assert "/logscan/trends?limit=${safeLimit}&include_archive_storage=0&include_ingest_health=0&include_incomplete=0" in script
    assert "fetchIncompleteRuns(safeLimit)" in script
    assert "fetchArchiveStorage()" in script
    assert "fetchIngestHealth()" in script


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
