import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"


def _load_collections():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    collections = []
    for group in data:
        collections.extend(group.get("collections", []))
    return collections


def _find_collection(collection_id, media_types):
    media_types = tuple(media_types)
    for collection in _load_collections():
        if collection.get("id") != collection_id:
            continue
        if tuple(collection.get("media_types") or []) == media_types:
            return collection
    raise AssertionError(f"Missing collection {collection_id} with media types {media_types}")


def _keys(collection):
    return [item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")]


def _child_suffixes(collection):
    suffixes = []
    for key in _keys(collection):
        if not key.startswith("use_"):
            continue
        if key in {"use_all", "use_separator", "use_year_collections"}:
            continue
        suffixes.append(key.removeprefix("use_"))
    return suffixes


def test_streaming_and_seasonal_sync_mode_child_overrides_follow_child_toggles():
    for collection_id, media_types in (
        ("collection_streaming", ("movie", "show")),
        ("collection_seasonal", ("movie",)),
    ):
        collection = _find_collection(collection_id, media_types)
        keys = set(_keys(collection))
        suffixes = _child_suffixes(collection)

        assert suffixes

        for suffix in suffixes:
            child_key = f"sync_mode_{suffix}"
            assert child_key in keys

            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == child_key)
            assert field["type"] == "select"
            assert field["default"] == ""
            assert field["options"][0] == {"value": "", "label": "Use Family Default"}


def test_universe_minimum_items_child_overrides_follow_child_toggles():
    collection = _find_collection("collection_universe", ("movie", "show"))
    keys = set(_keys(collection))
    suffixes = _child_suffixes(collection)

    assert suffixes

    for suffix in suffixes:
        child_key = f"minimum_items_{suffix}"
        assert child_key in keys

        field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == child_key)
        assert field["type"] == "text_input"
        assert field["input_type"] == "number"
        assert field["min"] == 1
        assert field["step"] == 1
        assert "default" not in field


def test_name_and_summary_child_overrides_follow_child_toggles_for_shared_naming_families():
    for collection in _load_collections():
        keys = _keys(collection)
        if "name_format" not in keys or "summary_format" not in keys:
            continue

        suffixes = _child_suffixes(collection)
        if not suffixes:
            continue

        for suffix in suffixes:
            name_key = f"name_{suffix}"
            summary_key = f"summary_{suffix}"
            assert name_key in keys
            assert summary_key in keys

            name_field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == name_key)
            summary_field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == summary_key)

            assert name_field["type"] == "text_input"
            assert summary_field["type"] == "text_input"
            assert "default" not in name_field
            assert "default" not in summary_field


def test_franchise_has_no_predefined_child_toggle_surface_yet():
    for media_types in (("movie",), ("show",)):
        collection = _find_collection("collection_franchise", media_types)
        keys = _keys(collection)

        assert all(not key.startswith("use_") for key in keys)
        assert all(not key.startswith("sync_mode_") for key in keys)
        assert all(not key.startswith("collection_order_") for key in keys)
        assert all(not key.startswith("sort_title_") for key in keys)


def test_year_collections_master_toggle_does_not_get_fake_child_name_or_summary_overrides():
    for collection in _load_collections():
        keys = _keys(collection)
        if "use_year_collections" not in keys:
            continue

        assert "name_year_collections" not in keys
        assert "summary_year_collections" not in keys
