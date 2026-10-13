import io
import json
from pathlib import Path

import jsonschema
import pytest
from jinja2 import Environment, FileSystemLoader
from ruamel.yaml import YAML
from werkzeug.datastructures import MultiDict

from modules.importer_simple_sections import _normalize_settings_section
from modules.jsonschema_compat import extend_asset_directory_schema
from modules.output_values import _normalize_asset_directory_values


def test_grouped_paths_preserve_order_and_normalize_windows_paths():
    value = {"movies": [r"C:\\Assets\\Movies", " /assets/extra "], "shows": " /assets/tv\n/assets/anime ", "music": [], "collections": r"\\server\\art"}
    assert _normalize_asset_directory_values(value) == {
        "movies": [r"C:\Assets\Movies", "/assets/extra"],
        "shows": ["/assets/tv", "/assets/anime"],
        "collections": [r"\\server\art"],
    }


@pytest.mark.parametrize("base", ["asset_directory", "mov-library_1-attribute_asset_directory"])
def test_grouped_form_keeps_multiple_paths_and_empty_inherited_groups(base):
    from modules.persistence import clean_form_data

    form = MultiDict([(f"{base}[movies]", " /assets/one "), (f"{base}[movies]", "/assets/two"), (f"{base}[shows]", ""), (f"{base}[collections]", "/assets/collections")])
    assert clean_form_data(form)[base] == {"movies": ["/assets/one", "/assets/two"], "shows": [], "collections": ["/assets/collections"]}


def test_global_import_preserves_grouped_mapping():
    assert _normalize_settings_section({"asset_directory": {"movies": "/movies", "collections": [" /collections "]}}) == {
        "asset_directory": {"movies": ["/movies"], "collections": ["/collections"]}
    }


def test_global_grouped_form_survives_storage_and_yaml_export(app, isolated_config_dir):
    from flask import session
    from modules import persistence
    from modules.output_dump import dump_section

    with app.test_request_context():
        session["config_name"] = "pytest_grouped_assets"
        persistence.save_settings(
            "150-settings",
            MultiDict(
                [
                    ("asset_directory[movies]", "/movies"),
                    ("asset_directory[movies]", "/more-movies"),
                    ("asset_directory[collections]", "/collections"),
                    ("asset_directory[shows]", ""),
                ]
            ),
        )
        stored = persistence.retrieve_settings("150-settings")["settings"]
        output = dump_section("", "settings", {"settings": stored}, "none", session["config_name"])
    assert YAML().load(output)["settings"]["asset_directory"] == {"movies": ["/movies", "/more-movies"], "collections": ["/collections"]}


def test_library_autosave_stores_groups_and_can_clear_an_override(client, isolated_config_dir):
    from modules import database

    config_name = "pytest_grouped_autosave"
    with client.session_transaction() as sess:
        sess["config_name"] = config_name
    base = "mov-library_movies-attribute_asset_directory"
    payload = {"config_name": config_name, "mov-library_movies-library": "Movies", f"{base}[movies]": ["/movies", "/extra"], f"{base}[collections]": ["/collections"]}
    response = client.post("/autosave_library/mov-library_movies", json=payload)
    assert response.status_code == 200, response.get_json()
    _, _, stored = database.retrieve_section_data(config_name, "libraries")
    assert stored["libraries"][base] == {"movies": ["/movies", "/extra"], "collections": ["/collections"]}
    payload[f"{base}[collections]"] = [""]
    response = client.post("/autosave_library/mov-library_movies", json=payload)
    assert response.status_code == 200, response.get_json()
    _, _, stored = database.retrieve_section_data(config_name, "libraries")
    assert not stored["libraries"][base].get("collections")


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_directory[movies]": ["/valid", r"/invalid\0assets"]},
        {"mov-library_1-attribute_asset_directory[collections]": [r"/invalid\0assets"]},
        {"asset_directory": {"movies": [r"/invalid\0assets"]}},
    ],
)
def test_server_validates_paths_inside_groups(payload):
    from modules.path_validation import validate_payload

    assert validate_payload(payload, platform_key="linux") == ["Asset Directory: Contains an invalid null sequence."]


@pytest.mark.parametrize("value", ["/assets/shared", ["/assets/one", "/assets/two"]])
def test_legacy_shared_paths_populate_all_groups_without_changing_paths(value):
    env = Environment(loader=FileSystemLoader("templates"))
    macro = env.get_template("partials/_macros.html").module.grouped_asset_directory_fields
    html = str(macro(value, "assets", "asset_directory"))
    paths = [value] if isinstance(value, str) else value
    for group in ("movies", "shows", "music", "collections"):
        for path in paths:
            assert f'name="asset_directory[{group}]"' in html
            assert html.count(f'value="{path}"') == 4


def test_library_import_to_yaml_preserves_collection_only_override(app):
    from modules.importer import ImportReport
    from modules.importer_library_settings import process_library_settings
    from modules.output_libraries_section import build_libraries_section

    data = {}
    report = ImportReport()
    process_library_settings("mov-library_1", "Movies", {"settings": {"asset_directory": {"collections": "/art/collections"}}}, libraries_data=data, report=report)
    with app.app_context():
        section = build_libraries_section(movie_libraries={"mov-library_1-library": "Movies"}, movie_attributes={"1": data})
    stream = io.StringIO()
    yaml = YAML()
    yaml.dump(section, stream)
    parsed = yaml.load(stream.getvalue())
    assert parsed["libraries"]["Movies"]["settings"]["asset_directory"] == {"collections": ["/art/collections"]}


def test_schema_accepts_grouped_global_and_library_paths_but_rejects_unknown_groups():
    schema = json.loads(Path("tests/fixtures/schema/config-schema.json").read_text())
    extend_asset_directory_schema(schema)
    validator = jsonschema.Draft7Validator(schema)
    config = {
        "settings": {"asset_directory": {"movies": ["/movies"], "shows": "/shows", "music": None}},
        "libraries": {"Movies": {"settings": {"asset_directory": {"collections": ["/collections"]}}}},
    }
    config.update({"plex": {"url": "http://localhost:32400", "token": "test-token"}, "tmdb": {"apikey": "test-key"}})
    assert not list(validator.iter_errors(config))
    config["settings"]["asset_directory"]["unknown"] = "/unknown"
    assert list(validator.iter_errors(config))
