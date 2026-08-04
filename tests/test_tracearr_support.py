import json
from pathlib import Path
from unittest.mock import MagicMock

from flask import session

from modules import database, output
from modules.importer_simple_sections import SIMPLE_SECTIONS
from modules.output_render import ORDERED_CONFIG_SECTIONS


def _tracearr_collection():
    payload = json.loads(Path("static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    return next(collection for group in payload for collection in group.get("collections", []) if collection.get("id") == "collection_tracearr")


def test_tracearr_service_is_registered_for_import_and_output():
    assert "tracearr" in SIMPLE_SECTIONS
    assert ("tracearr", "035-tracearr") in ORDERED_CONFIG_SECTIONS


def test_tracearr_setup_page_renders(client):
    response = client.get("/step/035-tracearr")

    assert response.status_code == 200
    assert b"Public API Key" in response.data
    assert b"requires Kometa nightly" in response.data


def test_tracearr_settings_round_trip_into_generated_yaml(app, monkeypatch):
    config_name = "pytest_tracearr_output"
    database.save_section_data(
        name=config_name,
        section="tracearr",
        validated=True,
        user_entered=True,
        data={
            "tracearr": {
                "url": "http://tracearr.local:3019",
                "apikey": "trr_pub_secret",
                "server_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        },
    )
    monkeypatch.setattr(output.helpers, "ensure_json_schema", lambda: None)
    monkeypatch.setattr(
        output.helpers,
        "check_for_update",
        lambda: {"kometa_branch": "nightly", "branch": "develop", "local_version": "test", "running_on": "Local-Tests"},
    )
    monkeypatch.setattr(output.helpers, "get_plex_summary", lambda: "Plex summary unavailable")
    monkeypatch.setattr(output.helpers, "get_quickstart_settings_summary", lambda: [])
    monkeypatch.setattr(output.helpers, "get_library_summaries", lambda _names: "Library summary unavailable")
    monkeypatch.setattr(output.jsonschema.Draft7Validator, "iter_errors", lambda self, parsed: [])

    with app.test_request_context("/step/900-kometa"):
        session["config_name"] = config_name
        _validated, _error, config_data, yaml_content, _errors = output.build_config("single line", config_name=config_name)

    assert config_data["tracearr"]["tracearr"] == {
        "url": "http://tracearr.local:3019",
        "apikey": "trr_pub_secret",
        "server_id": "550e8400-e29b-41d4-a716-446655440000",
    }
    assert "tracearr:" in yaml_content
    assert "server_id: 550e8400-e29b-41d4-a716-446655440000" in yaml_content


def test_tracearr_chart_exposes_all_shipped_defaults_and_activity_controls():
    collection = _tracearr_collection()
    fields = {field["key"]: field for field in collection["template_variables"]}

    for chart in ("popular", "watched", "trending", "rewatched", "completed", "binged", "transcoded"):
        assert f"use_{chart}" in fields
        assert f"list_days_{chart}" in fields
        assert f"list_minimum_{chart}" in fields
        assert f"list_size_{chart}" in fields

    assert fields["list_minimum"]["default"] == "0"
    assert fields["list_days_trending"]["default"] == "7"
    assert fields["use_binged"]["media_types"] == ["show"]


def test_tracearr_collection_selection_creates_dependency_reason(qs_module):
    reasons = qs_module._libraries_data_tracearr_dependency_reasons(
        {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_tracearr": True,
        }
    )

    assert reasons
    assert "Tracearr Charts collection enabled" in reasons[0]


def test_tracearr_collection_promotes_setup_step_to_required(qs_module, monkeypatch):
    rows = [
        {
            "section": "libraries",
            "validated": True,
            "user_entered": True,
            "data": {
                "libraries": {
                    "mov-library_movies-library": "Movies",
                    "mov-library_movies-collection_tracearr": True,
                }
            },
        }
    ]
    templates = [
        ("001-start.html", "Start"),
        ("010-plex.html", "Plex"),
        ("020-tmdb.html", "TMDb"),
        ("025-libraries.html", "Libraries"),
        ("035-tracearr.html", "Tracearr"),
        ("150-settings.html", "Settings"),
    ]
    monkeypatch.setattr(qs_module.database, "retrieve_config_sections", lambda _name: rows)

    status = qs_module._build_workspace_status_context("cfg", templates, available_configs=["cfg"])

    assert "035-tracearr" in status["required_keys"]
    assert status["tracearr_requirement_reasons"]


def test_tracearr_validator_returns_plex_servers(client, qs_module, monkeypatch):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "servers": [
            {"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Plex", "type": "plex"},
            {"id": "ignored", "name": "Jellyfin", "type": "jellyfin"},
        ]
    }
    response.raise_for_status.return_value = None
    get = MagicMock(return_value=response)
    monkeypatch.setattr(qs_module.validations.requests, "get", get)

    result = client.post(
        "/validate_tracearr",
        json={"tracearr_url": "http://tracearr.local:3019", "tracearr_apikey": "trr_pub_secret"},
    )

    assert result.status_code == 200
    assert result.get_json() == {
        "valid": True,
        "servers": [{"id": "550e8400-e29b-41d4-a716-446655440000", "name": "Plex"}],
    }
    get.assert_called_once_with(
        "http://tracearr.local:3019/api/v1/public/health",
        headers={"Authorization": "Bearer trr_pub_secret"},
        timeout=10,
    )


def test_tracearr_validator_rejects_non_public_key(client):
    result = client.post(
        "/validate_tracearr",
        json={"tracearr_url": "http://tracearr.local:3019", "tracearr_apikey": "private-key"},
    )

    assert result.status_code == 400
    assert result.get_json()["valid"] is False
