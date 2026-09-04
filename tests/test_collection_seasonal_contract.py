import json
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = ROOT / "tests" / "fixtures"
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"

# `config/kometa/defaults` is a gitignored local cache populated by a real Kometa
# install. A fresh checkout does not have it, so fall back to the checked-in
# fixtures so this contract remains reproducible in CI.
SEASONAL_DEFAULT_PATH = ROOT / "config" / "kometa" / "defaults" / "movie" / "seasonal.yml"
if not SEASONAL_DEFAULT_PATH.exists():
    SEASONAL_DEFAULT_PATH = FIXTURES_ROOT / "kometa" / "defaults" / "movie" / "seasonal.yml"


def _load_seasonal_collection():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    for group in data:
        for collection in group.get("collections", []):
            if collection.get("id") == "collection_seasonal":
                return collection
    raise AssertionError("Missing collection_seasonal")


def _field_map(collection):
    return {item["key"]: item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}


def _seasonal_keys():
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(SEASONAL_DEFAULT_PATH.read_text(encoding="utf-8"))
    data = parsed["dynamic_collections"]["Seasonal"]["data"]
    return list(data.keys())


def test_seasonal_holiday_toggles_match_repo_yaml_data():
    collection = _load_seasonal_collection()
    fields = _field_map(collection)

    qs_keys = sorted(key.removeprefix("use_") for key in fields if key.startswith("use_") and key not in {"use_all", "use_separator"})

    assert qs_keys == sorted(_seasonal_keys())


def test_seasonal_exposes_yaml_verified_shared_fields_and_override_maps():
    collection = _load_seasonal_collection()
    fields = _field_map(collection)

    expected_shared = {
        "schedule": {"type": "schedule", "section": "scope_schedule"},
        "name_mapping": {"type": "text_input", "section": "naming"},
        "delete_collections_named": {"type": "string_list", "section": "scope_schedule"},
        "emoji": {"type": "text_input", "section": "naming"},
        "tmdb_collection": {"type": "string_list", "validation_preset": "numeric_id", "section": "builder_defaults"},
        "tmdb_movie": {"type": "string_list", "validation_preset": "numeric_id", "section": "builder_defaults"},
        "imdb_list": {"type": "string_list", "section": "builder_defaults"},
        "imdb_search": {"type": "text_input", "section": "builder_defaults"},
        "trakt_list": {"type": "string_list", "section": "builder_defaults"},
        "mdblist_list": {"type": "string_list", "section": "builder_defaults"},
        "letterboxd_list": {"type": "string_list", "section": "builder_defaults"},
        "url_poster": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "url_background": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "url_logo": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
        "url_square_art": {"type": "text_input", "validation_preset": "url", "section": "artwork"},
    }

    for key, metadata in expected_shared.items():
        assert key in fields
        for meta_key, meta_value in metadata.items():
            assert fields[key].get(meta_key) == meta_value

    section_defs = collection.get("template_variable_sections") or []
    section_ids = [section.get("id") for section in section_defs if isinstance(section, dict)]
    assert section_ids[:8] == [
        "basics",
        "naming",
        "scope_schedule",
        "builder_defaults",
        "builder_override_maps",
        "artwork",
        "automation_defaults",
        "automation_override_maps",
    ]
    assert "holiday_halloween" in section_ids
    assert "holiday_christmas" in section_ids
    assert any(section.get("default_open") is True for section in section_defs if section.get("id") == "basics")

    expected_mappings = {
        "child_name_mapping_overrides": ("name_mapping_", "string", "builder_override_maps", None, None),
        "child_emoji_overrides": ("emoji_", "string", "builder_override_maps", None, None),
        "child_sort_by_overrides": ("sort_by_", "select", "builder_override_maps", None, None),
        "child_delete_collections_named_overrides": ("delete_collections_named_", "string_list", "builder_override_maps", None, None),
        "child_tmdb_collection_overrides": ("tmdb_collection_", "string_list", "builder_override_maps", None, None),
        "child_tmdb_movie_overrides": ("tmdb_movie_", "string_list", "builder_override_maps", None, None),
        "child_imdb_list_overrides": ("imdb_list_", "string_list", "builder_override_maps", None, None),
        "child_imdb_search_overrides": ("imdb_search_", "json", "builder_override_maps", None, None),
        "child_trakt_list_overrides": ("trakt_list_", "string_list", "builder_override_maps", None, None),
        "child_mdblist_list_overrides": ("mdblist_list_", "string_list", "builder_override_maps", None, None),
        "child_letterboxd_list_overrides": ("letterboxd_list_", "string_list", "builder_override_maps", None, None),
        "child_url_poster_overrides": ("url_poster_", "string", "artwork", "url", None),
        "child_url_background_overrides": ("url_background_", "string", "artwork", "url", None),
        "child_url_logo_overrides": ("url_logo_", "string", "artwork", "url", None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "artwork", "url", None),
        "child_radarr_folder_overrides": ("radarr_folder_", "string", "automation_override_maps", None, ["movie"]),
        "child_radarr_tag_overrides": ("radarr_tag_", "string_list", "automation_override_maps", None, ["movie"]),
        "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", "automation_override_maps", None, ["movie"]),
        "child_radarr_monitor_overrides": ("radarr_monitor_", "boolean", "automation_override_maps", None, ["movie"]),
        "child_radarr_upgrade_existing_overrides": ("radarr_upgrade_existing_", "boolean", "automation_override_maps", None, ["movie"]),
        "child_radarr_monitor_existing_overrides": ("radarr_monitor_existing_", "boolean", "automation_override_maps", None, ["movie"]),
        "child_radarr_search_overrides": ("radarr_search_", "boolean", "automation_override_maps", None, ["movie"]),
    }

    for key, (child_prefix, value_kind, section, value_validation_preset, media_types) in expected_mappings.items():
        assert key in fields
        field = fields[key]
        assert field["type"] == "mapping_list"
        assert field["dynamic_child_prefix"] == child_prefix
        assert field["dynamic_child_value_kind"] == value_kind
        assert field["key_validation_preset"] == "seasonal_key"
        assert field["key_input_mode"] == "select"
        assert field["section"] == section
        if value_validation_preset is None:
            assert "validation_preset" not in field
        else:
            assert field["validation_preset"] == value_validation_preset
        if media_types is None:
            assert "media_types" not in field
        else:
            assert field["media_types"] == media_types


def test_seasonal_halloween_fields_are_grouped_in_holiday_section():
    fields = _field_map(_load_seasonal_collection())

    section_id = "holiday_halloween"
    assert fields["use_halloween"]["section"] == section_id
    assert fields["name_halloween"]["section"] == section_id
    assert fields["summary_halloween"]["section"] == section_id
    assert fields["sync_mode_halloween"]["section"] == section_id
    assert fields["limit_halloween"]["section"] == section_id
    assert fields["radarr_add_missing_halloween"]["section"] == section_id
    assert fields["schedule_halloween"]["section"] == section_id
    assert fields["visible_home_halloween"]["section"] == section_id
    assert fields["visible_library_halloween"]["section"] == section_id
    assert fields["visible_shared_halloween"]["section"] == section_id
    assert fields["hub_priority_halloween"]["section"] == section_id
