import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"


def _load_collection(collection_id, media_types):
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    media_types = tuple(media_types)
    for group in data:
        for collection in group.get("collections", []):
            if collection.get("id") != collection_id:
                continue
            if tuple(collection.get("media_types") or []) == media_types:
                return collection
    raise AssertionError(f"Missing {collection_id} with media types {media_types}")


def _field_map(collection):
    return {item["key"]: item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}


def _assert_mapping(field, child_prefix, value_kind, section, key_validation_preset, validation_preset=None, media_types=None):
    assert field["type"] == "mapping_list"
    assert field["dynamic_child_prefix"] == child_prefix
    assert field["dynamic_child_value_kind"] == value_kind
    assert field["section"] == section
    assert field["key_validation_preset"] == key_validation_preset
    if validation_preset is None:
        assert "validation_preset" not in field
    else:
        assert field["validation_preset"] == validation_preset
    if media_types is None:
        assert "media_types" not in field
    else:
        assert field["media_types"] == media_types


def _assert_year_or_decade_contract(collection, key_validation_preset, expected_search_term, expected_image):
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "naming", "data_range", "scope", "child_override_maps", "artwork", "visibility"]

    for key in [
        "use_all",
        "search_term",
        "translation_key",
        "schedule",
        "name_mapping",
        "delete_collections_named",
        "image",
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

    assert fields["search_term"]["default"] == expected_search_term
    assert fields["image"]["default"] == expected_image
    assert fields["exclude"]["validation_preset"] == key_validation_preset

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
        _assert_mapping(fields[key], child_prefix, value_kind, section, key_validation_preset, validation_preset, media_types)


def test_year_collection_exposes_shared_defaults_and_dynamic_maps():
    collection = _load_collection("collection_year", ("movie", "show"))

    _assert_year_or_decade_contract(collection, "year", "year", "year/best/<<key>>")


def test_movie_decade_collection_exposes_shared_defaults_and_dynamic_maps():
    collection = _load_collection("collection_decade", ("movie",))

    _assert_year_or_decade_contract(collection, "decade", "decade", "decade/best/<<key>>")


def test_show_decade_collection_uses_year_search_term_and_dynamic_maps():
    collection = _load_collection("collection_decade", ("show",))

    _assert_year_or_decade_contract(collection, "decade", "year", "decade/best/<<key>>")
