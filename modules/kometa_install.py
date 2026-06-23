import shutil
import sys
from pathlib import Path

from flask import current_app as app, has_request_context, session
from ruamel.yaml import YAML

from modules import helpers, persistence

KOMETA_INSTALL_MODE_MANAGED = "managed"
KOMETA_INSTALL_MODE_EXISTING = "existing"
KOMETA_INSTALL_MODE_EXTERNAL = "external"


def default_managed_kometa_root() -> Path:
    return Path(helpers.CONFIG_DIR).resolve() / "kometa"


def normalize_kometa_install_mode(value) -> str:
    raw = str(value or "").strip().lower()
    if raw == KOMETA_INSTALL_MODE_EXISTING:
        return KOMETA_INSTALL_MODE_EXISTING
    if raw == KOMETA_INSTALL_MODE_EXTERNAL:
        return KOMETA_INSTALL_MODE_EXTERNAL
    return KOMETA_INSTALL_MODE_MANAGED


def canonicalize_kometa_section(section_data):
    section = dict(section_data) if isinstance(section_data, dict) else {}
    canonical = {
        "install_mode": KOMETA_INSTALL_MODE_MANAGED,
        "existing_root": "",
        "external_config_root": "",
        "external_log_root": "",
    }
    canonical.update(section)
    canonical["install_mode"] = normalize_kometa_install_mode(canonical.get("install_mode"))
    canonical["existing_root"] = str(canonical.get("existing_root") or "").strip()
    canonical["external_config_root"] = str(canonical.get("external_config_root") or "").strip()
    canonical["external_log_root"] = str(canonical.get("external_log_root") or "").strip()
    if canonical["install_mode"] != KOMETA_INSTALL_MODE_EXISTING:
        canonical["existing_root"] = ""
    if canonical["install_mode"] != KOMETA_INSTALL_MODE_EXTERNAL:
        canonical["external_config_root"] = ""
        canonical["external_log_root"] = ""
    return canonical


def resolve_kometa_selection(section_data=None):
    section = canonicalize_kometa_section(section_data)
    managed_root = default_managed_kometa_root().resolve()
    managed_config_dir = managed_root / "config"
    managed_log_dir = managed_config_dir / "logs"
    mode = section["install_mode"]
    existing_root_raw = section.get("existing_root", "")
    external_config_root_raw = section.get("external_config_root", "")
    external_log_root_raw = section.get("external_log_root", "")
    selected_root = managed_root
    primary_path = managed_root
    config_dir = managed_config_dir
    log_dir = managed_log_dir
    selection_valid = True
    status_message = "Quickstart will create and manage its own Kometa install under this workspace."
    mode_label = "Quickstart-managed install"
    can_launch = True
    can_update = True
    can_probe_runtime = True
    can_read_logs = True
    can_sync_config = True
    can_sync_managed_artifacts = True

    if mode == KOMETA_INSTALL_MODE_EXISTING:
        selection_valid = False
        status_message = (
            "Quickstart will use an existing Kometa install visible from this environment. Quickstart will not update that install; update it manually outside Quickstart."
        )
        mode_label = "Existing direct install"
        can_update = False
        if existing_root_raw:
            resolved_existing = helpers.resolve_user_dir(existing_root_raw)
            if resolved_existing:
                selected_root = resolved_existing
                primary_path = resolved_existing
                config_dir = resolved_existing / "config"
                log_dir = config_dir / "logs"
                selection_valid = True
                if not resolved_existing.exists():
                    status_message = "The selected existing Kometa path is saved, but it is not currently visible from this Quickstart environment."
                else:
                    status_message = (
                        "Quickstart will use the selected existing Kometa install. Quickstart can validate and launch it, but updates must be done manually outside Quickstart."
                    )
            else:
                selected_root = None
                primary_path = None
                config_dir = None
                log_dir = None
                status_message = "The saved existing Kometa path is invalid."
        else:
            selected_root = None
            primary_path = None
            config_dir = None
            log_dir = None
            status_message = "Choose an existing Kometa path for this config before using the Kometa run page."
    elif mode == KOMETA_INSTALL_MODE_EXTERNAL:
        selected_root = None
        primary_path = None
        config_dir = None
        log_dir = None
        selection_valid = False
        mode_label = "External/containerized config+logs"
        can_launch = False
        can_update = False
        can_probe_runtime = False
        can_sync_config = True
        can_sync_managed_artifacts = True
        status_message = "Quickstart will manage config and optional logs for an external Kometa runtime. It will not launch or update Kometa directly."
        if external_config_root_raw:
            resolved_config = helpers.resolve_user_dir(external_config_root_raw)
            if resolved_config:
                primary_path = resolved_config
                config_dir = resolved_config
                selection_valid = True
                if external_log_root_raw:
                    resolved_log = helpers.resolve_user_dir(external_log_root_raw)
                    if resolved_log:
                        log_dir = resolved_log
                    else:
                        selection_valid = False
                else:
                    log_dir = resolved_config / "logs"
                can_read_logs = bool(log_dir)
                if not resolved_config.exists():
                    status_message = "The selected external Kometa config path is saved, but it is not currently visible from this Quickstart environment."
                else:
                    status_message = "Quickstart will sync generated config and managed artifacts to the selected external Kometa config path."
                if log_dir and not log_dir.exists():
                    can_read_logs = False
                    status_message += " Log viewing and logscan will stay limited until the log path is accessible."
            else:
                status_message = "The saved external Kometa config path is invalid."
        else:
            status_message = "Choose the external Kometa config path for this config before using the Kometa run page."

    return {
        "install_mode": mode,
        "existing_root": existing_root_raw,
        "external_config_root": external_config_root_raw,
        "external_log_root": external_log_root_raw,
        "managed_root": managed_root,
        "managed_config_dir": managed_config_dir,
        "managed_log_dir": managed_log_dir,
        "selected_root": selected_root,
        "primary_path": primary_path,
        "config_dir": config_dir,
        "log_dir": log_dir,
        "selection_valid": selection_valid,
        "status_message": status_message,
        "is_managed": mode == KOMETA_INSTALL_MODE_MANAGED,
        "is_external": mode == KOMETA_INSTALL_MODE_EXTERNAL,
        "mode_label": mode_label,
        "can_launch": can_launch,
        "can_update": can_update,
        "can_probe_runtime": can_probe_runtime,
        "can_read_logs": can_read_logs,
        "can_sync_config": can_sync_config,
        "can_sync_managed_artifacts": can_sync_managed_artifacts,
    }


def get_kometa_settings_section(config_name=None):
    resolved_config = config_name or persistence.ensure_session_config_name()
    settings = persistence.retrieve_settings_for_config(resolved_config, "900-kometa") or {}
    section = settings.get("kometa", {}) if isinstance(settings, dict) else {}
    return settings, canonicalize_kometa_section(section)


def apply_kometa_selection(selection):
    selection = selection if isinstance(selection, dict) else {}
    mode = normalize_kometa_install_mode(selection.get("install_mode"))
    selected_root = selection.get("selected_root")
    config_dir = selection.get("config_dir")
    log_dir = selection.get("log_dir")
    resolved_root = Path(selected_root).resolve() if selected_root else None
    resolved_config_dir = Path(config_dir).resolve() if config_dir else None
    resolved_log_dir = Path(log_dir).resolve() if log_dir else None
    fallback_root = None
    if resolved_root is None and resolved_config_dir is not None:
        fallback_root = resolved_config_dir.parent if resolved_config_dir.name.lower() == "config" else resolved_config_dir

    if has_request_context():
        session["kometa_install_mode"] = mode
        session["kometa_root"] = resolved_root.as_posix() if resolved_root else (fallback_root.as_posix() if fallback_root else "")
        session["kometa_config_dir"] = resolved_config_dir.as_posix() if resolved_config_dir else ""
        session["kometa_log_dir"] = resolved_log_dir.as_posix() if resolved_log_dir else ""

    if resolved_root:
        app.config["KOMETA_ROOT"] = str(resolved_root)
    elif fallback_root:
        app.config["KOMETA_ROOT"] = str(fallback_root)
    app.config["KOMETA_INSTALL_MODE"] = mode
    app.config["KOMETA_CONFIG_DIR"] = str(resolved_config_dir) if resolved_config_dir else ""
    app.config["KOMETA_LOG_DIR"] = str(resolved_log_dir) if resolved_log_dir else ""


def build_kometa_install_context(config_name=None):
    _settings, section = get_kometa_settings_section(config_name)
    selection = resolve_kometa_selection(section)
    apply_kometa_selection(selection)
    selected_root = selection.get("selected_root")
    primary_path = selection.get("primary_path")
    config_dir = selection.get("config_dir")
    log_dir = selection.get("log_dir")
    return {
        "kometa_install_mode": selection["install_mode"],
        "kometa_existing_root": selection["existing_root"],
        "kometa_external_config_root": selection["external_config_root"],
        "kometa_external_log_root": selection["external_log_root"],
        "kometa_managed_root": selection["managed_root"].as_posix(),
        "kometa_managed_root_display": str(selection["managed_root"]),
        "kometa_managed_config_dir": selection["managed_config_dir"].as_posix(),
        "kometa_managed_config_dir_display": str(selection["managed_config_dir"]),
        "kometa_managed_log_dir": selection["managed_log_dir"].as_posix(),
        "kometa_managed_log_dir_display": str(selection["managed_log_dir"]),
        "kometa_selected_root": selected_root.as_posix() if selected_root else "",
        "kometa_selected_root_display": str(selected_root) if selected_root else "",
        "kometa_primary_path": primary_path.as_posix() if primary_path else "",
        "kometa_primary_path_display": str(primary_path) if primary_path else "",
        "kometa_active_config_dir": config_dir.as_posix() if config_dir else "",
        "kometa_active_config_dir_display": str(config_dir) if config_dir else "",
        "kometa_active_log_dir": log_dir.as_posix() if log_dir else "",
        "kometa_active_log_dir_display": str(log_dir) if log_dir else "",
        "kometa_selection_valid": bool(selection["selection_valid"]),
        "kometa_install_status_message": selection["status_message"],
        "kometa_is_managed_install": bool(selection["is_managed"]),
        "kometa_is_external_install": bool(selection["is_external"]),
        "kometa_mode_label": selection["mode_label"],
        "kometa_can_launch": bool(selection["can_launch"]),
        "kometa_can_update": bool(selection["can_update"]),
        "kometa_can_probe_runtime": bool(selection["can_probe_runtime"]),
        "kometa_can_read_logs": bool(selection["can_read_logs"]),
        "kometa_can_sync_config": bool(selection["can_sync_config"]),
        "kometa_can_sync_managed_artifacts": bool(selection["can_sync_managed_artifacts"]),
    }


def resolve_kometa_request_target(payload, logs=None, require_existing_root=False):
    request_payload = payload if isinstance(payload, dict) else {}
    config_name = persistence.resolve_request_config_name(request_payload)
    _settings, stored_section = get_kometa_settings_section(config_name)
    requested_mode = request_payload.get("install_mode")
    install_mode = normalize_kometa_install_mode(requested_mode if requested_mode not in [None, ""] else stored_section.get("install_mode"))
    raw_path = str(request_payload.get("path") or "").strip()
    existing_root = str(request_payload.get("existing_root") or stored_section.get("existing_root") or "").strip()
    external_config_root = str(request_payload.get("external_config_root") or stored_section.get("external_config_root") or "").strip()
    external_log_root = str(request_payload.get("external_log_root") or stored_section.get("external_log_root") or "").strip()

    if install_mode == KOMETA_INSTALL_MODE_MANAGED:
        selection = resolve_kometa_selection({"install_mode": KOMETA_INSTALL_MODE_MANAGED})
        if raw_path:
            resolved_managed = helpers.resolve_user_dir(raw_path)
            if not resolved_managed:
                if logs is not None:
                    logs.append("❌ Invalid path provided.")
                return {"error": "Invalid path provided."}
            selection["selected_root"] = resolved_managed
            selection["primary_path"] = resolved_managed
            selection["config_dir"] = resolved_managed / "config"
            selection["log_dir"] = selection["config_dir"] / "logs"
            selection["selection_valid"] = True
        apply_kometa_selection(selection)
        return {
            "config_name": config_name,
            "install_mode": install_mode,
            "path_obj": selection["selected_root"],
            "runtime_root": selection["selected_root"],
            "config_dir": selection["config_dir"],
            "log_dir": selection["log_dir"],
            "existing_root": "",
            "external_config_root": "",
            "external_log_root": "",
            "selection_valid": True,
        }

    if install_mode == KOMETA_INSTALL_MODE_EXTERNAL:
        candidate = raw_path or external_config_root
        if not candidate:
            if logs is not None:
                logs.append("❌ External Kometa mode requires a config path.")
            return {"error": "External Kometa mode requires a config path."}

        resolved_config = helpers.resolve_user_dir(candidate)
        if not resolved_config:
            if logs is not None:
                logs.append("❌ Invalid external config path provided.")
            return {"error": "Invalid external config path provided."}

        resolved_log = None
        if external_log_root:
            resolved_log = helpers.resolve_user_dir(external_log_root)
            if not resolved_log:
                if logs is not None:
                    logs.append("❌ Invalid external log path provided.")
                return {"error": "Invalid external log path provided."}

        if require_existing_root and not resolved_config.exists():
            if logs is not None:
                logs.append("❌ The selected external Kometa config path does not exist in this Quickstart environment.")
            return {"error": "The selected external Kometa config path does not exist in this Quickstart environment."}

        selection = resolve_kometa_selection(
            {
                "install_mode": KOMETA_INSTALL_MODE_EXTERNAL,
                "external_config_root": candidate,
                "external_log_root": external_log_root,
            }
        )
        apply_kometa_selection(selection)
        return {
            "config_name": config_name,
            "install_mode": install_mode,
            "path_obj": selection["config_dir"],
            "runtime_root": None,
            "config_dir": selection["config_dir"],
            "log_dir": selection["log_dir"],
            "existing_root": "",
            "external_config_root": candidate,
            "external_log_root": external_log_root,
            "selection_valid": selection["selection_valid"],
        }

    candidate = raw_path or existing_root
    if not candidate:
        if logs is not None:
            logs.append("❌ Existing Kometa mode requires a path.")
        return {"error": "Existing Kometa mode requires a path."}

    resolved_existing = helpers.resolve_user_dir(candidate)
    if not resolved_existing:
        if logs is not None:
            logs.append("❌ Invalid path provided.")
        return {"error": "Invalid path provided."}

    if require_existing_root and not resolved_existing.exists():
        if logs is not None:
            logs.append("❌ The selected existing Kometa path does not exist in this Quickstart environment.")
        return {"error": "The selected existing Kometa path does not exist in this Quickstart environment."}

    selection = resolve_kometa_selection(
        {
            "install_mode": KOMETA_INSTALL_MODE_EXISTING,
            "existing_root": candidate,
        }
    )
    apply_kometa_selection(selection)
    return {
        "config_name": config_name,
        "install_mode": install_mode,
        "path_obj": selection["selected_root"],
        "runtime_root": selection["selected_root"],
        "config_dir": selection["config_dir"],
        "log_dir": selection["log_dir"],
        "existing_root": candidate,
        "external_config_root": "",
        "external_log_root": "",
        "selection_valid": resolved_existing.exists(),
    }


def validate_existing_kometa_root(path_obj):
    p = Path(path_obj).resolve()
    missing = []
    if not p.exists():
        missing.append("path")
    if not (p / "config").exists():
        missing.append("config")
    if not (p / "kometa.py").exists():
        missing.append("kometa.py")
    if not (p / "requirements.txt").exists():
        missing.append("requirements.txt")
    return missing


def validate_saved_kometa_selection(section_data):
    section = canonicalize_kometa_section(section_data)
    install_mode = section.get("install_mode")

    if install_mode == KOMETA_INSTALL_MODE_MANAGED:
        return True, None, None

    if install_mode == KOMETA_INSTALL_MODE_EXISTING:
        existing_root = str(section.get("existing_root") or "").strip()
        if not existing_root:
            return False, "missing_location", "Choose the Kometa root folder that contains kometa.py, requirements.txt, and config/."
        resolved_existing = helpers.resolve_user_dir(existing_root)
        if not resolved_existing:
            return False, "invalid_paths", [f"Saved existing Kometa root is invalid. Path: {existing_root}"]
        if not resolved_existing.exists():
            return False, "invalid_paths", [f"Existing Kometa root does not exist. Path: {resolved_existing}"]
        missing = validate_existing_kometa_root(resolved_existing)
        if missing:
            if "path" in missing:
                return False, "invalid_paths", [f"Existing Kometa root does not exist. Path: {resolved_existing}"]
            missing_labels = []
            if "kometa.py" in missing:
                missing_labels.append("kometa.py")
            if "requirements.txt" in missing:
                missing_labels.append("requirements.txt")
            if "config" in missing:
                missing_labels.append("config/")
            label_text = ", ".join(missing_labels) if missing_labels else ", ".join(missing)
            return False, "invalid_paths", [f"Existing Kometa root is missing required items: {label_text}. Path: {resolved_existing}"]
        return True, None, None

    external_config_root = str(section.get("external_config_root") or "").strip()
    external_log_root = str(section.get("external_log_root") or "").strip()
    if not external_config_root:
        return False, "missing_location", "Choose the external Kometa config path Quickstart should use for this config."
    resolved_external_config = helpers.resolve_user_dir(external_config_root)
    if not resolved_external_config:
        return False, "invalid_paths", [f"Saved external Kometa config path is invalid. Path: {external_config_root}"]
    if not resolved_external_config.exists() or not resolved_external_config.is_dir():
        return False, "invalid_paths", [f"External Kometa config path does not exist. Path: {resolved_external_config}"]
    if external_log_root:
        resolved_external_log = helpers.resolve_user_dir(external_log_root)
        if not resolved_external_log:
            return False, "invalid_paths", [f"Saved external Kometa log path is invalid. Path: {external_log_root}"]
        if not resolved_external_log.exists() or not resolved_external_log.is_dir():
            return False, "invalid_paths", [f"External Kometa log path does not exist. Path: {resolved_external_log}"]
    return True, None, None


def _config_name_from_yaml_filename(filename: str | None) -> str | None:
    text = str(filename or "").strip()
    if not text:
        return None
    base = Path(text).name
    lowered = base.lower()
    if lowered.endswith("_config.yml"):
        return base[:-11]
    if lowered.endswith("_config.yaml"):
        return base[:-12]
    return None


def sync_generated_yaml_and_assets_to_kometa_config(config_dir, config_filename, logs=None):
    target_config_dir = Path(config_dir).resolve()

    def log(msg):
        if logs is not None:
            logs.append(msg)

    config_name = helpers.safe_rel_path(config_filename or "kometa")
    if not config_name:
        raise ValueError("Invalid config filename.")

    src_yaml = helpers.safe_join(Path("config"), config_name)
    if not src_yaml or not src_yaml.exists():
        raise FileNotFoundError(f"Generated YAML not found: {src_yaml}")

    target_config_dir.mkdir(parents=True, exist_ok=True)
    dest_yaml = helpers.safe_join(target_config_dir, config_name)
    if not dest_yaml:
        raise ValueError("Invalid config destination.")

    shutil.copy2(src_yaml, dest_yaml)
    log(f"✅ YAML copied to Kometa config folder at: {dest_yaml}")

    yaml_parser = YAML(typ="safe")
    with src_yaml.open("r", encoding="utf-8") as f:
        parsed_config = yaml_parser.load(f) or {}
    active_config_name = session.get("config_name") if has_request_context() else None
    config_scope = _config_name_from_yaml_filename(config_name) or active_config_name
    font_refs = helpers.collect_font_references(parsed_config)
    if font_refs:
        font_result = helpers.copy_fonts_to_kometa(font_refs, kometa_config_dir=target_config_dir, config_name=config_scope)
        copied = font_result.get("copied", [])
        missing = font_result.get("missing", [])
        errors = font_result.get("errors", [])
        if copied:
            log(f"✅ Synced {len(copied)} font(s) referenced in the config to Kometa fonts.")
        if missing:
            log(f"⚠️ Fonts referenced in the config not found: {', '.join(missing)}")
        for err in errors:
            log(f"⚠️ {err}")
    if config_scope:
        artifact_result = helpers.sync_managed_library_artifacts_to_kometa(config_scope, kometa_config_dir=target_config_dir)
        synced = artifact_result.get("synced", [])
        removed = artifact_result.get("removed", [])
        errors = artifact_result.get("errors", [])
        if synced:
            log(f"✅ Synced {len(synced)} managed library artifact tree(s) to Kometa config/{config_scope}.")
        if removed:
            log(f"ℹ️ Removed {len(removed)} stale managed library artifact tree(s) from Kometa config/{config_scope}.")
        for err in errors:
            log(f"⚠️ {err}")

    return {"config_filename": config_name, "destination": dest_yaml}


def probe_kometa_root_state(path_obj):
    p = Path(path_obj)
    kometa_root_posix = p.as_posix()
    kometa_root_display = str(p)
    is_windows = sys.platform.startswith("win")
    venv_dir = p / "kometa-venv"
    bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
    python_bin = bin_dir / ("python.exe" if is_windows else "python")
    version_path = p / "VERSION"
    kometa_py = p / "kometa.py"
    requirements = p / "requirements.txt"
    config_dir = p / "config"
    version_value = "Unknown"
    if version_path.exists():
        try:
            version_value = version_path.read_text(encoding="utf-8").strip() or "Unknown"
        except Exception:
            version_value = "Unknown"

    return {
        "kometa_root": kometa_root_posix,
        "kometa_root_display": kometa_root_display,
        "venv_python": python_bin.as_posix(),
        "venv_python_display": str(python_bin),
        "kometa_version": version_value,
        "root_exists": p.exists(),
        "config_dir_exists": config_dir.exists(),
        "kometa_installed": kometa_py.exists() and requirements.exists(),
        "venv_exists": venv_dir.exists(),
        "venv_python_exists": python_bin.exists(),
        "kometa_running": helpers.is_kometa_running(),
    }
