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


def test_movie_franchise_exposes_collection_data_and_artwork_template_variable_maps():
    collection = _load_collection("collection_franchise", ("movie",))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "naming", "collection_data", "child_override_maps", "artwork", "automation", "visibility"]

    assert fields["name_mapping"]["section"] == "naming"
    expected_mappings = {
        "child_movie_overrides": ("movie_", "string_list", "collection_data", None),
        "child_name_mapping_overrides": ("name_mapping_", "string", "child_override_maps", None),
        "child_order_overrides": ("order_", "string", "child_override_maps", None),
        "child_file_poster_overrides": ("file_poster_", "string", "artwork", None),
        "child_url_background_overrides": ("url_background_", "string", "artwork", "url"),
        "child_file_background_overrides": ("file_background_", "string", "artwork", None),
        "child_url_logo_overrides": ("url_logo_", "string", "artwork", "url"),
        "child_file_logo_overrides": ("file_logo_", "string", "artwork", None),
        "child_url_square_art_overrides": ("url_square_art_", "string", "artwork", "url"),
        "child_file_square_art_overrides": ("file_square_art_", "string", "artwork", None),
    }
    for key, (prefix, value_kind, section, validation_preset) in expected_mappings.items():
        _assert_mapping(fields[key], prefix, value_kind, section, "tmdb_collection_id", validation_preset)


def test_show_franchise_exposes_supported_name_order_and_poster_artwork_maps():
    collection = _load_collection("collection_franchise", ("show",))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "naming", "collection_data", "child_override_maps", "artwork", "automation", "visibility"]

    expected_mappings = {
        "child_name_mapping_overrides": ("name_mapping_", "string", "child_override_maps", None),
        "child_order_overrides": ("order_", "string", "child_override_maps", None),
        "child_url_poster_overrides": ("url_poster_", "string", "artwork", "url"),
    }
    for key, (prefix, value_kind, section, validation_preset) in expected_mappings.items():
        _assert_mapping(fields[key], prefix, value_kind, section, "numeric_id", validation_preset)
    assert "child_movie_overrides" not in fields
    assert "child_url_background_overrides" not in fields
    assert "child_url_logo_overrides" not in fields
    assert "child_url_square_art_overrides" not in fields


def test_based_exposes_fixed_child_builder_artwork_and_arr_template_variables():
    collection = _load_collection("collection_based", ("movie", "show"))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == [
        "basics",
        "naming",
        "child_defaults",
        "child_builder",
        "artwork",
        "automation_defaults",
        "automation_children",
        "visibility",
    ]

    for key in [
        "sep_style",
        "translation_key",
        "schedule",
        "name_mapping",
        "delete_collections_named",
        "image",
        "url_logo",
        "keywords_books",
        "image_comics",
        "limit_true_story",
        "sort_by_video_games",
        "schedule_books",
        "url_poster_true_story",
        "file_logo_video_games",
        "radarr_folder_books",
        "radarr_search_comics",
        "sonarr_folder_true_story",
        "sonarr_search_video_games",
    ]:
        assert key in fields
    assert fields["keywords_books"]["section"] == "child_builder"
    assert fields["radarr_folder_books"]["section"] == "automation_children"


def test_collectionless_exposes_all_optional_builder_template_variables():
    collection = _load_collection("collection_collectionless", ("movie", "show"))
    fields = _field_map(collection)

    section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]
    assert section_ids == ["basics", "naming", "builders", "artwork"]

    for key in [
        "collection_mode",
        "name_collectionless",
        "summary_collectionless",
        "url_poster",
        "tmdb_movie",
        "tmdb_show",
        "tmdb_list",
        "tvdb_movie",
        "tvdb_show",
        "tvdb_list",
        "imdb_id",
        "imdb_list",
        "plex_search",
        "mdblist_list",
        "trakt_list",
    ]:
        assert key in fields
    assert fields["exclude"]["section"] == "builders"
    assert fields["exclude"]["placeholder"] == "Add collection name (e.g. Marvel Cinematic Universe)"
    assert "validation_preset" not in fields["exclude"]
