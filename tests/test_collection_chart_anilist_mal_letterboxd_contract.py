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


def test_anilist_chart_exposes_shared_child_custom_and_arr_template_variables():
    collection = _collection("collection_anilist")
    keys = _field_keys("collection_anilist")

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
        "url_logo_season",
        "sync_mode_trending",
        "cache_builders_season",
        "collection_order_top",
        "radarr_folder_popular",
        "radarr_tag_trending",
        "sonarr_folder_season",
        "sonarr_search_season",
    }.issubset(keys)


def test_myanimelist_chart_exposes_starting_only_shared_child_custom_and_arr_template_variables():
    keys = _field_keys("collection_myanimelist")

    assert {
        "starting_only",
        "starting_only_season",
        "image",
        "allowed_libraries",
        "schedule",
        "url_logo",
        "url_logo_popular",
        "url_logo_favorited",
        "url_logo_top",
        "url_logo_airing",
        "url_logo_season",
        "sync_mode_season",
        "cache_builders_airing",
        "collection_order_top",
        "radarr_folder_favorited",
        "radarr_tag_popular",
        "sonarr_folder_season",
        "sonarr_search_season",
    }.issubset(keys)


def test_letterboxd_chart_exposes_shared_child_custom_and_arr_template_variables():
    keys = _field_keys("collection_letterboxd")

    assert {
        "image",
        "allowed_libraries",
        "schedule",
        "sort_title",
        "url_logo",
        "url_logo_top_500",
        "url_logo_1001_movies",
        "url_logo_black_directors",
        "url_logo_imdb_top_250",
        "url_logo_oscars",
        "url_logo_cannes",
        "sync_mode_oscars",
        "cache_builders_black_directors",
        "collection_order_cannes",
        "radarr_folder_women_directors",
        "radarr_tag_top_500",
        "sonarr_folder_imdb_top_250",
        "sonarr_search_imdb_top_250",
    }.issubset(keys)
