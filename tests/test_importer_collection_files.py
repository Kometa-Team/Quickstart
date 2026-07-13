import json

from modules import importer


def test_prepare_import_payload_maps_multiple_collection_files_per_library():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {"file": "config/collections/movies.yml"},
                        {"folder": "config/collections/movies"},
                        {"git": "bullmoose20/godzilla.yml"},
                        {"repo": "custom/movies_extra.yml"},
                        {"url": "https://example.com/movie-collections.yml"},
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert "mov-library_movies-collection_files" in libraries_payload
    assert (
        libraries_payload["mov-library_movies-collection_files"]
        == '[{"type": "file", "location": "config/collections/movies.yml"}, {"type": "folder", "location": "config/collections/movies"}, {"type": "git", "location": "bullmoose20/godzilla.yml"}, {"type": "repo", "location": "custom/movies_extra.yml"}, {"type": "url", "location": "https://example.com/movie-collections.yml"}]'
    )
    assert any("libraries.Movies.collection_files[0].file" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[1].folder" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[2].git" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[3].repo" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[4].url" in line for line in report.lines)


def test_prepare_import_payload_accepts_chart_builder_size_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "tautulli",
                            "template_variables": {
                                "list_days": 14,
                                "list_size": 50,
                                "list_days_popular": 7,
                                "list_size_watched": 25,
                                "image": "chart/color/plex",
                                "url_logo_popular": "https://example.com/plex-popular.png",
                                "sync_mode_watched": "append",
                                "cache_builders_popular": 0,
                                "collection_order_popular": "custom",
                            },
                        },
                        {
                            "default": "trakt",
                            "template_variables": {
                                "limit": 75,
                                "limit_popular": 50,
                                "limit_recommended": 30,
                            },
                        },
                        {
                            "default": "tmdb",
                            "template_variables": {
                                "limit": 60,
                                "limit_airing": 20,
                                "limit_trending": 40,
                            },
                        },
                        {
                            "default": "simkl",
                            "template_variables": {
                                "limit_trending_today": 15,
                                "limit_dvd": 10,
                            },
                        },
                        {
                            "default": "anilist",
                            "template_variables": {
                                "limit": 80,
                                "limit_popular": 40,
                                "limit_season": 25,
                            },
                        },
                        {
                            "default": "myanimelist",
                            "template_variables": {
                                "limit": 90,
                                "limit_favorited": 45,
                                "limit_airing": 12,
                            },
                        },
                        {
                            "default": "basic",
                            "template_variables": {
                                "limit": 20,
                                "limit_released": 10,
                                "limit_episodes": 5,
                                "allowed_libraries": "show",
                                "schedule": "weekly(sunday)",
                                "url_logo_released": "https://example.com/released.png",
                                "sort_by_episodes": "episode_air_date.asc",
                            },
                        },
                        {
                            "default": "letterboxd",
                            "template_variables": {
                                "limit": 120,
                                "limit_1001_movies": 80,
                                "limit_top_500": 60,
                                "limit_women_directors": 40,
                            },
                        },
                        {
                            "default": "imdb",
                            "template_variables": {
                                "limit": 250,
                                "allowed_libraries": "movie",
                                "url_logo_lowest": "https://example.com/lowest.png",
                                "collection_order_top": "custom",
                                "radarr_folder_top": r"C:\Media\Movies",
                                "sonarr_search_popular": "false",
                            },
                        },
                        {
                            "default": "other_chart",
                            "template_variables": {
                                "limit": 125,
                            },
                        },
                        {
                            "default": "streaming",
                            "template_variables": {
                                "limit": 500,
                                "discover_limit": 150,
                            },
                        },
                        {
                            "default": "seasonal",
                            "template_variables": {
                                "limit": 30,
                                "limit_halloween": 12,
                            },
                        },
                        {
                            "default": "year",
                            "template_variables": {
                                "limit": 8,
                            },
                        },
                        {
                            "default": "content_rating_us",
                            "template_variables": {
                                "limit": 40,
                                "limit_other": 5,
                            },
                        },
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_tautulli"] is True
    assert libraries_payload["mov-library_movies-template_collection_tautulli_list_days"] == 14
    assert libraries_payload["mov-library_movies-template_collection_tautulli_list_size"] == 50
    assert libraries_payload["mov-library_movies-template_collection_tautulli_list_days_popular"] == 7
    assert libraries_payload["mov-library_movies-template_collection_tautulli_list_size_watched"] == 25
    assert libraries_payload["mov-library_movies-template_collection_tautulli_image"] == "chart/color/plex"
    assert libraries_payload["mov-library_movies-template_collection_tautulli_url_logo_popular"] == "https://example.com/plex-popular.png"
    assert libraries_payload["mov-library_movies-template_collection_tautulli_sync_mode_watched"] == "append"
    assert libraries_payload["mov-library_movies-template_collection_tautulli_cache_builders_popular"] == 0
    assert libraries_payload["mov-library_movies-template_collection_tautulli_collection_order_popular"] == "custom"
    assert libraries_payload["mov-library_movies-template_collection_trakt_limit"] == 75
    assert libraries_payload["mov-library_movies-template_collection_trakt_limit_popular"] == 50
    assert libraries_payload["mov-library_movies-template_collection_trakt_limit_recommended"] == 30
    assert libraries_payload["mov-library_movies-template_collection_tmdb_limit"] == 60
    assert libraries_payload["mov-library_movies-template_collection_tmdb_limit_airing"] == 20
    assert libraries_payload["mov-library_movies-template_collection_tmdb_limit_trending"] == 40
    assert libraries_payload["mov-library_movies-template_collection_simkl_limit_trending_today"] == 15
    assert libraries_payload["mov-library_movies-template_collection_simkl_limit_dvd"] == 10
    assert libraries_payload["mov-library_movies-template_collection_anilist_limit"] == 80
    assert libraries_payload["mov-library_movies-template_collection_anilist_limit_popular"] == 40
    assert libraries_payload["mov-library_movies-template_collection_anilist_limit_season"] == 25
    assert libraries_payload["mov-library_movies-template_collection_myanimelist_limit"] == 90
    assert libraries_payload["mov-library_movies-template_collection_myanimelist_limit_favorited"] == 45
    assert libraries_payload["mov-library_movies-template_collection_myanimelist_limit_airing"] == 12
    assert libraries_payload["mov-library_movies-template_collection_basic_limit"] == 20
    assert libraries_payload["mov-library_movies-template_collection_basic_limit_released"] == 10
    assert libraries_payload["mov-library_movies-template_collection_basic_limit_episodes"] == 5
    assert libraries_payload["mov-library_movies-template_collection_basic_allowed_libraries"] == "show"
    assert libraries_payload["mov-library_movies-template_collection_basic_schedule"] == "weekly(sunday)"
    assert libraries_payload["mov-library_movies-template_collection_basic_url_logo_released"] == "https://example.com/released.png"
    assert libraries_payload["mov-library_movies-template_collection_basic_sort_by_episodes"] == "episode_air_date.asc"
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit"] == 120
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit_1001_movies"] == 80
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit_top_500"] == 60
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit_women_directors"] == 40
    assert libraries_payload["mov-library_movies-template_collection_imdb_limit"] == 250
    assert libraries_payload["mov-library_movies-template_collection_imdb_allowed_libraries"] == "movie"
    assert libraries_payload["mov-library_movies-template_collection_imdb_url_logo_lowest"] == "https://example.com/lowest.png"
    assert libraries_payload["mov-library_movies-template_collection_imdb_collection_order_top"] == "custom"
    assert libraries_payload["mov-library_movies-template_collection_imdb_radarr_folder_top"] == r"C:\Media\Movies"
    assert libraries_payload["mov-library_movies-template_collection_imdb_sonarr_search_popular"] == "false"
    assert libraries_payload["mov-library_movies-template_collection_other_chart_limit"] == 125
    assert libraries_payload["mov-library_movies-template_collection_streaming_limit"] == 500
    assert libraries_payload["mov-library_movies-template_collection_streaming_discover_limit"] == 150
    assert libraries_payload["mov-library_movies-template_collection_seasonal_limit"] == 30
    assert libraries_payload["mov-library_movies-template_collection_seasonal_limit_halloween"] == 12
    assert libraries_payload["mov-library_movies-template_collection_year_limit"] == 8
    assert libraries_payload["mov-library_movies-template_collection_content_rating_us_limit"] == 40
    assert libraries_payload["mov-library_movies-template_collection_content_rating_us_limit_other"] == 5
    assert any("libraries.Movies.collection_files[0].template_variables.list_days" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[1].template_variables.limit_popular" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[2].template_variables.limit_airing" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[3].template_variables.limit_trending_today" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[4].template_variables.limit_season" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[5].template_variables.limit_favorited" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[6].template_variables.limit_released" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[7].template_variables.limit_top_500" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[8].template_variables.limit" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[9].template_variables.limit" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[10].template_variables.discover_limit" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[11].template_variables.limit_halloween" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[12].template_variables.limit" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[13].template_variables.limit_other" in line for line in report.lines)


def test_prepare_import_payload_collapses_franchise_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "franchise",
                            "template_variables": {
                                "build_collection": False,
                                "name_10": "Skywalker Saga",
                                "sync_mode_10": "append",
                                "collection_order_10": "custom",
                                "url_poster_10": "https://example.com/star-wars.jpg",
                                "radarr_add_missing_10": True,
                                "radarr_folder_10": r"C:\Media\Movies",
                                "radarr_tag_10": ["4k", "franchise"],
                                "item_radarr_tag_10": ["collection", "tracked"],
                                "radarr_monitor_10": False,
                                "title_override": {"10": "Star Wars: Skywalker Saga"},
                            },
                        }
                    ]
                },
                "Shows": {
                    "collection_files": [
                        {
                            "default": "franchise",
                            "template_variables": {
                                "build_collection": False,
                                "summary_1399": "Dragons and dynasties",
                                "sort_title_1399": "!350_Game of Thrones",
                                "sonarr_add_missing_1399": True,
                                "sonarr_folder_1399": r"C:\Media\Shows",
                                "sonarr_tag_1399": ["tracked", "priority"],
                                "item_sonarr_tag_1399": ["watched", "tracked"],
                                "sonarr_monitor_1399": "future",
                            },
                        }
                    ]
                },
            }
        },
        {"Movies"},
        {"Shows"},
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_franchise"] is True
    assert libraries_payload["sho-library_shows-collection_franchise"] is True
    assert libraries_payload["mov-library_movies-template_collection_franchise_build_collection"] is False
    assert libraries_payload["mov-library_movies-template_collection_franchise_title_override"] == {"10": "Star Wars: Skywalker Saga"}
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_name_overrides"] == '{"10": "Skywalker Saga"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_sync_mode_overrides"] == '{"10": "append"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_collection_order_overrides"] == '{"10": "custom"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_url_poster_overrides"] == '{"10": "https://example.com/star-wars.jpg"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_radarr_add_missing_overrides"] == '{"10": "true"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_radarr_folder_overrides"] == '{"10": "C:\\\\Media\\\\Movies"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_radarr_tag_overrides"] == '{"10": "4k,franchise"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_item_radarr_tag_overrides"] == '{"10": "collection,tracked"}'
    assert libraries_payload["mov-library_movies-template_collection_franchise_child_radarr_monitor_overrides"] == '{"10": "false"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_summary_overrides"] == '{"1399": "Dragons and dynasties"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_sort_title_overrides"] == '{"1399": "!350_Game of Thrones"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_sonarr_add_missing_overrides"] == '{"1399": "true"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_sonarr_folder_overrides"] == '{"1399": "C:\\\\Media\\\\Shows"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_sonarr_tag_overrides"] == '{"1399": "tracked,priority"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_item_sonarr_tag_overrides"] == '{"1399": "watched,tracked"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_child_sonarr_monitor_overrides"] == '{"1399": "future"}'
    assert libraries_payload["sho-library_shows-template_collection_franchise_build_collection"] is False
    assert any("libraries.Movies.collection_files[0].template_variables.name_10" in line for line in report.lines)
    assert any("libraries.Shows.collection_files[0].template_variables.sonarr_monitor_1399" in line for line in report.lines)


def test_prepare_import_payload_collapses_universe_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "universe",
                            "template_variables": {
                                "url_poster_avp": "https://example.com/avp.jpg",
                                "schedule_arrow": "weekly(sunday)",
                                "trakt_list_trek": ["https://trakt.tv/users/example/lists/star-trek"],
                                "delete_collections_named_mummy": ["The Mummy Universe"],
                                "radarr_folder_avp": r"C:\Media\Movies",
                                "radarr_search_avp": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_universe"] is True
    assert libraries_payload["mov-library_movies-template_collection_universe_child_url_poster_overrides"] == '{"avp": "https://example.com/avp.jpg"}'
    assert libraries_payload["mov-library_movies-template_collection_universe_child_schedule_overrides"] == '{"arrow": "weekly(sunday)"}'
    assert libraries_payload["mov-library_movies-template_collection_universe_child_trakt_list_overrides"] == '{"trek": "https://trakt.tv/users/example/lists/star-trek"}'
    assert libraries_payload["mov-library_movies-template_collection_universe_child_delete_collections_named_overrides"] == '{"mummy": "The Mummy Universe"}'
    assert libraries_payload["mov-library_movies-template_collection_universe_child_radarr_folder_overrides"] == '{"avp": "C:\\\\Media\\\\Movies"}'
    assert libraries_payload["mov-library_movies-template_collection_universe_child_radarr_search_overrides"] == '{"avp": "false"}'
    assert any("libraries.Movies.collection_files[0].template_variables.url_poster_avp" in line for line in report.lines)


def test_prepare_import_payload_collapses_streaming_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "streaming",
                            "template_variables": {
                                "use_amc": False,
                                "use_movistar": False,
                                "schedule_amc": "weekly(sunday)",
                                "sort_by_filmin": "title.asc",
                                "delete_collections_named_appletv": ["Apple TV+ Movies", "Apple TV+ Shows"],
                                "discover_with_atresplayer": "62|2162",
                                "url_logo_movistar": "https://example.com/movistar.png",
                                "radarr_folder_amc": r"C:\Media\Movies\AMC",
                                "radarr_tag_filmin": ["filmin", "euro"],
                                "radarr_monitor_movistar": True,
                                "sonarr_folder_amc": r"C:\Media\Shows\AMC",
                                "sonarr_monitor_filmin": "future",
                                "sonarr_search_atresplayer": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_streaming"] is True
    assert libraries_payload["mov-library_movies-template_collection_streaming_use_amc"] is False
    assert libraries_payload["mov-library_movies-template_collection_streaming_use_movistar"] is False
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_schedule_overrides"] == '{"amc": "weekly(sunday)"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_sort_by_overrides"] == '{"filmin": "title.asc"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_delete_collections_named_overrides"] == '{"appletv": "Apple TV+ Movies,Apple TV+ Shows"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_discover_with_overrides"] == '{"atresplayer": "62|2162"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_url_logo_overrides"] == '{"movistar": "https://example.com/movistar.png"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_radarr_folder_overrides"] == '{"amc": "C:\\\\Media\\\\Movies\\\\AMC"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_radarr_tag_overrides"] == '{"filmin": "filmin,euro"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_radarr_monitor_overrides"] == '{"movistar": "true"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_sonarr_folder_overrides"] == '{"amc": "C:\\\\Media\\\\Shows\\\\AMC"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_sonarr_monitor_overrides"] == '{"filmin": "future"}'
    assert libraries_payload["mov-library_movies-template_collection_streaming_child_sonarr_search_overrides"] == '{"atresplayer": "false"}'
    assert any("libraries.Movies.collection_files[0].template_variables.use_amc" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[0].template_variables.schedule_amc" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[0].template_variables.url_logo_movistar" in line for line in report.lines)


def test_prepare_import_payload_collapses_seasonal_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "seasonal",
                            "template_variables": {
                                "name_mapping_halloween": "Spooky Season",
                                "emoji_halloween": "🎃",
                                "delete_collections_named_halloween": ["Old Halloween Movies"],
                                "tmdb_collection_halloween": [185103, 11716],
                                "tmdb_movie_halloween": [23437],
                                "imdb_list_years": ["ls066838460"],
                                "imdb_search_halloween": {"list.any": ["ls546214737"], "limit": 500},
                                "trakt_list_halloween": ["https://trakt.tv/users/example/lists/halloween"],
                                "mdblist_list_christmas": ["https://mdblist.com/lists/k0meta/christmas-extravaganza"],
                                "letterboxd_list_black_history": ["https://letterboxd.com/mardarrius/list/black-is-beautiful/"],
                                "url_logo_women": "https://example.com/women.png",
                                "radarr_folder_halloween": r"C:\Media\Movies\Halloween",
                                "radarr_tag_christmas": ["holiday", "christmas"],
                                "item_radarr_tag_women": ["history"],
                                "radarr_search_halloween": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_seasonal"] is True
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_name_mapping_overrides"]) == {"halloween": "Spooky Season"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_emoji_overrides"]) == {"halloween": "🎃"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_delete_collections_named_overrides"]) == {"halloween": "Old Halloween Movies"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_tmdb_collection_overrides"]) == {"halloween": "185103,11716"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_tmdb_movie_overrides"]) == {"halloween": "23437"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_imdb_list_overrides"]) == {"years": "ls066838460"}
    imdb_search_mapping = json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_imdb_search_overrides"])
    assert json.loads(imdb_search_mapping["halloween"]) == {"list.any": ["ls546214737"], "limit": 500}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_trakt_list_overrides"]) == {
        "halloween": "https://trakt.tv/users/example/lists/halloween"
    }
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_mdblist_list_overrides"]) == {
        "christmas": "https://mdblist.com/lists/k0meta/christmas-extravaganza"
    }
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_letterboxd_list_overrides"]) == {
        "black_history": "https://letterboxd.com/mardarrius/list/black-is-beautiful/"
    }
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_url_logo_overrides"]) == {"women": "https://example.com/women.png"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_radarr_folder_overrides"]) == {"halloween": r"C:\Media\Movies\Halloween"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_radarr_tag_overrides"]) == {"christmas": "holiday,christmas"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_item_radarr_tag_overrides"]) == {"women": "history"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_seasonal_child_radarr_search_overrides"]) == {"halloween": "false"}
    assert any("libraries.Movies.collection_files[0].template_variables.imdb_search_halloween" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[0].template_variables.letterboxd_list_black_history" in line for line in report.lines)


def test_prepare_import_payload_collapses_region_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "region",
                            "template_variables": {
                                "use_North America": False,
                                "schedule_Northern Africa": "weekly(sunday)",
                                "name_mapping_other": "other_regions",
                                "sort_by_Western Europe": "title.asc",
                                "limit_Central America": 12,
                                "url_logo_Southern Europe": "https://example.com/europe.png",
                                "visible_home_Caribbean": True,
                                "visible_library_Caribbean": False,
                                "visible_shared_Caribbean": True,
                                "hub_priority_Australia and New Zealand": 7,
                                "item_radarr_tag_North America": ["north", "america"],
                                "item_sonarr_tag_Eastern Asia": ["anime"],
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_region"] is True
    assert libraries_payload["mov-library_movies-template_collection_region_use_North America"] is False
    assert json.loads(libraries_payload["mov-library_movies-template_collection_region_child_schedule_overrides"]) == {"Northern Africa": "weekly(sunday)"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_region_child_name_mapping_overrides"]) == {"other": "other_regions"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_region_child_sort_by_overrides"]) == {"Western Europe": "title.asc"}
    assert libraries_payload["mov-library_movies-template_collection_region_limit_Central America"] == 12
    assert json.loads(libraries_payload["mov-library_movies-template_collection_region_child_url_logo_overrides"]) == {"Southern Europe": "https://example.com/europe.png"}
    assert libraries_payload["mov-library_movies-template_collection_region_visible_home_Caribbean"] is True
    assert libraries_payload["mov-library_movies-template_collection_region_visible_library_Caribbean"] is False
    assert libraries_payload["mov-library_movies-template_collection_region_visible_shared_Caribbean"] is True
    assert libraries_payload["mov-library_movies-template_collection_region_hub_priority_Australia and New Zealand"] == 7
    assert json.loads(libraries_payload["mov-library_movies-template_collection_region_child_item_radarr_tag_overrides"]) == {"North America": "north,america"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_region_child_item_sonarr_tag_overrides"]) == {"Eastern Asia": "anime"}
    assert any("libraries.Movies.collection_files[0].template_variables.use_North America" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[0].template_variables.name_mapping_other" in line for line in report.lines)


def test_prepare_import_payload_collapses_studio_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "studio",
                            "template_variables": {
                                "use_A24": False,
                                "name_Marvel Studios": "Marvel Films",
                                "summary_Warner Bros. Pictures": "Warner favorites",
                                "schedule_Studio Ghibli": "weekly(sunday)",
                                "name_mapping_Lucasfilm Ltd": "lucasfilm",
                                "sort_by_Marvel Studios": "title.asc",
                                "limit_A24": 10,
                                "url_poster_A24": "https://example.com/a24.jpg",
                                "visible_home_Pixar": False,
                                "visible_library_Pixar": True,
                                "visible_shared_Pixar": False,
                                "hub_priority_DreamWorks Studios": 3,
                                "item_radarr_tag_Lucasfilm Ltd": ["space", "saga"],
                                "item_sonarr_tag_Warner Bros. Pictures": ["prestige"],
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_studio"] is True
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_use_overrides"]) == {"A24": "false"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_name_overrides"]) == {"Marvel Studios": "Marvel Films"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_summary_overrides"]) == {"Warner Bros. Pictures": "Warner favorites"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_schedule_overrides"]) == {"Studio Ghibli": "weekly(sunday)"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_name_mapping_overrides"]) == {"Lucasfilm Ltd": "lucasfilm"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_sort_by_overrides"]) == {"Marvel Studios": "title.asc"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_limit_overrides"]) == {"A24": "10"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_url_poster_overrides"]) == {"A24": "https://example.com/a24.jpg"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_visible_home_overrides"]) == {"Pixar": "false"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_visible_library_overrides"]) == {"Pixar": "true"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_visible_shared_overrides"]) == {"Pixar": "false"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_hub_priority_overrides"]) == {"DreamWorks Studios": "3"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_item_radarr_tag_overrides"]) == {"Lucasfilm Ltd": "space,saga"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_studio_child_item_sonarr_tag_overrides"]) == {"Warner Bros. Pictures": "prestige"}
    assert any("libraries.Movies.collection_files[0].template_variables.use_A24" in line for line in report.lines)
    assert any("libraries.Movies.collection_files[0].template_variables.summary_Warner Bros. Pictures" in line for line in report.lines)


def test_prepare_import_payload_collapses_network_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Shows": {
                    "collection_files": [
                        {
                            "default": "network",
                            "template_variables": {
                                "use_Apple TV": False,
                                "name_HBO Max": "Max Originals",
                                "summary_Disney+": "Disney network picks",
                                "schedule_Netflix": "weekly(friday)",
                                "name_mapping_Apple TV": "apple_tv",
                                "sort_by_Netflix": "release.desc",
                                "limit_HBO": 15,
                                "url_background_HBO": "https://example.com/hbo-bg.jpg",
                                "visible_home_Showtime": True,
                                "visible_library_Showtime": False,
                                "visible_shared_Showtime": True,
                                "hub_priority_Disney+": 5,
                                "item_sonarr_tag_Apple TV": ["streaming", "tv"],
                            },
                        }
                    ]
                }
            }
        },
        set(),
        {"Shows"},
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["sho-library_shows-collection_network"] is True
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_use_overrides"]) == {"Apple TV": "false"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_name_overrides"]) == {"HBO Max": "Max Originals"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_summary_overrides"]) == {"Disney+": "Disney network picks"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_schedule_overrides"]) == {"Netflix": "weekly(friday)"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_name_mapping_overrides"]) == {"Apple TV": "apple_tv"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_sort_by_overrides"]) == {"Netflix": "release.desc"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_limit_overrides"]) == {"HBO": "15"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_url_background_overrides"]) == {"HBO": "https://example.com/hbo-bg.jpg"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_visible_home_overrides"]) == {"Showtime": "true"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_visible_library_overrides"]) == {"Showtime": "false"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_visible_shared_overrides"]) == {"Showtime": "true"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_hub_priority_overrides"]) == {"Disney+": "5"}
    assert json.loads(libraries_payload["sho-library_shows-template_collection_network_child_item_sonarr_tag_overrides"]) == {"Apple TV": "streaming,tv"}
    assert any("libraries.Shows.collection_files[0].template_variables.use_Apple TV" in line for line in report.lines)
    assert any("libraries.Shows.collection_files[0].template_variables.summary_Disney+" in line for line in report.lines)


def test_prepare_import_payload_collapses_genre_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "genre",
                            "template_variables": {
                                "use_Action": False,
                                "schedule_Comedy": "weekly(sunday)",
                                "sort_by_Drama": "title.asc",
                                "limit_Horror": 25,
                                "minimum_items_Sci-Fi": 3,
                                "file_poster_Action": r"C:\Posters\action.jpg",
                                "url_poster_Comedy": "https://example.com/comedy.jpg",
                                "visible_home_Drama": True,
                                "item_radarr_tag_Horror": ["genre", "horror"],
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_genre"] is True
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_use_overrides"]) == {"Action": "false"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_schedule_overrides"]) == {"Comedy": "weekly(sunday)"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_sort_by_overrides"]) == {"Drama": "title.asc"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_limit_overrides"]) == {"Horror": "25"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_minimum_items_overrides"]) == {"Sci-Fi": "3"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_file_poster_overrides"]) == {"Action": r"C:\Posters\action.jpg"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_url_poster_overrides"]) == {"Comedy": "https://example.com/comedy.jpg"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_visible_home_overrides"]) == {"Drama": "true"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_genre_child_item_radarr_tag_overrides"]) == {"Horror": "genre,horror"}
    assert any("libraries.Movies.collection_files[0].template_variables.file_poster_Action" in line for line in report.lines)


def test_prepare_import_payload_collapses_other_chart_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "other_chart",
                            "template_variables": {
                                "schedule_metacritic": "weekly(friday)",
                                "sync_mode_commonsense": "append",
                                "collection_order_pirated": "custom",
                                "cache_builders_stevenlu": 2,
                                "file_logo_commonsense": r"C:\Logos\css.png",
                                "radarr_search_pirated": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_other_chart"] is True
    assert json.loads(libraries_payload["mov-library_movies-template_collection_other_chart_child_schedule_overrides"]) == {"metacritic": "weekly(friday)"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_other_chart_child_sync_mode_overrides"]) == {"commonsense": "append"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_other_chart_child_collection_order_overrides"]) == {"pirated": "custom"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_other_chart_child_cache_builders_overrides"]) == {"stevenlu": "2"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_other_chart_child_file_logo_overrides"]) == {"commonsense": r"C:\Logos\css.png"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_other_chart_child_radarr_search_overrides"]) == {"pirated": "false"}
    assert any("libraries.Movies.collection_files[0].template_variables.radarr_search_pirated" in line for line in report.lines)


def test_prepare_import_payload_collapses_actor_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "actor",
                            "template_variables": {
                                "name_Tom Hanks": "Hanks Favorites",
                                "tmdb_person_offset_Tom Hanks": 1,
                                "limit_Tom Hanks": 50,
                                "file_poster_Tom Hanks": r"C:\Posters\tom-hanks.jpg",
                                "visible_library_Tom Hanks": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_actor"] is True
    assert json.loads(libraries_payload["mov-library_movies-template_collection_actor_child_name_overrides"]) == {"Tom Hanks": "Hanks Favorites"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_actor_child_tmdb_person_offset_overrides"]) == {"Tom Hanks": "1"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_actor_child_limit_overrides"]) == {"Tom Hanks": "50"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_actor_child_file_poster_overrides"]) == {"Tom Hanks": r"C:\Posters\tom-hanks.jpg"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_actor_child_visible_library_overrides"]) == {"Tom Hanks": "false"}
    assert any("libraries.Movies.collection_files[0].template_variables.tmdb_person_offset_Tom Hanks" in line for line in report.lines)


def test_prepare_import_payload_collapses_year_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "year",
                            "template_variables": {
                                "search_term": "year",
                                "image": "year/best/<<key>>",
                                "translation_key": "year",
                                "use_2024": False,
                                "name_2024": "Best of This Year",
                                "schedule_2023": "weekly(sunday)",
                                "sort_by_2022": "title.asc",
                                "limit_2021": 12,
                                "minimum_items_2020": 3,
                                "url_background_2019": "https://example.com/2019-bg.jpg",
                                "file_logo_2018": r"C:\Logos\2018.png",
                                "visible_home_2017": True,
                                "item_radarr_tag_2016": ["year", "2016"],
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_year"] is True
    assert libraries_payload["mov-library_movies-template_collection_year_search_term"] == "year"
    assert libraries_payload["mov-library_movies-template_collection_year_image"] == "year/best/<<key>>"
    assert libraries_payload["mov-library_movies-template_collection_year_translation_key"] == "year"
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_use_overrides"]) == {"2024": "false"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_name_overrides"]) == {"2024": "Best of This Year"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_schedule_overrides"]) == {"2023": "weekly(sunday)"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_sort_by_overrides"]) == {"2022": "title.asc"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_limit_overrides"]) == {"2021": "12"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_minimum_items_overrides"]) == {"2020": "3"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_url_background_overrides"]) == {"2019": "https://example.com/2019-bg.jpg"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_file_logo_overrides"]) == {"2018": r"C:\Logos\2018.png"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_visible_home_overrides"]) == {"2017": "true"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_year_child_item_radarr_tag_overrides"]) == {"2016": "year,2016"}
    assert any("libraries.Movies.collection_files[0].template_variables.schedule_2023" in line for line in report.lines)


def test_prepare_import_payload_collapses_decade_dynamic_child_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Shows": {
                    "collection_files": [
                        {
                            "default": "decade",
                            "template_variables": {
                                "search_term": "year",
                                "image": "decade/best/<<key>>",
                                "translation_key": "decade",
                                "use_2020": False,
                                "summary_2010": "2010s favorites",
                                "order_2000": "03",
                                "schedule_1990": "weekly(friday)",
                                "sort_by_1980": "critic_rating.desc",
                                "limit_1970": 25,
                                "url_square_art_1960": "https://example.com/1960-square.png",
                                "file_background_1950": r"C:\Backgrounds\1950.jpg",
                                "visible_library_1940": False,
                                "item_sonarr_tag_1930": ["decade", "1930s"],
                            },
                        }
                    ]
                }
            }
        },
        {"Shows"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_shows-collection_decade"] is True
    assert libraries_payload["mov-library_shows-template_collection_decade_search_term"] == "year"
    assert libraries_payload["mov-library_shows-template_collection_decade_image"] == "decade/best/<<key>>"
    assert libraries_payload["mov-library_shows-template_collection_decade_translation_key"] == "decade"
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_use_overrides"]) == {"2020": "false"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_summary_overrides"]) == {"2010": "2010s favorites"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_order_overrides"]) == {"2000": "03"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_schedule_overrides"]) == {"1990": "weekly(friday)"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_sort_by_overrides"]) == {"1980": "critic_rating.desc"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_limit_overrides"]) == {"1970": "25"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_url_square_art_overrides"]) == {"1960": "https://example.com/1960-square.png"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_file_background_overrides"]) == {"1950": r"C:\Backgrounds\1950.jpg"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_visible_library_overrides"]) == {"1940": "false"}
    assert json.loads(libraries_payload["mov-library_shows-template_collection_decade_child_item_sonarr_tag_overrides"]) == {"1930": "decade,1930s"}
    assert any("libraries.Shows.collection_files[0].template_variables.schedule_1990" in line for line in report.lines)


def test_prepare_import_payload_collapses_award_year_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "collection_files": [
                        {
                            "default": "oscars",
                            "template_variables": {
                                "allowed_libraries": "movie",
                                "image": "award/oscars/winner/<<key>>",
                                "translation_key": "oscars_year",
                                "url_logo": "https://example.com/oscars.png",
                                "collection_order_2024": "release",
                                "image_2024": "award/oscars/winner/2024",
                                "translation_key_2024": "oscars_year",
                                "url_logo_2024": "https://example.com/oscars-2024.png",
                                "radarr_folder_2024": r"C:\Media\Movies\Awards",
                                "radarr_search_2024": False,
                                "visible_home_2024": True,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_oscars"] is True
    assert libraries_payload["mov-library_movies-template_collection_oscars_allowed_libraries"] == "movie"
    assert libraries_payload["mov-library_movies-template_collection_oscars_image"] == "award/oscars/winner/<<key>>"
    assert libraries_payload["mov-library_movies-template_collection_oscars_translation_key"] == "oscars_year"
    assert libraries_payload["mov-library_movies-template_collection_oscars_url_logo"] == "https://example.com/oscars.png"
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_collection_order_overrides"]) == {"2024": "release"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_image_overrides"]) == {"2024": "award/oscars/winner/2024"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_translation_key_overrides"]) == {"2024": "oscars_year"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_url_logo_overrides"]) == {"2024": "https://example.com/oscars-2024.png"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_radarr_folder_overrides"]) == {"2024": r"C:\Media\Movies\Awards"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_radarr_search_overrides"]) == {"2024": "false"}
    assert json.loads(libraries_payload["mov-library_movies-template_collection_oscars_child_visible_home_overrides"]) == {"2024": "true"}
    assert any("libraries.Movies.collection_files[0].template_variables.image_2024" in line for line in report.lines)
