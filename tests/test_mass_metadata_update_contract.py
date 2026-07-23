import json

from modules import importer
from modules import dependency_reasons


def test_prepare_import_payload_accepts_mass_metadata_update():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "operations": {
                        "mass_metadata_update": {
                            "genre": {
                                "source": ["tmdb", "imdb"],
                                "mappings": {"Action & Adventure": "Action"},
                            },
                            "content_rating": {"source": "omdb"},
                            "original_title": "mal_english",
                            "collections": {"mode": "hide"},
                            "labels": {"severity": "mild"},
                            "ratings": {"audience": "tmdb"},
                            "poster": {"source": ["trakt", "tmdb"], "ignore_locked": True},
                            "logo": {"source": "tvdb"},
                            "square_art": {"source": "tvdb"},
                            "backup": {"path": "config/Movies_Backup.yml", "exclude": ["title"]},
                        }
                    }
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-attribute_mass_genre_update_order"] == '["tmdb", "imdb"]'
    assert json.loads(libraries["mov-library_movies-attribute_genre_mapper"]) == {"Action & Adventure": "Action"}
    assert libraries["mov-library_movies-attribute_mass_content_rating_update_order"] == '["omdb"]'
    assert libraries["mov-library_movies-attribute_mass_original_title_update_order"] == '["mal_english"]'
    assert libraries["mov-library_movies-attribute_mass_collection_mode"] == "hide"
    assert libraries["mov-library_movies-attribute_mass_imdb_parental_labels"] == "mild"
    assert libraries["mov-library_movies-attribute_mass_audience_rating_update_order"] == '["tmdb"]'
    assert libraries["mov-library_movies-attribute_mass_poster_source"] == "trakt"
    assert libraries["mov-library_movies-attribute_mass_poster_ignore_locked"] is True
    assert libraries["mov-library_movies-attribute_mass_logo_source"] == "tvdb"
    assert libraries["mov-library_movies-attribute_mass_square_art_source"] == "tvdb"
    assert libraries["mov-library_movies-attribute_metadata_backup_path"] == "config/Movies_Backup.yml"
    assert libraries["mov-library_movies-attribute_metadata_backup_exclude"] == '["title"]'
    assert any("libraries.Movies.operations.mass_metadata_update" in line for line in report.lines)


def test_prepare_import_payload_accepts_legacy_metadata_backup():
    payload, report = importer.prepare_import_payload(
        {
            "libraries": {
                "Movies": {
                    "operations": {
                        "metadata_backup": {
                            "path": "config/Movies_Backup.yml",
                            "exclude": ["title", "summary"],
                            "sync_tags": True,
                        }
                    }
                }
            }
        },
        {"Movies"},
        set(),
    )

    libraries = payload["libraries"]["libraries"]
    assert libraries["mov-library_movies-attribute_metadata_backup_path"] == "config/Movies_Backup.yml"
    assert libraries["mov-library_movies-attribute_metadata_backup_exclude"] == '["title", "summary"]'
    assert libraries["mov-library_movies-attribute_sync_tags"] is True
    assert any("libraries.Movies.operations.metadata_backup" in line for line in report.lines)


def test_build_libraries_section_emits_mass_metadata_update(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            movie_libraries={"mov-library_movies-library": "Movies"},
            movie_attributes={
                "movies": {
                    "mov-library_movies-attribute_mass_genre_update_order": '["tmdb"]',
                    "mov-library_movies-attribute_genre_mapper": json.dumps({"Action & Adventure": "Action"}),
                    "mov-library_movies-attribute_mass_content_rating_update_order": '["omdb"]',
                    "mov-library_movies-attribute_mass_original_title_update_order": '["mal_english"]',
                    "mov-library_movies-attribute_mass_collection_mode": "hide",
                    "mov-library_movies-attribute_mass_imdb_parental_labels": "mild",
                    "mov-library_movies-attribute_mass_audience_rating_update_order": '["tmdb"]',
                    "mov-library_movies-attribute_mass_poster_source": "trakt",
                    "mov-library_movies-attribute_mass_poster_ignore_locked": True,
                    "mov-library_movies-attribute_mass_logo_source": "tvdb",
                    "mov-library_movies-attribute_mass_square_art_source": "tvdb",
                    "mov-library_movies-attribute_metadata_backup_path": "config/Movies_Backup.yml",
                    "mov-library_movies-attribute_metadata_backup_exclude": '["title"]',
                }
            },
        )

    operations = libraries_section["libraries"]["Movies"]["operations"]
    mass_metadata = operations["mass_metadata_update"]
    assert mass_metadata["genre"]["source"] == "tmdb"
    assert mass_metadata["genre"]["mappings"] == {"Action & Adventure": "Action"}
    assert mass_metadata["content_rating"]["source"] == "omdb"
    assert mass_metadata["original_title"] == "mal_english"
    assert mass_metadata["collections"] == {"mode": "hide"}
    assert mass_metadata["labels"] == "mild"
    assert mass_metadata["ratings"]["audience"] == "tmdb"
    assert mass_metadata["poster"] == {"ignore_locked": True, "source": "trakt"}
    assert mass_metadata["logo"] == {"source": "tvdb"}
    assert mass_metadata["square_art"] == {"source": "tvdb"}
    assert mass_metadata["backup"] == {"path": "config/Movies_Backup.yml", "exclude": ["title"]}
    assert "mass_genre_update" not in operations
    assert "mass_content_rating_update" not in operations
    assert "metadata_backup" not in operations


def test_trakt_dependency_detects_mass_metadata_image_sources():
    reasons = dependency_reasons._libraries_data_trakt_dependency_reasons(
        {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-attribute_mass_poster_source": "trakt",
        }
    )

    assert any("mass_poster uses trakt" in reason for reason in reasons)
