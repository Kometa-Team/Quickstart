import json
import re
from unittest.mock import MagicMock

from modules import database, persistence


def _response(status_code=200, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload if payload is not None else {"items": []}
    if status_code >= 400:
        response.raise_for_status.side_effect = RuntimeError(f"HTTP {status_code}")
    return response


def test_floppy_authenticated_validation_uses_v1_lists_api(app, monkeypatch):
    from modules import validations_services

    request_get = MagicMock(return_value=_response())
    monkeypatch.setattr(validations_services.requests, "get", request_get)

    with app.app_context():
        result = validations_services.validate_floppy_server({"floppy_url": "https://floppy.example.com/", "floppy_token": "secret"})

    assert result.get_json()["valid"] is True
    request_get.assert_called_once_with(
        "https://floppy.example.com/api/v1/lists",
        headers={"X-API-Key": "secret"},
        params={"limit": 1},
        timeout=10,
    )


def test_floppy_public_list_validation_does_not_send_token(app, monkeypatch):
    from modules import validations_services

    request_get = MagicMock(return_value=_response())
    monkeypatch.setattr(validations_services.requests, "get", request_get)

    with app.app_context():
        result = validations_services.validate_floppy_server({"floppy_url": "http://localhost:8080"})

    assert result.get_json()["valid"] is True
    assert "public-list" in result.get_json()["message"]
    request_get.assert_called_once_with(
        "http://localhost:8080/api/v1/lists",
        headers=None,
        params={"limit": 1},
        timeout=10,
    )


def test_floppy_validation_requires_token_when_selected_features_need_it(app):
    from modules import validations_services

    with app.app_context():
        result, status = validations_services.validate_floppy_server({"floppy_url": "https://floppy.example.com", "floppy_require_token": True})

    assert status == 400
    assert result.get_json()["valid"] is False
    assert "token is required" in result.get_json()["error"]


def test_floppy_validation_route_propagates_failure(client, monkeypatch):
    from modules import validations

    response = MagicMock()
    response.get_json.return_value = {"valid": False, "error": "bad token"}
    monkeypatch.setattr(validations, "validate_floppy_server", lambda _data: (response, 400))

    result = client.post("/validate_floppy", json={"floppy_url": "https://floppy.example.com"})

    assert result.status_code == 400
    assert result.get_json() == {"valid": False, "error": "bad token"}


def test_floppy_step_renders_configured_url_and_module_script(client):
    config_name = "floppy-page-test"
    configured_url = "https://floppy.internal.example:9443"
    database.save_section_data(
        name=config_name,
        section="floppy",
        validated=False,
        user_entered=True,
        data={"floppy": {"url": configured_url, "token": "test-token"}},
    )
    with client.session_transaction() as session:
        session["config_name"] = config_name

    response = client.get("/step/067-floppy")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'id="floppy_url"' in page
    assert f'value="{configured_url}"' in page
    assert "floppy.example.com" not in page
    assert 'id="floppy_token"' in page
    assert 'id="toggleFloppyTokenVisibility"' in page
    assert 'aria-label="Show or hide API token"' in page
    # asset_url() serves the hashed Vite bundle when a build exists
    # (static/dist/.vite/manifest.json) and falls back to the raw source
    # file otherwise -- static/dist is gitignored, so accept either form.
    assert re.search(r'src="/static/(?:dist/067-floppy-[^"]+\.js|local-js/067-floppy\.js)"', page)
    assert 'src="/static/images/service-icons/floppy.png"' in page


def test_floppy_step_hides_dummy_template_url(client, monkeypatch):
    config_name = "floppy-dummy-url-test"
    original_get_dummy_data = persistence.get_dummy_data

    def get_dummy_data(section):
        if section == "floppy":
            return {"url": "http://192.168.1.12:8080", "token": None}
        return original_get_dummy_data(section)

    monkeypatch.setattr(persistence, "get_dummy_data", get_dummy_data)
    with client.session_transaction() as client_session:
        client_session["config_name"] = config_name

    response = client.get("/step/067-floppy")

    assert response.status_code == 200
    assert "192.168.1.12:8080" not in response.get_data(as_text=True)


def test_floppy_simple_section_import_round_trip_contract():
    from modules.importer import prepare_import_payload
    from modules.output_dump import dump_section

    payload, report = prepare_import_payload(
        {"floppy": {"url": "https://floppy.example.com", "token": "secret"}},
        set(),
        set(),
    )

    assert payload["floppy"] == {"floppy": {"url": "https://floppy.example.com", "token": "secret"}}
    assert "imported: floppy.url" in report.lines
    rendered = dump_section("", "floppy", payload["floppy"], "none", None)
    assert "floppy:" in rendered
    assert "url: https://floppy.example.com" in rendered
    assert "token: secret" in rendered


def test_floppy_dependency_reasons_cover_mass_and_direct_overlay_sources(qs_module):
    libraries = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-attribute_mass_user_rating_update_floppy": True,
        "mov-library_movies-movie-overlay_ratings": True,
        "mov-library_movies-movie-template_overlay_ratings[rating1]": "floppy",
    }

    reasons = qs_module._libraries_data_floppy_dependency_reasons(libraries)

    assert any("mass_user_rating_update uses floppy" in reason for reason in reasons)
    assert any("movie ratings overlay uses floppy" in reason for reason in reasons)


def test_floppy_dependency_promotes_workspace_step_to_required(monkeypatch, qs_module):
    rows = [
        {
            "section": "libraries",
            "validated": False,
            "user_entered": True,
            "data": {
                "libraries": {
                    "mov-library_movies-library": "Movies",
                    "mov-library_movies-attribute_mass_user_rating_update_floppy": True,
                }
            },
        }
    ]
    templates = [
        ("001-start.html", "Start"),
        ("025-libraries.html", "Libraries"),
        ("067-floppy.html", "Floppy"),
        ("900-kometa.html", "Kometa"),
    ]
    monkeypatch.setattr(qs_module.database, "retrieve_config_sections", lambda _name: rows)

    context = qs_module._build_workspace_status_context("cfg", templates, available_configs=["cfg"])

    assert "067-floppy" in context["required_keys"]
    assert context["floppy_requirement_reasons"]


def test_floppy_dependency_hint_endpoint_returns_reasons(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda _target: {"libraries": {}})

    response = client.post(
        "/libraries_floppy_dependency_hint",
        json={
            "source_library_id": "mov-library_movies",
            "source_payload": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-movie-overlay_ratings": "true",
                "mov-library_movies-movie-template_overlay_ratings[rating1]": "floppy",
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json()["required"] is True
    assert any("movie ratings overlay uses floppy" in reason for reason in response.get_json()["reasons"])


def test_floppy_rating_json_contracts_include_all_supported_slots():
    with open("static/json/quickstart_attributes.json", encoding="utf-8") as handle:
        attributes = json.load(handle)
    with open("static/json/quickstart_overlays.json", encoding="utf-8") as handle:
        overlays = json.load(handle)

    rating_prefixes = {
        "mass_audience_rating_update",
        "mass_critic_rating_update",
        "mass_user_rating_update",
        "mass_episode_audience_rating_update",
        "mass_episode_critic_rating_update",
        "mass_episode_user_rating_update",
    }
    rating_sections = [section for section in attributes["sections"] if section.get("prefix") in rating_prefixes]
    assert len(rating_sections) == 6
    assert all(any(source[0] == "floppy" for source in section["sources"]) for section in rating_sections)

    encoded_overlays = json.dumps(overlays)
    assert encoded_overlays.count('"value": "floppy"') == 10
