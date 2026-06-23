import gzip
import hashlib
import os
import re
import shlex
from pathlib import Path

from modules import database, helpers, logscan
from modules.logscan_resume import (
    format_compact_count_brief,
    format_duration_brief,
    format_imagemaid_bytes_brief,
    iso_from_mtime,
)

_is_logscan_gzip_path = helpers.is_logscan_gzip_path


def iter_logscan_text_lines(path, encoding="utf-8", errors="replace"):
    path = Path(path)
    if _is_logscan_gzip_path(path):
        with gzip.open(path, "rt", encoding=encoding, errors=errors) as handle:
            for line in handle:
                yield line
        return
    with path.open("r", encoding=encoding, errors=errors) as handle:
        for line in handle:
            yield line


def parse_imagemaid_runtime_seconds(runtime_text):
    text = str(runtime_text or "").strip()
    if not text:
        return None
    analyzer = logscan.LogscanAnalyzer()
    try:
        delta = analyzer._parse_run_time_from_line(f"Run Time: {text}")
    except Exception:
        delta = None
    if delta is None:
        return None
    return int(delta.total_seconds())


def extract_imagemaid_error_lines(lines):
    errors = []
    in_error_report = False
    for raw_line in lines:
        line = str(raw_line or "")
        if "Error Report" in line:
            in_error_report = True
            continue
        if in_error_report and "ImageMaid Summary" in line:
            break
        if not in_error_report:
            continue
        stripped = line.strip().strip("|").strip()
        if not stripped or stripped.startswith("="):
            continue
        if "Generic Errors:" in stripped:
            continue
        if "Error" not in stripped:
            continue
        errors.append(stripped)
    return errors


def parse_imagemaid_bytes(text):
    value = str(text or "").strip()
    if not value:
        return None
    match = re.match(r"^([\d.]+)\s*([A-Za-z]+)$", value, re.IGNORECASE)
    if match:
        try:
            number = float(match.group(1))
        except (TypeError, ValueError):
            return None
        unit = str(match.group(2) or "").strip().lower().rstrip("s")
        multipliers = {
            "byte": 1,
            "b": 1,
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
            "tb": 1024**4,
        }
        multiplier = multipliers.get(unit)
        if multiplier is None:
            return None
        try:
            return int(number * multiplier)
        except (TypeError, ValueError):
            return None
    return None


def normalize_imagemaid_snapshot_path(value):
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return ""
    try:
        return os.path.normcase(os.path.normpath(text))
    except Exception:
        return text.lower()


def parse_imagemaid_command_snapshot(run_command_text, fallback_mode=None):
    snapshot = {}
    mode = str(fallback_mode or "").strip().lower()
    if mode:
        snapshot["mode"] = mode

    command = str(run_command_text or "").strip()
    if not command:
        return snapshot

    try:
        parts = shlex.split(command, posix=False)
    except Exception:
        parts = command.split()

    flag_map = {
        "--photo-transcoder": "photo_transcoder",
        "--empty-trash": "empty_trash",
        "--clean-bundles": "clean_bundles",
        "--optimize-db": "optimize_db",
        "--local": "local_db",
        "--existing": "use_existing",
        "--ignore-running": "ignore_running",
        "--trace": "trace",
        "--log-requests": "log_requests",
        "--no-verify-ssl": "no_verify_ssl",
        "--overlays-only": "overlays_only",
    }
    value_map = {
        "--plex": "plex_path",
        "--mode": "mode",
        "--timeout": "timeout",
        "--sleep": "sleep",
    }

    idx = 0
    while idx < len(parts):
        part = str(parts[idx] or "").strip()
        if not part:
            idx += 1
            continue

        matched = False
        for flag, key in flag_map.items():
            if part == flag:
                snapshot[key] = True
                matched = True
                break
        if matched:
            idx += 1
            continue

        for flag, key in value_map.items():
            if part == flag and idx + 1 < len(parts):
                raw_value = str(parts[idx + 1] or "").strip()
                if key == "plex_path":
                    snapshot[key] = normalize_imagemaid_snapshot_path(raw_value)
                elif key in {"timeout", "sleep"}:
                    snapshot[key] = str(raw_value).strip()
                else:
                    snapshot[key] = str(raw_value).strip().lower()
                idx += 2
                matched = True
                break
            if part.startswith(f"{flag}="):
                raw_value = part.split("=", 1)[1].strip()
                if key == "plex_path":
                    snapshot[key] = normalize_imagemaid_snapshot_path(raw_value)
                elif key in {"timeout", "sleep"}:
                    snapshot[key] = str(raw_value).strip()
                else:
                    snapshot[key] = str(raw_value).strip().lower()
                idx += 1
                matched = True
                break
        if matched:
            continue

        idx += 1

    return snapshot


def build_imagemaid_section_snapshot(section_data):
    section = section_data if isinstance(section_data, dict) else {}
    snapshot = {}

    mode = str(section.get("mode") or "").strip().lower()
    if mode:
        snapshot["mode"] = mode

    plex_path = normalize_imagemaid_snapshot_path(section.get("plex_path"))
    if plex_path:
        snapshot["plex_path"] = plex_path

    for key in (
        "photo_transcoder",
        "empty_trash",
        "clean_bundles",
        "optimize_db",
        "local_db",
        "use_existing",
        "ignore_running",
        "trace",
        "log_requests",
        "no_verify_ssl",
        "overlays_only",
    ):
        snapshot[key] = helpers.booler(section.get(key))

    for key in ("timeout", "sleep"):
        value = section.get(key)
        if value not in [None, ""]:
            snapshot[key] = str(value).strip()

    return snapshot


def infer_imagemaid_config_name(mode=None, run_command_text=None):
    command_snapshot = parse_imagemaid_command_snapshot(run_command_text, fallback_mode=mode)
    relevant_keys = [key for key, value in command_snapshot.items() if value not in [None, ""]]
    discriminators = [key for key in relevant_keys if key != "mode"]
    if not discriminators:
        return None

    matches = []
    for config_name in database.get_unique_config_names() or []:
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(config_name, "imagemaid")
        except Exception:
            continue
        if not isinstance(stored, dict):
            continue
        section = stored.get("imagemaid") if isinstance(stored.get("imagemaid"), dict) else stored
        if not isinstance(section, dict) or not section:
            continue
        section_snapshot = build_imagemaid_section_snapshot(section)

        score = 0
        matched = True
        for key in relevant_keys:
            expected = command_snapshot.get(key)
            actual = section_snapshot.get(key)
            if actual != expected:
                matched = False
                break
            score += 5 if key == "plex_path" else 1
        if matched:
            matches.append((score, str(config_name)))

    if not matches:
        return None
    matches.sort(key=lambda item: (-item[0], item[1]))
    if len(matches) == 1:
        return matches[0][1]
    if matches[0][0] > matches[1][0]:
        return matches[0][1]
    return None


def resolve_imagemaid_run_config_name(run_record):
    if not isinstance(run_record, dict):
        return "unknown"
    tool_name = str(run_record.get("tool_name") or "").strip().lower()
    config_name = str(run_record.get("config_name") or "").strip()
    if tool_name != "imagemaid":
        return config_name
    if config_name and config_name.lower() not in {"imagemaid", "unknown"}:
        return config_name
    inferred = infer_imagemaid_config_name(
        mode=run_record.get("imagemaid_mode"),
        run_command_text=run_record.get("run_command"),
    )
    return inferred or "unknown"


def build_imagemaid_recommendations(summary, error_lines=None, completion_reason=None):
    recommendations = []
    completion_reason = str(completion_reason or "").strip().lower()
    if completion_reason == "user_stop":
        recommendations.append(
            {
                "first_line": "ImageMaid run stopped by user",
                "message": "Quickstart recorded an explicit stop request for this ImageMaid run.",
            }
        )
    elif completion_reason == "maintenance_blocked_start":
        window = ""
        maintenance_summary = summary.get("maintenance_summary") if isinstance(summary, dict) else {}
        if isinstance(maintenance_summary, dict):
            events = maintenance_summary.get("events")
            if isinstance(events, list) and events:
                window = str((events[0] or {}).get("window") or "").strip()
        suffix = f" during the Plex maintenance window ({window})" if window else " during the Plex maintenance window"
        recommendations.append(
            {
                "first_line": "ImageMaid start blocked by Plex maintenance",
                "message": f"Quickstart did not start ImageMaid{suffix}.",
            }
        )
    elif completion_reason and completion_reason != "completed":
        recommendations.append(
            {
                "first_line": "ImageMaid run appears incomplete",
                "message": f"Quickstart detected an incomplete ImageMaid run with reason: {completion_reason}.",
            }
        )
    if error_lines:
        recommendations.append(
            {
                "first_line": "ImageMaid reported errors",
                "message": "\n".join(error_lines[:8]),
            }
        )
    return recommendations


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


def build_imagemaid_progress_snapshot(summary=None):
    summary = summary if isinstance(summary, dict) else {}
    if str(summary.get("tool_name") or "").strip().lower() != "imagemaid":
        return {}

    analysis_counts = summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {}
    section_runtimes = summary.get("section_runtimes") if isinstance(summary.get("section_runtimes"), dict) else {}
    mode = str(summary.get("imagemaid_mode") or "report").strip().lower() or "report"
    run_complete = bool(summary.get("run_complete"))
    completion_reason = str(summary.get("completion_reason") or "").strip().lower()
    error_total = 0
    log_counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    for key in ("error", "critical", "trace"):
        if isinstance(log_counts.get(key), (int, float)):
            error_total += int(log_counts.get(key) or 0)
    if isinstance(analysis_counts.get("imagemaid_error_lines"), (int, float)):
        error_total = max(error_total, int(analysis_counts.get("imagemaid_error_lines") or 0))

    rows = []
    total_scan_seconds = 0
    total_action_seconds = 0

    def _runtime_cell(value):
        if not isinstance(value, (int, float)):
            return {}
        seconds = max(0, int(value))
        return {"label": format_duration_brief(seconds), "tone": "primary"}

    def _badge_cell(label, tone="success"):
        text = str(label or "").strip()
        return {"label": text, "tone": tone} if text else {}

    def _row_status(observed=False, enabled=False):
        if completion_reason == "maintenance_blocked_start":
            return "Blocked", " text-bg-warning"
        if observed:
            if run_complete:
                if error_total > 0:
                    return "Completed", " text-bg-warning"
                return "Completed", " text-bg-success"
            if completion_reason == "user_stop":
                return "Stopped", " text-bg-warning"
            return "Observed", " text-bg-primary"
        if enabled:
            if completion_reason == "maintenance_blocked_start":
                return "Blocked", " text-bg-warning"
            return "Pending", " text-bg-secondary"
        return "Skipped", " text-bg-secondary"

    def _append_row(name, row_type, scan_seconds=None, action_seconds=None, items_label="", outcome_label="", enabled=False, items_tone="success", outcome_tone="success"):
        nonlocal total_scan_seconds, total_action_seconds
        observed = any(
            [
                isinstance(scan_seconds, (int, float)),
                isinstance(action_seconds, (int, float)),
                bool(str(items_label or "").strip()),
                bool(str(outcome_label or "").strip()),
            ]
        )
        if not enabled and not observed:
            return
        if isinstance(scan_seconds, (int, float)):
            total_scan_seconds += max(0, int(scan_seconds))
        if isinstance(action_seconds, (int, float)):
            total_action_seconds += max(0, int(action_seconds))
        status, status_class = _row_status(observed=observed, enabled=enabled)
        rows.append(
            {
                "name": name,
                "type": row_type,
                "status": status,
                "status_class": status_class,
                "phase_cells": [
                    _runtime_cell(scan_seconds),
                    _runtime_cell(action_seconds),
                    _badge_cell(items_label, tone=items_tone),
                    _badge_cell(outcome_label, tone=outcome_tone),
                ],
            }
        )

    database_seen = bool(analysis_counts.get("imagemaid_database_seen"))
    local_db_enabled = bool(analysis_counts.get("imagemaid_local_db_enabled"))
    use_existing_enabled = bool(analysis_counts.get("imagemaid_use_existing_enabled"))
    database_downloaded_new = bool(analysis_counts.get("imagemaid_database_downloaded_new"))
    database_download_failed = bool(analysis_counts.get("imagemaid_database_download_failed"))
    database_enabled = database_seen or "database_download" in section_runtimes or "database_query" in section_runtimes
    database_items = ""
    if local_db_enabled:
        database_items = "Local DB"
    elif use_existing_enabled:
        database_items = "Existing DB"
    elif database_downloaded_new:
        database_items = "Downloaded"
    elif database_seen:
        database_items = "Plex API"
    database_outcome = "Failed" if database_download_failed else ("Ready" if database_enabled else "")
    _append_row(
        "Database Prep",
        "Source",
        scan_seconds=section_runtimes.get("database_download"),
        action_seconds=section_runtimes.get("database_query"),
        items_label=database_items,
        outcome_label=database_outcome,
        enabled=database_enabled,
        items_tone="secondary",
        outcome_tone="danger" if database_download_failed else "success",
    )

    report_enabled = mode == "report" or "report_bloat_scan" in section_runtimes or "report_bloat_action" in section_runtimes
    report_outcome = "Reported" if report_enabled and run_complete else ""
    _append_row(
        "Bloat Report",
        "Metadata",
        scan_seconds=section_runtimes.get("report_bloat_scan"),
        action_seconds=section_runtimes.get("report_bloat_action"),
        items_label="Mode report" if report_enabled else "",
        outcome_label=report_outcome,
        enabled=report_enabled,
        items_tone="secondary",
        outcome_tone="success",
    )

    restore_found = int(analysis_counts.get("imagemaid_restore_found_files") or 0) if isinstance(analysis_counts.get("imagemaid_restore_found_files"), (int, float)) else 0
    restore_removed = int(analysis_counts.get("imagemaid_restore_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_restore_removed_files"), (int, float)) else 0
    restore_recovered = (
        int(analysis_counts.get("imagemaid_restore_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_restore_recovered_bytes"), (int, float)) else 0
    )
    restore_enabled = mode in {"clear", "restore"} or "restore_dir_scan" in section_runtimes or "restore_dir_action" in section_runtimes or restore_found > 0 or restore_removed > 0
    restore_items = ""
    if restore_removed > 0:
        restore_items = f"Removed {format_compact_count_brief(restore_removed)}"
    elif restore_found > 0:
        restore_items = f"Found {format_compact_count_brief(restore_found)}"
    restore_outcome = format_imagemaid_bytes_brief(restore_recovered) if restore_recovered > 0 else ""
    _append_row(
        "Restore Cache",
        "File cleanup",
        scan_seconds=section_runtimes.get("restore_dir_scan"),
        action_seconds=section_runtimes.get("restore_dir_action"),
        items_label=restore_items,
        outcome_label=restore_outcome,
        enabled=restore_enabled,
        items_tone="primary",
        outcome_tone="success",
    )

    photo_found = int(analysis_counts.get("imagemaid_photo_found_files") or 0) if isinstance(analysis_counts.get("imagemaid_photo_found_files"), (int, float)) else 0
    photo_removed = int(analysis_counts.get("imagemaid_photo_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_photo_removed_files"), (int, float)) else 0
    photo_recovered = int(analysis_counts.get("imagemaid_photo_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_photo_recovered_bytes"), (int, float)) else 0
    photo_enabled = (
        bool(analysis_counts.get("imagemaid_photo_transcoder_enabled"))
        or "photo_transcoder_scan" in section_runtimes
        or "photo_transcoder_remove" in section_runtimes
        or photo_found > 0
        or photo_removed > 0
    )
    photo_items = ""
    if photo_removed > 0:
        photo_items = f"Removed {format_compact_count_brief(photo_removed)}"
    elif photo_found > 0:
        photo_items = f"Found {format_compact_count_brief(photo_found)}"
    photo_outcome = format_imagemaid_bytes_brief(photo_recovered) if photo_recovered > 0 else ""
    _append_row(
        "PhotoTranscoder",
        "File cleanup",
        scan_seconds=section_runtimes.get("photo_transcoder_scan"),
        action_seconds=section_runtimes.get("photo_transcoder_remove"),
        items_label=photo_items,
        outcome_label=photo_outcome,
        enabled=photo_enabled,
        items_tone="primary",
        outcome_tone="success",
    )

    for label, enabled_key, started_key, runtime_key in [
        ("Empty Trash", "imagemaid_empty_trash_enabled", "imagemaid_empty_trash_started", "empty_trash_action"),
        ("Clean Bundles", "imagemaid_clean_bundles_enabled", "imagemaid_clean_bundles_started", "clean_bundles_action"),
        ("Optimize DB", "imagemaid_optimize_db_enabled", "imagemaid_optimize_db_started", "optimize_db_action"),
    ]:
        enabled = bool(analysis_counts.get(enabled_key)) or bool(analysis_counts.get(started_key)) or runtime_key in section_runtimes
        runtime_value = section_runtimes.get(runtime_key)
        items_label = "Enabled" if enabled else ""
        outcome_label = "Done" if isinstance(runtime_value, (int, float)) and run_complete else ""
        _append_row(
            label,
            "Plex task",
            scan_seconds=None,
            action_seconds=runtime_value,
            items_label=items_label,
            outcome_label=outcome_label,
            enabled=enabled,
            items_tone="secondary",
            outcome_tone="success",
        )

    if not rows:
        return {}

    total_removed = int(analysis_counts.get("imagemaid_total_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_total_removed_files"), (int, float)) else 0
    total_recovered = int(analysis_counts.get("imagemaid_total_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_total_recovered_bytes"), (int, float)) else 0
    completed_count = 0
    for row in rows:
        if row.get("status") in {"Completed", "Skipped"}:
            completed_count += 1

    return {
        "name_label": "Operation",
        "type_label": "Area",
        "columns": [
            {"key": "scan", "label": "Scan Time"},
            {"key": "action", "label": "Action Time"},
            {"key": "items", "label": "Observed"},
            {"key": "outcome", "label": "Result"},
        ],
        "rows": rows,
        "completed_count": completed_count,
        "total_count": len(rows),
        "preparation_label": "",
        "footer_cells": [
            format_duration_brief(total_scan_seconds) if total_scan_seconds > 0 else "",
            format_duration_brief(total_action_seconds) if total_action_seconds > 0 else "",
            f"Removed {format_compact_count_brief(total_removed)}" if total_removed > 0 else "",
            format_imagemaid_bytes_brief(total_recovered) if total_recovered > 0 else "",
        ],
        "total_label": (
            format_duration_brief(summary.get("run_time_seconds")) if isinstance(summary.get("run_time_seconds"), (int, float)) and summary.get("run_time_seconds") else ""
        ),
    }
