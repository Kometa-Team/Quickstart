import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import jsonschema
import pytest
import requests
from flask import render_template, session
from ruamel.yaml import YAML
from werkzeug.datastructures import MultiDict

from modules import database, helpers, importer, output, persistence, seerr
from modules.output_defaults import _prune_template_variables


@pytest.fixture
def config_name(client):
    name = "seerr-tests"
    with client.session_transaction() as state:
        state["config_name"] = name
    return name


def test_connection_only_reads_authenticated_endpoint(client, monkeypatch):
    response = MagicMock(status_code=200)
    response.json.return_value = {"id": 1, "email": "private@example.com"}
    get = MagicMock(return_value=response)
    post = MagicMock(side_effect=AssertionError("Validation must not submit a request"))
    monkeypatch.setattr(seerr.requests, "get", get)
    monkeypatch.setattr(seerr.requests, "post", post)
    result = client.post("/validate_seerr", json={"seerr_url": "http://seerr:5055/base/", "seerr_apikey": "secret"})
    assert result.status_code == 200
    assert result.json == {"valid": True}
    get.assert_called_once_with("http://seerr:5055/base/api/v1/auth/me", headers={"X-Api-Key": "secret"}, timeout=10, allow_redirects=False)
    post.assert_not_called()


@pytest.mark.parametrize("status,payload", [(401, {}), (403, {}), (302, {}), (500, {}), (200, {}), (200, []), (200, "login")])
def test_connection_rejects_unauthenticated_or_unexpected_responses(client, monkeypatch, status, payload):
    response = MagicMock(status_code=status, text="secret-key")
    response.json.return_value = payload
    monkeypatch.setattr(seerr.requests, "get", MagicMock(return_value=response))
    result = client.post("/validate_seerr", json={"seerr_url": "http://seerr:5055", "seerr_apikey": "secret-key"})
    assert result.status_code in {400, 401}
    assert result.json["valid"] is False
    assert "secret-key" not in result.text


@pytest.mark.parametrize("error", [requests.Timeout("secret-key"), requests.ConnectionError("secret-key"), ValueError("secret-key")])
def test_connection_errors_do_not_leak_secrets(client, monkeypatch, error):
    monkeypatch.setattr(seerr.requests, "get", MagicMock(side_effect=error))
    result = client.post("/validate_seerr", json={"seerr_url": "http://seerr:5055", "seerr_apikey": "secret-key"})
    assert result.status_code == 400
    assert "secret-key" not in result.text


@pytest.mark.parametrize(
    "connection", [{}, {"url": "file:///tmp/seerr", "apikey": "key"}, {"url": "http://user:password@seerr", "apikey": "key"}, {"url": "http://seerr", "apikey": 12}]
)
def test_connection_validates_url_and_key_before_network(connection, monkeypatch):
    get = MagicMock()
    monkeypatch.setattr(seerr.requests, "get", get)
    assert seerr.validate_connection(connection)[0]["valid"] is False
    get.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    ["invalid", [], {"standard": []}, {"4k": {"server_id": True}}, {"standard": {"server_id": 0}}, {"standard": {"quality_profile": False}}, {"4k": {"root_folder": ""}}],
)
def test_override_validation_rejects_invalid_types(overrides):
    assert seerr.option_errors({"seerr_overrides": overrides})


def test_overrides_keep_profile_names_ids_and_unknown_values():
    overrides = {
        "standard": {"server_id": 1, "quality_profile": "HD-1080p", "future": False},
        "4k": {"quality_profile": 4, "root_folder": "/movies-4k"},
        "future_tier": {"enabled": False},
    }
    assert seerr.normalize_option("seerr_overrides", json.dumps(overrides)) == overrides
    assert seerr.option_errors({"seerr_overrides": overrides}) == []
    assert _prune_template_variables({"seerr_add_existing": False}, {"seerr_add_existing": False}) == {"seerr_add_existing": False}


def test_library_effective_credentials_inherit_individually(client, config_name, monkeypatch):
    database.save_section_data(name=config_name, section="seerr", validated=True, user_entered=True, data={"seerr": {"url": "http://global-seerr", "apikey": "global-secret"}})
    validate = MagicMock(return_value=({"valid": True}, 200))
    monkeypatch.setattr(seerr, "validate_connection", validate)
    assert client.post("/validate_library_seerr/mov-library_movies", json={"url": "http://movies-seerr"}).json["valid"]
    validate.assert_called_with({"url": "http://movies-seerr", "apikey": "global-secret"})
    assert client.post("/validate_library_seerr/mov-library_movies", json={"apikey": "override-secret"}).json["valid"]
    validate.assert_called_with({"url": "http://global-seerr", "apikey": "override-secret"})
    assert client.post("/validate_library_seerr/mov-library_movies", json={}).json["valid"]
    validate.assert_called_with({"url": "http://global-seerr", "apikey": "global-secret"})


def test_global_save_reopen_disable_preserves_unknown_fields_and_opaque_keys(app, client, config_name):
    database.save_section_data(
        name=config_name, section="seerr", validated=True, user_entered=True, data={"seerr": {"url": "http://seerr:5055", "apikey": "previous", "future": {"enabled": False}}}
    )
    with app.test_request_context("/step/125-seerr"):
        session["config_name"] = config_name
        persistence.save_settings("125-seerr", MultiDict([("seerr_url", "http://seerr:5055"), ("seerr_apikey", "001234"), ("seerr_tmp_enabled", "false")]))
        settings = persistence.retrieve_settings("125-seerr")["seerr"]
        assert settings["apikey"] == "001234"
        assert settings["future"] == {"enabled": False}
        assert settings["tmp_enabled"] is False
        data, _headers = output.retrieve_config_sections("single line")
        assert "seerr" not in data
    page = client.get("/step/125-seerr")
    assert page.status_code == 200
    assert b'type="password" id="seerr_apikey"' in page.data
    assert b'value="001234"' in page.data
    assert b"125-seerr" in page.data


def test_import_and_yaml_round_trip_preserve_connections_options_and_other_services(app, monkeypatch):
    overrides = {"standard": {"server_id": 1, "quality_profile": "HD-1080p"}, "4k": {"quality_profile": 4, "root_folder": "/movies-4k"}}
    imported = {
        "seerr": {"url": "http://seerr:5055", "apikey": "secret"},
        "libraries": {
            "Movies": {
                "seerr": {"url": "http://movie-seerr", "future": {"enabled": False}},
                "radarr": {"add_missing": False},
                "template_variables": {"seerr_add_existing": False},
                "collection_files": [
                    {
                        "default": "imdb",
                        "template_variables": {
                            "seerr_add_missing": True,
                            "seerr_add_existing": False,
                            "seerr_instance": "both",
                            "seerr_overrides": overrides,
                            "seerr_add_missing_top": False,
                        },
                    }
                ],
            }
        },
    }
    original = copy.deepcopy(imported)
    payload, report = importer.prepare_import_payload(imported, {"Movies"}, set())
    assert not [line for line in report.lines if line.startswith("unmapped:") and "seerr" in line]
    assert imported == original
    monkeypatch.setattr(seerr, "runtime_support", lambda: {"supported": True, "message": "Supported"})
    monkeypatch.setattr(output.helpers, "get_plex_summary", lambda: "Unavailable")
    monkeypatch.setattr(output.helpers, "get_library_summaries", lambda _names: "Unavailable")
    with app.test_request_context("/step/900-kometa"):
        session["config_name"] = "seerr-output"
        for section, data in payload.items():
            database.save_section_data(name="seerr-output", section=section, validated=True, user_entered=True, data=data)
        _valid, _error, config, yaml_text, errors = output.build_config("single line", config_name="seerr-output")
        parsed = YAML(typ="safe").load(yaml_text)
        assert parsed["seerr"] == original["seerr"]
        library = parsed["libraries"]["Movies"]
        assert library["seerr"] == original["libraries"]["Movies"]["seerr"]
        assert "apikey" not in library["seerr"]
        assert library["radarr"]["add_missing"] is False
        assert library["template_variables"]["seerr_add_existing"] is False
        options = library["collection_files"][0]["template_variables"]
        for key, value in original["libraries"]["Movies"]["collection_files"][0]["template_variables"].items():
            assert options[key] == value


def test_shared_and_collection_controls_render_imported_values(app):
    values = {"mov-library_movies-template_variables[seerr_add_existing]": False, "mov-library_movies-template_variables[seerr_overrides]": {"4k": {"quality_profile": "4K UHD"}}}
    with app.test_request_context():
        html = render_template("partials/_library_seerr.html", library={"id": "mov-library_movies", "type": "movie"}, data={"libraries": values})
    assert 'type="password"' in html
    assert 'value="4K UHD"' in html
    assert 'value="false"' in html
    assert "Restore global credentials" in html


def test_runtime_capability_detection_uses_selected_install(app, tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "get_kometa_root_path", lambda: tmp_path)
    monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: "managed")
    assert seerr.runtime_support()["supported"] is None
    (tmp_path / "kometa.py").write_text("")
    assert seerr.runtime_support()["supported"] is False
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "seerr.py").write_text("")
    (modules / "config.py").write_text("from modules.seerr import Seerr")
    (modules / "builder.py").write_text("seerr_add_missing")
    for mode in ("managed", "existing"):
        monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: mode)
        assert seerr.runtime_support()["supported"] is True
    monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: "external")
    assert seerr.runtime_support()["supported"] is None


def test_unsupported_runtime_blocks_export_without_losing_settings(app, monkeypatch):
    config = {"seerr": {"url": "http://seerr", "apikey": "secret"}}
    before = copy.deepcopy(config)
    monkeypatch.setattr(seerr, "runtime_support", lambda: {"supported": False, "message": "Update Kometa"})
    assert "Update Kometa" in seerr.configuration_errors(config)
    assert config == before
    monkeypatch.setattr(seerr, "runtime_support", lambda: {"supported": None, "message": "Confirm external runtime"})
    monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: "external")
    assert seerr.configuration_errors(config)
    assert seerr.configuration_errors(config, compatibility_confirmed=True) == []


def test_connector_and_default_template_capabilities_are_separate(app, tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "get_kometa_root_path", lambda: tmp_path)
    monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: "existing")
    monkeypatch.setattr(seerr, "runtime_support", lambda: {"supported": True, "message": "Supported"})
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    templates = defaults / "templates.yml"
    templates.write_text("templates:\n  arr:\n    radarr_add_missing: <<radarr_add_missing>>\n")
    config = {
        "seerr": {"url": "http://seerr", "apikey": "secret"},
        "libraries": {"Movies": {"collection_files": [{"default": "imdb", "template_variables": {"seerr_add_missing": True}}]}},
    }
    assert any("does not forward" in error for error in seerr.configuration_errors(config))
    templates.write_text("\n".join(option + ": value" for option in seerr.SEERR_OPTIONS))
    assert seerr.configuration_errors(config) == []


def test_lazy_collection_detail_renders_seerr_controls_and_imported_keyed_values(app, client, config_name):
    database.save_section_data(
        section="plex", validated=False, user_entered=True, data={"plex": {"tmp_movie_libraries": "1", "tmp_library_names": json.dumps({"1": "Movies"})}}, name=config_name
    )
    database.save_section_data(
        section="libraries",
        validated=False,
        user_entered=True,
        data={
            "libraries": {
                "mov-library_1-library": "Movies",
                "mov-library_1-collection_imdb": True,
                "mov-library_1-template_collection_imdb_seerr_add_missing": False,
                "mov-library_1-template_collection_imdb_seerr_add_existing_top": False,
            }
        },
        name=config_name,
    )
    groups = helpers.load_quickstart_config("quickstart_collections.json")
    group_index = next(index for index, group in enumerate(groups) if any(collection["id"] == "collection_imdb" for collection in group.get("collections", [])))
    response = client.get(f"/library_fragment/mov-library_1/section/collections/group/{group_index}/detail/collection_imdb")
    assert response.status_code == 200
    assert b"Advanced tier overrides" in response.data
    assert b'name="mov-library_1-template_collection_imdb_seerr_add_missing"' in response.data
    assert b'name="mov-library_1-template_collection_imdb_seerr_add_existing_top" data-seerr-keyed-output value="false"' in response.data


def test_upstream_schema_accepts_seerr_and_rejects_invalid_tiers():
    schema = json.loads(Path("tests/fixtures/schema/config-schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator({"$ref": "#/definitions/seerr-overrides", "definitions": schema["definitions"]})
    assert list(validator.iter_errors({"standard": {"server_id": 1, "quality_profile": "HD"}, "4k": {"quality_profile": 4}})) == []
    assert list(validator.iter_errors({"standard": {"server_id": False}}))
    assert list(validator.iter_errors({"other": {}}))


def test_validating_multiple_collections_cannot_hide_invalid_options(app, monkeypatch):
    monkeypatch.setattr(seerr, "global_settings", lambda: ({}, {"url": "http://seerr", "apikey": "key"}))
    libraries = {
        "mov-library_1-library": "Movies",
        "mov-library_1-collection_imdb": True,
        "mov-library_1-collection_tmdb": True,
        "mov-library_1-template_collection_imdb_seerr_instance": "invalid",
        "mov-library_1-template_collection_tmdb_seerr_instance": "both",
    }
    assert seerr.validate_library_settings(libraries, ["mov-library_1"])
    libraries["mov-library_1-collection_imdb"] = False
    assert seerr.validate_library_settings(libraries, ["mov-library_1"]) == []


def test_empty_seerr_connection_does_not_emit_an_empty_block(app):
    from modules.output_render import _dump_config_sections

    with app.test_request_context():
        session["config_name"] = "seerr-empty"
        text = _dump_config_sections({"seerr": {"seerr": {}}}, {}, "single line", "seerr-empty")
    assert "seerr:" not in text


def test_seerr_keys_are_redacted_in_debug_logs_and_support_exports(app, capsys, tmp_path, monkeypatch):
    from modules.helpers import _logging

    values = {"mov-library_movies-attribute_seerr_apikey": "secret-key", "seerr": {"apikey": "secret-key"}}
    assert "secret-key" not in json.dumps(seerr.redact_seerr_secrets(values))
    assert "secret-key" not in helpers.redact_sensitive_data("seerr:\n  apikey: secret-key\nlibraries:\n  Movies:\n    seerr:\n      apikey: secret-key")
    monkeypatch.setattr(_logging, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(_logging, "LOG_FILE", str(tmp_path / "log.txt"))
    _logging.ts_log(values, level="DEBUG")
    assert "secret-key" not in capsys.readouterr().out
    assert "secret-key" not in (tmp_path / "log.txt").read_text()
