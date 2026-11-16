"""Advisory parity, analyzer counts and fresh validated connection behavior."""

import hashlib
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from flask import Flask
import pytest

from modules._vendor.plex_security import assess_log, assessment_message, evaluate_advisories, parse_pms_version, server_observation
from modules import database, helpers, validations_services
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
        ("1.43.3.10896-cb3ebc72d", "patched"),
        ("'1.43.3.10896-cb3ebc72d'", "patched"),
        ('"1.43.3.10896-cb3ebc72d"', "patched"),
        ("1.43.5.11029-6bf8af3f0", "patched"),
        ("'1.43.3.10860'", "affected"),
        (None, "unknown"),
        ("", "unknown"),
        ("1.43.3", "unknown"),
        ("garbled", "unknown"),
        ("1.41.7.9100garbage", "unknown"),
        ("1.43.3.10861.0", "unknown"),
        ("'1.43.3.10896-cb3ebc72d", "unknown"),
        ("'1.43.3.10896-cb3ebc72djunk'", "unknown"),
        ("1.43.3.10861-hash", "unknown"),
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


@pytest.mark.parametrize("version", ["1.43.3.10861", "1.43.3.10896-cb3ebc72d", "1.43.5.11029-6bf8af3f0"])
@pytest.mark.parametrize("field", ["version {version}", "version '{version}'", 'version "{version}"', "(Version: '{version}')"])
def test_patched_versions_do_not_create_recommendations_in_full_analysis(version, field):
    connection = f"Connected to server NZWHS01 {field.format(version=version)}"
    content = (
        "Plex Configuration\n" f"[2026-11-16 06:57:00,000] [plex.py:10] [INFO] | {connection} |\n" "Running on Windows version 10.0.19045.6036\n" "Library Connection Successful\n"
    )
    observation = server_observation(connection)
    assert observation == ("NZWHS01", version)
    assessment = assess_log(enumerate(content.splitlines(), 1))[0]
    assert assessment["status"] == "patched"
    assert assessment["normalized_version"] == version.split("-", 1)[0]
    assert "No advisory-related update is needed" in assessment_message(assessment)
    assert "Validate the current server version" not in assessment_message(assessment)
    result = LogscanAnalyzer().analyze_content(content, include_people_scan=False)
    assert result["summary"]["analysis_counts"]["plex_security"] == 0
    assert result["summary"]["log_counts"]["info"] == 1
    assert not any(item.get("security_assessment") for item in result["recommendations"])


@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_historical_versions_keep_affected_status_and_update_remediation(reverse):
    lines = [
        "Connected to server NZWHS01 version '1.43.3.10896-cb3ebc72d'",
        "Connected to server NZWHS01 version '1.43.3.10860'",
    ]
    if reverse:
        lines.reverse()
    recommendations, counts = LogscanAnalyzer().make_recommendations("\n".join(lines), "")
    security = [item for item in recommendations if item.get("security_assessment")]
    assert len(security) == counts["plex_security"] == 1
    assert security[0]["severity"] == "critical"
    assert security[0]["evidence_lines"] == [1, 2]
    assert security[0]["occurrence_count"] == 2
    assert security[0]["security_assessment"]["status"] == "affected"
    assert "Proposed solution: Update Plex Media Server" in security[0]["message"]
    assert "No advisory-related update is needed" not in security[0]["message"]


def test_live_endpoint_refreshes_old_analysis_cache(client, isolated_config_dir, monkeypatch, qs_module):
    root = Path(qs_module.app.config["KOMETA_ROOT"])
    log_dir = root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "meta.log"
    log_path.write_text("Connected to server NZWHS01 version '1.43.3.10896-cb3ebc72d'\n", encoding="utf-8")
    stats = log_path.stat()
    monkeypatch.setattr(qs_module.helpers, "get_kometa_log_dir", lambda: log_dir)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: True)
    monkeypatch.setattr(qs_module, "_get_kometa_log_wait_payload", lambda *_: None)
    monkeypatch.setattr(LogscanAnalyzer, "scan_file_for_people_posters", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        qs_module,
        "LOGSCAN_ANALYSIS_CACHE",
        {"version": 3, "mtime": stats.st_mtime, "size": stats.st_size, "data": {"recommendations": [{"first_line": "Stale patched card"}]}},
    )
    payload = client.get("/logscan/analyze").get_json()
    assert payload["cached"] is False
    assert payload["summary"]["analysis_counts"]["plex_security"] == 0
    assert not any(item.get("security_assessment") for item in payload["recommendations"])
    assert "Stale patched card" not in json.dumps(payload)
    assert client.get("/logscan/analyze").get_json()["cached"] is True


def test_retained_completed_cards_and_counts_are_filtered_without_rewriting_history(client, isolated_config_dir):
    recommendations = [
        {"first_line": "Old patched card", "security_assessment": {"status": "patched"}},
        {"first_line": "Affected server", "security_assessment": {"status": "affected"}},
        {"first_line": "Unknown server", "security_assessment": {"status": "unknown"}},
        {"first_line": "Other advice"},
    ]
    summary = {"run_key": "retained-plex-version", "run_complete": True, "finished_at": "2026-11-16T06:57:00", "log_counts": {"info": 12, "critical": 2}}
    assert database.save_log_run(summary, recommendations=recommendations)
    run = database.get_log_run(summary["run_key"])
    assert run["recommendations_count"] == 3
    assert run["info_count"] == 12
    assert run["critical_count"] == 2
    assert database.get_log_runs()[0]["recommendations_count"] == 3
    payload = client.get("/logscan/trends/recommendations", query_string={"run_key": summary["run_key"]}).get_json()
    assert payload["recommendations"] == recommendations[1:]
    assert payload["run"]["recommendations_count"] == 3
    with sqlite3.connect(database.get_database_path()) as connection:
        stored = connection.execute("SELECT recommendations FROM log_runs WHERE run_key = ?", (summary["run_key"],)).fetchone()[0]
    assert json.loads(stored) == recommendations


def test_retained_incomplete_report_hides_patched_cards(isolated_config_dir, tmp_path):
    from modules.logscan_incomplete_resume import build_incomplete_run_from_cache_entry

    log_path = tmp_path / "meta.log"
    log_path.write_text("Connected to server NZWHS01 version '1.43.3.10896-cb3ebc72d'\n", encoding="utf-8")
    recommendations = [
        {"first_line": "Old patched card", "security_assessment": {"status": "patched"}},
        {"first_line": "Unknown server", "security_assessment": {"status": "unknown"}},
    ]
    cache_entry = {"run_key": "retained-incomplete", "recommendations": recommendations}
    run = build_incomplete_run_from_cache_entry(log_path, cache_entry)
    assert run["recommendations_count"] == 1
    assert run["recommendations"] == recommendations[1:]
    assert cache_entry["recommendations"] == recommendations


def test_malformed_quoted_version_remains_unknown_instead_of_patched():
    version = "'1.43.3.10896-cb3ebc72djunk'"
    assert parse_pms_version(version) is None
    recommendations, counts = LogscanAnalyzer().make_recommendations(f"Connected to server NZWHS01 version {version}", "")
    security = [item for item in recommendations if item.get("security_assessment")]
    assert len(security) == 1
    assert counts["plex_security"] == 0
    assert security[0]["security_assessment"]["status"] == "unknown"
    assert security[0]["severity"] == "advice"


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
