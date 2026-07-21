import json

from modules import importer


def test_prepare_import_payload_unknown_section():
    payload, report = importer.prepare_import_payload({"mystery": {"foo": "bar"}}, set(), set())
    assert payload == {}
    assert report.counts["unmapped"] >= 1
    assert any("mystery" in line for line in report.lines)


def test_prepare_import_payload_invalid_libraries_format():
    payload, report = importer.prepare_import_payload({"libraries": "not-a-dict"}, set(), set())
    assert payload == {}
    assert any("libraries" in line and "Unsupported libraries format" in line for line in report.lines)


def test_prepare_import_payload_maps_playlist_files_to_library_toggles():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {"Movies": {}},
            "playlist_files": [
                {
                    "default": "playlist",
                    "template_variables": {"libraries": ["Movies"]},
                }
            ],
        },
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-library"] == "Movies"
    assert libraries["mov-library_movies-playlist"] == "true"
    assert "playlist_files" not in payload
    assert any("libraries.Movies.playlist_files" in line for line in report.lines)


def test_prepare_import_payload_accepts_comma_separated_playlist_libraries():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {"Movies": {}, "TV Shows": {}},
            "playlist_files": [
                {
                    "default": "playlist",
                    "template_variables": {"libraries": "Movies, TV Shows"},
                }
            ],
        },
        {"Movies", "TV Shows"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-library"] == "Movies"
    assert libraries["mov-library_movies-playlist"] == "true"
    assert libraries["mov-library_tvshows-library"] == "TV Shows"
    assert libraries["mov-library_tvshows-playlist"] == "true"
    assert any("playlist_files[0].template_variables.libraries" in line for line in report.lines)


def test_prepare_import_payload_maps_playlist_template_variables_into_libraries_payload():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {"Movies": {}},
            "playlist_files": [
                {
                    "default": "playlist",
                    "template_variables": {
                        "libraries": ["Movies"],
                        "sync_to_users": ["alice", "bob"],
                        "delete_playlist": True,
                        "radarr_add_missing": True,
                        "radarr_folder": "/data/media/movies",
                        "radarr_tag": ["playlist-default"],
                        "sonarr_add_missing": False,
                        "sonarr_folder": "/data/media/shows",
                        "sonarr_tag": ["playlist-show"],
                        "trakt_list": ["https://trakt.tv/users/example/lists/default"],
                        "name_mcu": "Marvel Timeline",
                        "delete_playlist_mcu": True,
                        "radarr_add_missing_mcu": True,
                        "radarr_folder_mcu": "/data/media/movies/mcu",
                        "radarr_tag_mcu": ["mcu", "timeline"],
                        "sonarr_add_missing_mcu": False,
                        "sonarr_folder_mcu": "/data/media/shows/mcu",
                        "sonarr_tag_mcu": ["mcu-show"],
                        "trakt_list_mcu": ["https://trakt.tv/users/example/lists/mcu"],
                    },
                }
            ],
        },
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-library"] == "Movies"
    assert libraries["mov-library_movies-playlist"] == "true"
    assert libraries["playlist-template_variables[sync_to_users]"] == "alice, bob"
    assert libraries["playlist-template_variables[delete_playlist]"] is True
    assert libraries["playlist-template_variables[radarr_add_missing]"] is True
    assert libraries["playlist-template_variables[radarr_folder]"] == "/data/media/movies"
    assert json.loads(libraries["playlist-template_variables[radarr_tag]"]) == ["playlist-default"]
    assert libraries["playlist-template_variables[sonarr_add_missing]"] is False
    assert libraries["playlist-template_variables[sonarr_folder]"] == "/data/media/shows"
    assert json.loads(libraries["playlist-template_variables[sonarr_tag]"]) == ["playlist-show"]
    assert json.loads(libraries["playlist-template_variables[trakt_list]"]) == ["https://trakt.tv/users/example/lists/default"]
    assert json.loads(libraries["playlist-template_variables[name_]"]) == {"mcu": "Marvel Timeline"}
    assert json.loads(libraries["playlist-template_variables[delete_playlist_]"]) == {"mcu": "true"}
    assert json.loads(libraries["playlist-template_variables[radarr_add_missing_]"]) == {"mcu": "true"}
    assert json.loads(libraries["playlist-template_variables[radarr_folder_]"]) == {"mcu": "/data/media/movies/mcu"}
    assert json.loads(libraries["playlist-template_variables[radarr_tag_]"]) == {"mcu": ["mcu", "timeline"]}
    assert json.loads(libraries["playlist-template_variables[sonarr_add_missing_]"]) == {"mcu": "false"}
    assert json.loads(libraries["playlist-template_variables[sonarr_folder_]"]) == {"mcu": "/data/media/shows/mcu"}
    assert json.loads(libraries["playlist-template_variables[sonarr_tag_]"]) == {"mcu": ["mcu-show"]}
    assert json.loads(libraries["playlist-template_variables[trakt_list_]"]) == {"mcu": ["https://trakt.tv/users/example/lists/mcu"]}
    assert any("playlist_files[0].template_variables.name_mcu" in line for line in report.lines)


def test_prepare_import_payload_maps_direct_playlist_file_entries_into_libraries_payload():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {"Movies": {}},
            "playlist_files": [
                {
                    "default": "playlist",
                    "template_variables": {"libraries": ["Movies"]},
                },
                {
                    "file": "config/extra_playlists.yml",
                },
                {
                    "repo": "bullmoose20/playlists.yml",
                },
            ],
        },
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert json.loads(libraries["playlist_files_entries"]) == [
        {"type": "file", "location": "config/extra_playlists.yml"},
        {"type": "repo", "location": "bullmoose20/playlists.yml"},
    ]
    assert any("playlist_files[1].file" in line for line in report.lines)
    assert any("playlist_files[2].repo" in line for line in report.lines)


def test_annotate_yaml_with_report_unmapped_reason():
    raw = "plex:\n  url: http://example\n"
    report_lines = ["unmapped: plex.url - Bad URL"]
    annotated = importer.annotate_yaml_with_report(raw, report_lines)
    assert "unmapped - Bad URL" in annotated


def test_prepare_import_payload_maps_apprise_config_to_location():
    payload, report = importer.prepare_import_payload({"apprise": {"config": "/config/apprise.yml"}}, set(), set())

    assert payload["apprise"]["apprise"]["location"] == "/config/apprise.yml"
    assert any(line == "imported: apprise.config" for line in report.lines)
    assert report.counts["imported"] >= 1


def test_annotate_yaml_marks_apprise_config_as_imported():
    raw = "apprise:\n  config: /config/apprise.yml\n"
    _, report = importer.prepare_import_payload({"apprise": {"config": "/config/apprise.yml"}}, set(), set())

    annotated = importer.annotate_yaml_with_report(raw, report.lines)

    assert "apprise:  # mapped" in annotated
    assert "config: /config/apprise.yml  # mapped" in annotated
    assert "No matching Quickstart mapping" not in annotated


def test_prepare_import_payload_maps_yamtrack_credentials():
    payload, report = importer.prepare_import_payload(
        {
            "yamtrack": {
                "url": "http://yamtrack.local:8000",
                "username": "kometa",
                "password": "secret",
            }
        },
        set(),
        set(),
    )

    assert payload["yamtrack"]["yamtrack"] == {
        "url": "http://yamtrack.local:8000",
        "username": "kometa",
        "password": "secret",
    }
    assert any("yamtrack.url" in line for line in report.lines)


def test_coerce_import_bool_accepts_yaml_wide_truthy_and_falsy_values():
    """Regression guard for the duplicate `_coerce_import_bool` bug.

    Prior to develop #TBD, importer.py had TWO `_coerce_import_bool`
    definitions.  Python's last-def-wins meant callers got the "wide"
    version that accepts YAML-native `on`/`off` alongside the usual
    `true`/`false`/`yes`/`no`/`1`/`0`.

    The narrow (dead-code) def has been removed; this test locks
    in the wide semantics so a future refactor can't silently
    re-narrow the accepted set and break config imports that use
    `field: on` / `field: off`.
    """
    assert importer._coerce_import_bool("true") is True
    assert importer._coerce_import_bool("yes") is True
    assert importer._coerce_import_bool("1") is True
    assert importer._coerce_import_bool("on") is True
    assert importer._coerce_import_bool("True") is True  # case-insensitive
    assert importer._coerce_import_bool(" YES ") is True  # whitespace-tolerant

    assert importer._coerce_import_bool("false") is False
    assert importer._coerce_import_bool("no") is False
    assert importer._coerce_import_bool("0") is False
    assert importer._coerce_import_bool("off") is False
    assert importer._coerce_import_bool("False") is False

    assert importer._coerce_import_bool("maybe") is None
    assert importer._coerce_import_bool("") is None
    assert importer._coerce_import_bool(None) is None
    assert importer._coerce_import_bool(42) is None

    assert importer._coerce_import_bool(True) is True
    assert importer._coerce_import_bool(False) is False
