from pathlib import Path
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
                "resume_timing_summary": {"started_at": "2026-05-05 01:00:00"},
                "resume_scope_summary": {"completed_label": "Movies"},
                "resume_progress_snapshot": {"rows": [{"name": "Movies"}]},
                "resume_maintenance_events": [{"label": "Paused", "at": "2026-05-05 02:00:00"}],
            }
        ],
    )

    with qs_module.app.test_request_context("/step/900-kometa"):
        session["config_name"] = "testcfg"
        hint = qs_module._build_latest_incomplete_resume_hint()

    assert isinstance(hint, dict)
    assert hint["log_name"] == "meta.log"
    assert hint["explanation"] == ["Reason one", "Reason two"]
    assert hint["timing_summary"]["started_at"] == "2026-05-05 01:00:00"
    assert hint["scope_summary"]["completed_label"] == "Movies"
    assert hint["progress_snapshot"]["rows"][0]["name"] == "Movies"
    assert hint["maintenance_events"][0]["label"] == "Paused"


def test_build_incomplete_run_timing_summary_accounts_for_maintenance_pause(qs_module):
    summary = qs_module._build_incomplete_run_timing_summary(
        started_at="2026-05-05 01:00:00",
        last_log_at="2026-05-05 03:30:00",
        maintenance_summary={
            "had_pause": True,
            "pause_count": 1,
            "pause_seconds": 3600,
            "window": "02:00-05:00",
        },
    )

    assert summary["observed_label"] == "2h 30m"
    assert summary["pause_label"] == "1h"
    assert summary["pause_display"] == "1h"
    assert summary["active_label"] == "1h 30m"
    assert summary["window"] == "02:00-05:00"


def test_build_incomplete_run_timing_summary_marks_missing_maintenance_as_not_observed(qs_module):
    summary = qs_module._build_incomplete_run_timing_summary(
        started_at="2026-05-05 01:00:00",
        last_log_at="2026-05-05 03:30:00",
        maintenance_summary={},
    )

    assert summary["pause_display"] == "Not observed"


def test_build_incomplete_scope_summary_reports_completed_and_pruned_libraries(qs_module):
    summary = qs_module._build_incomplete_scope_summary(
        original_command="kometa.py --run --config <config>",
        suggested_command='kometa.py --run --run-libraries "Movies|TV Shows" --resume "Top Picks" --config <config>',
        progress_libraries=[
            {"name": "Anime", "status": "Done"},
            {"name": "Movies", "status": "In progress"},
            {"name": "TV Shows", "status": "Pending"},
        ],
    )

    assert summary["completed_label"] == "Anime"
    assert summary["pruned_label"] == "Anime"
    assert summary["recovery_scope_label"] == "Movies | TV Shows"


def test_build_incomplete_progress_snapshot_exposes_rows_and_totals(qs_module):
    snapshot = qs_module._build_incomplete_progress_snapshot(
        {
            "phase_current": "collections",
            "current_library": "Movies",
            "completed_count": 1,
            "total_count": 2,
            "current_phase_elapsed_seconds": 90,
            "preparation_seconds": 30,
            "libraries": [
                {
                    "name": "Anime",
                    "type": "show",
                    "status": "Done",
                    "durations": {"operations": 120, "collections": 240},
                },
                {
                    "name": "Movies",
                    "type": "movie",
                    "status": "In progress",
                    "durations": {"operations": 60},
                },
            ],
        },
        last_log_at="2026-05-05 03:30:00",
        config_data={"playlists": {"daily": {}}, "settings": {"run_order": ["operations", "metadata", "collections", "overlays"]}},
        original_command="kometa.py --run --config <config>",
    )

    assert [column["key"] for column in snapshot["columns"]] == ["operations", "metadata", "collections", "overlays", "playlists"]
    assert snapshot["preparation_label"] == "30s"
    assert snapshot["rows"][0]["phase_cells"][0]["label"] == "2m"
    assert snapshot["rows"][1]["phase_cells"][2]["label"] == "1m 30s"
    assert snapshot["total_label"] == "7m 30s"


def test_build_completed_log_progress_snapshot_does_not_require_request_context(qs_module, isolated_config_dir, monkeypatch):
    kometa_root = isolated_config_dir / "kometa"
    config_dir = kometa_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "default_config.yml").write_text("libraries: {}\n", encoding="utf-8")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)

    class _FakeProgressAnalyzer:
        def extract_progress(self, *_args, **_kwargs):
            return {
                "phase_current": "operations",
                "current_library": "Movies",
                "completed_count": 0,
                "total_count": 1,
                "preparation_seconds": 12,
                "libraries": [
                    {
                        "name": "Movies",
                        "type": "movie",
                        "status": "In progress",
                        "durations": {},
                    }
                ],
            }

    snapshot = qs_module._build_completed_log_progress_snapshot(
        summary={
            "tool_name": "kometa",
            "config_name": "",
            "run_command": "kometa.py --run --config <config>",
            "started_at": "2026-05-05 01:00:00",
            "finished_at": "2026-05-05 01:05:00",
        },
        content="[2026-05-05 01:05:00,000] [operations.py:1] [INFO] | Done |",
        analyzer=_FakeProgressAnalyzer(),
    )

    assert snapshot["preparation_label"] == "12s"
    assert snapshot["rows"][0]["name"] == "Movies"


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


def test_read_logscan_text_appends_live_kometa_maintenance_sidecar(tmp_path, qs_module):
    log_dir = tmp_path / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    meta_path = log_dir / "meta.log"
    sidecar_path = log_dir / "meta.quickstart-maintenance.log"
    meta_path.write_text("[2026-05-05 01:00:00,000] [kometa.py:1] [INFO] | Start\n", encoding="utf-8")
    sidecar_path.write_text("[Quickstart] Maintenance marker: event=paused at=2026-05-05T06:00:00Z local_at=2026-05-05T02:00:00 window=02:00-05:00\n", encoding="utf-8")

    content = qs_module._read_logscan_text(meta_path, encoding="utf-8", errors="replace")

    assert "Maintenance marker" in content
    assert content.count("Maintenance marker") == 1


def test_write_quickstart_maintenance_marker_falls_back_to_sidecar(monkeypatch, tmp_path, qs_module):
    kometa_root = tmp_path
    monkeypatch.setattr(qs_module, "_append_quickstart_meta_log_line", lambda *_args, **_kwargs: False)

    ok = qs_module._write_quickstart_maintenance_marker(kometa_root, "paused", window="02:00-05:00")

    assert ok is True
    sidecar_path = qs_module._get_kometa_maintenance_sidecar_path(kometa_root)
    assert sidecar_path.exists()
    sidecar_text = sidecar_path.read_text(encoding="utf-8")
    assert "event=paused" in sidecar_text
    assert "window=02:00-05:00" in sidecar_text


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
