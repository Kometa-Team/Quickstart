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


def _assert_mapping(field, child_prefix, value_kind, section, key_validation_preset, key_input_mode=None, validation_preset=None, media_types=None):
    assert field["type"] == "mapping_list"
    assert field["dynamic_child_prefix"] == child_prefix
    assert field["dynamic_child_value_kind"] == value_kind
    assert field["section"] == section
    assert field["key_validation_preset"] == key_validation_preset
    if key_input_mode is None:
        assert "key_input_mode" not in field
    else:
        assert field["key_input_mode"] == key_input_mode
    if validation_preset is None:
        assert "validation_preset" not in field
    else:
        assert field["validation_preset"] == validation_preset
    if media_types is None:
        assert "media_types" not in field
    else:
        assert field["media_types"] == media_types


def test_genre_collection_exposes_shared_defaults_and_dynamic_maps():
    collection = _load_collection("collection_genre", ("movie", "show"))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "naming", "scope", "child_override_maps", "artwork", "visibility"]

    for key in ["sep_style", "translation_key", "use_all", "schedule", "name_mapping", "delete_collections_named", "file_poster", "url_poster"]:
        assert key in fields

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", "child_override_maps", None, None),
        "child_name_overrides": ("name_", "string", "child_override_maps", None, None),
        "child_schedule_overrides": ("schedule_", "string", "child_override_maps", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", "child_override_maps", None, None),
        "child_limit_overrides": ("limit_", "integer", "child_override_maps", None, None),
        "child_minimum_items_overrides": ("minimum_items_", "integer", "child_override_maps", None, None),
        "child_file_poster_overrides": ("file_poster_", "string", "artwork", None, None),
        "child_url_poster_overrides": ("url_poster_", "string", "artwork", "url", None),
        "child_visible_home_overrides": ("visible_home_", "boolean", "visibility", None, None),
        "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", "visibility", None, ["movie"]),
        "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", "visibility", None, ["show"]),
    }
    for key, (child_prefix, value_kind, section, validation_preset, media_types) in expected_mappings.items():
        _assert_mapping(fields[key], child_prefix, value_kind, section, "name_like", validation_preset=validation_preset, media_types=media_types)


def test_other_chart_collection_uses_fixed_chart_key_dropdowns_for_override_maps():
    collection = _load_collection("collection_other_chart", ("movie", "show"))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids[:8] == ["basics", "naming", "child_defaults", "child_override_maps", "artwork", "automation_defaults", "automation_override_maps", "visibility"]
    assert "chart_commonsense" in section_ids
    assert "chart_pirated" in section_ids

    for key in ["schedule", "name_mapping", "delete_collections_named", "file_logo", "url_logo"]:
        assert key in fields

    expected_mappings = {
        "child_schedule_overrides": ("schedule_", "string", "child_override_maps", None, None),
        "child_sync_mode_overrides": ("sync_mode_", "select", "child_override_maps", None, None),
        "child_collection_order_overrides": ("collection_order_", "select", "child_override_maps", None, None),
        "child_cache_builders_overrides": ("cache_builders_", "string", "child_override_maps", None, None),
        "child_radarr_search_overrides": ("radarr_search_", "boolean", "automation_override_maps", None, ["movie"]),
        "child_sonarr_add_missing_overrides": ("sonarr_add_missing_", "boolean", "automation_override_maps", None, ["show"]),
        "child_file_logo_overrides": ("file_logo_", "string", "artwork", None, None),
        "child_url_logo_overrides": ("url_logo_", "string", "artwork", "url", None),
    }
    for key, (child_prefix, value_kind, section, validation_preset, media_types) in expected_mappings.items():
        _assert_mapping(fields[key], child_prefix, value_kind, section, "other_chart_key", "select", validation_preset, media_types)

    assert fields["use_commonsense"]["section"] == "chart_commonsense"
    assert fields["use_pirated"]["section"] == "chart_pirated"


def test_actor_collection_exposes_person_specific_defaults_and_dynamic_maps():
    collection = _load_collection("collection_actor", ("movie", "show"))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "naming", "people_data", "scope", "child_override_maps", "artwork", "visibility"]

    for key in ["sep_style", "translation_key", "use_all", "limit", "schedule", "tmdb_deathday", "file_poster", "url_poster"]:
        assert key in fields

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", "child_override_maps", None, None),
        "child_name_overrides": ("name_", "string", "child_override_maps", None, None),
        "child_tmdb_person_offset_overrides": ("tmdb_person_offset_", "integer", "child_override_maps", None, None),
        "child_limit_overrides": ("limit_", "integer", "child_override_maps", None, None),
        "child_file_poster_overrides": ("file_poster_", "string", "artwork", None, None),
        "child_url_poster_overrides": ("url_poster_", "string", "artwork", "url", None),
        "child_visible_library_overrides": ("visible_library_", "boolean", "visibility", None, None),
    }
    for key, (child_prefix, value_kind, section, validation_preset, media_types) in expected_mappings.items():
        _assert_mapping(fields[key], child_prefix, value_kind, section, "name_like", validation_preset=validation_preset, media_types=media_types)


def test_movie_person_collections_match_actor_dynamic_person_contract():
    for collection_id in ["collection_director", "collection_producer", "collection_writer"]:
        collection = _load_collection(collection_id, ("movie",))
        fields = _field_map(collection)

        section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
        assert section_ids == ["basics", "naming", "people_data", "scope", "child_override_maps", "artwork", "visibility"]

        for key in ["sep_style", "translation_key", "use_all", "limit", "schedule", "tmdb_deathday", "file_poster", "url_poster"]:
            assert key in fields

        expected_mappings = {
            "child_use_overrides": ("use_", "boolean", "child_override_maps", None, None),
            "child_name_overrides": ("name_", "string", "child_override_maps", None, None),
            "child_tmdb_person_offset_overrides": ("tmdb_person_offset_", "integer", "child_override_maps", None, None),
            "child_limit_overrides": ("limit_", "integer", "child_override_maps", None, None),
            "child_file_poster_overrides": ("file_poster_", "string", "artwork", None, None),
            "child_url_poster_overrides": ("url_poster_", "string", "artwork", "url", None),
            "child_visible_library_overrides": ("visible_library_", "boolean", "visibility", None, None),
            "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", "visibility", None, ["movie"]),
        }
        for key, (child_prefix, value_kind, section, validation_preset, media_types) in expected_mappings.items():
            _assert_mapping(fields[key], child_prefix, value_kind, section, "name_like", validation_preset=validation_preset, media_types=media_types)
