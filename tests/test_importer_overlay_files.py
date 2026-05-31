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
