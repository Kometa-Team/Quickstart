import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
LIBRARIES_JS_PATH = ROOT / "static" / "local-js" / "025-libraries.js"


def _load_collection(collection_id):
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    for group in data:
        for collection in group.get("collections", []):
            if collection.get("id") == collection_id:
                return collection
    raise AssertionError(f"Missing {collection_id}")


def _field_map(collection):
    return {item["key"]: item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}


def _assert_mapping(field, child_prefix, value_kind, section, validation_preset=None, media_types=None):
    assert field["type"] == "mapping_list"
    assert field["dynamic_child_prefix"] == child_prefix
    assert field["dynamic_child_value_kind"] == value_kind
    assert field["section"] == section
    assert field["key_validation_preset"] == "language_key"
    assert field["key_input_mode"] == "select"
    if validation_preset is None:
        assert "validation_preset" not in field
    else:
        assert field["validation_preset"] == validation_preset
    if media_types is None:
        assert "media_types" not in field
    else:
        assert field["media_types"] == media_types


def test_language_key_preset_is_select_backed():
    source = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    assert "const languageCollectionKeys" in source
    assert "language_key: {" in source
    for code in ['"en"', '"fr"', '"ja"', '"ko"', '"myn"', '"other"']:
        assert code in source


def test_audio_and_subtitle_language_collections_expose_shared_dynamic_contract():
    examples = [
        ("collection_audio_language", "audio_language", "audio_language/<<key>>"),
        ("collection_subtitle_language", "subtitle_language", "subtitle_language/<<key>>"),
    ]

    for collection_id, search_term, image_default in examples:
        collection = _load_collection(collection_id)
        fields = _field_map(collection)

        section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
        assert section_ids == [
            "basics",
            "naming",
            "scope",
            "other_collection",
            "child_override_maps",
            "artwork",
            "visibility",
        ]

        assert fields["search_term"]["default"] == search_term
        assert fields["translation_key"]["default"] == search_term
        assert fields["image"]["default"] == image_default

        for key in [
            "search_term2",
            "search_value2",
            "type",
            "schedule",
            "name_mapping",
            "delete_collections_named",
            "url_poster",
            "file_poster",
            "url_background",
            "file_background",
            "url_logo",
            "file_logo",
            "url_square_art",
            "file_square_art",
        ]:
            assert key in fields

        for key in ["include", "append_include", "exclude"]:
            assert fields[key]["validation_preset"] == "language_key"

        expected_mappings = {
            "child_use_overrides": ("use_", "boolean", "child_override_maps", None, None),
            "child_name_overrides": ("name_", "string", "child_override_maps", None, None),
            "child_summary_overrides": ("summary_", "string", "child_override_maps", None, None),
            "child_order_overrides": ("order_", "string", "child_override_maps", None, None),
            "child_schedule_overrides": ("schedule_", "string", "child_override_maps", None, None),
            "child_sort_by_overrides": ("sort_by_", "select", "child_override_maps", None, None),
            "child_limit_overrides": ("limit_", "integer", "child_override_maps", None, None),
            "child_minimum_items_overrides": ("minimum_items_", "integer", "child_override_maps", None, None),
            "child_url_poster_overrides": ("url_poster_", "string", "artwork", "url", None),
            "child_file_poster_overrides": ("file_poster_", "string", "artwork", None, None),
            "child_url_background_overrides": ("url_background_", "string", "artwork", "url", None),
            "child_file_background_overrides": ("file_background_", "string", "artwork", None, None),
            "child_url_logo_overrides": ("url_logo_", "string", "artwork", "url", None),
            "child_file_logo_overrides": ("file_logo_", "string", "artwork", None, None),
            "child_url_square_art_overrides": ("url_square_art_", "string", "artwork", "url", None),
            "child_file_square_art_overrides": ("file_square_art_", "string", "artwork", None, None),
            "child_visible_home_overrides": ("visible_home_", "boolean", "visibility", None, None),
            "child_visible_library_overrides": ("visible_library_", "boolean", "visibility", None, None),
            "child_visible_shared_overrides": ("visible_shared_", "boolean", "visibility", None, None),
            "child_hub_priority_overrides": ("hub_priority_", "string", "visibility", None, None),
            "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", "visibility", None, ["movie"]),
            "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", "visibility", None, ["show"]),
        }
        for key, (child_prefix, value_kind, section, validation_preset, media_types) in expected_mappings.items():
            _assert_mapping(fields[key], child_prefix, value_kind, section, validation_preset, media_types)

        assert "child_name_mapping_overrides" not in fields
        assert "child_delete_collections_named_overrides" not in fields
        assert "child_sync_mode_overrides" not in fields
