from pathlib import Path

import pytest
from flask import session


def test_get_incomplete_resume_runs_only_evaluates_latest_candidate(tmp_path, monkeypatch, qs_module):
    latest_candidate = tmp_path / "meta-latest.log"
    older_candidate = tmp_path / "meta-older.log"
    latest_candidate.write_text("latest", encoding="utf-8")
    older_candidate.write_text("older", encoding="utf-8")

    ingest_cache = {
        "logs": {
            str(latest_candidate.resolve()): {"run_complete": False, "mtime": 200.0},
            str(older_candidate.resolve()): {"run_complete": False, "mtime": 100.0},
        }
    }

    monkeypatch.setattr(qs_module, "_load_logscan_ingest_cache", lambda: ingest_cache)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    # Keep live meta candidate out of this test.
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: tmp_path / "no-meta-root")

    calls = []

    def fake_analyze(path, cache_entry=None, config_name=None):
        resolved = Path(path).resolve()
        calls.append(resolved)
        if resolved == latest_candidate.resolve():
            return None
        if resolved == older_candidate.resolve():
            return {
                "incomplete_log_name": older_candidate.name,
                "resume_reason": "Run appears incomplete.",
                "resume_primary": "kometa.py --run --resume abc",
                "config_name": config_name or "default",
            }
        return None

    monkeypatch.setattr(qs_module, "_analyze_incomplete_log_for_resume", fake_analyze)

    runs = qs_module._get_incomplete_resume_runs(limit=1, config_name="testcfg")
    assert runs == []
    assert calls == [latest_candidate.resolve()]


def test_build_latest_incomplete_resume_hint_exposes_explanation(monkeypatch, qs_module):
    monkeypatch.setattr(
        qs_module,
        "_get_incomplete_resume_runs",
        lambda limit=1, config_name=None: [
            {
                "resume_reason": "Run appears incomplete.",
                "phase_current": "operations",
                "current_library": "Movies",
                "run_command": "kometa.py --run --config <config>",
                "resume_primary": 'kometa.py --run --operations-only --run-libraries "Movies" --config "C:/config.yml"',
                "incomplete_log_name": "meta.log",
                "config_name": "testcfg",
                "resume_explanation": ["Reason one", "Reason two"],
            }
        ],
    )

    with qs_module.app.test_request_context("/step/900-kometa"):
        session["config_name"] = "testcfg"
        hint = qs_module._build_latest_incomplete_resume_hint()

    assert isinstance(hint, dict)
    assert hint["log_name"] == "meta.log"
    assert hint["explanation"] == ["Reason one", "Reason two"]


def test_resume_explanation_calls_out_resume_not_used_for_operations(qs_module):
    lines = qs_module._build_resume_explanation(
        original_command="kometa.py --run --operations-only --config <config>",
        suggested_command='kometa.py --run --operations-only --run-libraries "Movies" --config "C:/cfg.yml"',
        phase_current="operations",
        current_library="Movies",
        finished_at="2026-04-03 17:40:33",
    )
    joined = "\n".join(lines)
    assert "--resume was not used" in joined
    assert "operations-phase" in joined


def test_build_recovery_suggestions_preserves_full_run_scope_for_collection_resume(qs_module):
    suggestions = qs_module._build_recovery_suggestions(
        original_command="kometa.py --run --config <config>",
        phase_current="collections",
        current_library="Movies",
        current_collection="Top Picks",
    )
    assert suggestions
    assert '--resume "Top Picks"' in suggestions[0]
    assert '--run-libraries "Movies"' in suggestions[0]
    assert "--collections-only" not in suggestions[0]


def test_build_recovery_suggestions_preserves_collections_only_scope_when_original_was_collections_only(qs_module):
    suggestions = qs_module._build_recovery_suggestions(
        original_command="kometa.py --run --collections-only --config <config>",
        phase_current="collections",
        current_library="Movies",
        current_collection="Top Picks",
    )

    assert suggestions
    assert '--resume "Top Picks"' in suggestions[0]
    assert '--run-libraries "Movies"' in suggestions[0]
    assert "--collections-only" in suggestions[0]


def test_build_resume_library_scope_for_collections_only_without_run_libraries_uses_remaining_order(qs_module):
    scope = qs_module._build_resume_library_scope(
        original_command="kometa.py --run --collections-only --config <config>",
        progress_libraries=[
            {"name": "Movies", "status": "Done"},
            {"name": "TV Shows", "status": "In progress"},
            {"name": "Anime", "status": "Pending"},
        ],
        current_library="TV Shows",
    )

    assert scope == ["TV Shows", "Anime"]


def test_build_resume_library_scope_for_collections_only_with_run_libraries_uses_selected_minus_completed(qs_module):
    scope = qs_module._build_resume_library_scope(
        original_command='kometa.py --run --collections-only --run-libraries "Movies|TV Shows|Anime" --config <config>',
        progress_libraries=[
            {"name": "Movies", "status": "Done"},
            {"name": "TV Shows", "status": "In progress"},
            {"name": "Anime", "status": "Pending"},
            {"name": "Documentaries", "status": "Pending"},
        ],
        current_library="TV Shows",
    )

    assert scope == ["TV Shows", "Anime"]


def test_build_recovery_suggestions_for_collections_only_scopes_to_remaining_libraries(qs_module):
    suggestions = qs_module._build_recovery_suggestions(
        original_command="kometa.py --run --collections-only --config <config>",
        phase_current="collections",
        current_library="TV Shows",
        current_collection="Top Picks",
        progress_libraries=[
            {"name": "Movies", "status": "Done"},
            {"name": "TV Shows", "status": "In progress"},
            {"name": "Anime", "status": "Pending"},
        ],
    )

    assert suggestions
    assert '--run-libraries "TV Shows|Anime"' in suggestions[0]
    assert '--resume "Top Picks"' in suggestions[0]
    assert "--collections-only" in suggestions[0]


@pytest.mark.parametrize(
    "phase_flag,phase_current",
    [
        ("--operations-only", "operations"),
        ("--playlists-only", "playlists"),
        ("--metadata-only", "metadata"),
        ("--overlays-only", "overlays"),
    ],
)
def test_build_recovery_suggestions_for_phase_only_runs_prune_completed_libraries(qs_module, phase_flag, phase_current):
    suggestions = qs_module._build_recovery_suggestions(
        original_command=f"kometa.py --run {phase_flag} --config <config>",
        phase_current=phase_current,
        current_library="TV Shows",
        progress_libraries=[
            {"name": "Movies", "status": "Done"},
            {"name": "TV Shows", "status": "In progress"},
            {"name": "Anime", "status": "Pending"},
        ],
    )

    assert suggestions
    assert phase_flag in suggestions[0]
    assert '--run-libraries "TV Shows|Anime"' in suggestions[0]
    assert "--resume" not in suggestions[0]


def test_build_recovery_suggestions_for_full_run_prune_completed_libraries_without_changing_scope(qs_module):
    suggestions = qs_module._build_recovery_suggestions(
        original_command="kometa.py --run --config <config>",
        phase_current="operations",
        current_library="TV Shows",
        progress_libraries=[
            {"name": "Movies", "status": "Done"},
            {"name": "TV Shows", "status": "In progress"},
            {"name": "Anime", "status": "Pending"},
        ],
    )

    assert suggestions
    assert '--run-libraries "TV Shows|Anime"' in suggestions[0]
    assert "--operations-only" not in suggestions[0]
    assert "--resume" not in suggestions[0]


def test_build_recovery_suggestions_returns_no_recovery_when_pruning_leaves_zero_libraries(qs_module):
    suggestions = qs_module._build_recovery_suggestions(
        original_command="kometa.py --run --collections-only --config <config>",
        phase_current="collections",
        current_library="Movies",
        current_collection="Top Picks",
        progress_libraries=[{"name": "Movies", "status": "Done"}],
    )

    assert suggestions == []


def test_completed_scope_resume_message_states_scope_is_fully_completed(qs_module):
    message = qs_module._build_completed_scope_resume_message(
        phase_current="collections",
        current_library="Movies",
        finished_at="2026-04-03 17:40:33",
    )

    assert "fully completed" in message
    assert "Movies" in message


def test_build_latest_incomplete_resume_hint_marks_completed_scope(monkeypatch, qs_module):
    monkeypatch.setattr(
        qs_module,
        "_get_incomplete_resume_runs",
        lambda limit=1, config_name=None: [
            {
                "resume_reason": "The original run scope appears fully completed.",
                "phase_current": "collections",
                "current_library": "Movies",
                "run_command": "kometa.py --run --collections-only --config <config>",
                "resume_primary": "",
                "incomplete_log_name": "meta.log",
                "config_name": "testcfg",
                "resume_explanation": [],
                "resume_scope_completed": True,
            }
        ],
    )

    with qs_module.app.test_request_context("/step/900-kometa"):
        session["config_name"] = "testcfg"
        hint = qs_module._build_latest_incomplete_resume_hint()

    assert isinstance(hint, dict)
    assert hint["scope_completed"] is True
    assert hint["suggested_command"] == ""


def test_resume_explanation_calls_out_scoped_resume_for_collections(qs_module):
    lines = qs_module._build_resume_explanation(
        original_command="kometa.py --run --collections-only --config <config>",
        suggested_command='kometa.py --run --collections-only --run-libraries "Movies" --resume "Top Picks" --config "C:/cfg.yml"',
        phase_current="collections",
        current_library="Movies",
        current_collection="Top Picks",
        finished_at="2026-04-03 17:40:33",
    )
    joined = "\n".join(lines)
    assert 'using --resume "Top Picks"' in joined
    assert "instead of blind resume across all libraries" in joined


def test_resume_explanation_calls_out_scope_preservation_for_full_run(qs_module):
    lines = qs_module._build_resume_explanation(
        original_command="kometa.py --run --config <config>",
        suggested_command='kometa.py --run --run-libraries "Movies" --resume "Top Picks" --config "C:/cfg.yml"',
        phase_current="collections",
        current_library="Movies",
        current_collection="Top Picks",
        finished_at="2026-04-03 17:40:33",
    )
    joined = "\n".join(lines)
    assert "was not collections-only" in joined
    assert "keeping the original run scope" in joined
    assert "--collections-only" not in joined
