import json
from pathlib import Path

QS_COLLECTIONS_PATH = Path("static/json/quickstart_collections.json")

CHART_COLLECTION_IDS = [
    "collection_basic",
    "collection_tautulli",
    "collection_tracearr",
    "collection_imdb",
    "collection_tmdb",
    "collection_trakt",
    "collection_simkl",
    "collection_anilist",
    "collection_myanimelist",
    "collection_letterboxd",
]

EXPECTED_TEMPLATE_SECTIONS = [
    "basics",
    "naming",
    "shared_defaults",
    "child_collections",
    "filtering",
    "artwork",
    "visibility",
    "item_tags",
    "radarr",
    "sonarr",
]


def _load_collections():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    return {collection["id"]: collection for group in data for collection in group.get("collections", []) if collection.get("id") in CHART_COLLECTION_IDS}


def _field_map(collection):
    return {field["key"]: field for field in collection.get("template_variables", []) if isinstance(field, dict) and field.get("key")}


def test_chart_source_collections_define_collapsible_template_variable_sections():
    collections = _load_collections()

    assert set(collections) == set(CHART_COLLECTION_IDS)
    for collection_id in CHART_COLLECTION_IDS:
        collection = collections[collection_id]
        section_defs = collection.get("template_variable_sections") or []

        assert [section["id"] for section in section_defs] == EXPECTED_TEMPLATE_SECTIONS
        assert section_defs[0]["default_open"] is True

        field_sections = {field.get("section") for field in collection.get("template_variables") or []}
        assert None not in field_sections
        assert field_sections <= set(EXPECTED_TEMPLATE_SECTIONS)


def test_chart_source_common_fields_are_grouped_by_ui_purpose():
    fields = _field_map(_load_collections()["collection_imdb"])

    assert fields["collection_section"]["section"] == "basics"
    assert fields["allowed_libraries"]["section"] == "basics"
    assert fields["sort_title"]["section"] == "naming"
    assert fields["delete_collections_named"]["section"] == "naming"
    assert fields["limit"]["section"] == "shared_defaults"
    assert fields["sync_mode"]["section"] == "shared_defaults"
    assert fields["ignore_ids"]["section"] == "filtering"
    assert fields["ignore_imdb_ids"]["section"] == "filtering"
    assert fields["image"]["section"] == "artwork"
    assert fields["url_logo_lowest"]["section"] == "artwork"
    assert fields["hub_priority_top"]["section"] == "visibility"
    assert fields["visible_home_popular"]["section"] == "visibility"
    assert fields["item_radarr_tag_top"]["section"] == "item_tags"
    assert fields["item_sonarr_tag_lowest"]["section"] == "item_tags"
    assert fields["radarr_folder_top"]["section"] == "radarr"
    assert fields["radarr_monitor_existing_lowest"]["section"] == "radarr"
    assert fields["sonarr_folder_popular"]["section"] == "sonarr"
    assert fields["sonarr_search_popular"]["section"] == "sonarr"


def test_chart_source_child_specific_controls_share_chart_collections_section():
    collections = _load_collections()

    examples = {
        "collection_basic": ["use_released", "name_episodes", "sort_by_released", "limit_episodes"],
        "collection_tautulli": ["list_days_popular", "list_size_watched", "cache_builders_popular", "collection_order_watched"],
        "collection_tracearr": ["list_days_popular", "list_minimum_trending", "list_size_transcoded", "use_binged"],
        "collection_tmdb": ["use_trending", "limit_airing", "sync_mode_top", "schedule_air"],
        "collection_simkl": ["period", "limit_trending_today", "schedule_dvd"],
        "collection_myanimelist": ["starting_only", "starting_only_season", "limit_favorited", "schedule_airing"],
        "collection_letterboxd": ["use_top_500", "limit_1001_movies", "cache_builders_black_directors", "collection_order_cannes"],
    }

    for collection_id, keys in examples.items():
        fields = _field_map(collections[collection_id])
        for key in keys:
            if key in {"period", "starting_only"}:
                assert fields[key]["section"] == "shared_defaults"
            else:
                assert fields[key]["section"] == "child_collections"
