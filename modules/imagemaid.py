import subprocess
import sys
import time
from pathlib import Path

from flask import current_app as app, has_request_context, session

from modules import database, helpers, persistence


def probe_imagemaid_root_state(path_obj):
    p = Path(path_obj)
    imagemaid_root_posix = p.as_posix()
    imagemaid_root_display = str(p)
    is_windows = sys.platform.startswith("win")
    venv_dir = p / "imagemaid-venv"
    bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
    python_bin = bin_dir / ("python.exe" if is_windows else "python3")
    if not python_bin.exists():
        python_bin = bin_dir / ("python.exe" if is_windows else "python")
    imagemaid_py = p / "imagemaid.py"
    requirements = p / "requirements.txt"
    config_dir = p / "config"
    capabilities = get_imagemaid_supported_options(p)

    return {
        "imagemaid_root": imagemaid_root_posix,
        "imagemaid_root_display": imagemaid_root_display,
        "venv_python": python_bin.as_posix(),
        "venv_python_display": str(python_bin),
        "root_exists": p.exists(),
        "config_dir_exists": config_dir.exists(),
        "imagemaid_installed": imagemaid_py.exists() and requirements.exists(),
        "venv_exists": venv_dir.exists(),
        "venv_python_exists": python_bin.exists(),
        "imagemaid_running": helpers.is_imagemaid_running(),
        "local_version": helpers.get_imagemaid_local_version(p) or "",
        "local_sha": helpers.get_imagemaid_local_sha(p) or "",
        "local_branch": helpers.get_imagemaid_local_branch(p) or "",
        "supports_no_verify_ssl": bool(capabilities.get("no_verify_ssl")),
        "supports_overlays_only": bool(capabilities.get("overlays_only")),
    }


def imagemaid_settings_to_form_payload(payload):
    if not isinstance(payload, dict):
        return {}
    keys = [
        "branch_override",
        "plex_path",
        "mode",
        "timeout",
        "sleep",
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
    ]
    form_payload = {}
    raw_config_name = str(payload.get("config_name") or "").strip()
    config_name = helpers.normalize_config_name_for_storage(raw_config_name) if raw_config_name else ""
    if config_name:
        form_payload["config_name"] = config_name
    for key in keys:
        if key in payload:
            form_payload[f"imagemaid_{key}"] = payload.get(key)
    return form_payload


def get_stored_plex_credentials_for_config(config_name):
    try:
        stored_validated, stored_user_entered, stored_payload = database.retrieve_section_data(name=config_name, section="plex")
        payload = stored_payload if isinstance(stored_payload, dict) else {}
        plex_settings = payload.get("plex", {})
        if not plex_settings:
            plex_settings = persistence.get_dummy_data("plex")
        plex_url = plex_settings.get("url")
        plex_token = plex_settings.get("token")
        if plex_url and plex_token:
            return plex_url, plex_token
    except Exception as exc:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Failed to retrieve Plex credentials for config {config_name}: {exc}", level="ERROR")
    return None, None


def save_imagemaid_settings_for_config(config_name, form_payload):
    clean_data = persistence.clean_form_data(form_payload)
    data = helpers.build_config_dict("imagemaid", clean_data)
    stored_validated, stored_user_entered, stored_payload = database.retrieve_section_data(config_name, "imagemaid")
    existing_payload = stored_payload if isinstance(stored_payload, dict) else {}
    existing_section = existing_payload.get("imagemaid", {}) if isinstance(existing_payload.get("imagemaid"), dict) else {}
    canonical_existing_section = canonicalize_imagemaid_section(existing_section)
    canonical_new_section = canonicalize_imagemaid_section(data.get("imagemaid", {}) if isinstance(data.get("imagemaid"), dict) else {})
    payload = dict(existing_payload)
    payload["imagemaid"] = canonical_new_section
    if "validated_at" in data:
        payload["validated_at"] = data.get("validated_at")
    elif existing_payload.get("validated_at") is not None:
        payload["validated_at"] = existing_payload.get("validated_at")
    user_entered = bool(canonical_new_section.get("plex_path"))
    database.save_section_data(
        name=config_name,
        section="imagemaid",
        validated=helpers.booler(stored_validated),
        user_entered=user_entered,
        data=payload,
    )
    changed = canonical_new_section != canonical_existing_section
    return payload, changed


def canonicalize_imagemaid_section(section_data):
    section = dict(section_data) if isinstance(section_data, dict) else {}
    canonical = {
        "branch_override": "",
        "plex_path": "",
        "mode": "report",
        "timeout": 600,
        "sleep": 60,
        "photo_transcoder": False,
        "empty_trash": False,
        "clean_bundles": False,
        "optimize_db": False,
        "local_db": False,
        "use_existing": False,
        "ignore_running": False,
        "trace": False,
        "log_requests": False,
        "no_verify_ssl": False,
        "overlays_only": False,
    }
    canonical.update(section)

    canonical["branch_override"] = helpers.normalize_imagemaid_branch_override(canonical.get("branch_override")) or ""
    canonical["plex_path"] = str(canonical.get("plex_path") or "").strip()
    canonical["mode"] = str(canonical.get("mode") or "report").strip().lower() or "report"

    for numeric_key, default_value in (("timeout", 600), ("sleep", 60)):
        raw_value = canonical.get(numeric_key)
        try:
            canonical[numeric_key] = int(raw_value)
        except (TypeError, ValueError):
            canonical[numeric_key] = default_value

    for bool_key in (
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
        canonical[bool_key] = helpers.booler(canonical.get(bool_key))

    return canonical


def get_imagemaid_settings_section(config_name=None):
    resolved_config = config_name or persistence.ensure_session_config_name()
    settings = persistence.retrieve_settings_for_config(resolved_config, "915-imagemaid") or {}
    section = settings.get("imagemaid", {}) if isinstance(settings, dict) else {}
    if not isinstance(section, dict):
        section = {}
    return settings, section


def persist_imagemaid_validation(config_name, section_data, is_valid, reason=None, details=None):
    stored_validated, user_entered, stored_payload = database.retrieve_section_data(config_name, "imagemaid")
    payload = stored_payload if isinstance(stored_payload, dict) else {}
    payload["imagemaid"] = section_data if isinstance(section_data, dict) else {}
    if is_valid:
        payload["validated_at"] = helpers.utc_now_iso()
        payload["validation_status"] = "validated"
        payload.pop("validation_reason", None)
        payload.pop("validation_details", None)
        payload["validation_updated_at"] = helpers.utc_now_iso()
        database.save_section_data(
            name=config_name,
            section="imagemaid",
            validated=True,
            user_entered=True,
            data=payload,
        )
        return payload

    existing_validated_at = payload.get("validated_at")
    if existing_validated_at:
        payload["validated_at"] = existing_validated_at
    payload["validation_status"] = "failed"
    payload["validation_reason"] = reason
    payload["validation_details"] = details
    payload["validation_updated_at"] = helpers.utc_now_iso()
    database.save_section_data(
        name=config_name,
        section="imagemaid",
        validated=False,
        user_entered=True,
        data=payload,
    )
    return payload


def get_imagemaid_supported_options(imagemaid_root=None):
    root = Path(imagemaid_root or helpers.get_imagemaid_root_path())
    script_path = root / "imagemaid.py"
    try:
        text = script_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {"no_verify_ssl": False, "overlays_only": False}

    lowered = text.lower()
    return {
        "no_verify_ssl": ('"env": "no_verify_ssl"' in lowered) or ('"key": "no-verify-ssl"' in lowered) or ("--no-verify-ssl" in lowered),
        "overlays_only": ('"env": "overlays_only"' in lowered) or ('"key": "overlays-only"' in lowered) or ("--overlays-only" in lowered),
    }


def validate_imagemaid_plex_path(path_value, require_transcoder=False):
    resolved = helpers.resolve_user_dir(path_value)
    required_label = "Plex path must point to the Plex config directory containing Cache, Metadata, and Plug-in Support."
    if not resolved:
        return False, "invalid_paths", f"{required_label} Use an absolute path."
    if not resolved.exists() or not resolved.is_dir():
        return False, "invalid_paths", f"{required_label} The selected path does not exist or is not a directory."

    required_dirs = ["Metadata", "Plug-in Support"]
    missing = [name for name in required_dirs if not (resolved / name).exists()]
    if missing:
        return False, "invalid_paths", f"{required_label} The selected folder is missing: {', '.join(missing)}."

    if require_transcoder and not (resolved / "Cache" / "PhotoTranscoder").exists():
        return False, "invalid_paths", f"{required_label} PhotoTranscoder cleanup also requires Cache\\PhotoTranscoder."

    return True, None, None


def build_imagemaid_command_parts(section_data, plex_url, plex_token, imagemaid_root=None, redact=False):
    imagemaid_root = Path(imagemaid_root or helpers.get_imagemaid_root_path())
    capabilities = get_imagemaid_supported_options(imagemaid_root)
    is_win = sys.platform.startswith("win")
    python_bin = imagemaid_root / "imagemaid-venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python3")
    if not python_bin.exists():
        python_bin = imagemaid_root / "imagemaid-venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python")
    script_path = imagemaid_root / "imagemaid.py"

    parts = [str(python_bin), str(script_path)]
    parts.extend(["--url", "(saved Plex URL)" if redact else str(plex_url or "")])
    parts.extend(["--token", "(saved Plex token)" if redact else str(plex_token or "")])

    plex_path = str(section_data.get("plex_path") or "").strip()
    if plex_path:
        parts.extend(["--plex", plex_path])

    mode = str(section_data.get("mode") or "report").strip().lower() or "report"
    parts.extend(["--mode", mode])

    bool_flags = {
        "photo_transcoder": "--photo-transcoder",
        "empty_trash": "--empty-trash",
        "clean_bundles": "--clean-bundles",
        "optimize_db": "--optimize-db",
        "local_db": "--local",
        "use_existing": "--existing",
        "ignore_running": "--ignore",
        "trace": "--trace",
        "log_requests": "--log-requests",
    }
    if capabilities.get("no_verify_ssl"):
        bool_flags["no_verify_ssl"] = "--no-verify-ssl"
    if capabilities.get("overlays_only"):
        bool_flags["overlays_only"] = "--overlays-only"
    for key, flag in bool_flags.items():
        if helpers.booler(section_data.get(key)):
            parts.append(flag)

    timeout_value = str(section_data.get("timeout") or "").strip()
    if timeout_value:
        parts.extend(["--timeout", timeout_value])
    sleep_value = str(section_data.get("sleep") or "").strip()
    if sleep_value:
        parts.extend(["--sleep", sleep_value])

    return parts


def build_imagemaid_command(section_data, plex_url, plex_token, imagemaid_root=None, redact=False):
    parts = build_imagemaid_command_parts(
        section_data,
        plex_url,
        plex_token,
        imagemaid_root=imagemaid_root,
        redact=redact,
    )
    return subprocess.list2cmdline(parts)


def validate_imagemaid_settings(section_data, config_name=None):
    if config_name:
        resolved_config = config_name
    elif has_request_context():
        resolved_config = session.get("config_name") or persistence.ensure_session_config_name()
    else:
        resolved_config = None
    mode = str(section_data.get("mode") or "report").strip().lower() or "report"
    valid_modes = {"report", "move", "restore", "clear", "remove", "nothing"}
    if mode not in valid_modes:
        return False, "invalid_mode", f"ImageMaid mode must be one of: {', '.join(sorted(valid_modes))}."

    plex_settings = persistence.retrieve_settings_for_config(resolved_config, "010-plex") if resolved_config else (persistence.retrieve_settings("010-plex") or {})
    if not helpers.booler(plex_settings.get("validated", False)):
        return False, "missing_plex_validation", "Validate the Plex page before running ImageMaid."
    if resolved_config:
        plex_url, plex_token = get_stored_plex_credentials_for_config(resolved_config)
    else:
        plex_url, plex_token = persistence.get_stored_plex_credentials()
    if not plex_url or not plex_token:
        return False, "missing_credentials", "Saved Plex URL/token are required."
    valid_path, reason, details = validate_imagemaid_plex_path(
        section_data.get("plex_path"),
        require_transcoder=helpers.booler(section_data.get("photo_transcoder")),
    )
    if not valid_path:
        return False, reason, details

    resolved_plex_path = helpers.resolve_user_dir(section_data.get("plex_path"))
    restore_dir = resolved_plex_path / "ImageMaid Restore" if resolved_plex_path else None
    if mode in {"report", "move", "remove"} and restore_dir and restore_dir.exists():
        return (
            False,
            "restore_dir_blocks_mode",
            f"{mode.capitalize()} mode is not allowed while the ImageMaid Restore folder exists: {restore_dir}. " "Use nothing, restore, or clear while that folder is present.",
        )
    if mode in {"restore", "clear"} and restore_dir and not restore_dir.exists():
        return False, "missing_restore_dir", f"{mode.capitalize()} mode expects the ImageMaid Restore folder at: {restore_dir}"

    return True, None, None


def get_latest_imagemaid_log_path():
    log_dir = helpers.get_imagemaid_root_path() / "config" / "logs"
    if not log_dir.exists():
        return None
    candidates = sorted(
        [path for path in log_dir.glob("*.log") if path.name.lower() != "imagemaid.quickstart-maintenance.log"],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def read_text_tail_payload(path, max_lines=200):
    path_obj = Path(path)
    content = helpers.read_logscan_text(path_obj, encoding="utf-8", errors="replace")
    lines = content.splitlines()
    tail_text = "\n".join(lines[-max_lines:]) if lines else ""
    if tail_text and content.endswith("\n"):
        tail_text += "\n"
    try:
        stats = path_obj.stat()
        log_age_seconds = max(0, int(time.time() - stats.st_mtime))
    except Exception:
        log_age_seconds = None
    return {
        "text": tail_text,
        "total_lines": len(lines),
        "log_age_seconds": log_age_seconds,
    }


def sanitize_imagemaid_log_tail(text):
    content = str(text or "")
    if not content:
        return content
    lines = content.splitlines()
    filtered = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            line.startswith("Exception ignored in: <function _ExecutorManagerThread.__init__.<locals>.weakref_cb")
            and i + 3 < len(lines)
            and lines[i + 1] == "Traceback (most recent call last):"
            and "concurrent" in lines[i + 2]
            and "process.py" in lines[i + 2]
            and "AttributeError: 'NoneType' object has no attribute 'debug'" in lines[i + 3]
        ):
            i += 4
            continue
        filtered.append(line)
        i += 1
    return "\n".join(filtered).strip("\n")
