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
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit"] == 120
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit_1001_movies"] == 80
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit_top_500"] == 60
    assert libraries_payload["mov-library_movies-template_collection_letterboxd_limit_women_directors"] == 40
    assert libraries_payload["mov-library_movies-template_collection_imdb_limit"] == 250
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
                                "name_10": "Skywalker Saga",
                                "sync_mode_10": "append",
                                "collection_order_10": "custom",
                                "url_poster_10": "https://example.com/star-wars.jpg",
                                "radarr_add_missing_10": True,
                                "radarr_folder_10": r"C:\Media\Movies",
                                "radarr_tag_10": ["4k", "franchise"],
                                "item_radarr_tag_10": ["collection", "tracked"],
                                "radarr_monitor_10": False,
                            },
                        }
                    ]
                },
                "Shows": {
                    "collection_files": [
                        {
                            "default": "franchise",
                            "template_variables": {
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
    assert any("libraries.Movies.collection_files[0].template_variables.name_10" in line for line in report.lines)
    assert any("libraries.Shows.collection_files[0].template_variables.sonarr_monitor_1399" in line for line in report.lines)
