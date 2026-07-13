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


def test_region_collection_exposes_verified_shared_fields_and_sections():
    collection = _load_collection("collection_region", ("movie", "show"))
    fields = _field_map(collection)

    expected_shared = {
        "blank_collection": {"type": "toggle", "section": "basics"},
        "schedule": {"type": "schedule", "section": "defaults"},
        "name_mapping": {"type": "text_input", "section": "defaults"},
        "delete_collections_named": {"type": "string_list", "section": "defaults"},
        "url_poster": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "url_background": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "url_logo": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "url_square_art": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
    }

    for key, metadata in expected_shared.items():
        assert key in fields
        for meta_key, meta_value in metadata.items():
            assert fields[key].get(meta_key) == meta_value

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids[:5] == ["basics", "scope", "defaults", "child_override_maps", "artwork"]
    assert "regions_africa" in section_ids
    assert "regions_oceania" in section_ids

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", None, None),
        "child_name_mapping_overrides": ("name_mapping_", "string", None, None),
        "child_schedule_overrides": ("schedule_", "string", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", None, None),
        "child_limit_overrides": ("limit_", "integer", None, None),
        "child_url_poster_overrides": ("url_poster_", "string", "url", None),
        "child_url_background_overrides": ("url_background_", "string", "url", None),
        "child_url_logo_overrides": ("url_logo_", "string", "url", None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "url", None),
        "child_visible_home_overrides": ("visible_home_", "boolean", None, None),
        "child_visible_library_overrides": ("visible_library_", "boolean", None, None),
        "child_visible_shared_overrides": ("visible_shared_", "boolean", None, None),
        "child_hub_priority_overrides": ("hub_priority_", "string", None, None),
        "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", None, ["movie"]),
        "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", None, ["show"]),
    }
    for key, (child_prefix, value_kind, validation_preset, media_types) in expected_mappings.items():
        field = fields[key]
        assert field["type"] == "mapping_list"
        assert field["dynamic_child_prefix"] == child_prefix
        assert field["dynamic_child_value_kind"] == value_kind
        assert field["key_validation_preset"] == "region_key"
        assert field["key_input_mode"] == "select"
        assert field["section"] == "child_override_maps"
        if validation_preset is None:
            assert "validation_preset" not in field
        else:
            assert field["validation_preset"] == validation_preset
        if media_types is None:
            assert "media_types" not in field
        else:
            assert field["media_types"] == media_types

    assert fields["use_Northern Africa"]["section"] == "regions_africa"
    assert fields["use_Caribbean"]["section"] == "regions_americas"
    assert fields["use_Eastern Asia"]["section"] == "regions_asia"
    assert fields["use_Western Europe"]["section"] == "regions_europe"
    assert fields["use_Australia and New Zealand"]["section"] == "regions_oceania"
    assert fields["use_other"]["section"] == "regions_polar_other"


def test_studio_collection_exposes_verified_shared_fields_and_override_maps():
    collection = _load_collection("collection_studio", ("movie", "show"))
    fields = _field_map(collection)

    for key in ["blank_collection", "schedule", "name_mapping", "delete_collections_named", "limit", "url_poster", "url_background", "url_logo", "url_square_art"]:
        assert key in fields

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "scope", "defaults", "child_override_maps", "artwork"]

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", None, None),
        "child_name_overrides": ("name_", "string", None, None),
        "child_summary_overrides": ("summary_", "string", None, None),
        "child_schedule_overrides": ("schedule_", "string", None, None),
        "child_name_mapping_overrides": ("name_mapping_", "string", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", None, None),
        "child_limit_overrides": ("limit_", "integer", None, None),
        "child_url_poster_overrides": ("url_poster_", "string", "url", None),
        "child_url_background_overrides": ("url_background_", "string", "url", None),
        "child_url_logo_overrides": ("url_logo_", "string", "url", None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "url", None),
        "child_visible_home_overrides": ("visible_home_", "boolean", None, None),
        "child_visible_library_overrides": ("visible_library_", "boolean", None, None),
        "child_visible_shared_overrides": ("visible_shared_", "boolean", None, None),
        "child_hub_priority_overrides": ("hub_priority_", "string", None, None),
        "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", None, ["movie"]),
        "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", None, ["show"]),
    }
    for key, (child_prefix, value_kind, validation_preset, media_types) in expected_mappings.items():
        field = fields[key]
        assert field["type"] == "mapping_list"
        assert field["dynamic_child_prefix"] == child_prefix
        assert field["dynamic_child_value_kind"] == value_kind
        assert field["key_validation_preset"] == "studio_key"
        assert field["key_input_mode"] == "select"
        assert field["section"] == "child_override_maps"
        if validation_preset is None:
            assert "validation_preset" not in field
        else:
            assert field["validation_preset"] == validation_preset
        if media_types is None:
            assert "media_types" not in field
        else:
            assert field["media_types"] == media_types


def test_network_collection_exposes_verified_shared_fields_and_override_maps():
    collection = _load_collection("collection_network", ("show",))
    fields = _field_map(collection)

    for key in ["blank_collection", "schedule", "name_mapping", "delete_collections_named", "limit", "url_poster", "url_background", "url_logo", "url_square_art"]:
        assert key in fields

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "scope", "defaults", "child_override_maps", "artwork"]

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", None, None),
        "child_name_overrides": ("name_", "string", None, None),
        "child_summary_overrides": ("summary_", "string", None, None),
        "child_schedule_overrides": ("schedule_", "string", None, None),
        "child_name_mapping_overrides": ("name_mapping_", "string", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", None, None),
        "child_limit_overrides": ("limit_", "integer", None, None),
        "child_url_poster_overrides": ("url_poster_", "string", "url", None),
        "child_url_background_overrides": ("url_background_", "string", "url", None),
        "child_url_logo_overrides": ("url_logo_", "string", "url", None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "url", None),
        "child_visible_home_overrides": ("visible_home_", "boolean", None, None),
        "child_visible_library_overrides": ("visible_library_", "boolean", None, None),
        "child_visible_shared_overrides": ("visible_shared_", "boolean", None, None),
        "child_hub_priority_overrides": ("hub_priority_", "string", None, None),
        "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", None, ["show"]),
    }
    for key, (child_prefix, value_kind, validation_preset, media_types) in expected_mappings.items():
        field = fields[key]
        assert field["type"] == "mapping_list"
        assert field["dynamic_child_prefix"] == child_prefix
        assert field["dynamic_child_value_kind"] == value_kind
        assert field["key_validation_preset"] == "network_key"
        assert field["key_input_mode"] == "select"
        assert field["section"] == "child_override_maps"
        if validation_preset is None:
            assert "validation_preset" not in field
        else:
            assert field["validation_preset"] == validation_preset
        if media_types is None:
            assert "media_types" not in field
        else:
            assert field["media_types"] == media_types

    assert "child_item_radarr_tag_overrides" not in fields
