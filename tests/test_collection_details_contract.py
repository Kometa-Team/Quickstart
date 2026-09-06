import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS_PATH = ROOT / "templates" / "partials" / "_macros.html"
STYLES_PATH = ROOT / "static" / "css" / "styles.css"
LIBRARIES_JS_PATH = ROOT / "static" / "local-js" / "025-libraries.js"
EVENT_HANDLER_JS_PATH = ROOT / "static" / "local-js" / "eventHandler.js"
VALIDATION_JS_PATH = ROOT / "static" / "local-js" / "validationHandler.js"
START_JS_PATH = ROOT / "static" / "local-js" / "001-start.js"
OVERLAYS_PATH = ROOT / "static" / "json" / "quickstart_overlays.json"
LIBRARIES_TEMPLATE_PATH = ROOT / "templates" / "025-libraries.html"
PLAYLIST_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_playlists.html"
LIBRARY_CARD_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_card.html"
CORE_SEPARATOR_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_core_separator.html"
ADVANCED_SEPARATOR_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_advanced_separator.html"
COLLECTION_FILES_ACCORDION_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_collection_files_accordion.html"
COLLECTION_FILES_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_collection_files.html"
METADATA_FILES_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_metadata_files.html"
OVERLAY_FILES_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_overlay_files.html"
RADARR_OVERRIDES_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_radarr_overrides.html"
SONARR_OVERRIDES_PARTIAL_PATH = ROOT / "templates" / "partials" / "_library_sonarr_overrides.html"


def test_collection_macros_render_collapsible_detail_section():
    macros = MACROS_PATH.read_text(encoding="utf-8")

    assert "collection-details-toggle" in macros
    assert "collection-detail-actions" in macros
    assert 'data-collection-parent-reset="true"' in macros
    assert "Reset {{ group.accordion }}" in macros
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


def test_event_handler_does_not_scan_selects_inside_input_loop():
    script = EVENT_HANDLER_JS_PATH.read_text(encoding="utf-8")
    attach_section = script.split("initializeOverlays(libraryId, isMovie)", 1)[1]
    attach_section = attach_section.split("// Attach attribute_reset_overlays listeners", 1)[0]

    assert "function queryScopedElements" in script
    assert "attachLibraryListeners: function (scope = document)" in script
    assert "reattachmentScopes.forEach(scope => EventHandler.attachLibraryListeners(scope))" in script
    assert attach_section.index("library.querySelectorAll('.accordion select')") < attach_section.index("library.querySelectorAll('.accordion input')")
    input_loop = attach_section.split("library.querySelectorAll('.accordion input')", 1)[1]
    assert "library.querySelectorAll('.accordion select')" not in input_loop


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
    assert "function isOverlayTemplateGroupActiveForCounts" in script
    assert "if (!isOverlayTemplateGroupActiveForCounts(group)) return total" in script
    assert "const activeGroup = isOverlayTemplateGroupActiveForCounts(group)" in script


def test_schedule_override_comparison_normalizes_month_day_padding():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "function normalizeScheduleOverrideValue" in script
    assert "normalizeMonthDay" in script
    assert "primaryField.closest('[data-schedule-builder]')" in script
    assert "normalizeScheduleOverrideValue(value) !== normalizeScheduleOverrideValue(defaultValue)" in script
    assert "const scheduleEquivalent = input.closest('[data-schedule-builder]')" in script


def test_libraries_script_replaces_mirror_confirm_handler():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "copyConfirmBtn.onclick = onConfirm" in script
    assert "copyConfirmBtn.addEventListener('click', onConfirm)" not in script


def test_start_import_confirm_is_single_bound_and_in_flight_guarded():
    script = START_JS_PATH.read_text(encoding="utf-8")

    assert "let importConfirmInFlight = false" in script
    assert "confirmImportButton.dataset.importConfirmBound !== 'true'" in script
    assert "confirmImportButton.dataset.importConfirmBound = 'true'" in script
    assert "if (importConfirmInFlight) return" in script
    assert "importConfirmInFlight = true" in script
    assert "importConfirmInFlight = false" in script


def test_libraries_lookup_label_autosave_uses_narrow_payload():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "function buildLookupLabelPayloadFromCard" in script
    assert "__lookup_labels_only: true" in script
    assert "autosaveActiveLibrary({ quiet: true, lookupLabelsOnly: true })" in script
    assert "lookupLabelsOnly ? buildLookupLabelPayloadFromCard(card) : buildPayloadFromCard(card)" in script


def test_mirror_modal_explains_targets_stay_excluded():
    template = LIBRARIES_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "does not include target libraries in the final config automatically" in template
    assert "runs the normal library validation flow" in template
    assert "placeholder IDs" in template
    assert "enable <strong>Include in config</strong>" in template


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


def test_libraries_page_does_not_auto_load_first_library():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    picker_init = script.split("if (libraryPicker) {", 1)[1].split(
        "document.addEventListener('qs:before-step-navigation'",
        1,
    )[0]

    assert "refreshPickerLabels()" in picker_init
    assert "libraryPicker.value = ''" in picker_init
    assert "loadLibrary(configuredFirst.value, 'initial')" not in picker_init
    assert "loadLibrary(firstLibrary, 'initial')" not in picker_init


def test_library_card_mount_scopes_event_handler_to_current_card():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    initializer_body = script.split("function initializeLibraryCardControls (card, libraryId) {", 1)[1].split(
        "function wireLazyLibrarySections",
        1,
    )[0]
    mount_body = script.split("function mountCard (card, libraryId) {", 1)[1].split(
        "function fetchLibraryFragment",
        1,
    )[0]

    assert "EventHandler.attachLibraryListeners(card)" in initializer_body
    assert "initializeLibraryCardControls(card, libraryId)" in mount_body
    assert "EventHandler.attachLibraryListeners()" not in mount_body


def test_libraries_lazy_loads_heavy_collection_and_overlay_sections():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    movie_settings = (ROOT / "templates" / "partials" / "_movie_library_settings.html").read_text(encoding="utf-8")
    show_settings = (ROOT / "templates" / "partials" / "_show_library_settings.html").read_text(encoding="utf-8")
    routes = (ROOT / "blueprints" / "library_routes.py").read_text(encoding="utf-8")

    assert "function wireLazyLibrarySections" in script
    assert "function wireLazyCollectionGroups" in script
    assert "function loadLazyCollectionGroup" in script
    assert "function markLazyCollectionGroupLoaded" in script
    assert "function markCollectionDefaultsReset" in script
    assert "function clearLazyCollectionShellOverrideSummaries" in script
    assert "function updateLazySectionOverrideSummaries" in script
    assert "shown.bs.collapse" in script
    assert "/section/${encodeURIComponent(sectionName)}" in script
    assert "/section/collections/group/${encodeURIComponent(groupIndex)}" in script
    assert "__loaded_collection_groups" in script
    assert "__reset_collection_defaults" in script
    assert "clearLazyCollectionShellOverrideSummaries(sectionBody)" in script
    assert "await autosaveActiveLibrary({ quiet: true })" in script
    assert "await loadAllLazyCollectionGroups(sectionBody, card)" not in script
    assert "async function loadAllCollectionGroupsForReorder (libraryId)" in script
    assert "await loadLazyCollectionGroup(collapse, card, { expand: false })" in script
    assert "await loadAllCollectionGroupsForReorder(libraryId)" in script
    assert "await loadLazyCollectionGroup(lazyCollapse, card)" in script
    assert "initializeLibraryCardControls(card, libraryId)" in script
    assert "wireLazyLibrarySections(card)" in script
    assert "wireLazyCollectionGroups(card)" in script
    assert "updateLazySectionOverrideSummaries(card)" in script
    assert "data-lazy-override-count" in movie_settings
    assert "data-lazy-override-count" in show_settings
    assert 'data-library-lazy-section="collections"' in movie_settings
    assert 'data-library-lazy-section="overlays"' in movie_settings
    assert 'data-library-lazy-section="collections"' in show_settings
    assert 'data-library-lazy-section="overlays"' in show_settings
    assert "defer_heavy_sections=True" in routes
    assert '@bp.route("/library_fragment/<library_id>/section/<section_name>")' in routes
    assert '@bp.route("/library_fragment/<library_id>/section/collections/group/<int:group_index>")' in routes


def test_collection_section_partials_lazy_load_parent_groups():
    movie_collections = (ROOT / "templates" / "partials" / "_movie_collections.html").read_text(encoding="utf-8")
    show_collections = (ROOT / "templates" / "partials" / "_show_collections.html").read_text(encoding="utf-8")
    group_fragment = (ROOT / "templates" / "partials" / "_collection_group_fragment.html").read_text(encoding="utf-8")

    for partial in (movie_collections, show_collections):
        assert "data-collection-group-shell" in partial
        assert "data-collection-group-lazy-collapse" in partial
        assert "data-collection-group-lazy-placeholder" in partial
        assert 'data-collection-all-reset="true"' in partial
        assert "Reset Collections" in partial
        assert 'data-collection-parent-reset="true"' not in partial
        assert "Reset {{ group.accordion }}" not in partial
        assert "collection_group_override_counts.get(loop.index0, 0)" in partial
        assert "Open this group to load" in partial
        assert "macros.collection_group_section" not in partial

    assert "macros.collection_group_section(library, data, version_info, group, telemetry)" in group_fragment


def test_collection_section_reorder_modal_sorts_by_saved_section_value():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    entries_body = script.split("function getCollectionSectionEntries (libraryId) {", 1)[1].split(
        "function buildCollectionSectionListItem",
        1,
    )[0]
    sort_body = entries_body.split("entries.sort((left, right) => {", 1)[1].split("  })\n  return entries", 1)[0]

    assert "const byValue = compareCollectionSectionValues(left.effectiveValue, right.effectiveValue)" in sort_body
    assert "if (byValue !== 0) return byValue" in sort_body
    assert "return left.domIndex - right.domIndex" in sort_body
    assert "isCollectionless" not in sort_body


def test_collection_section_reorder_modal_hydrates_lazy_collection_groups_before_render():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    click_body = script.split("const trigger = event.target.closest('[data-collection-section-modal-trigger]')", 1)[1].split(
        "const resetButton = event.target.closest('[data-collection-section-reset]')",
        1,
    )[0]

    assert "await loadAllCollectionGroupsForReorder(libraryId)" in click_body
    assert click_body.index("await loadAllCollectionGroupsForReorder(libraryId)") < click_body.index("renderCollectionSectionModalList(modalEl)")
    assert "Loading collection defaults..." in click_body
    assert "Unable to load all collection defaults for reordering. Try again." in click_body


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
    assert 'data-library-override-label="Playlist Files"' in playlists
    assert 'id="{{ library.id }}-playlist-accordion"' in playlists
    assert 'data-library-override-label="Shared Playlist Defaults"' in playlist_vars
    assert 'data-library-override-label="Per-Playlist Modifications"' in playlist_vars
    for label in ("Separators", "Overlay Operations", "Library Operations", "Miscellaneous"):
        assert f'data-library-override-label="{label}"' in movie_attributes
        assert f'data-library-override-label="{label}"' in show_attributes

    assert 'data-default=""' in macros
    assert 'data-default="false"' in macros
    assert 'data-default="false"' in playlists
    assert 'data-default="false"' in playlist_vars


def test_advanced_library_sections_have_override_scope_counts_and_defaults():
    script = LIBRARIES_JS_PATH.read_text(encoding="utf-8")
    library_card = LIBRARY_CARD_PARTIAL_PATH.read_text(encoding="utf-8")
    core_separator = CORE_SEPARATOR_PARTIAL_PATH.read_text(encoding="utf-8")
    advanced_separator = ADVANCED_SEPARATOR_PARTIAL_PATH.read_text(encoding="utf-8")
    movie_settings = (ROOT / "templates" / "partials" / "_movie_library_settings.html").read_text(encoding="utf-8")
    show_settings = (ROOT / "templates" / "partials" / "_show_library_settings.html").read_text(encoding="utf-8")
    collection_files_accordion = COLLECTION_FILES_ACCORDION_PARTIAL_PATH.read_text(encoding="utf-8")
    collection_files = COLLECTION_FILES_PARTIAL_PATH.read_text(encoding="utf-8")
    metadata_files = METADATA_FILES_PARTIAL_PATH.read_text(encoding="utf-8")
    overlay_files = OVERLAY_FILES_PARTIAL_PATH.read_text(encoding="utf-8")
    radarr_overrides = RADARR_OVERRIDES_PARTIAL_PATH.read_text(encoding="utf-8")
    sonarr_overrides = SONARR_OVERRIDES_PARTIAL_PATH.read_text(encoding="utf-8")

    assert "function updateLibraryAggregateOverrideSummaries" in script
    assert "function getLibrarySectionOverrideTotal" in script
    assert "data-library-core-summary" in script
    assert "refreshTemplateOverrideState(card)" in script
    assert "refreshTemplateOverrideState(libraryContainer?.firstElementChild || document)" in script
    assert "[data-playlist-files-editor]" in script
    assert "[data-collection-files-editor]" in script
    assert "[data-metadata-files-editor]" in script
    assert "[data-overlay-files-editor]" in script
    assert "[data-playlist-key-toggle-group]" in script
    assert "[data-playlist-user-picker]" in script
    assert "name.includes('-library_service_')" in script

    assert "data-library-total-summary" in library_card
    assert "Library Defaults" in core_separator
    assert "data-library-core-summary" in core_separator
    assert "data-library-advanced-summary" in advanced_separator
    assert '{% include "partials/_library_core_separator.html" %}' in movie_settings
    assert '{% include "partials/_library_core_separator.html" %}' in show_settings
    assert 'data-library-override-label="Collection Files"' in collection_files_accordion
    assert 'data-library-override-label="Metadata Files"' in metadata_files
    assert 'data-library-override-label="Overlay Files"' in overlay_files
    assert 'data-library-override-label="Radarr Modifications"' in radarr_overrides
    assert 'data-library-override-label="Sonarr Modifications"' in sonarr_overrides
    assert radarr_overrides.count('data-default=""') >= 10
    assert sonarr_overrides.count('data-default=""') >= 10
    assert 'data-library-service-validated="radarr"' in radarr_overrides
    assert 'data-library-service-validated="sonarr"' in sonarr_overrides
    assert 'data-default="[]"' in collection_files
    assert 'data-default="[]"' in metadata_files
    assert 'data-default="[]"' in overlay_files


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
    assert ".accordion-header.template-variable-section-has-overrides > .accordion-button" in styles
    assert ".accordion-header.template-variable-section-has-overrides {\n    border-left:" not in styles
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
