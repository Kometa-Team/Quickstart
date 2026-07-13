import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"


def _load_collections():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    return [collection for group in data for collection in group.get("collections", [])]


def _award_collections():
    return [collection for collection in _load_collections() if "/defaults/award/" in str(collection.get("url") or "") and collection.get("id") != "collection_separator_award"]


def _field_map(collection):
    return {item["key"]: item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}


def _assert_mapping(field, child_prefix, value_kind, section, validation_preset=None, media_types=None):
    assert field["type"] == "mapping_list"
    assert field["dynamic_child_prefix"] == child_prefix
    assert field["dynamic_child_value_kind"] == value_kind
    assert field["section"] == section
    assert field["key_validation_preset"] == "year"
    if validation_preset is None:
        assert "validation_preset" not in field
    else:
        assert field["validation_preset"] == validation_preset
    if media_types is None:
        assert "media_types" not in field
    else:
        assert field["media_types"] == media_types


def test_award_separator_remains_readonly_without_template_variables():
    separator = next(collection for collection in _load_collections() if collection.get("id") == "collection_separator_award")

    assert separator.get("readonly") is True
    assert "template_variables" not in separator
    assert "template_variable_sections" not in separator


def test_award_defaults_expose_shared_yaml_backed_fields():
    expected_sections = [
        "basics",
        "naming",
        "data_range",
        "scope",
        "award_children",
        "year_override_maps",
        "artwork",
        "automation_defaults",
        "automation_children",
        "automation_override_maps",
        "visibility",
    ]

    for collection in _award_collections():
        fields = _field_map(collection)
        section_ids = [section.get("id") for section in collection.get("template_variable_sections") or [] if isinstance(section, dict)]

        assert section_ids == expected_sections
        for key in [
            "use_year_collections",
            "winning",
            "collection_order",
            "allowed_libraries",
            "image",
            "translation_key",
            "url_logo",
        ]:
            assert key in fields

        assert fields["allowed_libraries"]["type"] == "select"
        assert fields["image"]["section"] == "artwork"
        assert fields["translation_key"]["section"] == "naming"
        assert fields["url_logo"]["validation_preset"] == "url"


def test_award_defaults_expose_year_keyed_override_maps():
    collection = next(collection for collection in _award_collections() if collection.get("id") == "collection_oscars")
    fields = _field_map(collection)

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", "year_override_maps", None, None),
        "child_name_overrides": ("name_", "string", "year_override_maps", None, None),
        "child_summary_overrides": ("summary_", "string", "year_override_maps", None, None),
        "child_schedule_overrides": ("schedule_", "string", "year_override_maps", None, None),
        "child_collection_order_overrides": ("collection_order_", "select", "year_override_maps", None, None),
        "child_cache_builders_overrides": ("cache_builders_", "string", "year_override_maps", None, None),
        "child_image_overrides": ("image_", "string", "artwork", None, None),
        "child_translation_key_overrides": ("translation_key_", "string", "naming", None, None),
        "child_url_logo_overrides": ("url_logo_", "string", "artwork", "url", None),
        "child_radarr_folder_overrides": ("radarr_folder_", "string", "automation_override_maps", None, ["movie"]),
        "child_sonarr_monitor_overrides": ("sonarr_monitor_", "select", "automation_override_maps", None, ["show"]),
        "child_visible_home_overrides": ("visible_home_", "boolean", "visibility", None, None),
    }

    for key, (child_prefix, value_kind, section, validation_preset, media_types) in expected_mappings.items():
        _assert_mapping(fields[key], child_prefix, value_kind, section, validation_preset, media_types)
