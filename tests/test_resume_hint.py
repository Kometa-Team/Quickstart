from pathlib import Path

from flask import session


def test_get_incomplete_resume_runs_scans_past_unparsable_latest(tmp_path, monkeypatch, qs_module):
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

    def fake_analyze(path, cache_entry=None, config_name=None):
        resolved = Path(path).resolve()
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
    assert len(runs) == 1
    assert runs[0]["incomplete_log_name"] == older_candidate.name


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

    with qs_module.app.test_request_context("/step/900-final"):
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


def test_build_recovery_suggestions_prefers_scoped_collection_resume(qs_module):
    suggestions = qs_module._build_recovery_suggestions(
        original_command="kometa.py --run --config <config>",
        phase_current="collections",
        current_library="Movies",
        current_collection="Top Picks",
    )
    assert suggestions
    assert '--resume "Top Picks"' in suggestions[0]
    assert '--run-libraries "Movies"' in suggestions[0]
    assert "--collections-only" in suggestions[0]


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
