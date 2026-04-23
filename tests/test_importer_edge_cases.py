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


def test_annotate_yaml_with_report_unmapped_reason():
    raw = "plex:\n  url: http://example\n"
    report_lines = ["unmapped: plex.url - Bad URL"]
    annotated = importer.annotate_yaml_with_report(raw, report_lines)
    assert "unmapped - Bad URL" in annotated
