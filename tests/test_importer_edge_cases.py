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
                        "radarr_add_missing": True,
                        "name_mcu": "Marvel Timeline",
                        "delete_playlist_mcu": True,
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
    assert json.loads(libraries["playlist-template_variables[sync_to_users]"]) == ["alice", "bob"]
    assert libraries["playlist-template_variables[radarr_add_missing]"] is True
    assert json.loads(libraries["playlist-template_variables[name_]"]) == {"mcu": "Marvel Timeline"}
    assert json.loads(libraries["playlist-template_variables[delete_playlist_]"]) == {"mcu": "true"}
    assert json.loads(libraries["playlist-template_variables[trakt_list_]"]) == {"mcu": ["https://trakt.tv/users/example/lists/mcu"]}
    assert any("playlist_files[0].template_variables.name_mcu" in line for line in report.lines)


def test_annotate_yaml_with_report_unmapped_reason():
    raw = "plex:\n  url: http://example\n"
    report_lines = ["unmapped: plex.url - Bad URL"]
    annotated = importer.annotate_yaml_with_report(raw, report_lines)
    assert "unmapped - Bad URL" in annotated


def test_prepare_import_payload_maps_apprise_config_to_location():
    payload, report = importer.prepare_import_payload({"apprise": {"config": "/config/apprise.yml"}}, set(), set())

    assert payload["apprise"]["apprise"]["location"] == "/config/apprise.yml"
    assert report.counts["imported"] >= 1
