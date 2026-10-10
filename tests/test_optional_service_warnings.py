from datetime import datetime, timezone

import pytest

from modules.workspace_rollups import _build_final_gate
from modules.workspace_status_constants import QS_REQUIRED_STEP_KEYS, QS_VALIDATION_STEP_KEYS
from modules.workspace_step_status import _derive_step_status

OPTIONAL_SERVICE_KEYS = sorted(QS_VALIDATION_STEP_KEYS - set(QS_REQUIRED_STEP_KEYS))


@pytest.mark.parametrize("key", OPTIONAL_SERVICE_KEYS)
@pytest.mark.parametrize("state", ["warn", "error"])
def test_unused_optional_service_does_not_block_final_gate(key, state):
    workspace = {
        "step_statuses": {"010-plex": "ok", key: state},
        "required_keys": ["010-plex"],
        "optional_keys": [key],
    }
    gate = _build_final_gate(workspace, [], datetime.now(timezone.utc).isoformat())

    assert gate["todo_blockers"] == []
    assert gate["todo_count"] == 0
    assert gate["can_build_config"] is True
    assert gate["stage"] == "config"


@pytest.mark.parametrize("key", OPTIONAL_SERVICE_KEYS)
@pytest.mark.parametrize("state", ["unknown", "warn", "error"])
def test_required_service_still_blocks_final_gate(key, state):
    workspace = {"step_statuses": {key: state}, "required_keys": [key], "optional_keys": []}
    gate = _build_final_gate(workspace, [], datetime.now(timezone.utc).isoformat())

    assert gate["todo_blockers"] == [{"key": key, "label": key, "state": state, "group": "required"}]
    assert gate["stage"] == "todo"
    assert gate["can_build_config"] is False


def test_unused_service_does_not_bypass_validation_freshness():
    workspace = {"step_statuses": {"067-floppy": "warn"}, "required_keys": [], "optional_keys": ["067-floppy"]}
    gate = _build_final_gate(workspace, [], None)

    assert gate["todo_count"] == 0
    assert gate["stage"] == "freshness"
    assert gate["can_build_config"] is False


def test_invalid_optional_playlist_files_still_block():
    rows = {
        "playlist_files": {
            "validated": False,
            "user_entered": True,
            "data": {"validation_status": "failed", "validation_reason": "invalid_fields"},
        }
    }
    state = _derive_step_status("027-playlist_files", "optional", rows, config_exists=True)
    assert state == "error"
    gate = _build_final_gate(
        {"step_statuses": {"027-playlist_files": state}, "required_keys": [], "optional_keys": ["027-playlist_files"]},
        [],
        datetime.now(timezone.utc).isoformat(),
    )
    assert gate["todo_count"] == 1
    assert gate["stage"] == "todo"


@pytest.mark.parametrize(
    "validation_metadata",
    [
        {"validation_status": "failed", "validation_reason": "validation_error"},
        {"validation_status": "skipped", "validation_reason": "token_invalid"},
        {"validated_at": "2026-01-01T00:00:00Z"},
        {},
    ],
)
@pytest.mark.parametrize("active_source", [False, True])
@pytest.mark.parametrize("feature", ["overlay", "operation"])
def test_floppy_warning_becomes_blocker_only_when_used(monkeypatch, workspace_status_module, active_source, validation_metadata, feature):
    libraries = {"mov-library_movies-library": "Movies"}
    if feature == "overlay":
        libraries.update(
            {
                "mov-library_movies-movie-overlay_ratings": active_source,
                "mov-library_movies-movie-template_overlay_ratings[rating1]": "floppy",
            }
        )
    else:
        libraries["mov-library_movies-attribute_mass_user_rating_update_floppy"] = active_source
    rows = [
        {
            "section": "libraries",
            "validated": True,
            "user_entered": True,
            "data": {"libraries": libraries},
        },
        {
            "section": "floppy",
            "validated": False,
            "user_entered": True,
            "data": {"floppy": {"url": "https://floppy.example.com", "token": "test-token"}, **validation_metadata},
        },
    ]
    templates = [("025-libraries.html", "Libraries"), ("067-floppy.html", "Floppy")]
    monkeypatch.setattr(workspace_status_module.database, "retrieve_config_sections", lambda _name: rows)
    context = workspace_status_module._build_workspace_status_context("cfg", templates, available_configs=["cfg"], include_app_readiness_overrides=False)
    gate = _build_final_gate(context, templates, datetime.now(timezone.utc).isoformat())

    if active_source:
        assert "067-floppy" in context["required_keys"]
        assert gate["todo_count"] == 1
        assert gate["dependency_cards"][0]["provider"] == "floppy"
        assert gate["can_build_config"] is False
    else:
        assert "067-floppy" in context["optional_keys"]
        assert context["step_statuses"]["067-floppy"] == "warn"
        assert context["section_statuses"]["optional"] == "warn"
        assert context["readiness"]["optional_issue_count"] == 1
        assert gate["todo_count"] == 0
        assert gate["dependency_cards"] == []
        assert gate["can_build_config"] is True


@pytest.mark.parametrize(
    "key,section,settings",
    [
        ("030-tautulli", "tautulli", {"url": "https://tautulli.example.com", "apikey": "test"}),
        ("050-omdb", "omdb", {"apikey": "test"}),
        ("060-mdblist", "mdblist", {"apikey": "test"}),
        ("065-serializd", "serializd", {"email": "test@example.com", "password": "test"}),
        ("067-floppy", "floppy", {"url": "https://floppy.example.com", "token": "test"}),
        ("100-anidb", "anidb", {"enable": True}),
        ("110-radarr", "radarr", {"url": "https://radarr.example.com", "token": "test"}),
        ("120-sonarr", "sonarr", {"url": "https://sonarr.example.com", "token": "test"}),
        ("140-mal", "mal", {"client_id": "test"}),
    ],
)
@pytest.mark.parametrize("group,expected", [("optional", "warn"), ("required", "error")])
def test_configured_service_failure_severity_depends_on_requirement(key, section, settings, group, expected):
    rows = {
        section: {
            "validated": False,
            "user_entered": True,
            "data": {section: settings, "validation_status": "failed", "validation_reason": "validation_error"},
        }
    }
    assert _derive_step_status(key, group, rows, config_exists=True) == expected


def test_unvalidated_optional_service_is_not_emitted(monkeypatch):
    from modules import output_render

    monkeypatch.setattr(
        output_render.helpers,
        "get_template_list",
        lambda: {"floppy": {"stem": "067-floppy", "raw_name": "floppy", "name": "Floppy"}},
    )
    monkeypatch.setattr(
        output_render.persistence,
        "retrieve_settings",
        lambda _stem: {"validated": False, "floppy": {"url": "https://floppy.example.com", "token": "test-token"}},
    )
    monkeypatch.setattr(output_render, "render_section_header", lambda *_args: "")
    config_data, _header_art = output_render.retrieve_config_sections("none")
    assert "floppy" not in config_data
