from modules import importer


def test_prepare_import_payload_maps_library_radarr_overrides():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "radarr": {
                        "url": "http://radarr.local:7878",
                        "quality_profile": "HD-1080p",
                        "search": True,
                        "add_existing": False,
                    }
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-library"] == "Movies"
    assert libraries["mov-library_movies-attribute_radarr_url"] == "http://radarr.local:7878"
    assert libraries["mov-library_movies-attribute_radarr_quality_profile"] == "HD-1080p"
    assert libraries["mov-library_movies-attribute_radarr_search"] == "true"
    assert libraries["mov-library_movies-attribute_radarr_add_existing"] == "false"
    assert any("libraries.Movies.radarr.url" in line for line in report.lines)


def test_prepare_import_payload_maps_library_sonarr_overrides():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Shows": {
                    "sonarr": {
                        "url": "http://sonarr.local:8989",
                        "language_profile": "English",
                        "monitor": "future",
                        "season_folder": True,
                    }
                }
            }
        },
        set(),
        {"Shows"},
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["sho-library_shows-library"] == "Shows"
    assert libraries["sho-library_shows-attribute_sonarr_url"] == "http://sonarr.local:8989"
    assert libraries["sho-library_shows-attribute_sonarr_language_profile"] == "English"
    assert libraries["sho-library_shows-attribute_sonarr_monitor"] == "future"
    assert libraries["sho-library_shows-attribute_sonarr_season_folder"] == "true"
    assert any("libraries.Shows.sonarr.language_profile" in line for line in report.lines)


def test_prepare_import_payload_maps_library_schedule_overlays():
    payload, report = importer.prepare_import_payload(
        {"libraries": {"Movies": {"schedule_overlays": "weekly(saturday)"}}},
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-top_level_schedule_overlays"] == "weekly(saturday)"
    assert any("libraries.Movies.schedule_overlays" in line for line in report.lines)


def test_prepare_import_payload_maps_library_schedule():
    payload, report = importer.prepare_import_payload(
        {"libraries": {"Movies": {"schedule": "weekly(saturday)"}}},
        {"Movies"},
        set(),
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-top_level_schedule"] == "weekly(saturday)"
    assert any("libraries.Movies.schedule" in line for line in report.lines)


def test_prepare_import_payload_maps_library_auto_sort_hubs():
    payload, report = importer.prepare_import_payload(
        {"libraries": {"Movies": {"auto_sort_hubs": "configured.desc"}}},
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-top_level_auto_sort_hubs"] == "configured.desc"
    assert any("libraries.Movies.auto_sort_hubs" in line for line in report.lines)
