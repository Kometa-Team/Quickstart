"""Generated global defaults must satisfy Kometa's real config initializer."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ruamel.yaml import YAML

from modules import database, importer, persistence
from modules.output_dump import _KOMETA_NULL_DEFAULTS, dump_section

FIXTURE = Path(__file__).parent / "fixtures" / "kometa" / "check_for_attribute.txt"
CONTRACT = json.loads(FIXTURE.with_suffix(".json").read_text(encoding="utf-8"))
OBSERVED_MISSING_KEYS = [
    ("settings", "custom_repo"),
    ("radarr", "radarr_path"),
    ("radarr", "plex_path"),
    ("sonarr", "sonarr_path"),
    ("sonarr", "plex_path"),
]
BASE_CONFIG = {
    "settings": {"cache": True},
    "plex": {"url": "http://plex:32400", "token": "plex-token"},
    "tmdb": {"apikey": "a" * 32},
    "github": {"token": "github-token"},
    "radarr": {"url": "http://radarr:7878", "token": "radarr-token"},
    "sonarr": {"url": "http://sonarr:8989", "token": "sonarr-token"},
    "lidarr": {"url": "http://lidarr:8686", "token": "lidarr-token"},
    "tautulli": {"url": "http://tautulli:8181", "apikey": "tautulli-key"},
    "tracearr": {"url": "http://tracearr:3000", "apikey": "tracearr-key"},
    "webhooks": {"run_end": ["http://example.invalid/hook"]},
    "mal": {"client_id": "mal-client"},
    "floppy": {"url": "http://floppy:8080"},
    "wetrakr": {"authorization": {"access_token": "wetrakr-token"}},
}


def exported_section(section, values):
    text = dump_section("", section, {section: values}, "none", None)
    return YAML(typ="safe", pure=True).load(text) or {}


@pytest.fixture
def kometa_checker():
    """Execute the pinned upstream function without importing/running Kometa."""
    source = FIXTURE.read_text(encoding="utf-8")
    assert hashlib.sha256(source.replace("\r\n", "\n").encode()).hexdigest() == CONTRACT["sha256"]
    log = Mock()
    requests = Mock()
    namespace = {
        "self": SimpleNamespace(read_only=False, Requests=requests, config_path="generated_config.yml"),
        "logger": log,
        "Failed": RuntimeError,
        "util": SimpleNamespace(get_list=lambda value, **_: value if isinstance(value, list) else [value]),
    }
    exec(compile(source, str(FIXTURE), "exec"), namespace)
    return namespace["check_for_attribute"], log, requests


def test_defaults_cover_the_audited_upstream_calls():
    expected = {(call["section"], call["attribute"]) for call in CONTRACT["null_default_calls"]}
    assert {(section, key) for section, keys in _KOMETA_NULL_DEFAULTS.items() for key in keys} == expected


def test_kometa_reproduces_the_five_reported_config_insertions(kometa_checker):
    check, log, requests = kometa_checker
    stored_yaml = SimpleNamespace(data=copy.deepcopy(BASE_CONFIG), save=Mock())
    requests.file_yaml.return_value = stored_yaml
    for section, key in OBSERVED_MISSING_KEYS:
        assert check(BASE_CONFIG, key, parent=section, default_is_none=True) is None
        assert key in stored_yaml.data[section]
        assert stored_yaml.data[section][key] is None
    assert stored_yaml.save.call_count == len(OBSERVED_MISSING_KEYS)
    for section, key in OBSERVED_MISSING_KEYS:
        assert any(f"{section} sub-attribute {key} not found using None as default" in str(call) for call in log.warning.call_args_list)


def test_exported_config_triggers_no_kometa_null_default_writes_or_warnings(kometa_checker):
    check, log, requests = kometa_checker
    generated = {}
    for section, values in BASE_CONFIG.items():
        generated.update(exported_section(section, copy.deepcopy(values)))
    for call in CONTRACT["null_default_calls"]:
        check(generated, call["attribute"], parent=call["section"], var_type=call["var_type"], default_is_none=True)
    log.warning.assert_not_called()
    requests.file_yaml.assert_not_called()


@pytest.mark.parametrize("section,key", OBSERVED_MISSING_KEYS)
@pytest.mark.parametrize("value", [..., None, "", "  "])
def test_missing_or_blank_observed_fields_emit_explicit_yaml_null(section, key, value):
    values = copy.deepcopy(BASE_CONFIG[section])
    if value is not ...:
        values[key] = value
    before = copy.deepcopy(values)
    generated = exported_section(section, values)[section]
    assert key in generated
    assert generated[key] is None
    assert values == before


def test_explicit_values_false_zero_and_lists_survive_export():
    config = copy.deepcopy(BASE_CONFIG)
    config["settings"].update(custom_repo="http://example.invalid/repo/", playlist_sync_to_users=["Alice"], auto_sort_hubs="alpha", asset_directory=["/assets"])
    config["plex"].update(verify_ssl=False, db_cache=0)
    config["radarr"].update(radarr_path="/downloads", plex_path="/media", tag=["kometa"], root_folder_path="/movies")
    for section, values in config.items():
        before = copy.deepcopy(values)
        generated = exported_section(section, values)[section]
        for key, value in values.items():
            assert generated[key] == value
        assert values == before


@pytest.mark.parametrize("section", sorted(set(_KOMETA_NULL_DEFAULTS) - {"settings"}))
@pytest.mark.parametrize("values", [None, {}, {"unused": None}])
def test_null_defaults_do_not_create_unconfigured_services(section, values):
    generated = exported_section(section, values)
    assert section not in generated


def test_global_defaults_do_not_override_library_inheritance_or_empty_overlay_cleanup():
    data = {
        "Movies": {
            "radarr": {"tag": ["movies"], "plex_path": None},
            "settings": {"cache": False, "custom_repo": None},
            "overlay_files": [{"default": "resolution", "template_variables": {"style": None, "horizontal_position": "left"}}],
        }
    }
    generated = exported_section("libraries", data)["libraries"]["Movies"]
    assert generated["radarr"] == {"tag": ["movies"]}
    assert generated["settings"] == {"cache": False}
    assert generated["overlay_files"][0]["template_variables"] == {"horizontal_position": "left"}


def test_import_save_and_repeated_export_preserve_blanks(client, isolated_config_dir, app):
    config = {section: copy.deepcopy(BASE_CONFIG[section]) for section in ("settings", "radarr", "sonarr")}
    for section, key in OBSERVED_MISSING_KEYS:
        config[section][key] = None
    for _ in range(2):
        with app.test_request_context():
            payload, _report = importer.prepare_import_payload(config, set(), set())
        rebuilt = {}
        for section in config:
            database.save_section_data(section, True, True, payload[section], name="null_defaults")
            stored = database.retrieve_section_data("null_defaults", section)[2]
            rebuilt.update(YAML(typ="safe", pure=True).load(dump_section("", section, stored, "none", "null_defaults")))
        config = rebuilt
        for section, key in OBSERVED_MISSING_KEYS:
            assert key in config[section]
            assert config[section][key] is None


def test_final_config_export_passes_schema_with_null_defaults(app, isolated_config_dir, monkeypatch):
    from flask import session
    from modules import output_render

    monkeypatch.setattr(output_render, "render_yaml_header", lambda *_: "")
    config = {section: {section: copy.deepcopy(BASE_CONFIG[section])} for section in ("settings", "plex", "tmdb", "radarr", "sonarr")}
    config["libraries"] = {"libraries": {"Movies": {"collection_files": [{"default": "basic"}]}}}
    with app.test_request_context():
        session["config_name"] = "null_defaults_export"
        valid, _first, _data, text, errors = output_render.emit_and_validate_config(config, {}, "none", "null_defaults_export", {"Movies": "movie"}, ["Movies"], [])
    assert valid, [(list(error.path), error.message) for error in errors]
    generated = YAML(typ="safe", pure=True).load(text)
    for section, key in OBSERVED_MISSING_KEYS:
        assert key in generated[section]
        assert generated[section][key] is None
    assert "seerr" not in generated


def test_form_none_values_are_kept_as_blank_yaml_not_literal_none():
    values = persistence.clean_form_data({"radarr_path": "None", "plex_path": ""})
    values.update(BASE_CONFIG["radarr"])
    generated = exported_section("radarr", values)["radarr"]
    assert generated["radarr_path"] is None
    assert generated["plex_path"] is None


@pytest.mark.parametrize("value,valid", [(None, True), ("English", True), (3, False), (False, False), ([], False)])
def test_sonarr_language_profile_schema_accepts_only_text_or_runtime_null(app, value, valid):
    from jsonschema import Draft7Validator
    from modules.output_render import _load_config_schema

    _yaml, schema = _load_config_schema()
    properties = schema["definitions"]["sonarr-api"]["properties"]
    assert Draft7Validator(properties["language_profile"]).is_valid(value) is valid
    assert schema["definitions"]["sonarr-api-lib"]["properties"]["language_profile"]["type"] == "string"
