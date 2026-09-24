import json
import pickle
import sqlite3
from pathlib import Path

from werkzeug.datastructures import MultiDict

from modules.output_render import _strip_retired_trakt_fields
from modules.persistence import clean_form_data

ROOT = Path(__file__).resolve().parents[1]


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_trakt_is_absent_from_quickstart_catalogs():
    collections = json.loads((ROOT / "static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    attributes = json.loads((ROOT / "static/json/quickstart_attributes.json").read_text(encoding="utf-8"))
    overlays = json.loads((ROOT / "static/json/quickstart_overlays.json").read_text(encoding="utf-8"))

    objects = [item for item in _walk(collections) if isinstance(item, dict)]
    assert all(item.get("id") != "collection_trakt" for item in objects)
    assert all(item.get("key") not in {"trakt_list", "child_trakt_list_overrides"} for item in objects)

    option_values = [item[0] for item in _walk(attributes) if isinstance(item, list) and item]
    assert "trakt" not in option_values
    assert "trakt_user" not in option_values
    assert "mdb_trakt" not in option_values

    overlay_options = [item.get("value") for item in _walk(overlays) if isinstance(item, dict)]
    assert "trakt" not in overlay_options


def test_cleared_rating_selector_keeps_explicit_none_sentinel():
    key = "mov-library_movies-movie-template_overlay_ratings[rating3]"

    cleaned = clean_form_data(MultiDict({key: "none", "ordinary_field": "none"}))

    assert cleaned[key] == "none"
    assert cleaned["ordinary_field"] is None


def test_database_sanitizer_removes_legacy_trakt_rows_and_library_fields(isolated_config_dir):
    from modules import database

    database.save_section_data("libraries", True, True, {"libraries": {}}, name="legacy_trakt")
    legacy_libraries = {
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_trakt": True,
            "mov-library_movies-movie-template_overlay_ratings[rating1]": "trakt_user",
            "mov-library_movies-movie-template_overlay_ratings[rating1_image]": "trakt",
            "mov-library_movies-attribute_language": "English",
        }
    }
    with sqlite3.connect(database.get_database_path()) as connection:
        connection.execute(
            "UPDATE section_data SET data = ? WHERE name == ? AND section == ?",
            (pickle.dumps(legacy_libraries), "legacy_trakt", "libraries"),
        )
        connection.execute(
            "INSERT INTO section_data(name, section, validated, user_entered, data) VALUES (?, ?, ?, ?, ?)",
            ("legacy_trakt", "trakt", True, True, pickle.dumps({"trakt": {"client_id": "old"}})),
        )

    assert database.sanitize_all_section_data() == 2

    _validated, _entered, stored = database.retrieve_section_data("legacy_trakt", "libraries")
    assert stored == {
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-attribute_language": "English",
        }
    }
    assert database.retrieve_section_data("legacy_trakt", "trakt") == (False, False, None)


def test_retired_trakt_fields_are_scrubbed_from_generated_data():
    config = {
        "trakt": {"client_id": "secret"},
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "seasonal",
                        "template_variables": {
                            "trakt_list": "https://trakt.tv/example",
                            "trakt_list_halloween": ["https://trakt.tv/halloween"],
                            "rating_source": "trakt_user",
                            "mdb_rating_source": "mdb_trakt",
                            "overlay_value": "mdb_trakt_rating",
                            "imdb_list": "https://imdb.com/list/ls1",
                        },
                    }
                ]
            }
        },
    }

    _strip_retired_trakt_fields(config)

    assert "trakt" not in config
    variables = config["libraries"]["Movies"]["collection_files"][0]["template_variables"]
    assert variables == {
        "imdb_list": "https://imdb.com/list/ls1",
    }
