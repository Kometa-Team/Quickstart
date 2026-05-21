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
