from modules import importer


def test_prepare_import_payload_maps_multiple_metadata_files_per_library():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "metadata_files": [
                        {"file": "config/metadata/movies.yml"},
                        {"folder": "config/metadata/movies"},
                        {"git": "bullmoose20/godzilla.yml"},
                        {"repo": "custom/movies_extra.yml"},
                        {"url": "https://example.com/movie-metadata.yml"},
                    ]
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert "mov-library_movies-metadata_files" in libraries_payload
    assert (
        libraries_payload["mov-library_movies-metadata_files"]
        == '[{"type": "file", "location": "config/metadata/movies.yml"}, {"type": "folder", "location": "config/metadata/movies"}, {"type": "git", "location": "bullmoose20/godzilla.yml"}, {"type": "repo", "location": "custom/movies_extra.yml"}, {"type": "url", "location": "https://example.com/movie-metadata.yml"}]'
    )
    assert any("libraries.Movies.metadata_files[0].file" in line for line in report.lines)
    assert any("libraries.Movies.metadata_files[1].folder" in line for line in report.lines)
    assert any("libraries.Movies.metadata_files[2].git" in line for line in report.lines)
    assert any("libraries.Movies.metadata_files[3].repo" in line for line in report.lines)
    assert any("libraries.Movies.metadata_files[4].url" in line for line in report.lines)
