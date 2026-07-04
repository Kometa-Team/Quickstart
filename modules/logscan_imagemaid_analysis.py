import gzip
import os
import re
import shlex
from pathlib import Path

from modules import database, helpers, logscan

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
