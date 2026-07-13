import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
MACROS_PATH = ROOT / "templates" / "partials" / "_macros.html"


def _load_universe_collection():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    for group in data:
        for collection in group.get("collections", []):
            if collection.get("id") == "collection_universe":
                return collection
    raise AssertionError("Missing collection_universe")


def _field_map(collection):
    return {item["key"]: item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}


def test_universe_exposes_inherited_shared_family_level_fields():
    collection = _load_universe_collection()
    fields = _field_map(collection)

    expected = {
        "schedule": {"type": "schedule"},
        "name_mapping": {"type": "text_input"},
        "delete_collections_named": {"type": "string_list"},
        "url_poster": {"type": "text_input", "validation_preset": "url"},
        "url_background": {"type": "text_input", "validation_preset": "url"},
        "url_logo": {"type": "text_input", "validation_preset": "url"},
        "url_square_art": {"type": "text_input", "validation_preset": "url"},
    }

    for key, metadata in expected.items():
        assert key in fields
        for meta_key, meta_value in metadata.items():
            assert fields[key].get(meta_key) == meta_value

    exclude_field = fields["exclude"]
    assert exclude_field["type"] == "string_list"
    assert exclude_field["validation_preset"] == "universe_key"
    assert exclude_field["input_mode"] == "select"

    section_defs = collection.get("template_variable_sections") or []
    section_ids = [section.get("id") for section in section_defs if isinstance(section, dict)]
    assert section_ids[:8] == [
        "basics",
        "naming",
        "scope_schedule",
        "child_defaults",
        "child_override_maps",
        "artwork",
        "automation_defaults",
        "automation_override_maps",
    ]
    assert "universe_mcu" in section_ids
    assert "universe_star" in section_ids
    assert any(section.get("default_open") is True for section in section_defs if section.get("id") == "basics")

    assert fields["collection_section"]["section"] == "basics"
    assert fields["name_mapping"]["section"] == "naming"
    assert fields["ignore_imdb_ids"]["section"] == "scope_schedule"
    assert fields["visible_home"]["section"] == "child_defaults"
    assert fields["child_imdb_list_overrides"]["section"] == "child_override_maps"
    assert fields["url_poster"]["section"] == "artwork"
    assert fields["radarr_folder"]["section"] == "automation_defaults"
    assert fields["child_radarr_folder_overrides"]["section"] == "automation_override_maps"
    assert fields["use_mcu"]["section"] == "universe_mcu"
    assert fields["visible_home_mcu"]["section"] == "universe_mcu"


def test_universe_uses_dynamic_child_override_surface_for_inherited_prefixes():
    fields = _field_map(_load_universe_collection())

    expected = {
        "child_order_overrides": ("order_", "string", "universe_key", None),
        "child_schedule_overrides": ("schedule_", "string", "universe_key", None),
        "child_name_mapping_overrides": ("name_mapping_", "string", "universe_key", None),
        "child_delete_collections_named_overrides": ("delete_collections_named_", "string_list", "universe_key", None),
        "child_imdb_list_overrides": ("imdb_list_", "string_list", "universe_key", None),
        "child_mdblist_list_overrides": ("mdblist_list_", "string_list", "universe_key", None),
        "child_trakt_list_overrides": ("trakt_list_", "string_list", "universe_key", None),
        "child_sync_mode_overrides": ("sync_mode_", "select", "universe_key", None),
        "child_collection_order_overrides": ("collection_order_", "select", "universe_key", None),
        "child_cache_builders_overrides": ("cache_builders_", "string", "universe_key", None),
        "child_url_poster_overrides": ("url_poster_", "string", "universe_key", "url"),
        "child_url_background_overrides": ("url_background_", "string", "universe_key", "url"),
        "child_url_logo_overrides": ("url_logo_", "string", "universe_key", "url"),
        "child_url_square_art_overrides": ("url_square_art_", "string", "universe_key", "url"),
        "child_radarr_folder_overrides": ("radarr_folder_", "string", "universe_key", None),
        "child_radarr_tag_overrides": ("radarr_tag_", "string_list", "universe_key", None),
        "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", "universe_key", None),
        "child_radarr_upgrade_existing_overrides": ("radarr_upgrade_existing_", "boolean", "universe_key", None),
        "child_radarr_monitor_existing_overrides": ("radarr_monitor_existing_", "boolean", "universe_key", None),
        "child_radarr_search_overrides": ("radarr_search_", "boolean", "universe_key", None),
        "child_sonarr_folder_overrides": ("sonarr_folder_", "string", "universe_key", None),
        "child_sonarr_tag_overrides": ("sonarr_tag_", "string_list", "universe_key", None),
        "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", "universe_key", None),
        "child_sonarr_upgrade_existing_overrides": ("sonarr_upgrade_existing_", "boolean", "universe_key", None),
        "child_sonarr_monitor_existing_overrides": ("sonarr_monitor_existing_", "boolean", "universe_key", None),
        "child_sonarr_search_overrides": ("sonarr_search_", "boolean", "universe_key", None),
    }

    for key, (child_prefix, value_kind, key_validation_preset, value_validation_preset) in expected.items():
        assert key in fields
        field = fields[key]
        assert field["type"] == "mapping_list"
        assert field["dynamic_child_prefix"] == child_prefix
        assert field["dynamic_child_value_kind"] == value_kind
        assert field.get("key_validation_preset") == key_validation_preset
        assert field.get("key_input_mode") == "select"
        if value_validation_preset is None:
            assert "validation_preset" not in field
        else:
            assert field.get("validation_preset") == value_validation_preset
        assert field.get("key_placeholder")
        assert field.get("value_placeholder")

    assert fields["child_radarr_folder_overrides"]["media_types"] == ["movie"]
    assert fields["child_radarr_tag_overrides"]["media_types"] == ["movie"]
    assert fields["child_item_radarr_tag_overrides"]["media_types"] == ["movie"]
    assert fields["child_radarr_upgrade_existing_overrides"]["media_types"] == ["movie"]
    assert fields["child_radarr_monitor_existing_overrides"]["media_types"] == ["movie"]
    assert fields["child_radarr_search_overrides"]["media_types"] == ["movie"]

    assert fields["child_sonarr_folder_overrides"]["media_types"] == ["show"]
    assert fields["child_sonarr_tag_overrides"]["media_types"] == ["show"]
    assert fields["child_item_sonarr_tag_overrides"]["media_types"] == ["show"]
    assert fields["child_sonarr_upgrade_existing_overrides"]["media_types"] == ["show"]
    assert fields["child_sonarr_monitor_existing_overrides"]["media_types"] == ["show"]
    assert fields["child_sonarr_search_overrides"]["media_types"] == ["show"]


def test_mapping_list_macro_supports_select_backed_keys():
    text = MACROS_PATH.read_text(encoding="utf-8")

    assert 'data-key-input-mode="{{ key_input_mode }}"' in text
    assert "data-key-options='{{ key_options_json }}'" in text
    assert "{% if key_input_mode == 'select' %}" in text
    assert '<select class="form-select" data-template-mapping-key' in text


def test_string_list_macro_supports_select_backed_inputs_and_schedule_type():
    text = MACROS_PATH.read_text(encoding="utf-8")

    assert 'data-input-mode="{{ string_input_mode }}"' in text
    assert "data-select-options='{{ string_options_json }}'" in text
    assert "{% if string_input_mode == 'select' %}" in text
    assert '<select class="form-select" id="{{ input_name }}_input" data-template-string-input' in text
    assert "{% elif item.type == 'schedule' or (item.key is defined and item.key.startswith('schedule_')) %}" in text
