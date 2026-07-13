import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
LIBRARIES_JS_PATH = ROOT / "static" / "local-js" / "025-libraries.js"


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


def test_geography_key_presets_are_select_backed():
    source = LIBRARIES_JS_PATH.read_text(encoding="utf-8")

    for preset in ["country_name_key", "country_code_key", "continent_key", "region_key"]:
        assert f"{preset}: {{" in source
    assert "const countryNameCollectionKeys" in source
    assert "const countryCodeCollectionKeys" in source
    assert "const continentCollectionKeys" in source
    assert "France" in source
    assert '"fr"' in source
    assert "Europe" in source


def test_region_collection_exposes_verified_shared_fields_and_sections():
    collection = _load_collection("collection_region", ("movie", "show"))
    fields = _field_map(collection)

    expected_shared = {
        "blank_collection": {"type": "toggle", "section": "basics"},
        "search_term": {"type": "text_input", "section": "scope", "media_types": ["movie"]},
        "filter_term": {"type": "text_input", "section": "scope", "media_types": ["show"]},
        "translation_key": {"type": "text_input", "section": "defaults"},
        "image": {"type": "text_input", "section": "defaults"},
        "schedule": {"type": "schedule", "section": "defaults"},
        "name_mapping": {"type": "text_input", "section": "defaults"},
        "delete_collections_named": {"type": "string_list", "section": "defaults"},
        "trakt_list": {"type": "string_list", "section": "scope", "validation_preset": "url"},
        "url_poster": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "file_poster": {"type": "text_input", "section": "artwork"},
        "url_background": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "file_background": {"type": "text_input", "section": "artwork"},
        "url_logo": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "file_logo": {"type": "text_input", "section": "artwork"},
        "url_square_art": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "file_square_art": {"type": "text_input", "section": "artwork"},
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
        "child_name_overrides": ("name_", "string", None, None),
        "child_summary_overrides": ("summary_", "string", None, None),
        "child_order_overrides": ("order_", "string", None, None),
        "child_schedule_overrides": ("schedule_", "string", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", None, None),
        "child_limit_overrides": ("limit_", "integer", None, None),
        "child_minimum_items_overrides": ("minimum_items_", "integer", None, None),
        "child_sync_mode_overrides": ("sync_mode_", "select", None, ["show"]),
        "child_url_poster_overrides": ("url_poster_", "string", "url", None),
        "child_file_poster_overrides": ("file_poster_", "string", None, None),
        "child_url_background_overrides": ("url_background_", "string", "url", None),
        "child_file_background_overrides": ("file_background_", "string", None, None),
        "child_url_logo_overrides": ("url_logo_", "string", "url", None),
        "child_file_logo_overrides": ("file_logo_", "string", None, None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "url", None),
        "child_file_square_art_overrides": ("file_square_art_", "string", None, None),
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
        assert field["section"] in {"child_override_maps", "artwork", "visibility", "defaults"}
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
    assert "child_name_mapping_overrides" not in fields


def test_country_collection_exposes_movie_and_show_specific_keys():
    movie_collection = _load_collection("collection_country", ("movie",))
    show_collection = _load_collection("collection_country", ("show",))
    movie_fields = _field_map(movie_collection)
    show_fields = _field_map(show_collection)

    for collection in [movie_collection, show_collection]:
        section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
        assert section_ids == ["basics", "scope", "defaults", "child_override_maps", "artwork", "visibility"]

    assert "sync_mode" not in movie_fields
    assert "filter_term" not in movie_fields
    assert movie_fields["search_term"]["media_types"] == ["movie"]
    assert "child_sync_mode_overrides" not in movie_fields
    assert movie_fields["child_use_overrides"]["key_validation_preset"] == "country_name_key"
    assert movie_fields["child_use_overrides"]["key_input_mode"] == "select"
    assert movie_fields["child_item_radarr_tag_overrides"]["media_types"] == ["movie"]
    assert "child_item_sonarr_tag_overrides" not in movie_fields

    assert "search_term" not in show_fields
    assert show_fields["filter_term"]["media_types"] == ["show"]
    assert show_fields["sync_mode"]["media_types"] == ["show"]
    assert show_fields["child_use_overrides"]["key_validation_preset"] == "country_code_key"
    assert show_fields["child_use_overrides"]["key_input_mode"] == "select"
    assert show_fields["child_sync_mode_overrides"]["media_types"] == ["show"]
    assert show_fields["child_item_sonarr_tag_overrides"]["media_types"] == ["show"]
    assert "child_item_radarr_tag_overrides" not in show_fields

    for fields in [movie_fields, show_fields]:
        for key in [
            "translation_key",
            "image",
            "schedule",
            "name_mapping",
            "delete_collections_named",
            "trakt_list",
            "file_poster",
            "file_background",
            "file_logo",
            "file_square_art",
        ]:
            assert key in fields
        for key in [
            "child_name_overrides",
            "child_summary_overrides",
            "child_order_overrides",
            "child_minimum_items_overrides",
            "child_file_poster_overrides",
            "child_file_background_overrides",
            "child_file_logo_overrides",
            "child_file_square_art_overrides",
        ]:
            assert key in fields
        assert "child_name_mapping_overrides" not in fields


def test_continent_collection_exposes_geography_override_maps():
    collection = _load_collection("collection_continent", ("movie", "show"))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "scope", "defaults", "child_override_maps", "artwork", "continents", "visibility"]

    assert fields["search_term"]["media_types"] == ["movie"]
    assert fields["filter_term"]["media_types"] == ["show"]
    assert fields["sync_mode"]["media_types"] == ["show"]
    assert fields["use_Africa"]["section"] == "continents"
    assert fields["use_Oceania"]["section"] == "continents"

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", None, None),
        "child_name_overrides": ("name_", "string", None, None),
        "child_summary_overrides": ("summary_", "string", None, None),
        "child_order_overrides": ("order_", "string", None, None),
        "child_schedule_overrides": ("schedule_", "string", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", None, None),
        "child_limit_overrides": ("limit_", "integer", None, None),
        "child_minimum_items_overrides": ("minimum_items_", "integer", None, None),
        "child_sync_mode_overrides": ("sync_mode_", "select", None, ["show"]),
        "child_url_poster_overrides": ("url_poster_", "string", "url", None),
        "child_file_poster_overrides": ("file_poster_", "string", None, None),
        "child_url_background_overrides": ("url_background_", "string", "url", None),
        "child_file_background_overrides": ("file_background_", "string", None, None),
        "child_url_logo_overrides": ("url_logo_", "string", "url", None),
        "child_file_logo_overrides": ("file_logo_", "string", None, None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "url", None),
        "child_file_square_art_overrides": ("file_square_art_", "string", None, None),
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
        assert field["key_validation_preset"] == "continent_key"
        assert field["key_input_mode"] == "select"
        assert field["section"] in {"child_override_maps", "artwork", "visibility", "defaults"}
        if validation_preset is None:
            assert "validation_preset" not in field
        else:
            assert field["validation_preset"] == validation_preset
        if media_types is None:
            assert "media_types" not in field
        else:
            assert field["media_types"] == media_types

    assert "child_name_mapping_overrides" not in fields


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
