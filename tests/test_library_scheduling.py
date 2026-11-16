import copy
import json
import shlex
from pathlib import Path
from unittest.mock import Mock

import jsonschema
import pytest
from ruamel.yaml import YAML

from modules import database, helpers, importer, library_scheduling as scheduling, persistence
from modules.output_dump import dump_section
from modules.output_library_ops import build_top_level_fields

RULES = [
    {"schedule": "weekly(monday)", "mode": "added(7)"},
    {"schedule": "weekly(tuesday)", "mode": "index(A-F#)"},
    {"schedule": "weekly.not(monday|tuesday)", "mode": "full"},
]


@pytest.mark.parametrize(
    "mode",
    [
        "full",
        "diff",
        "added(7)",
        "added(30m)",
        "added(1h)",
        "ADDED(12D)",
        "added(007)",
        "index(A)",
        "index(A-F#)",
        "index(g-z)",
        "items(imdb:tt0133093|tmdb:550|tvdb:350396|plex:42)",
    ],
)
def test_finalized_processing_modes(mode):
    assert scheduling.validate_mode(mode) == mode


@pytest.mark.parametrize(
    "mode",
    [
        "",
        None,
        "added(0)",
        "added(-1)",
        "added(1.5)",
        "added(1w)",
        "added(999999999999999999999)",
        "index(Z-A)",
        "index(A#)",
        "index(1-9)",
        "items(42)",
        "items(plex:0)",
        "items(imdb:123)",
        "items(tmdb:-2)",
        "items(plex:1|)",
        "items(plex:1); echo hi",
        "changed",
    ],
)
def test_invalid_modes_explain_the_problem(mode):
    with pytest.raises(ValueError):
        scheduling.validate_mode(mode)


@pytest.mark.parametrize(
    "expression",
    [
        "daily",
        "never",
        "weekly(mon|fri)",
        "weekly.not(monday|tuesday)",
        "monthly(1|15|21-last)",
        "monthly.not(last)",
        "hourly(17-4)",
        "yearly(02/29|12/25)",
        "date(02/14/2027)",
        "range(12/01-01/15)",
        "all[weekly(monday), hourly(6)]",
    ],
)
def test_schedule_expressions(expression):
    assert scheduling.validate_expression(expression) == expression


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "dailygarbage",
        "weekly(funday)",
        "weekly(mon|)",
        "monthly(0)",
        "monthly(31-2)",
        "monthly(32)",
        "hourly(24)",
        "hourly(4-4)",
        "date(02/30/2027)",
        "yearly(13/01)",
        "range(11/31-12/01)",
        "weekly.before(mon)",
        "all[all[weekly(mon)]]",
        "all[weekly(mon)",
        "weekly(mon))",
    ],
)
def test_invalid_schedule_expressions(expression):
    with pytest.raises(ValueError):
        scheduling.validate_expression(expression)


@pytest.mark.parametrize("value", [None, "", "weekly(mon)", ["weekly(mon)", "weekly(fri)"], RULES])
def test_legacy_and_scoped_schedule_shapes(value):
    assert scheduling.schedule_errors(value) == []


@pytest.mark.parametrize(
    "value",
    [
        [],
        RULES[0],
        [RULES[0], "daily"],
        [{"schedule": "daily"}],
        [{"schedule": "daily", "mode": "full", "future": 1}],
        [{"schedule": "monthly(32)", "mode": "full"}],
        '[{"schedule":',
    ],
)
def test_invalid_rules_are_not_silently_accepted(value):
    assert scheduling.schedule_errors(value)


@pytest.mark.parametrize("schedule", ["weekly(mon)", ["weekly(mon)"], ["weekly(mon)", "weekly(fri)"], RULES])
def test_import_clean_and_yaml_roundtrip_preserves_schedule(schedule):
    original = copy.deepcopy(schedule)
    payload, _report = importer.prepare_import_payload({"libraries": {"Movies": {"schedule": schedule}}}, {"Movies"}, set())
    fields = payload["libraries"]["libraries"]
    assert fields["mov-library_movies-top_level_schedule"] == original
    cleaned = persistence.clean_form_data(fields)
    library = build_top_level_fields(cleaned, "mov", "movies")
    assert library["schedule"] == original
    config = {"libraries": {"Movies": library}}
    yaml = dump_section("", "libraries", config, "none", None)
    assert YAML(typ="safe", pure=True).load(yaml)["libraries"]["Movies"]["schedule"] == original
    assert schedule == original


def test_autosave_reopen_and_partial_save_preserve_order(client, isolated_config_dir):
    name, library_id = "pytest_scheduling", "mov-library_movies"
    with client.session_transaction() as session:
        session["config_name"] = name
    ordered = [RULES[2], RULES[0], RULES[1]]
    reply = client.post(f"/autosave_library/{library_id}", json={f"{library_id}-library": "Movies", f"{library_id}-top_level_schedule": json.dumps(ordered)})
    assert reply.status_code == 200, reply.json
    _valid, _entered, saved = database.retrieve_section_data(name, "libraries")
    assert saved["libraries"][f"{library_id}-top_level_schedule"] == ordered
    assert client.post(f"/autosave_library/{library_id}", json={f"{library_id}-library": "Movies", f"{library_id}-top_level_report_path": "report.yml"}).status_code == 200
    _valid, _entered, saved = database.retrieve_section_data(name, "libraries")
    assert saved["libraries"][f"{library_id}-top_level_schedule"] == ordered
    invalid = client.post(
        f"/autosave_library/{library_id}", json={f"{library_id}-library": "Movies", f"{library_id}-top_level_schedule": '[{"schedule":"daily","mode":"added(0)"}]'}
    )
    assert invalid.status_code == 400
    assert invalid.json["errors"][0]["field"] == "schedule"
    assert database.retrieve_section_data(name, "libraries")[2]["libraries"][f"{library_id}-top_level_schedule"] == ordered


@pytest.mark.parametrize("supported,confirmed,expected_errors", [(True, False, False), (False, False, True), (False, True, True), (None, False, True), (None, True, False)])
def test_export_requires_runtime_support_or_external_confirmation(monkeypatch, supported, confirmed, expected_errors):
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": supported, "message": "Update or confirm Kometa support."})
    fields = {"mov-library_movies-library": "Movies", "mov-library_movies-tmp_schedule_compatibility_confirmed": confirmed}
    errors = scheduling.configuration_errors({"libraries": {"Movies": {"schedule": RULES}}}, fields)
    assert bool(errors) is expected_errors
    assert scheduling.configuration_errors({"libraries": {"Movies": {"schedule": "weekly(mon)"}}}, {}) == []


def test_diff_requires_cache_at_export(monkeypatch):
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": True, "message": ""})
    errors = scheduling.configuration_errors({"settings": {"cache": False}, "libraries": {"Movies": {"schedule": [{"schedule": "daily", "mode": "diff"}]}}}, {})
    assert "persistent cache" in errors[0]


def test_basic_exclusions_also_require_a_supporting_runtime(monkeypatch):
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": False, "message": "Update Kometa."})
    assert scheduling.configuration_errors({"libraries": {"Movies": {"schedule": "weekly.not(monday)"}}}, {}) == ["Movies: Update Kometa."]


def test_runtime_detection_does_not_trust_branch_or_version(monkeypatch, tmp_path):
    monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: "managed")
    monkeypatch.setattr(helpers, "get_kometa_root_path", lambda: tmp_path)
    assert scheduling.runtime_support()["supported"] is None
    (tmp_path / "modules").mkdir()
    (tmp_path / "kometa.py").write_text("KOMETA_MODE", encoding="utf-8")
    (tmp_path / "modules/config.py").write_text("schedule_modes runtime_mode", encoding="utf-8")
    (tmp_path / "modules/library.py").write_text("old runtime", encoding="utf-8")
    assert scheduling.runtime_support()["supported"] is False
    (tmp_path / "modules/library.py").write_text("parse_added_duration", encoding="utf-8")
    assert scheduling.runtime_support()["supported"] is True
    monkeypatch.setattr(helpers, "get_kometa_install_mode", lambda: "external")
    assert scheduling.runtime_support()["supported"] is None


def test_cached_library_schema_supports_modes_without_changing_other_schedules():
    schema = json.loads((Path(__file__).parent / "fixtures/schema/config-schema.json").read_text(encoding="utf-8-sig"))
    original = copy.deepcopy(schema)
    scheduling.extend_config_schema(schema)
    library_validator = jsonschema.Draft7Validator({"$ref": "#/definitions/library-section", "definitions": schema["definitions"]})
    assert list(library_validator.iter_errors({"Movies": {"schedule": RULES}})) == []
    assert list(library_validator.iter_errors({"Movies": {"schedule": [{"schedule": "daily", "mode": "added(0)"}]}}))
    for name, definition in original["definitions"].items():
        if name != "library-section":
            assert definition == schema["definitions"][name]
    previous = copy.deepcopy(schema)
    scheduling.extend_config_schema(schema)
    assert schema == previous


@pytest.mark.parametrize("platform", ["unix", "windows"])
def test_runtime_override_is_one_quoted_argument(monkeypatch, platform):
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": True, "message": ""})
    parts = shlex.split("python kometa.py --run-libraries 'Movies|TV Shows' --mode 'items(imdb:tt0133093|plex:42)'", posix=platform == "unix")
    scheduling.validate_command_mode(parts)
    helpers.normalize_flag_values(parts)
    assert parts[parts.index("--mode") + 1] == "items(imdb:tt0133093|plex:42)"


def test_start_route_rejects_bad_or_unsupported_mode_before_launch(client, qs_module, monkeypatch):
    launch = Mock()
    monkeypatch.setattr(qs_module, "_launch_kometa_command", launch)
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": False, "message": "Update Kometa."})
    for command in ["python kometa.py --run --mode 'added(0)'", "python kometa.py --run --mode 'full'", "python kometa.py --mode", "python kometa.py --mode full --mode diff"]:
        reply = client.post("/start-kometa", json={"command": command})
        assert reply.status_code == 400, reply.json
    launch.assert_not_called()


def test_one_time_override_launches_without_changing_saved_rules(client, qs_module, isolated_config_dir, monkeypatch):
    name = "pytest_scoped_run"
    database.save_section_data("libraries", True, True, {"libraries": {"mov-library_movies-library": "Movies", "mov-library_movies-top_level_schedule": RULES}}, name=name)
    with client.session_transaction() as session:
        session["config_name"] = name
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": True, "message": ""})
    monkeypatch.setattr(qs_module, "_resolve_kometa_selection", lambda *_: {"install_mode": "managed"})
    monkeypatch.setattr(helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: None)
    monkeypatch.setattr(qs_module, "_get_active_work_blocker", lambda *_: None)
    monkeypatch.setattr(qs_module, "_resolve_maintenance_window_live", lambda **_: (None, None, None))
    monkeypatch.setattr(qs_module, "_resolve_maintenance_window_from_db", lambda **_: (None, None, None))
    launch = Mock(return_value=(True, 12345))
    monkeypatch.setattr(qs_module, "_launch_kometa_command", launch)
    command = "python kometa.py --run-libraries Movies --mode 'added(1)'"
    reply = client.post("/start-kometa", json={"command": command})
    assert reply.status_code == 200, reply.json
    assert launch.call_args.args[:2] == (command, name)
    assert database.retrieve_section_data(name, "libraries")[2]["libraries"]["mov-library_movies-top_level_schedule"] == RULES


@pytest.mark.parametrize("supported", [True, False])
def test_final_yaml_validation_enforces_runtime_compatibility(app, isolated_config_dir, monkeypatch, supported):
    from flask import session
    from modules import output_render

    monkeypatch.setitem(app.config, "QS_OPTIMIZE_DEFAULTS", False)
    monkeypatch.setattr(scheduling, "runtime_support", lambda: {"supported": supported, "message": "Update Kometa for processing modes."})
    monkeypatch.setattr(output_render, "render_yaml_header", lambda *_: "")
    database.save_section_data(
        "libraries", True, True, {"libraries": {"mov-library_movies-library": "Movies", "mov-library_movies-top_level_schedule": RULES}}, name="scheduling_export"
    )
    config = {"plex": {"plex": {"url": "http://plex:32400", "token": "token"}}, "tmdb": {"tmdb": {"apikey": "a" * 32}}, "libraries": {"libraries": {"Movies": {"schedule": RULES}}}}
    with app.test_request_context():
        session["config_name"] = "scheduling_export"
        valid, _first, _data, yaml, errors = output_render.emit_and_validate_config(config, {}, "none", "scheduling_export", {"Movies": "movie"}, ["Movies"], [])
    assert valid is supported, errors
    assert YAML(typ="safe", pure=True).load(yaml)["libraries"]["Movies"]["schedule"] == RULES
    if not supported:
        assert any("Update Kometa" in str(error) for error in errors)
