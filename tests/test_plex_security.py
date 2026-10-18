"""Advisory parity, analyzer counts and fresh validated connection behavior."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from flask import Flask
import pytest

from modules._vendor.plex_security import assess_log, evaluate_advisories
from modules import helpers, validations_services
from modules.logscan import LogscanAnalyzer


@pytest.mark.parametrize(
    "version,status",
    [
        ("1.42.0.99999", "affected"),
        ("1.43.2.99999", "affected"),
        ("1.43.3.10860", "affected"),
        ("1.43.3.10861", "patched"),
        ("1.43.3.10861-07dfddaeb", "patched"),
        ("1.43.4.10000", "patched"),
        (None, "unknown"),
        ("", "unknown"),
        ("1.43.3", "unknown"),
        ("garbled", "unknown"),
        ("1.41.7.9100garbage", "unknown"),
        ("1.43.3.10861.0", "unknown"),
    ],
)
def test_version_assessment(version, status):
    assert evaluate_advisories(version)[0]["status"] == status


def test_vendored_source_matches_pinned_manifest():
    directory = Path(__file__).resolve().parents[1] / "modules" / "_vendor"
    manifest = json.loads((directory / "plex_security.json").read_text())
    source = (directory / "plex_security.py").read_text(encoding="utf-8").replace("\r\n", "\n").encode()
    assert hashlib.sha256(source).hexdigest() == manifest["sha256"]
    assert manifest["repository"] == "Kometa-Team/Logscan"
    assert len(manifest["revision"]) == 40


def test_analyzer_uses_one_finding_per_server_and_preserves_legacy():
    analyzer = LogscanAnalyzer()
    content = "Connected to server A version 1.41.7.9100\n" * 3 + "Connected to server B version 1.43.3.10860\n"
    recommendations, counts = analyzer.make_recommendations(content, "")
    security = [item for item in recommendations if item.get("security_assessment")]
    assert len(security) == 2
    assert counts["plex_security"] == 2
    assert security[0]["security_assessment"]["legacy_vulnerability_affected"]
    assert security[0]["security_assessment"]["evidence_lines"] == [1, 2, 3]
    assert security[0]["severity"] == "critical"
    assert [item["security_assessment"] for item in security] == assess_log(enumerate(content.splitlines(), 1))


def test_missing_version_does_not_create_critical_finding():
    recommendations, counts = LogscanAnalyzer().make_recommendations("No Plex connection here", "")
    assert counts["plex_security"] == 0
    assert next(item for item in recommendations if item.get("security_assessment"))["security_assessment"]["status"] == "unknown"


def test_revalidation_refreshes_version_and_connection_cache(monkeypatch):
    helpers.clear_plex_discovery_cache()
    version = ["1.43.2.99999"]
    calls = []

    def connect(url, token, timeout):
        calls.append((url, token))
        account = SimpleNamespace(users=lambda: [], subscriptionActive=True)
        return SimpleNamespace(
            version=version[0],
            settings=SimpleNamespace(get=lambda key: SimpleNamespace(value=2048)),
            myPlexAccount=lambda: account,
            library=SimpleNamespace(sections=lambda: []),
        )

    monkeypatch.setattr(validations_services, "PlexServer", connect)
    data = {"plex_url": "http://localhost:32400", "plex_token": "token"}
    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context():
        first = validations_services.validate_plex_server(data).get_json()
        assert first["plex_security"][0]["status"] == "affected"
        helpers.set_cached_plex_metadata(data["plex_url"], data["plex_token"], {"version": version[0]})
        version[0] = "1.43.3.10861"
        refreshed = validations_services.validate_plex_server({**data, "force_refresh": True}).get_json()
        assert refreshed["plex_security"][0]["status"] == "patched"
        assert helpers.get_cached_plex_metadata(data["plex_url"], data["plex_token"]) is None
        assert len(calls) == 2
        version[0] = None
        other = validations_services.validate_plex_server({**data, "plex_token": "other"}).get_json()
        assert other["validated"]
        assert other["plex_security"][0]["status"] == "unknown"
    helpers.clear_plex_discovery_cache()


def test_validation_route_always_requests_fresh_connection(client, monkeypatch, qs_module):
    from flask import jsonify

    payloads = []

    def validate(data):
        payloads.append(data)
        return jsonify({"valid": False})

    monkeypatch.setattr(qs_module.validations, "validate_plex_server", validate)
    client.post("/validate_plex", json={"plex_url": "http://localhost:32400", "plex_token": "token"})
    assert payloads[0]["force_refresh"] is True


def test_fresh_security_assessment_overrides_stale_telemetry(client, monkeypatch, qs_module):
    from flask import jsonify

    monkeypatch.setattr(
        qs_module.validations,
        "validate_plex_server",
        lambda data: jsonify(
            {
                "validated": True,
                "version": None,
                "plex_security": evaluate_advisories(None),
                "movie_libraries": [],
                "show_libraries": [],
                "music_libraries": [],
                "user_list": [],
            }
        ),
    )
    monkeypatch.setattr(
        qs_module.helpers,
        "get_plex_metadata",
        lambda **kwargs: {
            "version": "1.43.4.10000",
            "plex_security": evaluate_advisories("1.43.4.10000"),
        },
    )
    response = client.post("/validate_plex", json={"plex_url": "http://localhost:32400", "plex_token": "token"})
    assert response.status_code == 200
    assert response.get_json()["version"] is None
    assert response.get_json()["plex_security"][0]["status"] == "unknown"
