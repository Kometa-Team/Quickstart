import json
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader
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


def test_seasonal_visibility_uses_schedule_builder_with_boolean_options():
    collection = _load_seasonal_collection()
    assert collection["media_types"] == ["movie"]
    fields = _field_map(collection)
    for suffix in [""] + [f"_{key}" for key in _seasonal_keys()]:
        for target in ("home", "library", "shared"):
            field = fields[f"visible_{target}{suffix}"]
            assert field["type"] == "schedule"
            assert field["allow_boolean"] is True
            assert field["default"] is False


@pytest.mark.parametrize("value, expected", [(False, "false"), (True, "true"), ("range(02/01-02/21)", "range(02/01-02/21)"), ("weekly(friday)", "weekly(friday)")])
def test_seasonal_visibility_renders_saved_boolean_and_schedule_values(value, expected):
    from html.parser import HTMLParser

    class Inputs(HTMLParser):
        def __init__(self):
            super().__init__()
            self.by_id = {}

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if "id" in attrs:
                self.by_id[attrs["id"]] = attrs

    field_name = "mov-library_movies-template_collection_seasonal_visible_home_valentine"
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))
    macros = env.get_template("partials/_macros.html").module
    collection = _load_seasonal_collection()
    html = macros.collection_group_section(
        {"id": "mov-library_movies", "name": "Movies", "type": "movie"},
        {"libraries": {field_name: value}},
        {},
        {"accordion": "Time Collections", "collections": [collection]},
        {"plex_pass": True, "libraries": {}},
    )
    parsed = Inputs()
    parsed.feed(str(html))
    hidden = parsed.by_id[field_name]
    assert hidden["type"] == "hidden"
    assert hidden["value"] == expected
    assert hidden["data-default"] == "false"
    assert hidden["data-template-variable-key"] == "visible_home_valentine"
    assert 'value="true">Always visible</option>' in html
    assert 'value="false">Hidden</option>' in html


def test_seasonal_visibility_import_export_round_trip():
    from io import StringIO

    from modules import importer, output_collections
    from modules.output_optimize import optimize_template_variables

    template_vars = {
        "use_valentine": True,
        "schedule_valentine": "daily",
        "visible_home_valentine": "range(02/01-02/21)",
        "visible_shared_valentine": "range(02/01-02/21)",
        "visible_library_valentine": True,
        "visible_home": "weekly(friday)",
        "visible_shared": False,
    }
    payload, report = importer.prepare_import_payload(
        {"libraries": {"Movies": {"collection_files": [{"default": "seasonal", "template_variables": template_vars}]}}},
        {"Movies"},
        set(),
    )
    libraries = payload["libraries"]["libraries"]
    for key, value in template_vars.items():
        assert libraries[f"mov-library_movies-template_collection_seasonal_{key}"] == value
    entries, _ = output_collections.build_collection_files(
        "mov-library_movies-library",
        "mov",
        {"movies": libraries},
        {},
        {},
        {},
    )
    assert entries[0]["template_variables"] == template_vars
    optimized = optimize_template_variables({"libraries": {"Movies": {"collection_files": entries}}}, {"Movies": "movie"})
    stream = StringIO()
    yaml = YAML()
    yaml.dump(optimized, stream)
    exported = yaml.load(stream.getvalue())["libraries"]["Movies"]["collection_files"][0]["template_variables"]
    assert exported["schedule_valentine"] == "daily"
    assert exported["visible_home_valentine"] == "range(02/01-02/21)"
    assert exported["visible_shared_valentine"] == "range(02/01-02/21)"
    assert exported["visible_library_valentine"] is True
    assert exported["visible_home"] == "weekly(friday)"


@pytest.mark.parametrize("value, expected", [(False, False), ("false", False), (True, True), ("true", True), ("range(02/01-02/21)", True), ("weekly(friday)", True)])
def test_seasonal_visibility_schedules_count_as_overrides(library_routes_module, value, expected):
    assert library_routes_module._template_value_is_configured(value, False, "schedule") is expected
