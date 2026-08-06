import json
from unittest.mock import MagicMock, patch

from modules import database, importer, validations_services
from modules.output_dump import dump_section


def test_serializd_validator_uses_kometa_client_contract(app, monkeypatch):
    response = MagicMock()
    response.ok = True
    response.json.return_value = {"username": "kometa-user", "token": "secret-token"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(validations_services.requests, "post", post)

    with app.app_context():
        result = validations_services.validate_serializd_server(
            {
                "serializd_email": "user@example.com",
                "serializd_password": "password",
                "serializd_timeout": "45",
            }
        )

    assert result.get_json()["valid"] is True
    post.assert_called_once_with(
        "https://serializd.onrender.com/api/login",
        data=json.dumps({"email": "user@example.com", "password": "password"}),
        headers={
            "Origin": "https://www.serializd.com",
            "Referer": "https://www.serializd.com",
            "X-Requested-With": "serializd_vercel",
        },
        timeout=45,
    )


def test_serializd_validator_rejects_missing_credentials(app):
    with app.app_context():
        result, status = validations_services.validate_serializd_server({})

    assert status == 400
    assert result.get_json() == {"valid": False, "error": "Serializd email is required."}


def test_validate_serializd_route_returns_400_on_failure(client):
    result = MagicMock()
    result.get_json.return_value = {"valid": False, "error": "Bad credentials"}
    with patch("modules.validations.validate_serializd_server", return_value=(result, 400)):
        response = client.post(
            "/validate_serializd",
            json={"serializd_email": "user@example.com", "serializd_password": "bad"},
        )

    assert response.status_code == 400
    assert response.get_json()["valid"] is False


def test_serializd_import_and_output_round_trip(app):
    source = {"serializd": {"email": "user@example.com", "password": "password", "timeout": 60}}
    payload, report = importer.prepare_import_payload(source, set(), set())

    assert payload["serializd"] == source
    assert "imported: serializd.email" in report.lines
    with app.app_context():
        rendered = dump_section("", "serializd", source["serializd"], "none", None)
    assert "email: user@example.com" in rendered
    assert "password: password" in rendered
    assert "timeout: 60" in rendered


def test_serializd_page_renders(client, isolated_config_dir):
    response = client.get("/step/065-serializd")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="serializd_email"' in html
    assert 'id="serializd_password"' in html
    assert 'id="serializd_timeout"' in html
    assert 'src="/static/local-js/065-serializd.js"' in html
    assert 'src="/static/images/service-icons/serializd.png"' in html


def test_serializd_page_renders_null_credentials_as_empty(client, isolated_config_dir):
    config_name = "serializd-null-credentials-test"
    database.save_section_data(
        name=config_name,
        section="serializd",
        validated=False,
        user_entered=True,
        data={"serializd": {"email": None, "password": None, "timeout": 60}},
    )
    with client.session_transaction() as session:
        session["config_name"] = config_name

    response = client.get("/step/065-serializd")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="serializd_email" name="serializd_email"\n    value=""' in html
    assert 'id="serializd_password" name="serializd_password"\n    value=""' in html
