"""Incomplete-run detection and resume-cache machinery.

Extracted from :mod:`modules.logscan_progress` to isolate the
~549 lines of "was this run cut short, and if so can we suggest
a resume command?" logic.

Kometa runs get killed for lots of reasons: maintenance windows,
user-initiated stops, network hiccups, container restarts.  This
module inspects a log file (plus the logscan cache) to figure out
where the run ended up, what libraries had been processed, and
what resume command Quickstart should offer.

Public API (all called from ``quickstart.py`` via the ``_underscore``
re-exports it maintains for tests):

* :func:`analyze_incomplete_log_for_resume` -- the big one.  Parses
  a partial log, extracts run-command + processed libraries +
  progress snapshot, and returns a rich resume-suggestion dict.
* :func:`build_incomplete_run_from_cache_entry` -- fast path that
  builds a run-summary dict from a logscan-cache entry when we
  already parsed the log recently.
* :func:`build_incomplete_resume_cache_fields` -- extracts JUST
  the fields that need to be persisted back into the cache entry
  after a re-analysis.
* :func:`build_incomplete_log_fallback` -- minimal placeholder
  built from log-mtime alone when analysis fails.
* :func:`get_logscan_incomplete_runs` /
  :func:`get_logscan_incomplete_run` -- list / lookup helpers for
  the incomplete-runs dashboard row.
* :func:`get_incomplete_resume_runs` -- narrower list that only
  returns runs eligible for automatic resume suggestion.
* :func:`build_latest_incomplete_resume_hint` -- one-shot helper
  that returns the resume-hint payload for the *most recent*
  incomplete run, shaped for the dashboard banner.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from flask import session

from modules import helpers, logscan
from modules.logscan_cache import normalize_logscan_tool_name
from modules.logscan_progress import (
    build_incomplete_progress_snapshot,
    get_progress_library_list,
)
from modules.logscan_resume import (
    build_completed_scope_resume_message,
    build_incomplete_resume_message,
    build_incomplete_run_timing_summary,
    build_incomplete_scope_summary,
    build_maintenance_event_rows,
    build_recovery_suggestions,
    build_resume_explanation,
    extract_cli_option_value,
    extract_first_log_timestamp,
    extract_last_log_timestamp,
    inject_config_path_for_command,
    iso_from_mtime,
)
from modules.process_control import extract_selected_libraries

_read_logscan_text = helpers.read_logscan_text


def analyze_incomplete_log_for_resume(log_path, cache_entry=None, config_name=None):
    import quickstart

    try:
        content = _read_logscan_text(log_path, encoding="utf-8", errors="replace")
    except Exception:
        return None
    started_at_fallback = extract_first_log_timestamp(content)

    analyzer = logscan.LogscanAnalyzer()
    try:
        analysis = analyzer.analyze_content(
            content,
            log_path=log_path,
            config_name=config_name,
            include_people_scan=False,
        )
    except Exception:
        return None

    summary = analysis.get("summary") if isinstance(analysis, dict) else None
    recommendations = analysis.get("recommendations") if isinstance(analysis, dict) else None
    if not isinstance(recommendations, list):
        recommendations = []
    if not isinstance(summary, dict):
        return None
    if summary.get("run_complete"):
        return None

    try:
        original_command = inject_config_path_for_command(
            summary.get("run_command") or "",
            config_name=summary.get("config_name") or config_name,
        )
        config_path = extract_cli_option_value(original_command, "--config")
        config_data = quickstart._load_progress_config(config_path) if config_path else {}
        selected_libraries = extract_selected_libraries(original_command)[1]
        progress = analyzer.extract_progress(
            content,
            library_list=get_progress_library_list(
                selected_libraries=selected_libraries,
                config_path=config_path,
                config_data=config_data,
            ),
            selected_libraries=selected_libraries,
        )
    except Exception:
        progress = {}
    if not isinstance(progress, dict):
        progress = {}

    phase_current = (progress.get("phase_current") or "").strip().lower() or None
    current_library = progress.get("current_library") if isinstance(progress.get("current_library"), str) else None
    if current_library is None or not current_library.strip():
        current_library = None
        for entry in progress.get("libraries", []) or []:
            if entry.get("status") == "In progress" and entry.get("name"):
                current_library = str(entry.get("name"))
                break
    if current_library is not None and not current_library.strip():
        current_library = None

    current_collection = None
    collection_in_library_re = re.compile(r"^\s*(.+?)\s+Collection\s+in\s+.+$", re.IGNORECASE)
    running_collection_re = re.compile(r"^\s*Running\s+(.+?)\s+Collection\b", re.IGNORECASE)
    try:
        for raw_line in content.splitlines():
            if not raw_line:
                continue
            msg = raw_line.split("|", 1)[1].strip() if "|" in raw_line else raw_line.strip()
            msg = analyzer._strip_divider_wrappers(msg)
            match = running_collection_re.search(msg) or collection_in_library_re.search(msg)
            if match:
                candidate = str(match.group(1) or "").strip()
                if candidate:
                    current_collection = candidate
    except Exception:
        current_collection = None

    progress_libraries = progress.get("libraries") if isinstance(progress.get("libraries"), list) else []
    last_log_at = extract_last_log_timestamp(content)
    timing_summary = build_incomplete_run_timing_summary(
        started_at=summary.get("started_at") or started_at_fallback,
        last_log_at=last_log_at,
        maintenance_summary=summary.get("maintenance_summary"),
    )

    suggestions = build_recovery_suggestions(
        original_command,
        phase_current=phase_current,
        current_library=current_library,
        current_collection=current_collection,
        progress_libraries=progress_libraries,
    )
    primary = suggestions[0] if suggestions else ""
    scope_completed = not primary and not suggestions
    explanation = []
    if primary:
        explanation = build_resume_explanation(
            original_command,
            primary,
            phase_current=phase_current,
            current_library=current_library,
            current_collection=current_collection,
            finished_at=summary.get("finished_at"),
            progress_libraries=progress_libraries,
        )
    reason = build_incomplete_resume_message(
        phase_current=phase_current,
        current_library=current_library,
        finished_at=summary.get("finished_at"),
    )
    if scope_completed:
        reason = build_completed_scope_resume_message(
            phase_current=phase_current,
            current_library=current_library,
            finished_at=summary.get("finished_at"),
        )
    counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    mtime = summary.get("log_mtime")
    if not isinstance(mtime, (int, float)) and isinstance(cache_entry, dict):
        mtime = cache_entry.get("mtime")
    created_at = summary.get("created_at")
    if not created_at and isinstance(cache_entry, dict):
        created_at = cache_entry.get("updated_at") or iso_from_mtime(cache_entry.get("mtime"))
    if not created_at:
        created_at = iso_from_mtime(mtime)
    run_key = summary.get("run_key")
    if not run_key:
        run_key_seed = f"incomplete|{log_path}|{mtime or 0}"
        run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()
    started_at = summary.get("started_at") or started_at_fallback
    scope_summary = build_incomplete_scope_summary(
        original_command=original_command,
        suggested_command=primary,
        progress_libraries=progress_libraries,
    )
    progress_snapshot = build_incomplete_progress_snapshot(
        progress,
        last_log_at=last_log_at,
        config_data=config_data,
        original_command=original_command,
    )
    maintenance_events = build_maintenance_event_rows(summary.get("maintenance_summary"))

    return {
        "run_key": run_key,
        "started_at": started_at,
        "last_log_at": last_log_at,
        "finished_at": summary.get("finished_at"),
        "run_time_seconds": summary.get("run_time_seconds"),
        "kometa_version": summary.get("kometa_version"),
        "kometa_newest_version": summary.get("kometa_newest_version"),
        "config_name": summary.get("config_name") or config_name or "",
        "config_hash": summary.get("config_hash"),
        "run_command": original_command,
        "command_signature": summary.get("command_signature"),
        "section_runtimes": summary.get("section_runtimes") or {},
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
        "log_mtime": mtime,
        "log_size": summary.get("log_size"),
        "debug_count": counts.get("debug", 0),
        "info_count": counts.get("info", 0),
        "warning_count": counts.get("warning", 0),
        "error_count": counts.get("error", 0),
        "critical_count": counts.get("critical", 0),
        "trace_count": counts.get("trace", 0),
        "analysis_counts": summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {},
        "library_counts": summary.get("library_counts") if isinstance(summary.get("library_counts"), dict) else {},
        "maintenance_summary": summary.get("maintenance_summary") if isinstance(summary.get("maintenance_summary"), dict) else {},
        "maintenance_had_pause": bool((summary.get("maintenance_summary") or {}).get("had_pause")),
        "quiet_period_summary": summary.get("quiet_period_summary") if isinstance(summary.get("quiet_period_summary"), dict) else {},
        "quickstart_run_marker": bool(summary.get("quickstart_run_marker")),
        "start_mode": summary.get("start_mode"),
        "config_line_count": summary.get("config_line_count"),
        "cache_line_count": summary.get("cache_line_count"),
        "created_at": created_at,
        "run_complete": False,
        "is_incomplete": True,
        "incomplete_log_name": Path(log_path).name,
        "incomplete_log_path": str(Path(log_path)),
        "phase_current": phase_current,
        "current_library": current_library,
        "current_collection": current_collection,
        "resume_reason": reason,
        "resume_primary": primary,
        "resume_recommendations": suggestions,
        "resume_explanation": explanation,
        "resume_scope_completed": scope_completed,
        "resume_timing_summary": timing_summary,
        "resume_scope_summary": scope_summary,
        "resume_progress_snapshot": progress_snapshot,
        "resume_maintenance_events": maintenance_events,
    }


def build_incomplete_run_from_cache_entry(log_path, cache_entry=None, config_name=None):
    path = Path(log_path)
    cache_entry = cache_entry if isinstance(cache_entry, dict) else {}
    summary = cache_entry.get("summary") if isinstance(cache_entry.get("summary"), dict) else {}
    tool_name = normalize_logscan_tool_name(summary.get("tool_name") or cache_entry.get("tool_name"))
    recommendations = cache_entry.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    try:
        stats = path.stat()
        mtime = stats.st_mtime
        size = stats.st_size
    except Exception:
        mtime = cache_entry.get("mtime") if isinstance(cache_entry.get("mtime"), (int, float)) else None
        size = cache_entry.get("size") if isinstance(cache_entry.get("size"), int) else None
    counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    run_key = summary.get("run_key") or cache_entry.get("run_key")
    if not run_key:
        run_key_seed = f"incomplete|cached|{path}|{mtime or 0}|{size or 0}"
        run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()
    created_at = summary.get("created_at")
    if not created_at:
        created_at = cache_entry.get("updated_at") or iso_from_mtime(mtime)
    started_at = summary.get("started_at")
    if not started_at:
        try:
            started_at = extract_first_log_timestamp(_read_logscan_text(path, encoding="utf-8", errors="replace"))
        except Exception:
            started_at = None
    original_command = summary.get("run_command") or ""
    if tool_name == "kometa":
        original_command = inject_config_path_for_command(
            original_command,
            config_name=summary.get("config_name") or config_name,
        )
    progress_snapshot = summary.get("progress_snapshot") if isinstance(summary.get("progress_snapshot"), dict) else {}
    if not progress_snapshot:
        progress_snapshot = cache_entry.get("resume_progress_snapshot") if isinstance(cache_entry.get("resume_progress_snapshot"), dict) else {}
    return {
        "run_key": run_key,
        "tool_name": tool_name,
        "started_at": started_at,
        "finished_at": summary.get("finished_at"),
        "run_time_seconds": summary.get("run_time_seconds"),
        "kometa_version": summary.get("kometa_version"),
        "kometa_newest_version": summary.get("kometa_newest_version"),
        "config_name": summary.get("config_name") or config_name or "",
        "config_hash": summary.get("config_hash"),
        "run_command": original_command,
        "command_signature": summary.get("command_signature"),
        "section_runtimes": summary.get("section_runtimes") or {},
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
        "log_mtime": mtime,
        "log_size": summary.get("log_size") if isinstance(summary.get("log_size"), int) else size,
        "debug_count": counts.get("debug", 0),
        "info_count": counts.get("info", 0),
        "warning_count": counts.get("warning", 0),
        "error_count": counts.get("error", 0),
        "critical_count": counts.get("critical", 0),
        "trace_count": counts.get("trace", 0),
        "analysis_counts": summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {},
        "library_counts": summary.get("library_counts") if isinstance(summary.get("library_counts"), dict) else {},
        "maintenance_summary": summary.get("maintenance_summary") if isinstance(summary.get("maintenance_summary"), dict) else {},
        "maintenance_had_pause": bool((summary.get("maintenance_summary") or {}).get("had_pause")),
        "quiet_period_summary": summary.get("quiet_period_summary") if isinstance(summary.get("quiet_period_summary"), dict) else {},
        "quickstart_run_marker": bool(summary.get("quickstart_run_marker")),
        "start_mode": summary.get("start_mode") or cache_entry.get("start_mode"),
        "config_line_count": summary.get("config_line_count"),
        "cache_line_count": summary.get("cache_line_count"),
        "created_at": created_at,
        "run_complete": False,
        "is_incomplete": True,
        "incomplete_log_name": path.name,
        "incomplete_log_path": str(path),
        "phase_current": cache_entry.get("phase_current"),
        "current_library": cache_entry.get("current_library"),
        "current_collection": cache_entry.get("current_collection"),
        "progress_snapshot": progress_snapshot,
        "resume_progress_snapshot": (progress_snapshot if isinstance(progress_snapshot, dict) else {}),
        "resume_reason": cache_entry.get("resume_reason") or "Run appears incomplete. Open the report for more detail or download the log for investigation.",
        "resume_primary": cache_entry.get("resume_primary") or "",
        "resume_recommendations": cache_entry.get("resume_recommendations") if isinstance(cache_entry.get("resume_recommendations"), list) else [],
        "resume_explanation": cache_entry.get("resume_explanation") if isinstance(cache_entry.get("resume_explanation"), list) else [],
    }


def build_incomplete_resume_cache_fields(log_path, cache_entry=None, config_name=None):
    import quickstart

    cache_entry = cache_entry if isinstance(cache_entry, dict) else {}
    parsed = quickstart._analyze_incomplete_log_for_resume(log_path, cache_entry=cache_entry, config_name=config_name)
    if not isinstance(parsed, dict):
        return {}
    fields = {}
    for key in (
        "phase_current",
        "current_library",
        "current_collection",
        "resume_reason",
        "resume_primary",
        "resume_recommendations",
        "resume_explanation",
        "resume_progress_snapshot",
        "resume_scope_completed",
        "resume_timing_summary",
        "resume_scope_summary",
        "resume_maintenance_events",
    ):
        value = parsed.get(key)
        if value is None:
            continue
        fields[key] = value
    return fields


def build_incomplete_log_fallback(log_path, cache_entry=None, config_name=None):
    path = Path(log_path)
    cache_entry = cache_entry if isinstance(cache_entry, dict) else {}
    tool_name = normalize_logscan_tool_name(cache_entry.get("tool_name"))
    try:
        stats = path.stat()
        mtime = stats.st_mtime
        size = stats.st_size
    except Exception:
        mtime = cache_entry.get("mtime") if isinstance(cache_entry.get("mtime"), (int, float)) else None
        size = cache_entry.get("size") if isinstance(cache_entry.get("size"), int) else None
    run_key = cache_entry.get("run_key")
    if not run_key:
        run_key_seed = f"incomplete|fallback|{path}|{mtime or 0}|{size or 0}"
        run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()
    created_at = cache_entry.get("updated_at") or iso_from_mtime(mtime)
    try:
        started_at = extract_first_log_timestamp(_read_logscan_text(path, encoding="utf-8", errors="replace"))
    except Exception:
        started_at = None
    return {
        "run_key": run_key,
        "tool_name": tool_name,
        "started_at": started_at,
        "finished_at": None,
        "run_time_seconds": None,
        "kometa_version": "",
        "kometa_newest_version": "",
        "config_name": config_name or "",
        "config_hash": None,
        "run_command": "",
        "command_signature": "",
        "section_runtimes": {},
        "recommendations_count": 0,
        "recommendations": [],
        "log_mtime": mtime,
        "log_size": size,
        "debug_count": 0,
        "info_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "critical_count": 0,
        "trace_count": 0,
        "analysis_counts": {},
        "library_counts": {},
        "maintenance_summary": {},
        "maintenance_had_pause": False,
        "quiet_period_summary": {},
        "quickstart_run_marker": False,
        "start_mode": cache_entry.get("start_mode"),
        "config_line_count": None,
        "cache_line_count": None,
        "created_at": created_at,
        "run_complete": False,
        "is_incomplete": True,
        "incomplete_log_name": path.name,
        "incomplete_log_path": str(path),
        "phase_current": None,
        "current_library": None,
        "current_collection": None,
        "resume_reason": "Run appears incomplete. Detailed parse data is not available, but the log is preserved for investigation.",
        "resume_primary": "",
        "resume_recommendations": [],
        "resume_explanation": ["Quickstart preserved this incomplete log file even though detailed parsing was unavailable."],
    }


def get_logscan_incomplete_runs(limit=100, config_name=None):
    import quickstart

    if limit is None:
        safe_limit = None
    else:
        safe_limit = max(0, min(int(limit or 0), 1000000))
    if safe_limit == 0:
        return []
    ingest_cache = quickstart._load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return []

    candidates = []
    for path_key, entry in cache_logs.items():
        if not isinstance(entry, dict) or entry.get("run_complete") is True:
            continue
        try:
            path = Path(path_key).resolve()
        except Exception:
            continue
        if not path.exists() or not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = entry.get("mtime") if isinstance(entry.get("mtime"), (int, float)) else 0
        candidates.append((float(mtime or 0), path, entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    parsed_runs = []
    selected_candidates = candidates if safe_limit is None else candidates[:safe_limit]
    for _, path, entry in selected_candidates:
        if isinstance(entry.get("summary"), dict):
            parsed = build_incomplete_run_from_cache_entry(path, cache_entry=entry, config_name=config_name)
        else:
            parsed = build_incomplete_log_fallback(path, cache_entry=entry, config_name=config_name)
        if parsed:
            parsed_runs.append(parsed)
    return parsed_runs


def get_logscan_incomplete_run(run_key, config_name=None):
    import quickstart

    if not run_key:
        return None
    ingest_cache = quickstart._load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return None
    for path_key, entry in cache_logs.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("run_complete") is True:
            continue
        if entry.get("run_key") != run_key:
            continue
        path = Path(path_key)
        if not path.exists() or not path.is_file():
            return None
        if isinstance(entry.get("summary"), dict):
            return build_incomplete_run_from_cache_entry(path, cache_entry=entry, config_name=config_name)
        if normalize_logscan_tool_name(entry.get("tool_name")) != "kometa":
            return build_incomplete_log_fallback(path, cache_entry=entry, config_name=config_name)
        parsed = analyze_incomplete_log_for_resume(path, cache_entry=entry, config_name=config_name)
        if parsed:
            return parsed
        return build_incomplete_log_fallback(path, cache_entry=entry, config_name=config_name)
    return None


def get_incomplete_resume_runs(limit=25, config_name=None):
    import quickstart

    safe_limit = max(0, min(int(limit or 0), 100))
    if safe_limit == 0:
        return []
    ingest_cache = quickstart._load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    if not isinstance(cache_logs, dict):
        return []

    is_running = helpers.is_kometa_running()
    candidates = []
    for path_key, entry in cache_logs.items():
        if not isinstance(entry, dict):
            continue
        if normalize_logscan_tool_name(entry.get("tool_name")) != "kometa":
            continue
        try:
            path = Path(path_key).resolve()
        except Exception:
            continue
        if not path.exists() or not path.is_file():
            continue
        if is_running and path.name.lower() == "meta.log":
            continue
        # Prefer ingest-cache mtime to preserve analyzed-run ordering; live
        # meta.log is refreshed separately below when Kometa is not running.
        mtime = entry.get("mtime")
        if not isinstance(mtime, (int, float)):
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0
        candidates.append((float(mtime), path, entry))

    try:
        live_meta = (helpers.get_kometa_log_dir() / "meta.log").resolve()
    except Exception:
        live_meta = None
    if live_meta and live_meta.exists() and live_meta.is_file():
        if not is_running:
            try:
                live_mtime = live_meta.stat().st_mtime
            except Exception:
                live_mtime = 0
            # Replace any cached candidate for live meta with a fresh mtime candidate.
            candidates = [item for item in candidates if item[1] != live_meta]
            live_entry = cache_logs.get(str(live_meta), {}) if isinstance(cache_logs, dict) else {}
            if not isinstance(live_entry, dict):
                live_entry = {}
            if not isinstance(live_entry.get("mtime"), (int, float)):
                live_entry["mtime"] = live_mtime
            live_entry.setdefault("run_complete", False)
            candidates.append((float(live_mtime), live_meta, live_entry))

    candidates.sort(key=lambda item: item[0], reverse=True)
    if not candidates:
        return []

    # Only evaluate the latest run candidate. Older incomplete logs may no longer
    # be actionable once a newer run has completed.
    _, path, entry = candidates[0]
    parsed = quickstart._analyze_incomplete_log_for_resume(path, cache_entry=entry, config_name=config_name)
    if not parsed:
        return []
    return [parsed]


def build_latest_incomplete_resume_hint():
    import quickstart

    incomplete_runs = quickstart._get_incomplete_resume_runs(limit=1, config_name=session.get("config_name"))
    if not incomplete_runs:
        return None
    latest = incomplete_runs[0]

    session_config = (session.get("config_name") or "default").strip()
    summary_config = (latest.get("config_name") or "").strip()
    context_mismatch = bool(summary_config and session_config and summary_config != session_config)

    return {
        "message": latest.get("resume_reason") or "Last run appears incomplete.",
        "phase_current": latest.get("phase_current"),
        "current_library": latest.get("current_library"),
        "current_collection": latest.get("current_collection"),
        "original_command": latest.get("run_command") or "",
        "suggested_command": latest.get("resume_primary") or "",
        "log_name": latest.get("incomplete_log_name") or "",
        "log_path": latest.get("incomplete_log_path") or "",
        "config_name": summary_config,
        "context_mismatch": context_mismatch,
        "explanation": latest.get("resume_explanation") if isinstance(latest.get("resume_explanation"), list) else [],
        "scope_completed": bool(latest.get("resume_scope_completed")),
        "timing_summary": latest.get("resume_timing_summary") if isinstance(latest.get("resume_timing_summary"), dict) else {},
        "scope_summary": latest.get("resume_scope_summary") if isinstance(latest.get("resume_scope_summary"), dict) else {},
        "progress_snapshot": latest.get("resume_progress_snapshot") if isinstance(latest.get("resume_progress_snapshot"), dict) else {},
        "maintenance_events": latest.get("resume_maintenance_events") if isinstance(latest.get("resume_maintenance_events"), list) else [],
    }
