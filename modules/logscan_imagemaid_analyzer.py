"""Imagemaid log-content analyzer.

Extracted from :mod:`modules.logscan_imagemaid_analysis` to isolate
the 468-line ``analyze_imagemaid_log_content`` parser.

Scans a full imagemaid run log line-by-line, tracking Quickstart
run markers, runtime timings, per-operation state (photo scan,
photo remove, restore scan, restore action, empty trash, clean
bundles, optimize db), and error/critical log-level counts.

Returns a ``{"summary": {...}, "recommendations": [...]}`` dict
consumed by:

* the ``/logscan/analyze`` HTTP endpoint,
* :func:`modules.logscan_imagemaid_progress.build_imagemaid_progress_snapshot`
  for the live-progress UI,
* the reingest / trends pipeline in ``quickstart.py``.

Kept as a single public function to preserve the existing call
surface; the smaller parsing helpers it uses still live in
:mod:`modules.logscan_imagemaid_analysis` and are imported below.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from modules import helpers
from modules.logscan_imagemaid_analysis import (
    build_imagemaid_recommendations,
    extract_imagemaid_error_lines,
    infer_imagemaid_config_name,
    parse_imagemaid_bytes,
    parse_imagemaid_command_snapshot,
    parse_imagemaid_runtime_seconds,
)
from modules.logscan_imagemaid_progress import build_imagemaid_progress_snapshot
from modules.logscan_resume import iso_from_mtime


def analyze_imagemaid_log_content(content, log_path=None):
    if not content:
        return None
    path = Path(log_path) if log_path else None
    try:
        stats = path.stat() if path and path.exists() else None
    except Exception:
        stats = None
    lines = content.splitlines()
    run_marker_pattern = re.compile(
        r"\[Quickstart\]\s+Run marker:\s+started=([^\s]+)\s+config=([^\s]+).*?\btool=imagemaid\b(?:\s+mode=([^\s]+))?",
        re.IGNORECASE,
    )
    stop_pattern = re.compile(
        r"\[Quickstart\]\s+Run event:\s+event=stopped\s+at=([^\s]+)\s+config=([^\s]+).*?\btool=imagemaid\b(?:\s+mode=([^\s]+))?(?:\s+reason=([^\s]+))?",
        re.IGNORECASE,
    )
    blocked_pattern = re.compile(
        r"\[Quickstart\]\s+Maintenance marker:\s+event=blocked_start\s+at=([^\s]+)\s+local_at=[^\s]+\s+config=([^\s]+).*?\btool=imagemaid\b(?:\s+mode=([^\s]+))?.*?(?:\s+window=([^\s]+))?",
        re.IGNORECASE,
    )
    timestamp_pattern = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),")
    total_runtime_pattern = re.compile(r"\|\s*Total Runtime\s*\|\s*(.*?)\s*\|?$", re.IGNORECASE)
    summary_header_pattern = re.compile(r"\|\s*=+\s*(.*?)\s*=+\s*\|?$")
    summary_runtime_row_pattern = re.compile(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|?$")

    started_at = None
    config_name = ""
    mode = ""
    stop_at = None
    stop_reason = ""
    blocked_at = None
    blocked_window = ""
    first_timestamp = None
    finished_at = None
    finished_seen = False
    run_time_seconds = None
    cache_count = 0
    debug_count = 0
    info_count = 0
    warning_count = 0
    error_count = 0
    critical_count = 0
    trace_count = 0
    quickstart_run_marker = False
    local_version = ""
    run_command_text = ""
    photo_scan_runtime = None
    photo_remove_runtime = None
    photo_found_files = 0
    photo_removed_files = 0
    photo_recovered_bytes = 0
    restore_scan_runtime = None
    restore_action_runtime = None
    restore_found_files = 0
    restore_removed_files = 0
    restore_recovered_bytes = 0
    generic_error_lines = []
    database_downloaded_new = False
    database_download_failed = False
    database_section_seen = False
    photo_transcoder_enabled = False
    empty_trash_enabled = False
    clean_bundles_enabled = False
    optimize_db_enabled = False
    local_db_enabled = False
    use_existing_enabled = False
    no_verify_ssl_enabled = False
    overlays_only_enabled = False
    current_runtime_section = ""
    summary_section = ""
    summary_section_runtimes = {}
    operation_started = {
        "empty_trash": False,
        "clean_bundles": False,
        "optimize_db": False,
    }

    for line in lines:
        timestamp_match = timestamp_pattern.search(line)
        if timestamp_match and not first_timestamp:
            first_timestamp = timestamp_match.group(1)
        if "[CACHE]" in line:
            cache_count += 1
        if "[DEBUG]" in line:
            debug_count += 1
        if "[INFO]" in line:
            info_count += 1
        if "[WARNING]" in line:
            warning_count += 1
        if "[ERROR]" in line:
            error_count += 1
        if "[CRITICAL]" in line:
            critical_count += 1
        if "Traceback" in line:
            trace_count += 1
        stripped_line = line.strip().strip("|").strip()
        if stripped_line and "Error:" in stripped_line and stripped_line not in generic_error_lines:
            generic_error_lines.append(stripped_line)

        if not quickstart_run_marker:
            marker_match = run_marker_pattern.search(line)
            if marker_match:
                started_at = marker_match.group(1)
                config_name = marker_match.group(2) or config_name
                mode = marker_match.group(3) or mode
                quickstart_run_marker = True

        stop_match = stop_pattern.search(line)
        if stop_match:
            stop_at = stop_match.group(1)
            config_name = stop_match.group(2) or config_name
            mode = stop_match.group(3) or mode
            stop_reason = stop_match.group(4) or stop_reason or "user_stop"

        blocked_match = blocked_pattern.search(line)
        if blocked_match:
            blocked_at = blocked_match.group(1)
            config_name = blocked_match.group(2) or config_name
            mode = blocked_match.group(3) or mode
            blocked_window = blocked_match.group(4) or blocked_window

        if "ImageMaid Finished" in line:
            finished_seen = True
            if timestamp_match:
                finished_at = timestamp_match.group(1)

        summary_header_match = summary_header_pattern.search(line)
        if summary_header_match:
            header_text = str(summary_header_match.group(1) or "").strip().lower()
            if header_text in {
                "database",
                "reporting bloat images",
                "remove phototranscoder images",
                "remove imagemaid restore bloat images",
                "empty trash plex operation",
                "clean bundles plex operation",
                "optimize db plex operation",
                "imagemaid summary",
            }:
                summary_section = header_text

        summary_runtime_match = summary_runtime_row_pattern.search(line)
        if summary_runtime_match:
            summary_label = str(summary_runtime_match.group(1) or "").strip().lower()
            parsed_summary_runtime = parse_imagemaid_runtime_seconds(summary_runtime_match.group(2))
            if parsed_summary_runtime is not None:
                if summary_section == "database":
                    if summary_label == "downloaded":
                        summary_section_runtimes["database_download"] = parsed_summary_runtime
                    elif summary_label == "query":
                        summary_section_runtimes["database_query"] = parsed_summary_runtime
                elif summary_section == "reporting bloat images":
                    if summary_label == "scan time":
                        summary_section_runtimes["report_bloat_scan"] = parsed_summary_runtime
                    elif summary_label == "report time":
                        summary_section_runtimes["report_bloat_action"] = parsed_summary_runtime
                elif summary_section == "remove phototranscoder images":
                    if summary_label == "scan time":
                        summary_section_runtimes["photo_transcoder_scan"] = parsed_summary_runtime
                    elif summary_label == "remove time":
                        summary_section_runtimes["photo_transcoder_remove"] = parsed_summary_runtime
                elif summary_section == "remove imagemaid restore bloat images":
                    if summary_label == "scan time":
                        summary_section_runtimes["restore_dir_scan"] = parsed_summary_runtime
                    elif summary_label == "remove time":
                        summary_section_runtimes["restore_dir_action"] = parsed_summary_runtime
                elif summary_section == "empty trash plex operation" and summary_label == "runtime":
                    summary_section_runtimes["empty_trash_action"] = parsed_summary_runtime
                elif summary_section == "clean bundles plex operation" and summary_label == "runtime":
                    summary_section_runtimes["clean_bundles_action"] = parsed_summary_runtime
                elif summary_section == "optimize db plex operation" and summary_label == "runtime":
                    summary_section_runtimes["optimize_db_action"] = parsed_summary_runtime

        runtime_match = total_runtime_pattern.search(line)
        if runtime_match:
            parsed_runtime = parse_imagemaid_runtime_seconds(runtime_match.group(1))
            if parsed_runtime is not None:
                run_time_seconds = parsed_runtime

        if not mode and "Running in " in line and " Mode" in line:
            mode_match = re.search(r"Running in\s+([A-Za-z]+)\s+Mode", line, re.IGNORECASE)
            if mode_match:
                mode = (mode_match.group(1) or "").strip().lower()

        version_match = re.search(r"\|\s*Version:\s*([^\s|]+)", line, re.IGNORECASE)
        if version_match and not local_version:
            local_version = str(version_match.group(1) or "").strip()

        command_match = re.search(r"\|\s*Run Command:\s*(.*?)\s*\|?$", line, re.IGNORECASE)
        if command_match and not run_command_text:
            run_command_text = str(command_match.group(1) or "").strip()

        if "Downloading Database via the Plex API" in line:
            database_section_seen = True
            current_runtime_section = "database_download"
        if "Downloaded New Database" in line:
            database_downloaded_new = True
        if "Database File Could not Downloaded" in line:
            database_download_failed = True
        if "Database Opened Querying For In-Use Images" in line or "Querying For In-Use Images" in line:
            current_runtime_section = "database_query"

        if "PhotoTranscoder set to True" in line:
            photo_transcoder_enabled = True

        if "Empty Trash Plex Operation Started" in line:
            operation_started["empty_trash"] = True
            empty_trash_enabled = True
        if "Clean Bundles Plex Operation Started" in line:
            operation_started["clean_bundles"] = True
            clean_bundles_enabled = True
        if "Optimize DB Plex Operation Started" in line:
            operation_started["optimize_db"] = True
            optimize_db_enabled = True

        if "Scanning ImageMaid Restore for Bloat Images to Remove" in line:
            current_runtime_section = "restore_scan"
        elif "Removing ImageMaid Restore Bloat Images" in line or ("Removing Complete:" in line and "ImageMaid Restore Bloat Images" in line):
            current_runtime_section = "restore_action"
        elif "Scanning Metadata Directory For Bloat Images" in line:
            current_runtime_section = "report_bloat_scan"
        elif "Reporting Bloat Images" in line or ("Reporting Complete:" in line and "Bloat Images" in line):
            current_runtime_section = "report_bloat_action"
        elif "Scanning for PhotoTranscoder Images" in line or ("Scanning Complete:" in line and "PhotoTranscoder Images" in line):
            current_runtime_section = "photo_scan"
        elif "Removing PhotoTranscoder Images" in line or ("Remove Complete:" in line and "PhotoTranscoder Images" in line):
            current_runtime_section = "photo_remove"
        elif "Empty Trash Plex Operation Started" in line:
            current_runtime_section = "empty_trash_action"
        elif "Clean Bundles Plex Operation Started" in line:
            current_runtime_section = "clean_bundles_action"
        elif "Optimize DB Plex Operation Started" in line:
            current_runtime_section = "optimize_db_action"

        restore_found_match = re.search(
            r"Found\s+(\d+)\s+Bloat Images in the ImageMaid Directory to Remove",
            line,
            re.IGNORECASE,
        )
        if restore_found_match:
            try:
                restore_found_files = int(restore_found_match.group(1))
            except (TypeError, ValueError):
                pass
        restore_removed_match = re.search(
            r"Removed\s+(\d+)\s+ImageMaid Restore Bloat Images",
            line,
            re.IGNORECASE,
        )
        if restore_removed_match:
            try:
                restore_removed_files = int(restore_removed_match.group(1))
            except (TypeError, ValueError):
                pass
        found_match = re.search(r"Found\s+(\d+)\s+PhotoTranscoder Images to Remove", line, re.IGNORECASE)
        if found_match:
            try:
                photo_found_files = int(found_match.group(1))
            except (TypeError, ValueError):
                pass
        removed_match = re.search(r"Removed\s+(\d+)\s+PhotoTranscoder Images", line, re.IGNORECASE)
        if removed_match:
            try:
                photo_removed_files = int(removed_match.group(1))
            except (TypeError, ValueError):
                pass
        bytes_match = re.search(r"Space Recovered:\s*(.*?)\s*\|?$", line, re.IGNORECASE)
        if bytes_match:
            parsed_bytes = parse_imagemaid_bytes(bytes_match.group(1))
            if parsed_bytes is not None:
                if current_runtime_section in {"restore_scan", "restore_action"}:
                    restore_recovered_bytes = parsed_bytes
                elif current_runtime_section in {"photo_scan", "photo_remove"}:
                    photo_recovered_bytes = parsed_bytes
        runtime_line_match = re.search(r"\|\s*Runtime:\s*(.*?)\s*\|?$", line, re.IGNORECASE)
        if runtime_line_match:
            parsed_runtime = parse_imagemaid_runtime_seconds(runtime_line_match.group(1))
            if parsed_runtime is not None:
                if current_runtime_section == "database_download":
                    summary_section_runtimes.setdefault("database_download", parsed_runtime)
                elif current_runtime_section == "database_query":
                    summary_section_runtimes.setdefault("database_query", parsed_runtime)
                elif current_runtime_section == "restore_scan":
                    restore_scan_runtime = parsed_runtime
                elif current_runtime_section == "restore_action":
                    restore_action_runtime = parsed_runtime
                elif current_runtime_section == "report_bloat_scan":
                    summary_section_runtimes.setdefault("report_bloat_scan", parsed_runtime)
                elif current_runtime_section == "report_bloat_action":
                    summary_section_runtimes.setdefault("report_bloat_action", parsed_runtime)
                elif current_runtime_section == "photo_scan":
                    photo_scan_runtime = parsed_runtime
                elif current_runtime_section == "photo_remove":
                    photo_remove_runtime = parsed_runtime
                elif current_runtime_section == "empty_trash_action":
                    summary_section_runtimes.setdefault("empty_trash_action", parsed_runtime)
                elif current_runtime_section == "clean_bundles_action":
                    summary_section_runtimes.setdefault("clean_bundles_action", parsed_runtime)
                elif current_runtime_section == "optimize_db_action":
                    summary_section_runtimes.setdefault("optimize_db_action", parsed_runtime)

    if finished_seen and not finished_at:
        finished_at = iso_from_mtime(stats.st_mtime if stats else None)

    if not started_at and first_timestamp:
        started_at = first_timestamp

    if not config_name:
        inferred_config_name = infer_imagemaid_config_name(mode=mode, run_command_text=run_command_text)
        if inferred_config_name:
            config_name = inferred_config_name

    completion_reason = "completed"
    run_complete = bool(finished_at and run_time_seconds is not None)
    if not run_complete:
        if stop_at:
            completion_reason = stop_reason or "user_stop"
            finished_at = finished_at or stop_at
        elif blocked_at:
            completion_reason = "maintenance_blocked_start"
            finished_at = finished_at or blocked_at
        else:
            completion_reason = "unknown_incomplete"

    maintenance_events = []
    if blocked_at:
        maintenance_events.append(
            {
                "event": "blocked_start",
                "at": blocked_at,
                "local_at": "",
                "window": blocked_window or "",
                "paused_seconds": None,
            }
        )
    maintenance_summary = {
        "had_pause": False,
        "pause_count": 0,
        "pause_seconds": 0,
        "open_pause": False,
        "window": blocked_window or "",
        "events": maintenance_events,
    }
    error_lines = extract_imagemaid_error_lines(lines)
    if generic_error_lines:
        for item in generic_error_lines:
            if item not in error_lines:
                error_lines.append(item)
    if error_lines and error_count == 0:
        error_count = len(error_lines)
    if run_complete and (error_count > 0 or error_lines):
        completion_reason = "completed_with_errors"
    mode = (mode or "report").strip().lower() or "report"
    config_name = str(config_name or "").strip() or "unknown"
    command_signature = f"--mode {mode}"
    run_command = run_command_text or f"imagemaid {command_signature}"
    command_snapshot = parse_imagemaid_command_snapshot(run_command_text, fallback_mode=mode)
    photo_transcoder_enabled = bool(photo_transcoder_enabled or command_snapshot.get("photo_transcoder"))
    empty_trash_enabled = bool(empty_trash_enabled or command_snapshot.get("empty_trash"))
    clean_bundles_enabled = bool(clean_bundles_enabled or command_snapshot.get("clean_bundles"))
    optimize_db_enabled = bool(optimize_db_enabled or command_snapshot.get("optimize_db"))
    local_db_enabled = bool(local_db_enabled or command_snapshot.get("local_db"))
    use_existing_enabled = bool(use_existing_enabled or command_snapshot.get("use_existing"))
    no_verify_ssl_enabled = bool(no_verify_ssl_enabled or command_snapshot.get("no_verify_ssl"))
    overlays_only_enabled = bool(overlays_only_enabled or command_snapshot.get("overlays_only"))
    timestamp_seed = started_at or finished_at or (stats.st_mtime if stats else 0)
    run_key_seed = f"imagemaid|{timestamp_seed}|{mode}|{path.name if path else 'imagemaid.log'}"
    created_at = finished_at or started_at or iso_from_mtime(stats.st_mtime if stats else None)
    section_runtimes = {}
    if summary_section_runtimes.get("database_download") is not None:
        section_runtimes["database_download"] = summary_section_runtimes["database_download"]
    if summary_section_runtimes.get("database_query") is not None:
        section_runtimes["database_query"] = summary_section_runtimes["database_query"]
    if summary_section_runtimes.get("report_bloat_scan") is not None:
        section_runtimes["report_bloat_scan"] = summary_section_runtimes["report_bloat_scan"]
    if summary_section_runtimes.get("report_bloat_action") is not None:
        section_runtimes["report_bloat_action"] = summary_section_runtimes["report_bloat_action"]
    if restore_scan_runtime is not None:
        section_runtimes["restore_dir_scan"] = restore_scan_runtime
    if restore_action_runtime is not None:
        section_runtimes["restore_dir_action"] = restore_action_runtime
    if photo_scan_runtime is not None:
        section_runtimes["photo_transcoder_scan"] = photo_scan_runtime
    if photo_remove_runtime is not None:
        section_runtimes["photo_transcoder_remove"] = photo_remove_runtime
    if summary_section_runtimes.get("empty_trash_action") is not None:
        section_runtimes["empty_trash_action"] = summary_section_runtimes["empty_trash_action"]
    if summary_section_runtimes.get("clean_bundles_action") is not None:
        section_runtimes["clean_bundles_action"] = summary_section_runtimes["clean_bundles_action"]
    if summary_section_runtimes.get("optimize_db_action") is not None:
        section_runtimes["optimize_db_action"] = summary_section_runtimes["optimize_db_action"]
    total_found_files = restore_found_files + photo_found_files
    total_removed_files = restore_removed_files + photo_removed_files
    total_recovered_bytes = restore_recovered_bytes + photo_recovered_bytes
    analysis_counts = {
        "imagemaid_error_lines": len(error_lines),
        "imagemaid_database_seen": int(database_section_seen),
        "imagemaid_database_downloaded_new": int(database_downloaded_new),
        "imagemaid_database_download_failed": int(database_download_failed),
        "imagemaid_restore_found_files": restore_found_files,
        "imagemaid_restore_removed_files": restore_removed_files,
        "imagemaid_restore_recovered_bytes": restore_recovered_bytes,
        "imagemaid_photo_found_files": photo_found_files,
        "imagemaid_photo_removed_files": photo_removed_files,
        "imagemaid_photo_recovered_bytes": photo_recovered_bytes,
        "imagemaid_total_found_files": total_found_files,
        "imagemaid_total_removed_files": total_removed_files,
        "imagemaid_total_recovered_bytes": total_recovered_bytes,
        "imagemaid_empty_trash_enabled": int(empty_trash_enabled),
        "imagemaid_clean_bundles_enabled": int(clean_bundles_enabled),
        "imagemaid_optimize_db_enabled": int(optimize_db_enabled),
        "imagemaid_photo_transcoder_enabled": int(photo_transcoder_enabled),
        "imagemaid_local_db_enabled": int(local_db_enabled),
        "imagemaid_use_existing_enabled": int(use_existing_enabled),
        "imagemaid_no_verify_ssl_enabled": int(no_verify_ssl_enabled),
        "imagemaid_overlays_only_enabled": int(overlays_only_enabled),
        "imagemaid_empty_trash_started": int(operation_started["empty_trash"]),
        "imagemaid_clean_bundles_started": int(operation_started["clean_bundles"]),
        "imagemaid_optimize_db_started": int(operation_started["optimize_db"]),
        "imagemaid_enabled_operation_count": int(database_section_seen)
        + int(photo_transcoder_enabled)
        + int(empty_trash_enabled)
        + int(clean_bundles_enabled)
        + int(optimize_db_enabled),
        "imagemaid_completed_with_errors": int(completion_reason == "completed_with_errors"),
    }
    summary = {
        "run_key": hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest(),
        "tool_name": "imagemaid",
        "started_at": started_at,
        "finished_at": finished_at,
        "run_time_seconds": run_time_seconds,
        "kometa_version": local_version or helpers.get_imagemaid_local_version() or "",
        "kometa_newest_version": "",
        "config_name": config_name,
        "config_hash": None,
        "run_command": run_command,
        "command_signature": command_signature,
        "section_runtimes": section_runtimes,
        "log_size": int(stats.st_size) if stats else None,
        "log_counts": {
            "cache": cache_count,
            "debug": debug_count,
            "info": info_count,
            "warning": warning_count,
            "error": error_count,
            "critical": critical_count,
            "trace": trace_count,
        },
        "analysis_counts": analysis_counts,
        "library_counts": {},
        "maintenance_summary": maintenance_summary,
        "maintenance_had_pause": False,
        "quiet_period_summary": {},
        "quickstart_run_marker": quickstart_run_marker,
        "config_line_count": None,
        "cache_line_count": cache_count,
        "created_at": created_at,
        "run_complete": run_complete,
        "completion_reason": completion_reason,
        "imagemaid_mode": mode,
    }
    summary["progress_snapshot"] = build_imagemaid_progress_snapshot(summary)
    recommendations = build_imagemaid_recommendations(summary, error_lines=error_lines, completion_reason=completion_reason)
    return {"summary": summary, "recommendations": recommendations}
