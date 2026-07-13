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


def test_tmdb_chart_exposes_shared_child_custom_and_arr_template_variables():
    collection = _collection("collection_tmdb")
    keys = _field_keys("collection_tmdb")

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
        "url_logo_popular",
        "url_logo_top",
        "url_logo_trending",
        "url_logo_airing",
        "url_logo_air",
        "sync_mode_trending",
        "cache_builders_airing",
        "collection_order_air",
        "radarr_folder_top",
        "radarr_tag_popular",
        "sonarr_folder_airing",
        "sonarr_search_air",
    }.issubset(keys)


def test_trakt_chart_exposes_shared_child_custom_and_arr_template_variables():
    keys = _field_keys("collection_trakt")

    assert {
        "image",
        "allowed_libraries",
        "schedule",
        "url_logo",
        "url_logo_collected",
        "url_logo_recommended",
        "url_logo_watched",
        "sync_mode_recommended",
        "cache_builders_trending",
        "collection_order_watched",
        "radarr_folder_collected",
        "radarr_tag_popular",
        "sonarr_folder_trending",
        "sonarr_search_watched",
    }.issubset(keys)


def test_simkl_chart_exposes_period_shared_child_custom_and_arr_template_variables():
    keys = _field_keys("collection_simkl")

    assert {
        "period",
        "image",
        "allowed_libraries",
        "schedule",
        "url_logo",
        "url_logo_trending_today",
        "url_logo_trending_week",
        "url_logo_trending_month",
        "url_logo_dvd",
        "sync_mode_trending_week",
        "cache_builders_trending_month",
        "collection_order_dvd",
        "radarr_folder_dvd",
        "radarr_tag_trending_today",
        "sonarr_folder_trending_month",
        "sonarr_search_trending_week",
    }.issubset(keys)
