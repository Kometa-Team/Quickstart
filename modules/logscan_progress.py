from datetime import datetime, timezone
from pathlib import Path

from flask import has_request_context
from ruamel.yaml import YAML

from modules import database, helpers, logscan, persistence
from modules.logscan_resume import (
    detect_explicit_phase_from_command,
    extract_cli_option_value,
    format_duration_brief,
    inject_config_path_for_command,
    resolve_config_path_for_command,
)
from modules.process_control import extract_selected_libraries

_read_logscan_text = helpers.read_logscan_text


def load_progress_config(config_path=None):
    if not config_path:
        return None
    try:
        yaml_parser = YAML(typ="safe", pure=True)
        with Path(config_path).open("r", encoding="utf-8", errors="ignore") as handle:
            return yaml_parser.load(handle) or {}
    except Exception:
        return None


def normalize_run_order_value(value):
    lowered = str(value or "").strip().lower()
    if not lowered:
        return None
    if lowered.startswith("operation"):
        return "operations"
    if lowered.startswith("overlay"):
        return "overlays"
    if lowered.startswith("collection"):
        return "collections"
    if lowered.startswith("metadata"):
        return "metadata"
    return None


def get_progress_run_order(config_data=None):
    if not isinstance(config_data, dict):
        return []
    settings = config_data.get("settings") if isinstance(config_data.get("settings"), dict) else {}
    run_order = settings.get("run_order") if isinstance(settings, dict) else None
    if not isinstance(run_order, list):
        return []
    normalized = []
    for item in run_order:
        key = normalize_run_order_value(item)
        if key and key not in normalized:
            normalized.append(key)
    return normalized


def get_progress_library_list(selected_libraries=None, config_path=None, config_data=None, config_name=None):
    import json as _json
    import quickstart

    library_settings = {}
    plex_name_map = {}
    if has_request_context():
        settings = persistence.retrieve_settings("025-libraries")
        library_settings = settings.get("libraries", {}) if isinstance(settings, dict) else {}
        plex_name_map = persistence.get_library_names()
    elif config_name:
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(config_name, "libraries")
            if not isinstance(stored, dict):
                _validated, _user_entered, stored = database.retrieve_section_data(config_name, "025-libraries")
            if isinstance(stored, dict):
                if isinstance(stored.get("libraries"), dict):
                    library_settings = stored.get("libraries", {})
                else:
                    library_settings = stored
        except Exception:
            library_settings = {}
        try:
            plex_settings = persistence.retrieve_settings_for_config(config_name, "010-plex")
            raw = plex_settings.get("plex", {}).get("tmp_library_names", "")
            plex_name_map = _json.loads(raw) if raw else {}
        except Exception:
            plex_name_map = {}
    libraries = []
    type_by_name = {}
    if isinstance(library_settings, dict):
        for key, value in library_settings.items():
            if not value:
                continue
            if key.startswith("mov-library_") and key.endswith("-library"):
                lib_id = helpers.extract_library_name(key)
                display_name = plex_name_map.get(lib_id, "") if lib_id else ""
                if display_name:
                    type_by_name[display_name] = "movie"
            elif key.startswith("sho-library_") and key.endswith("-library"):
                lib_id = helpers.extract_library_name(key)
                display_name = plex_name_map.get(lib_id, "") if lib_id else ""
                if display_name:
                    type_by_name[display_name] = "show"
    parsed = config_data if isinstance(config_data, dict) else quickstart._load_progress_config(config_path)
    if isinstance(parsed, dict):
        lib_section = parsed.get("libraries")
        if isinstance(lib_section, dict):
            for lib_name in lib_section.keys():
                if lib_name:
                    libraries.append({"name": lib_name, "type": type_by_name.get(lib_name)})
    if not libraries:
        for name, lib_type in type_by_name.items():
            libraries.append({"name": name, "type": lib_type})
    if selected_libraries:
        existing = {lib["name"] for lib in libraries}
        for name in selected_libraries:
            if name and name not in existing:
                libraries.append({"name": name, "type": None})
                existing.add(name)
    return libraries


def build_incomplete_progress_snapshot(
    progress=None,
    last_log_at=None,
    config_data=None,
    original_command="",
    config_name=None,
):
    progress = progress if isinstance(progress, dict) else {}
    libraries = progress.get("libraries") if isinstance(progress.get("libraries"), list) else []
    if not libraries:
        return {}
    phase_lookup = {
        "operations": "Operations",
        "metadata": "Metadata",
        "collections": "Collections",
        "overlays": "Overlays",
        "playlists": "Playlists",
    }
    current_phase = str(progress.get("phase_current") or "").strip().lower()
    current_library = str(progress.get("current_library") or "").strip()
    preparation_seconds = progress.get("preparation_seconds")
    if not isinstance(preparation_seconds, (int, float)):
        preparation_seconds = progress.get("preparation_elapsed_seconds")
    current_phase_elapsed_seconds = progress.get("current_phase_elapsed_seconds") if isinstance(progress.get("current_phase_elapsed_seconds"), (int, float)) else None
    explicit_phase = detect_explicit_phase_from_command(original_command)
    run_mode = explicit_phase if explicit_phase in ("collections", "operations", "metadata", "overlays", "playlists") else "all"
    allowed_phases = get_progress_run_order(config_data=config_data)
    if not allowed_phases:
        allowed_phases = ["operations", "metadata", "collections", "overlays"]
    playlists_configured = bool(config_data.get("playlists")) if isinstance(config_data, dict) else False
    if run_mode in ("collections", "overlays", "operations", "metadata", "playlists"):
        allowed_phases = [run_mode]
    elif "playlists" not in allowed_phases:
        allowed_phases = allowed_phases + ["playlists"]
    columns = [{"key": key, "label": phase_lookup.get(key, key.title())} for key in allowed_phases]
    configured_library_entries = []
    configured_library_names = []
    configured_type_by_name = {}
    config_path = extract_cli_option_value(original_command, "--config")
    selected_libraries = extract_selected_libraries(original_command)[1]
    for entry in get_progress_library_list(
        selected_libraries=selected_libraries,
        config_path=config_path,
        config_data=config_data,
        config_name=config_name,
    ):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        lib_type = str(entry.get("type") or "").strip()
        if name.strip():
            configured_type_by_name[name] = lib_type or None
    if isinstance(config_data, dict):
        config_libraries = config_data.get("libraries")
        if isinstance(config_libraries, dict):
            # Preserve names exactly as they appear in the YAML — leading/trailing
            # whitespace is meaningful for libraries named e.g. " Movies ".
            configured_library_names = [str(name) for name in config_libraries.keys() if str(name).strip()]
            configured_library_entries = [{"name": name, "type": configured_type_by_name.get(name)} for name in configured_library_names]
    elif configured_type_by_name:
        configured_library_names = list(configured_type_by_name.keys())
        configured_library_entries = [{"name": name, "type": configured_type_by_name.get(name)} for name in configured_library_names]

    def _normalize_snapshot_library_name(raw_name):
        name = str(raw_name or "")
        if not name:
            return ""
        if configured_library_entries:
            matched = logscan.LogscanAnalyzer()._match_library_name(name, configured_library_entries)
            if matched:
                return matched
            if name.lower().startswith("finished "):
                alternate = name[9:]
                matched = logscan.LogscanAnalyzer()._match_library_name(alternate, configured_library_entries)
                if matched:
                    return matched
        if name.lower().startswith("finished "):
            return name[9:]
        return name

    current_library = _normalize_snapshot_library_name(current_library)

    rows = []
    totals = {column["key"]: 0 for column in columns}
    visible_libraries = [entry for entry in libraries if str((entry or {}).get("status") or "").strip() != "Skipped"]
    for entry in visible_libraries:
        name = _normalize_snapshot_library_name(entry.get("name"))
        status = str(entry.get("status") or "Pending").strip() or "Pending"
        status_class = "text-bg-secondary"
        if status == "Done":
            status_class = "text-bg-success"
        elif status == "In progress":
            status_class = "text-bg-primary"
        elif status == "Stopped":
            status_class = "text-bg-danger"

        durations = entry.get("durations") if isinstance(entry.get("durations"), dict) else {}
        phase_cells = []
        for column in columns:
            phase_key = column["key"]
            label = ""
            tone = ""
            seconds = durations.get(phase_key)
            if phase_key == "playlists":
                playlist_total = progress.get("playlist_total_seconds") if isinstance(progress.get("playlist_total_seconds"), (int, float)) else None
                playlist_running = bool(progress.get("playlist_running"))
                playlist_elapsed = progress.get("playlist_elapsed_seconds") if isinstance(progress.get("playlist_elapsed_seconds"), (int, float)) else None
                if playlist_running:
                    label = format_duration_brief(playlist_elapsed)
                    tone = "primary"
                elif isinstance(playlist_total, (int, float)) and (playlist_total > 0 or playlists_configured):
                    label = format_duration_brief(playlist_total)
                    tone = "success" if label else ""
                    if label:
                        totals[phase_key] = max(0, int(playlist_total))
                phase_cells.append({"label": label, "tone": tone})
                continue
            if current_library and current_phase and current_library == name and current_phase == phase_key and isinstance(current_phase_elapsed_seconds, (int, float)):
                label = format_duration_brief(current_phase_elapsed_seconds)
                tone = "primary"
            elif isinstance(seconds, (int, float)):
                label = format_duration_brief(seconds)
                tone = "success"
                totals[phase_key] = totals.get(phase_key, 0) + int(seconds or 0)
            phase_cells.append({"label": label, "tone": tone})

        row_type = configured_type_by_name.get(name) or entry.get("type")
        rows.append(
            {
                "name": name,
                "type": str(row_type or "—").strip() or "—",
                "status": status,
                "status_class": status_class,
                "phase_cells": phase_cells,
            }
        )

    total_seconds = 0
    if isinstance(preparation_seconds, (int, float)):
        total_seconds += int(preparation_seconds or 0)
    for value in totals.values():
        if isinstance(value, (int, float)):
            total_seconds += int(value or 0)

    return {
        "columns": columns,
        "rows": rows,
        "completed_count": progress.get("completed_count"),
        "total_count": progress.get("total_count"),
        "current_library": current_library,
        "phase_current": current_phase,
        "last_log_at": last_log_at or "",
        "preparation_label": (format_duration_brief(preparation_seconds) if isinstance(preparation_seconds, (int, float)) else ""),
        "footer_cells": [
            (format_duration_brief(totals.get(column["key"])) if isinstance(totals.get(column["key"]), (int, float)) and totals.get(column["key"]) > 0 else "")
            for column in columns
        ],
        "total_label": (format_duration_brief(total_seconds) if total_seconds > 0 else ""),
    }


def build_completed_log_progress_snapshot(summary=None, content="", analyzer=None):
    import quickstart

    summary = summary if isinstance(summary, dict) else {}
    if not content:
        return {}
    tool_name = str(summary.get("tool_name") or "kometa").strip().lower() or "kometa"
    if tool_name != "kometa":
        return {}

    original_command = summary.get("run_command") or ""
    if not original_command:
        return {}
    config_name = str(summary.get("config_name") or "").strip()
    original_command = inject_config_path_for_command(
        original_command,
        config_name=config_name,
    )
    config_path = extract_cli_option_value(original_command, "--config")
    if not config_path and config_name:
        config_path = resolve_config_path_for_command(config_name=config_name)
    config_data = quickstart._load_progress_config(config_path) if config_path else {}
    selected_libraries = extract_selected_libraries(original_command)[1]
    progress_analyzer = analyzer if analyzer is not None else logscan.LogscanAnalyzer()
    progress = progress_analyzer.extract_progress(
        content,
        library_list=get_progress_library_list(
            selected_libraries=selected_libraries,
            config_path=config_path,
            config_data=config_data,
            config_name=config_name,
        ),
        selected_libraries=selected_libraries,
        previous=None,
        run_started_at=summary.get("started_at"),
        now_ts=datetime.now(timezone.utc),
        is_running=False,
    )
    snapshot = build_incomplete_progress_snapshot(
        progress=progress,
        last_log_at=summary.get("finished_at") or summary.get("started_at"),
        config_data=config_data,
        original_command=original_command,
        config_name=config_name,
    )
    if not snapshot:
        return {}
    return snapshot
