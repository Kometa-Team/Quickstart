import re
from datetime import datetime, timezone

from flask import has_request_context, session

from modules import helpers
from modules.process_control import extract_selected_libraries


def normalize_cli_whitespace(command):
    return re.sub(r"\s+", " ", str(command or "")).strip()


def command_has_flag(command, flag):
    if not command or not flag:
        return False
    pattern = re.compile(rf"(^|\s){re.escape(flag)}(?=\s|$)")
    return bool(pattern.search(command))


def remove_cli_switch(command, flag):
    if not command or not flag:
        return command
    pattern = re.compile(rf"(^|\s){re.escape(flag)}(?=\s|$)")
    return pattern.sub(" ", command)


def remove_cli_option_with_value(command, flag):
    if not command or not flag:
        return command
    pattern = re.compile(rf"(^|\s){re.escape(flag)}(?:=(?:\"[^\"]*\"|'[^']*'|[^\s]+)|\s+(?:\"[^\"]*\"|'[^']*'|[^\s]+))?")
    return pattern.sub(" ", command)


def quote_cli_value(value):
    text = str(value or "")
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'


def normalize_library_scope_values(current_library=None, library_scope=None):
    values = []
    seen = set()

    def add_value(raw):
        candidate = str(raw or "").strip()
        if not candidate:
            return
        normalized = candidate.casefold()
        if normalized in seen:
            return
        seen.add(normalized)
        values.append(candidate)

    if isinstance(library_scope, (list, tuple, set)):
        for item in library_scope:
            add_value(item)
    elif library_scope:
        if isinstance(library_scope, str) and "|" in library_scope:
            for item in library_scope.split("|"):
                add_value(item)
        else:
            add_value(library_scope)
    elif current_library:
        add_value(current_library)

    return values


def build_resume_library_scope(original_command, progress_libraries=None, current_library=None, allow_current_fallback=False):
    run_option, selected_libraries = extract_selected_libraries(original_command)
    progress_libraries = progress_libraries if isinstance(progress_libraries, list) else []

    status_by_name = {}
    ordered_library_names = []
    for entry in progress_libraries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        ordered_library_names.append(name)
        status_by_name[name.casefold()] = str(entry.get("status") or "").strip()

    base_scope = []
    if isinstance(selected_libraries, list) and selected_libraries:
        base_scope = [str(name).strip() for name in selected_libraries if str(name).strip()]
    elif run_option != "--run-libraries":
        base_scope = ordered_library_names[:]

    remaining = []
    seen = set()
    for name in base_scope:
        key = name.casefold()
        status = status_by_name.get(key, "")
        if status in ("Done", "Skipped"):
            continue
        if key in seen:
            continue
        seen.add(key)
        remaining.append(name)

    current_name = str(current_library or "").strip()
    if current_name:
        current_key = current_name.casefold()
        if current_key not in seen:
            current_status = status_by_name.get(current_key, "")
            current_in_base_scope = (not base_scope) or any(str(name).strip().casefold() == current_key for name in base_scope)
            if current_in_base_scope and current_status not in ("Done", "Skipped"):
                if current_key in status_by_name or allow_current_fallback:
                    remaining.insert(0, current_name)

    return remaining


def should_suppress_recovery_for_completed_scope(original_command, progress_libraries=None, current_library=None):
    progress_libraries = progress_libraries if isinstance(progress_libraries, list) else []
    if not progress_libraries:
        return False

    run_option, selected_libraries = extract_selected_libraries(original_command)
    explicit_phase = detect_explicit_phase_from_command(original_command)
    if explicit_phase not in ("collections", "operations", "metadata", "overlays", "playlists") and run_option != "--run-libraries":
        return False

    remaining = build_resume_library_scope(
        original_command,
        progress_libraries=progress_libraries,
        current_library=current_library,
        allow_current_fallback=False,
    )
    return len(remaining) == 0


def resolve_config_path_for_command(config_name=None):
    normalized_name = str(config_name or "").strip().lower().replace(" ", "_")
    if not normalized_name:
        if has_request_context():
            normalized_name = str(session.get("config_name") or "default").strip().lower().replace(" ", "_") or "default"
        else:
            normalized_name = "default"
    return str((helpers.get_kometa_config_dir() / f"{normalized_name}_config.yml").resolve())


def inject_config_path_for_command(command, config_name=None):
    cleaned = normalize_cli_whitespace(command)
    if not cleaned:
        return ""
    if "<config>" not in cleaned and "--config" not in cleaned and "-c" not in cleaned and not str(config_name or "").strip():
        return cleaned
    config_path = resolve_config_path_for_command(config_name=config_name)
    quoted = quote_cli_value(config_path)
    if "<config>" in cleaned:
        return normalize_cli_whitespace(cleaned.replace("<config>", quoted))
    cleaned = remove_cli_option_with_value(cleaned, "--config")
    cleaned = remove_cli_option_with_value(cleaned, "-c")
    return normalize_cli_whitespace(f"{cleaned} --config {quoted}")


def build_recovery_command(base_command, phase=None, current_library=None, library_scope=None):
    command = normalize_cli_whitespace(base_command)
    if not command:
        return ""

    phase_modes = {
        "operations": "--operations-only",
        "metadata": "--metadata-only",
        "collections": "--collections-only",
        "overlays": "--overlays-only",
        "playlists": "--playlists-only",
    }
    mode_flags = list(phase_modes.values())
    scoped_flags = ["--run-libraries", "--run-collections", "--resume"]

    for flag in mode_flags:
        command = remove_cli_switch(command, flag)
    for flag in scoped_flags:
        command = remove_cli_option_with_value(command, flag)

    phase_flag = phase_modes.get((phase or "").strip().lower())
    if phase_flag:
        command = f"{command} {phase_flag}"
    library_values = normalize_library_scope_values(current_library=current_library, library_scope=library_scope)
    if library_scope is not None and not library_values:
        return ""
    if library_values:
        command = f"{command} --run-libraries {quote_cli_value('|'.join(library_values))}"
    if not command_has_flag(command, "--run") and not command_has_flag(command, "--times"):
        command = f"{command} --run"

    return normalize_cli_whitespace(command)


def build_collection_resume_command(base_command, current_collection=None, current_library=None):
    command = build_recovery_command(base_command, phase="collections", current_library=current_library)
    if not command or not current_collection:
        return ""
    command = remove_cli_option_with_value(command, "--resume")
    command = f"{command} --resume {quote_cli_value(current_collection)}"
    return normalize_cli_whitespace(command)


def build_resume_command_preserving_scope(base_command, current_collection=None, current_library=None, library_scope=None):
    command = normalize_cli_whitespace(base_command)
    if not command or not current_collection:
        return ""

    explicit_phase = detect_explicit_phase_from_command(command)
    preserved_phase = explicit_phase if explicit_phase not in (None, "mixed") else None
    command = build_recovery_command(
        command,
        phase=preserved_phase,
        current_library=current_library,
        library_scope=library_scope,
    )
    if not command:
        return ""
    command = remove_cli_option_with_value(command, "--resume")
    command = f"{command} --resume {quote_cli_value(current_collection)}"
    return normalize_cli_whitespace(command)


def iso_from_mtime(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None
    return None


def extract_first_log_timestamp(content):
    if not content:
        return None
    match = re.search(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]", str(content), re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def extract_last_log_timestamp(content):
    if not content:
        return None
    matches = re.findall(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]", str(content), re.MULTILINE)
    if not matches:
        return None
    return str(matches[-1]).strip()


def parse_log_display_datetime(value):
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S",):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


def format_duration_brief(total_seconds):
    if not isinstance(total_seconds, (int, float)):
        return ""
    seconds = max(0, int(total_seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def format_compact_count_brief(value):
    if not isinstance(value, (int, float)):
        return ""
    count = max(0, int(value))
    if count >= 1000000:
        return f"{(count / 1000000):.1f}".rstrip("0").rstrip(".") + "M"
    if count >= 1000:
        return f"{(count / 1000):.1f}".rstrip("0").rstrip(".") + "K"
    return str(count)


def format_imagemaid_bytes_brief(value):
    if not isinstance(value, (int, float)):
        return ""
    total = max(0, int(value))
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(total)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        display = str(int(size))
    elif size >= 10:
        display = f"{size:.1f}".rstrip("0").rstrip(".")
    else:
        display = f"{size:.2f}".rstrip("0").rstrip(".")
    return f"{display} {units[unit_index]}"


def build_incomplete_run_timing_summary(started_at=None, last_log_at=None, maintenance_summary=None):
    summary = maintenance_summary if isinstance(maintenance_summary, dict) else {}
    started_dt = parse_log_display_datetime(started_at)
    last_log_dt = parse_log_display_datetime(last_log_at)
    pause_seconds = int(summary.get("pause_seconds") or 0) if isinstance(summary.get("pause_seconds"), (int, float)) else 0
    observed_seconds = None
    active_seconds = None
    if started_dt and last_log_dt and last_log_dt >= started_dt:
        observed_seconds = int((last_log_dt - started_dt).total_seconds())
        active_seconds = max(0, observed_seconds - pause_seconds)
    return {
        "started_at": started_at or "",
        "last_log_at": last_log_at or "",
        "window": summary.get("window") or "",
        "pause_count": int(summary.get("pause_count") or 0) if isinstance(summary.get("pause_count"), (int, float)) else 0,
        "pause_seconds": pause_seconds,
        "pause_label": format_duration_brief(pause_seconds) if pause_seconds else "",
        "pause_display": format_duration_brief(pause_seconds) if pause_seconds else "Not observed",
        "observed_seconds": observed_seconds,
        "observed_label": format_duration_brief(observed_seconds) if observed_seconds is not None else "",
        "active_seconds": active_seconds,
        "active_label": format_duration_brief(active_seconds) if active_seconds is not None else "",
        "had_pause": bool(summary.get("had_pause")),
    }


def dedupe_preserve_order(values):
    seen = set()
    ordered = []
    for value in values or []:
        name = str(value or "").strip()
        if not name:
            continue
        lowered = name.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(name)
    return ordered


def build_incomplete_scope_summary(original_command="", suggested_command="", progress_libraries=None):
    progress_libraries = progress_libraries if isinstance(progress_libraries, list) else []
    original_selected = extract_selected_libraries(original_command)[1] or []
    recovery_selected = extract_selected_libraries(suggested_command)[1] or []
    progress_names = dedupe_preserve_order(entry.get("name") for entry in progress_libraries if isinstance(entry, dict))
    completed = dedupe_preserve_order(entry.get("name") for entry in progress_libraries if isinstance(entry, dict) and str(entry.get("status") or "").strip() == "Done")

    original_scope = dedupe_preserve_order(original_selected or progress_names)
    recovery_scope = dedupe_preserve_order(recovery_selected or original_scope)
    pruned = []
    if original_scope and recovery_scope:
        recovery_lookup = {name.casefold() for name in recovery_scope}
        pruned = [name for name in original_scope if name.casefold() not in recovery_lookup]

    return {
        "original_scope": original_scope,
        "recovery_scope": recovery_scope,
        "completed_libraries": completed,
        "pruned_libraries": pruned,
        "original_scope_label": " | ".join(original_scope) if original_scope else "",
        "recovery_scope_label": " | ".join(recovery_scope) if recovery_scope else "",
        "completed_label": " | ".join(completed) if completed else "",
        "pruned_label": " | ".join(pruned) if pruned else "",
    }


def build_maintenance_event_rows(maintenance_summary=None):
    summary = maintenance_summary if isinstance(maintenance_summary, dict) else {}
    rows = []
    for event in summary.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "").strip().lower()
        if event_name not in ("paused", "resumed"):
            continue
        label = "Paused" if event_name == "paused" else "Resumed"
        at_value = str(event.get("local_at") or event.get("at") or "").strip()
        pause_label = format_duration_brief(event.get("paused_seconds")) if isinstance(event.get("paused_seconds"), (int, float)) else ""
        window = str(event.get("window") or "").strip()
        rows.append(
            {
                "label": label,
                "at": at_value,
                "pause_label": pause_label,
                "window": window,
            }
        )
    return rows


def build_incomplete_resume_message(phase_current=None, current_library=None, finished_at=None):
    if phase_current and current_library:
        message = f"Run appears incomplete during {phase_current} in library '{current_library}'."
    elif phase_current:
        message = f"Run appears incomplete during {phase_current}."
    elif current_library:
        message = f"Run appears incomplete while processing library '{current_library}'."
    else:
        message = "Run appears incomplete."

    if finished_at:
        return f"{message} Last finished marker: {finished_at}."
    return f"{message} No Finished Run marker was found."


def build_completed_scope_resume_message(phase_current=None, current_library=None, finished_at=None):
    if current_library:
        message = f"The original run scope appears fully completed through library '{current_library}'."
    elif phase_current:
        message = f"The original run scope appears fully completed through the {phase_current} phase."
    else:
        message = "The original run scope appears fully completed."

    if finished_at:
        return f"{message} Last finished marker: {finished_at}."
    return message


def build_recovery_suggestions(original_command, phase_current=None, current_library=None, current_collection=None, progress_libraries=None):
    suggestions = []
    if not original_command:
        return suggestions

    if should_suppress_recovery_for_completed_scope(
        original_command,
        progress_libraries=progress_libraries,
        current_library=current_library,
    ):
        return []

    phase_key = (phase_current or "").strip().lower()
    explicit_phase = detect_explicit_phase_from_command(original_command)
    resume_library_scope = build_resume_library_scope(
        original_command,
        progress_libraries=progress_libraries,
        current_library=current_library,
        allow_current_fallback=bool(phase_key == "collections" or explicit_phase == "collections"),
    )
    scoped_library_scope = resume_library_scope or None

    if phase_key == "collections" and current_collection:
        suggestions.append(
            build_resume_command_preserving_scope(
                original_command,
                current_collection=current_collection,
                current_library=current_library,
                library_scope=scoped_library_scope,
            )
        )
        if scoped_library_scope is not None:
            suggestions.append(
                build_resume_command_preserving_scope(
                    original_command,
                    current_collection=current_collection,
                    current_library=None,
                    library_scope=None,
                )
            )

    phase_scope = explicit_phase if explicit_phase not in (None, "mixed") else None

    if phase_scope:
        suggestions.append(build_recovery_command(original_command, phase=phase_scope, library_scope=scoped_library_scope))
        if scoped_library_scope is not None:
            suggestions.append(build_recovery_command(original_command, phase=phase_scope, library_scope=None))
    elif scoped_library_scope is not None:
        suggestions.append(build_recovery_command(original_command, phase=None, library_scope=scoped_library_scope))
    suggestions.append(normalize_cli_whitespace(original_command))

    deduped = []
    seen = set()
    for item in suggestions:
        normalized = normalize_cli_whitespace(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:4]


def extract_cli_option_value(command, flag):
    normalized = normalize_cli_whitespace(command)
    if not normalized or not flag:
        return ""
    pattern = re.compile(rf"(?:^|\s){re.escape(flag)}(?:=(\"[^\"]*\"|'[^']*'|[^\s]+)|\s+(\"[^\"]*\"|'[^']*'|[^\s]+))")
    match = pattern.search(normalized)
    if not match:
        return ""
    raw = match.group(1) or match.group(2) or ""
    if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
        return raw[1:-1]
    return raw


def detect_explicit_phase_from_command(command):
    normalized = normalize_cli_whitespace(command)
    if not normalized:
        return None
    phase_modes = {
        "operations": "--operations-only",
        "metadata": "--metadata-only",
        "collections": "--collections-only",
        "overlays": "--overlays-only",
        "playlists": "--playlists-only",
    }
    matches = [phase for phase, flag in phase_modes.items() if command_has_flag(normalized, flag)]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return "mixed"


def build_resume_explanation(
    original_command,
    suggested_command,
    phase_current=None,
    current_library=None,
    current_collection=None,
    finished_at=None,
    progress_libraries=None,
):
    lines = []
    if finished_at:
        lines.append(f"Last finished marker seen in the log: {finished_at}.")
        lines.append("A final Finished Run block was not found after that point, so this run was treated as incomplete.")
    else:
        lines.append("No Finished Run marker was found in this log, so the run was treated as incomplete.")

    phase_modes = {
        "operations": "--operations-only",
        "metadata": "--metadata-only",
        "collections": "--collections-only",
        "overlays": "--overlays-only",
        "playlists": "--playlists-only",
    }
    phase_key = (phase_current or "").strip().lower()
    phase_flag = phase_modes.get(phase_key)
    explicit_phase = detect_explicit_phase_from_command(original_command)
    explicit_phase_flag = phase_modes.get(explicit_phase)
    if phase_flag and explicit_phase == phase_key:
        lines.append(f"Original logged command already targeted {phase_key} via {phase_flag}; recovery kept that same scope.")
    elif phase_key == "collections":
        if explicit_phase == "collections":
            lines.append("Detected active phase 'collections', and the original logged command was already collections-only.")
        else:
            lines.append("Detected active phase 'collections', but the original logged command was not collections-only; recovery kept the original run scope.")
    elif phase_flag:
        if explicit_phase == phase_key:
            lines.append(f"Detected active phase '{phase_key}', and the original logged command already used {phase_flag}.")
        elif explicit_phase in (None, "mixed"):
            lines.append(f"Detected active phase '{phase_key}', but the original logged command was not phase-only; recovery kept the original run scope.")
        else:
            lines.append(f"Detected active phase '{phase_key}', while the original logged command already targeted {explicit_phase}; recovery kept the original run scope.")
    elif phase_current:
        lines.append(f"Detected phase '{phase_current}', but no phase-only flag mapping was found.")
    else:
        if explicit_phase and explicit_phase != "mixed":
            lines.append(f"Detected explicit phase mode in the logged command: {phase_modes.get(explicit_phase, explicit_phase)}.")
        elif explicit_phase == "mixed":
            lines.append("Detected multiple phase-only flags in the logged command; mode flags were normalized.")

    effective_phase = phase_key or (explicit_phase if explicit_phase not in (None, "mixed") else "")
    resume_value = extract_cli_option_value(original_command, "--resume")
    has_resume_flag = command_has_flag(original_command, "--resume")
    suggested_resume = extract_cli_option_value(suggested_command, "--resume")
    suggested_library = extract_cli_option_value(suggested_command, "--run-libraries")

    if effective_phase and effective_phase != "collections":
        lines.append(f"Kometa --resume was not used because this run is {effective_phase}-phase; --resume only applies to collections.")
    elif suggested_resume:
        if suggested_resume:
            if explicit_phase_flag == "--collections-only":
                if current_collection and suggested_resume == current_collection:
                    lines.append(f'Collections-only run preserved; using --resume "{suggested_resume}" from latest in-progress collection activity.')
                else:
                    lines.append(f'Collections-only run preserved; suggestion uses --resume "{suggested_resume}".')
            else:
                if current_collection and suggested_resume == current_collection:
                    lines.append(f'Run was interrupted during collections, so recovery adds --resume "{suggested_resume}" while keeping the original run scope.')
                else:
                    lines.append(f'Recovery adds --resume "{suggested_resume}" while keeping the original run scope.')
            if suggested_library:
                lines.append(f'Used scoped resume (--run-libraries "{suggested_library}") instead of blind resume across all libraries.')
    elif has_resume_flag and resume_value:
        lines.append(f"Logged command already included --resume {resume_value}; it was not auto-carried forward to avoid stale checkpoints.")
    elif effective_phase == "collections" or phase_key == "collections":
        lines.append("Collections phase was detected. --resume can apply here, but no reliable resume checkpoint was found in this log.")
    else:
        lines.append("Kometa --resume was not used because phase could not be confirmed as collections.")

    if current_library:
        lines.append(f"Detected in-progress library '{current_library}', so the suggestion scopes with --run-libraries.")

    if isinstance(progress_libraries, list):
        completed_libraries = [
            str(entry.get("name")).strip() for entry in progress_libraries if str(entry.get("status") or "").strip() == "Done" and str(entry.get("name") or "").strip()
        ]
        if completed_libraries:
            lines.append(f"Completed libraries already seen in the log: {' | '.join(completed_libraries)}.")

    config_path = extract_cli_option_value(suggested_command, "--config")
    if config_path:
        lines.append(f"Config path in the suggested command is: {config_path}.")

    normalized_original = normalize_cli_whitespace(original_command)
    normalized_suggested = normalize_cli_whitespace(suggested_command)
    if normalized_original and normalized_suggested and normalized_original != normalized_suggested:
        lines.append("Conflicting mode/scope flags were normalized before applying the detected phase/library scope.")
    return lines
