import json
from pathlib import Path

QS_COLLECTIONS_PATH = Path("static/json/quickstart_collections.json")

EXPECTED_SECTIONS = [
    "basics",
    "naming",
    "scope",
    "other_collection",
    "child_override_maps",
    "artwork",
    "visibility",
]

EXPECTED_DEFAULTS = {
    ("collection_content_rating_us", ("movie",)): ("content_rating/us/<<key_name>>", "content_rating"),
    ("collection_content_rating_us", ("show",)): ("content_rating/us/<<key_name>>", "content_rating"),
    ("collection_content_rating_uk", ("movie", "show")): ("content_rating/uk/<<key_name>>", "content_rating"),
    ("collection_content_rating_de", ("movie", "show")): ("content_rating/de/<<key_name>>", "content_rating"),
    ("collection_content_rating_au", ("movie", "show")): ("content_rating/au/<<key_name>>", "content_rating"),
    ("collection_content_rating_nz", ("movie", "show")): ("content_rating/nz/<<key_name>>", "content_rating"),
    ("collection_content_rating_mal", ("movie", "show")): ("content_rating/mal/<<key_name_encoded>>", "content_rating"),
    ("collection_content_rating_cs", ("movie", "show")): ("content_rating/cs/<<key_name>>", "content_rating_cs"),
}


def _load_collections():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    collections = {}
    for group in data:
        for collection in group.get("collections", []):
            collection_id = collection.get("id")
            if collection_id and collection_id.startswith("collection_content_rating"):
                collections[(collection_id, tuple(collection.get("media_types") or []))] = collection
    return collections


def _field_map(collection):
    return {field["key"]: field for field in collection.get("template_variables", []) if isinstance(field, dict) and field.get("key")}


def _assert_mapping(field, child_prefix, value_kind, section, media_types=None):
    assert field["type"] == "mapping_list"
    assert field["dynamic_child_prefix"] == child_prefix
    assert field["dynamic_child_value_kind"] == value_kind
    assert field["section"] == section
    assert "key_input_mode" not in field
    if media_types is None:
        assert "media_types" not in field
    else:
        assert field["media_types"] == media_types


def test_content_rating_collections_expose_defaults_and_collapsible_sections():
    collections = _load_collections()

    assert set(collections) == set(EXPECTED_DEFAULTS)
    for key, (image_default, translation_default) in EXPECTED_DEFAULTS.items():
        collection = collections[key]
        fields = _field_map(collection)

        assert [section["id"] for section in collection.get("template_variable_sections") or []] == EXPECTED_SECTIONS
        assert fields["search_term"]["default"] == "content_rating"
        assert fields["search_term"]["section"] == "scope"
        assert fields["image"]["default"] == image_default
        assert fields["image"]["section"] == "artwork"
        assert fields["translation_key"]["default"] == translation_default
        assert fields["translation_key"]["section"] == "naming"
        assert fields["use_other"]["section"] == "other_collection"
        assert fields["limit_other"]["section"] == "other_collection"


def test_content_rating_collections_expose_per_rating_override_maps():
    fields = _field_map(_load_collections()[("collection_content_rating_uk", ("movie", "show"))])

    expected_mappings = {
        "child_use_overrides": ("use_", "boolean", "child_override_maps", None),
        "child_name_overrides": ("name_", "string", "child_override_maps", None),
        "child_summary_overrides": ("summary_", "string", "child_override_maps", None),
        "child_order_overrides": ("order_", "string", "child_override_maps", None),
        "child_schedule_overrides": ("schedule_", "string", "child_override_maps", None),
        "child_sort_by_overrides": ("sort_by_", "select", "child_override_maps", None),
        "child_limit_overrides": ("limit_", "integer", "child_override_maps", None),
        "child_minimum_items_overrides": ("minimum_items_", "integer", "child_override_maps", None),
        "child_image_overrides": ("image_", "string", "artwork", None),
        "child_translation_key_overrides": ("translation_key_", "string", "child_override_maps", None),
        "child_visible_home_overrides": ("visible_home_", "boolean", "visibility", None),
        "child_visible_library_overrides": ("visible_library_", "boolean", "visibility", None),
        "child_visible_shared_overrides": ("visible_shared_", "boolean", "visibility", None),
        "child_hub_priority_overrides": ("hub_priority_", "string", "visibility", None),
        "child_item_radarr_tag_overrides": ("item_radarr_tag_", "string_list", "visibility", ["movie"]),
        "child_item_sonarr_tag_overrides": ("item_sonarr_tag_", "string_list", "visibility", ["show"]),
    }
    for key, (child_prefix, value_kind, section, media_types) in expected_mappings.items():
        _assert_mapping(fields[key], child_prefix, value_kind, section, media_types)


def test_all_collection_template_variable_entries_are_sectioned_after_content_rating_pass():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    unsectioned = []
    missing_sections = []
    for group in data:
        for collection in group.get("collections", []):
            collection_id = collection.get("id")
            if not collection_id or collection_id.startswith("collection_separator"):
                continue
            if collection.get("template_variables") and not collection.get("template_variable_sections"):
                missing_sections.append(collection_id)
            for field in collection.get("template_variables") or []:
                if not field.get("section"):
                    unsectioned.append((collection_id, field.get("key")))

    assert missing_sections == []
    assert unsectioned == []
