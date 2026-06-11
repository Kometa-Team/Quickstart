from modules import importer


def test_prepare_import_payload_maps_multiple_overlay_files_per_library():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {"file": "config/overlays/movies.yml"},
                        {"folder": "config/overlays/movies"},
                        {"git": "bullmoose20/overlays.yml"},
                        {"repo": "custom/movies_overlays.yml"},
                        {"url": "https://example.com/movie-overlays.yml"},
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert "mov-library_movies-overlay_files" in libraries_payload
    assert (
        libraries_payload["mov-library_movies-overlay_files"]
        == '[{"type": "file", "location": "config/overlays/movies.yml"}, {"type": "folder", "location": "config/overlays/movies"}, {"type": "git", "location": "bullmoose20/overlays.yml"}, {"type": "repo", "location": "custom/movies_overlays.yml"}, {"type": "url", "location": "https://example.com/movie-overlays.yml"}]'
    )
    assert any("libraries.Movies.overlay_files[0].file" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[1].folder" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[2].git" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[3].repo" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[4].url" in line for line in report.lines)


def test_prepare_import_payload_accepts_resolution_template_variables():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "overlay_files": [
                        {
                            "default": "resolution",
                            "template_variables": {
                                "use_resolution": False,
                                "use_edition": True,
                                "use_4k": False,
                                "use_1080p": False,
                                "use_dv": False,
                                "use_extended": False,
                                "use_openmatte": False,
                            },
                        }
                    ]
                }
            }
        },
        {"Movies"},
        set(),
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_resolution"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_resolution]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_edition]"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_4k]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_1080p]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_dv]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_extended]"] is False
    assert libraries_payload["mov-library_movies-movie-template_overlay_resolution[use_openmatte]"] is False
    assert any("libraries.Movies.overlay_files[0].template_variables.use_resolution" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_1080p" in line for line in report.lines)
    assert any("libraries.Movies.overlay_files[0].template_variables.use_extended" in line for line in report.lines)
