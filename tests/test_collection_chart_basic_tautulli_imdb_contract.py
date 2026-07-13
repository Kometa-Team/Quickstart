import json
from pathlib import Path


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _collection(collection_id):
    data = json.loads(Path("static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    return next(node for node in _walk(data) if node.get("id") == collection_id)


def _field_keys(collection_id):
    return {field["key"] for field in _collection(collection_id)["template_variables"]}


def test_basic_chart_exposes_shared_artwork_and_fixed_child_controls():
    collection = _collection("collection_basic")
    keys = _field_keys("collection_basic")

    assert [section["id"] for section in collection["sections"]] == [
        "basics",
        "naming",
        "builder",
        "children",
        "artwork",
        "automation",
        "visibility",
    ]
    assert {
        "image",
        "allowed_libraries",
        "schedule",
        "url_logo",
        "url_logo_released",
        "url_logo_episodes",
        "sort_by_released",
        "sort_by_episodes",
    }.issubset(keys)
    assert "collection_order" not in keys
    assert "in_the_last_released" not in keys
    assert "in_the_last_episodes" not in keys


def test_tautulli_chart_exposes_shared_artwork_and_fixed_child_custom_controls():
    keys = _field_keys("collection_tautulli")

    assert {
        "image",
        "allowed_libraries",
        "schedule",
        "url_logo",
        "url_logo_popular",
        "url_logo_watched",
        "sync_mode_popular",
        "sync_mode_watched",
        "cache_builders_popular",
        "cache_builders_watched",
        "collection_order_popular",
        "collection_order_watched",
    }.issubset(keys)


def test_imdb_chart_exposes_shared_artwork_fixed_child_custom_and_arr_controls():
    keys = _field_keys("collection_imdb")

    assert {
        "image",
        "allowed_libraries",
        "schedule",
        "url_logo",
        "url_logo_popular",
        "url_logo_top",
        "url_logo_lowest",
        "sync_mode_popular",
        "cache_builders_top",
        "collection_order_lowest",
        "radarr_folder_top",
        "radarr_tag_popular",
        "sonarr_folder_popular",
        "sonarr_search_popular",
        "sonarr_monitor_existing_lowest",
    }.issubset(keys)
