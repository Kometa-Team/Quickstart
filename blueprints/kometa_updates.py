import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from modules import database, helpers, kometa_install, persistence
from modules.background_jobs import (
    JOB_TARGET_PAGES,
    clear_active_background_job,
    complete_background_job,
    create_background_job,
    fail_background_job,
    get_active_background_job,
    get_background_job,
    update_background_job,
)

bp = Blueprint("kometa_updates", __name__)


@bp.route("/save-kometa-install-mode", methods=["POST"])
def save_kometa_install_mode():
    payload = request.get_json(silent=True) or {}
    config_name = persistence.resolve_request_config_name(payload)
    install_mode = kometa_install.normalize_kometa_install_mode(payload.get("install_mode"))
    existing_root = str(payload.get("existing_root") or "").strip()
    external_config_root = str(payload.get("external_config_root") or "").strip()
    external_log_root = str(payload.get("external_log_root") or "").strip()
    managed_root = kometa_install.default_managed_kometa_root().resolve()

    if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
        if not existing_root:
            return jsonify(success=False, error="Choose the existing Kometa path Quickstart should use for this config."), 400
        resolved_existing = helpers.resolve_user_dir(existing_root)
        if not resolved_existing:
            return jsonify(success=False, error="The existing Kometa path is invalid."), 400
        if not resolved_existing.exists():
            return jsonify(success=False, error="The selected existing Kometa path does not exist in this Quickstart environment."), 400
        missing = kometa_install.validate_existing_kometa_root(resolved_existing)
        if missing:
            if "kometa.py" in missing or "requirements.txt" in missing or "config" in missing:
                return (
                    jsonify(
                        success=False,
                        error="Choose the Kometa root folder that contains kometa.py, requirements.txt, and config/.",
                    ),
                    400,
                )
        section_payload_update = {
            "install_mode": install_mode,
            "existing_root": existing_root,
            "external_config_root": "",
            "external_log_root": "",
        }
    elif install_mode == kometa_install.KOMETA_INSTALL_MODE_EXTERNAL:
        if not external_config_root:
            return jsonify(success=False, error="Choose the external Kometa config path Quickstart should use for this config."), 400
        resolved_external_config = helpers.resolve_user_dir(external_config_root)
        if not resolved_external_config:
            return jsonify(success=False, error="The external Kometa config path is invalid."), 400
        if not resolved_external_config.exists() or not resolved_external_config.is_dir():
            return jsonify(success=False, error="The selected external Kometa config path does not exist in this Quickstart environment."), 400
        if external_log_root:
            resolved_external_log = helpers.resolve_user_dir(external_log_root)
            if not resolved_external_log:
                return jsonify(success=False, error="The external Kometa log path is invalid."), 400
        section_payload_update = {
            "install_mode": install_mode,
            "existing_root": "",
            "external_config_root": external_config_root,
            "external_log_root": external_log_root,
        }
    else:
        existing_root = ""
        external_config_root = ""
        external_log_root = ""
        section_payload_update = {
            "install_mode": install_mode,
            "existing_root": "",
            "external_config_root": "",
            "external_log_root": "",
        }

    stored_validated, stored_user_entered, stored_payload = database.retrieve_section_data(config_name, "kometa")
    section_payload = stored_payload if isinstance(stored_payload, dict) else {}
    section_payload["kometa"] = kometa_install.canonicalize_kometa_section(
        {
            **(section_payload.get("kometa") if isinstance(section_payload.get("kometa"), dict) else {}),
            **section_payload_update,
        }
    )
    section_payload = persistence.apply_validation_metadata(section_payload, "validated")
    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=True,
        user_entered=True,
        data=section_payload,
    )
    selection = kometa_install.resolve_kometa_selection(section_payload["kometa"])
    kometa_install.apply_kometa_selection(selection)

    if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
        message = "Quickstart will now use the selected existing Kometa install for this config."
    elif install_mode == kometa_install.KOMETA_INSTALL_MODE_EXTERNAL:
        message = "Quickstart will now sync config and optional logs for the selected external Kometa setup."
    else:
        message = "Quickstart will now use its managed Kometa install for this config."
    return jsonify(
        success=True,
        message=message,
        install_mode=install_mode,
        kometa_root=selection["selected_root"].as_posix() if selection.get("selected_root") else "",
        kometa_root_display=str(selection["selected_root"]) if selection.get("selected_root") else "",
        kometa_primary_path=selection["primary_path"].as_posix() if selection.get("primary_path") else "",
        kometa_primary_path_display=str(selection["primary_path"]) if selection.get("primary_path") else "",
        kometa_config_dir=selection["config_dir"].as_posix() if selection.get("config_dir") else "",
        kometa_config_dir_display=str(selection["config_dir"]) if selection.get("config_dir") else "",
        kometa_log_dir=selection["log_dir"].as_posix() if selection.get("log_dir") else "",
        kometa_log_dir_display=str(selection["log_dir"]) if selection.get("log_dir") else "",
        managed_root=managed_root.as_posix(),
        managed_root_display=str(managed_root),
        existing_root=existing_root,
        external_config_root=external_config_root,
        external_log_root=external_log_root,
        can_launch=selection.get("can_launch"),
        can_update=selection.get("can_update"),
        can_probe_runtime=selection.get("can_probe_runtime"),
        can_read_logs=selection.get("can_read_logs"),
    )


@bp.route("/validate-kometa-root", methods=["POST"])
def validate_kometa_root():
    payload = request.get_json(silent=True) or {}
    logs = []

    def log(msg):
        print(msg, file=sys.stderr)
        logs.append(msg)

    target = kometa_install.resolve_kometa_request_target(payload, logs=logs, require_existing_root=True)
    if target.get("error"):
        return jsonify(success=False, error=target["error"], log=logs), 400
    install_mode = target["install_mode"]
    p = target["path_obj"]
    config_dir = target.get("config_dir")
    log_dir = target.get("log_dir")

    if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXTERNAL:
        if not p or not p.exists() or not p.is_dir():
            log("❌ The selected external Kometa config path does not exist in this Quickstart environment.")
            return jsonify(success=False, error="The selected external Kometa config path does not exist in this Quickstart environment.", log=logs), 400
        log(f"🔍 Checking external Kometa config path: {p}")
        if log_dir and Path(log_dir).exists():
            log(f"📄 External Kometa logs are accessible at: {log_dir}")
        else:
            log("ℹ️ External Kometa logs are not currently accessible from this Quickstart environment.")
        try:
            sync_result = kometa_install.sync_generated_yaml_and_assets_to_kometa_config(config_dir, payload.get("config_name", "kometa"), logs=logs)
        except FileNotFoundError:
            log("❌ Generated YAML not found.")
            return jsonify(success=False, error="Generated YAML not found.", log=logs), 500
        except ValueError as exc:
            log(f"❌ {exc}")
            return jsonify(success=False, error=str(exc), log=logs), 400
        except Exception as exc:
            log(f"⚠️ Failed to sync config-owned assets referenced in the config: {exc}")
            return jsonify(success=False, error="Failed to sync generated config to the external Kometa config path.", log=logs), 500
        log("✅ External Kometa config path is valid and synced.")
        return (
            jsonify(
                success=True,
                kometa_root="",
                kometa_root_display="",
                kometa_config_dir=Path(config_dir).resolve().as_posix() if config_dir else "",
                kometa_config_dir_display=str(Path(config_dir).resolve()) if config_dir else "",
                kometa_log_dir=Path(log_dir).resolve().as_posix() if log_dir else "",
                kometa_log_dir_display=str(Path(log_dir).resolve()) if log_dir else "",
                venv_python="",
                venv_python_display="",
                kometa_version="External / unmanaged",
                external_mode=True,
                log=logs,
                synced_config=str(sync_result.get("destination")),
            ),
            200,
        )

    # Auto-create the Kometa root and config/ if missing
    if install_mode == kometa_install.KOMETA_INSTALL_MODE_MANAGED and not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
            log(f"📁 Created Kometa root: {p}")
        except Exception as e:
            log(f"❌ Failed to create Kometa root: {e}")
            return jsonify(success=False, error="Failed to create Kometa root.", log=logs), 500
    elif install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING and not p.exists():
        log("❌ The selected existing Kometa path does not exist in this Quickstart environment.")
        return jsonify(success=False, error="The selected existing Kometa path does not exist in this Quickstart environment.", log=logs), 400
    elif install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
        missing = kometa_install.validate_existing_kometa_root(p)
        if missing:
            log("❌ The selected existing Kometa path does not look like a Kometa root.")
            log("ℹ️ Choose the folder that contains kometa.py, requirements.txt, and config/.")
            return (
                jsonify(
                    success=False,
                    error="Choose the Kometa root folder that contains kometa.py, requirements.txt, and config/.",
                    log=logs,
                ),
                400,
            )

    try:
        if install_mode == kometa_install.KOMETA_INSTALL_MODE_MANAGED:
            (p / "config").mkdir(parents=True, exist_ok=True)
        elif not (p / "config").exists():
            log("❌ The selected existing Kometa path is missing its config folder.")
            return jsonify(success=False, error="The selected existing Kometa path is missing its config folder.", log=logs), 400
    except Exception as e:
        log(f"❌ Failed to create config folder: {e}")
        return jsonify(success=False, error="Failed to create config folder.", log=logs), 500

    # Keep POSIX (internal) and native (display) versions
    kometa_root_posix = p.as_posix()
    kometa_root_display = str(p)  # native (Windows => backslashes)
    session["kometa_root"] = kometa_root_posix  # store normalized internally

    log(f"🔍 Checking path: {kometa_root_display}")

    # --- External tool check (python is required) ---
    missing_tools = []
    if shutil.which("python") is None and shutil.which("python3") is None:
        missing_tools.append("python or python3")

    if missing_tools:
        for tool in missing_tools:
            log(f"❌ Required tool not found: {tool}")
        return jsonify(success=False, error=f"Missing required tools: {', '.join(missing_tools)}", log=logs), 400

    log("✅ All required external tools are available.")

    # Python version (best-effort)
    try:
        python_cmd = shutil.which("python") or shutil.which("python3")
        version_output = subprocess.check_output([python_cmd, "--version"], stderr=subprocess.STDOUT, text=True)
        log(f"🐍 Detected Python version: {version_output.strip()}")
    except Exception as e:
        log(f"⚠️ Failed to detect Python version: {e}")

    # Git version (optional/best-effort)
    try:
        git_output = subprocess.check_output(["git", "--version"], stderr=subprocess.STDOUT, text=True)
        log(f"🔧 Detected Git version: {git_output.strip()}")
    except Exception as e:
        log(f"⚠️ Failed to detect Git version: {e}")

    # --- Kometa files check (if you're expecting them to already be present) ---
    kometa_version = "Unknown"
    version_path = p / "VERSION"
    if version_path.exists():
        try:
            kometa_version = version_path.read_text(encoding="utf-8").strip()
            log(f"📦 Kometa version detected: {kometa_version}")
        except Exception as e:
            log(f"⚠️ Failed to read VERSION file: {e}")

    required_files = ["kometa.py", "requirements.txt"]
    for fname in required_files:
        fpath = p / fname
        if not fpath.exists():
            log(f"❌ Required file missing: {fname}")
            return jsonify(success=False, error=f"{fname} not found.", log=logs), 400
        log(f"✔️ Found required file: {fname}")

    # --- Virtualenv & deps under <root>/kometa-venv ---
    is_windows = sys.platform.startswith("win")
    venv_dir = p / "kometa-venv"
    bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
    python_bin = bin_dir / ("python.exe" if is_windows else "python")
    pip_bin = bin_dir / ("pip.exe" if is_windows else "pip")

    if not venv_dir.exists():
        log("📦 Creating virtual environment...")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
            log("✅ Virtual environment created.")
        except subprocess.CalledProcessError as e:
            log(f"❌ Failed to create venv: {str(e)}")
            return jsonify(success=False, error="Failed to create venv.", log=logs), 500
    else:
        log("ℹ️ Virtual environment already exists.")

    if not pip_bin.exists():
        log(f"❌ pip not found in venv at {pip_bin}")
        return jsonify(success=False, error=f"pip not found in {pip_bin}", log=logs), 500

    log("⬆️ Checking pip version and attempting upgrade...")
    try:
        result = subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        output = result.stdout.strip()
        log("ℹ️ pip is already up to date." if "Requirement already satisfied" in output else "✅ pip upgraded.")
        for line in output.splitlines():
            log(f"    {line}")
    except subprocess.CalledProcessError as e:
        log(f"❌ pip upgrade failed: {e}")
        return jsonify(success=False, error="pip upgrade failed.", log=logs), 500

    log("📦 Installing requirements.txt...")
    try:
        result = subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-r", str(p / "requirements.txt")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
        )
        output = result.stdout.strip()
        log(
            "ℹ️ All requirements are already satisfied."
            if "Requirement already satisfied" in output and "Successfully installed" not in output
            else "✅ requirements.txt installed or updated."
        )
        for line in output.splitlines():
            log(f"    {line}")
    except subprocess.CalledProcessError as e:
        log(f"❌ Error installing requirements: {str(e)}")
        return jsonify(success=False, error="Failed pip install.", log=logs), 500

    try:
        kometa_install.sync_generated_yaml_and_assets_to_kometa_config(p / "config", payload.get("config_name", "kometa"), logs=logs)
    except FileNotFoundError:
        log("❌ Generated YAML not found.")
        return jsonify(success=False, error="Generated YAML not found.", log=logs), 500
    except ValueError as exc:
        log(f"❌ {exc}")
        return jsonify(success=False, error=str(exc), log=logs), 400
    except Exception as e:
        log(f"⚠️ Failed to sync config-owned assets referenced in the config: {e}")

    log("✅ Kometa root is valid and ready.")

    return (
        jsonify(
            success=True,
            # internal normalized for any future backend use
            kometa_root=kometa_root_posix,
            venv_python=python_bin.as_posix(),
            # native-display for UI/command builder
            kometa_root_display=kometa_root_display,
            venv_python_display=str(python_bin),
            kometa_version=kometa_version,
            log=logs,
        ),
        200,
    )


@bp.route("/probe-kometa-root", methods=["POST"])
def probe_kometa_root():
    payload = request.get_json(silent=True) or {}
    logs = []

    def log(msg):
        print(msg, file=sys.stderr)
        logs.append(msg)

    target = kometa_install.resolve_kometa_request_target(payload, logs=logs, require_existing_root=False)
    if target.get("error"):
        return jsonify(success=False, error=target["error"], log=logs), 400
    if target.get("install_mode") == kometa_install.KOMETA_INSTALL_MODE_EXTERNAL:
        config_dir = target.get("config_dir")
        log_dir = target.get("log_dir")
        state = {
            "kometa_root": "",
            "kometa_root_display": "",
            "kometa_config_dir": Path(config_dir).resolve().as_posix() if config_dir else "",
            "kometa_config_dir_display": str(Path(config_dir).resolve()) if config_dir else "",
            "kometa_log_dir": Path(log_dir).resolve().as_posix() if log_dir else "",
            "kometa_log_dir_display": str(Path(log_dir).resolve()) if log_dir else "",
            "venv_python": "",
            "venv_python_display": "",
            "kometa_version": "External / unmanaged",
            "root_exists": bool(config_dir and Path(config_dir).exists()),
            "config_dir_exists": bool(config_dir and Path(config_dir).exists()),
            "log_dir_exists": bool(log_dir and Path(log_dir).exists()),
            "kometa_installed": False,
            "venv_exists": False,
            "venv_python_exists": False,
            "kometa_running": False,
            "external_mode": True,
        }
        log(f"🔍 Probing external Kometa config path: {state['kometa_config_dir_display']}")
        if state["config_dir_exists"]:
            log("✅ External Kometa config path is accessible.")
        else:
            log("❌ External Kometa config path is not currently accessible.")
        if state["log_dir_exists"]:
            log(f"📄 External Kometa logs are accessible at: {state['kometa_log_dir_display']}")
        else:
            log("ℹ️ External Kometa log path is not currently accessible.")
        log("ℹ️ Quickstart cannot probe or launch the external Kometa runtime directly in this mode.")
        return jsonify(success=True, log=logs, **state), 200
    if target.get("install_mode") == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
        missing = kometa_install.validate_existing_kometa_root(target["path_obj"])
        if missing:
            log("❌ The selected existing Kometa path does not look like a Kometa root.")
            log("ℹ️ Choose the folder that contains kometa.py, requirements.txt, and config/.")
            return (
                jsonify(
                    success=False,
                    error="Choose the Kometa root folder that contains kometa.py, requirements.txt, and config/.",
                    log=logs,
                ),
                400,
            )
    p = target["path_obj"]

    import quickstart

    state = quickstart._probe_kometa_root_state(p)
    log(f"🔍 Probing Kometa path: {state['kometa_root_display']}")
    if not state["root_exists"]:
        log("ℹ️ Kometa root does not exist yet. Install required.")
    elif not state["kometa_installed"]:
        log("ℹ️ Kometa files not found yet. Install required.")
    else:
        log("✅ Kometa files detected locally.")
        if state["kometa_version"]:
            log(f"📦 Local Kometa version: {state['kometa_version']}")
        if state["venv_python_exists"]:
            log(f"🐍 Kometa venv python detected at: {state['venv_python_display']}")
        else:
            log("ℹ️ Kometa venv python not present yet. Prepare step still needed.")
    if state["kometa_running"]:
        log("ℹ️ Kometa is currently running.")

    return jsonify(success=True, log=logs, **state), 200


@bp.route("/check-kometa-update", methods=["POST"])
def check_kometa_update():
    payload = request.get_json(silent=True) or {}
    branch_override_raw = payload.get("branch_override")
    branch_override = helpers.normalize_kometa_branch_override(branch_override_raw)
    logs = []

    def log(msg):
        print(msg, file=sys.stderr)
        logs.append(msg)

    if branch_override_raw and not branch_override:
        log(f"❌ Invalid Kometa branch override: {branch_override_raw}")
        return jsonify(success=False, error="Invalid Kometa branch override.", log=logs), 400

    target = kometa_install.resolve_kometa_request_target(payload, logs=logs, require_existing_root=False)
    if target.get("error"):
        return jsonify(success=False, error=target["error"], log=logs), 400
    if target.get("install_mode") == kometa_install.KOMETA_INSTALL_MODE_EXTERNAL:
        config_dir = target.get("config_dir")
        log_dir = target.get("log_dir")
        log("ℹ️ Quickstart cannot check or update an external Kometa runtime in config/log-only mode.")
        return (
            jsonify(
                success=True,
                log=logs,
                update_check_completed=False,
                kometa_update_check_skipped=True,
                local_version="External / unmanaged",
                remote_version="",
                kometa_update_available=False,
                cached=False,
                kometa_installed=False,
                kometa_running=False,
                external_mode=True,
                kometa_root="",
                kometa_root_display="",
                kometa_config_dir=Path(config_dir).resolve().as_posix() if config_dir else "",
                kometa_config_dir_display=str(Path(config_dir).resolve()) if config_dir else "",
                kometa_log_dir=Path(log_dir).resolve().as_posix() if log_dir else "",
                kometa_log_dir_display=str(Path(log_dir).resolve()) if log_dir else "",
            ),
            200,
        )
    if target.get("install_mode") == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
        missing = kometa_install.validate_existing_kometa_root(target["path_obj"])
        if missing:
            log("❌ The selected existing Kometa path does not look like a Kometa root.")
            log("ℹ️ Choose the folder that contains kometa.py, requirements.txt, and config/.")
            return (
                jsonify(
                    success=False,
                    error="Choose the Kometa root folder that contains kometa.py, requirements.txt, and config/.",
                    log=logs,
                ),
                400,
            )
    p = target["path_obj"]

    import quickstart

    state = quickstart._probe_kometa_root_state(p)
    if not state["kometa_installed"]:
        log("ℹ️ Kometa is not installed yet; update check skipped.")
        return (
            jsonify(
                success=True,
                log=logs,
                update_check_completed=False,
                kometa_update_check_skipped=False,
                local_version=state["kometa_version"],
                remote_version="",
                kometa_update_available=False,
                cached=False,
                **state,
            ),
            200,
        )

    if state["kometa_running"]:
        log("ℹ️ Kometa is currently running; update check skipped.")
        return (
            jsonify(
                success=True,
                log=logs,
                update_check_completed=True,
                kometa_update_check_skipped=True,
                local_version=state["kometa_version"],
                remote_version="",
                kometa_update_available=False,
                cached=False,
                **state,
            ),
            200,
        )

    if branch_override:
        log(f"⚠️ Kometa branch override selected: {branch_override}")
    else:
        log("ℹ️ Kometa branch selection: auto")

    update_info = helpers.get_cached_kometa_update(
        p,
        force_refresh=helpers.booler(payload.get("force", False)),
        branch_override=branch_override,
    )
    local_version = update_info.get("local_version") or state["kometa_version"]
    remote_version = update_info.get("remote_version") or ""
    remote_branch = update_info.get("branch") or "nightly"
    local_branch = update_info.get("local_branch") or "unknown"
    local_sha = update_info.get("local_sha") or ""
    remote_sha = update_info.get("remote_sha") or ""
    comparison_basis = update_info.get("comparison_basis") or "version"
    remote_version_url = helpers.GITHUB_BASE_URL + f"/{remote_branch}/VERSION"
    log(f"🌐 Remote VERSION source: {remote_version_url}")
    log(f"ℹ️ Installed Kometa branch metadata: {local_branch}")
    if local_sha:
        log(f"🔎 Local Kometa SHA: {local_sha[:12]}")
    if remote_sha:
        log(f"🔎 Remote Kometa SHA: {remote_sha[:12]}")
    log(f"ℹ️ Update comparison basis: {comparison_basis}")
    if update_info.get("cached"):
        log("ℹ️ Using cached Kometa update lookup.")
    if update_info.get("update_available"):
        if update_info.get("branch_mismatch"):
            log(f"⚠️ Installed branch '{local_branch}' differs from selected branch '{remote_branch}'.")
        log(f"⬆️ Update available: {local_version} → {remote_version}")
    else:
        log(f"✅ Kometa is up to date: {local_version}")

    return (
        jsonify(
            success=True,
            log=logs,
            update_check_completed=True,
            kometa_update_check_skipped=False,
            local_version=local_version,
            remote_version=remote_version,
            kometa_update_available=bool(update_info.get("update_available")),
            cached=bool(update_info.get("cached")),
            **state,
        ),
        200,
    )


@bp.route("/update-kometa", methods=["POST"])
def update_kometa():
    import quickstart

    blocker = quickstart._get_active_work_blocker("kometa_update")
    if blocker:
        pid = blocker.get("pid")
        target_page = blocker.get("target_page")
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"Kometa is currently running (PID {pid}). Stop it before updating.",
                    "blocked_by": blocker.get("blocked_by"),
                    "pid": pid,
                    "target_page": target_page,
                }
            ),
            409,
        )
    try:
        data = request.get_json(silent=True) or {}
        target = kometa_install.resolve_kometa_request_target(data, require_existing_root=True)
        if target.get("error"):
            return jsonify({"success": False, "error": target["error"], "log": [f"❌ {target['error']}"]}), 400
        if target.get("install_mode") == kometa_install.KOMETA_INSTALL_MODE_EXTERNAL:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "External Kometa mode does not support runtime updates. Change to a managed or existing direct install on the Start page to update from Quickstart.",
                        "log": [
                            "❌ External Kometa mode does not support runtime updates.",
                            "ℹ️ Change to a managed or existing direct install on the Start page if Quickstart should update Kometa itself.",
                        ],
                    }
                ),
                400,
            )
        if target.get("install_mode") == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Existing direct Kometa installs must be updated manually outside Quickstart. Quickstart can validate and check version status, but it will not modify that install.",
                        "log": [
                            "❌ Existing direct Kometa installs are manual-update only in Quickstart.",
                            "ℹ️ Quickstart can validate and check version status for this install, but update it manually outside Quickstart to reduce the risk of runtime failures.",
                        ],
                    }
                ),
                400,
            )
        kometa_root = target["path_obj"]
        install_mode = target["install_mode"]
        branch_override_raw = data.get("branch_override")
        branch_override = helpers.normalize_kometa_branch_override(branch_override_raw)
        if branch_override_raw and not branch_override:
            return jsonify({"success": False, "error": "Invalid Kometa branch override.", "log": ["❌ Invalid Kometa branch override."]}), 400
        qs_branch = data.get("branch") or helpers.detect_git_branch(quickstart.app.root_path)
        kometa_branch = branch_override or ("master" if qs_branch == "master" else "nightly")
        force_update = helpers.booler(data.get("force", False))
        background = data.get("background") is True

        if background:
            active = get_active_background_job("kometa_update")
            if active:
                phase = active.get("phase")
                if phase and phase not in ["done", "error"]:
                    return (
                        jsonify(success=True, active=True, existing_job=True, job_id=active.get("job_id"), phase=phase),
                        200,
                    )
                clear_active_background_job("kometa_update", job_id=active.get("job_id"))

            job = create_background_job(
                "kometa_update",
                trigger="manual",
                phase="queued",
                status="running",
                target_page=JOB_TARGET_PAGES.get("kometa_update"),
                logs=[],
                done=False,
                success=False,
                up_to_date=False,
                skipped=False,
                force=force_update,
                qs_branch=qs_branch,
                kometa_branch=kometa_branch,
                started_epoch=time.time(),
            )
            job_id = job["job_id"]

            def worker():
                class _ProgressLog(list):
                    def append(self_inner, item):
                        super().append(item)
                        current = get_background_job(job_id) or {}
                        lines = list(current.get("logs") or [])
                        lines.append(item)
                        update_background_job(job_id, logs=lines)

                logs = _ProgressLog()
                update_background_job(job_id, phase="running", status="running")
                logs.append(f"🔎 Quickstart branch: {qs_branch}")
                logs.append(f"📍 Kometa install mode: {install_mode}")
                logs.append(f"📁 Target Kometa root: {kometa_root}")
                if branch_override:
                    logs.append(f"⚠️ Kometa branch override selected: {branch_override}")
                else:
                    logs.append("ℹ️ Kometa branch selection: auto")
                logs.append(f"⚙️ Kometa branch selected: {kometa_branch} (ZIP mode)")
                if force_update:
                    logs.append("Force update enabled.")

                try:
                    if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
                        result = helpers.perform_kometa_update_zip_only_at_root(kometa_root, branch=kometa_branch, force=force_update, logs=logs)
                    else:
                        result = helpers.perform_kometa_update_zip_only(helpers.CONFIG_DIR, branch=kometa_branch, force=force_update, logs=logs)
                    try:
                        invalidate_target = kometa_root if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING else helpers.CONFIG_DIR
                        helpers.invalidate_cached_kometa_update(invalidate_target)
                    except Exception:
                        pass
                    if result.get("success", False):
                        complete_background_job(
                            job_id,
                            phase="done",
                            success=True,
                            done=True,
                            up_to_date=bool(result.get("up_to_date", False)),
                            skipped=bool(result.get("skipped", False)),
                        )
                    else:
                        fail_background_job(
                            job_id,
                            "Kometa update failed.",
                            done=True,
                            success=False,
                            up_to_date=bool(result.get("up_to_date", False)),
                            skipped=bool(result.get("skipped", False)),
                        )
                except Exception as e:
                    logs.append("Exception during Kometa update.")
                    helpers.ts_log(f"Kometa update failed: {e}", level="ERROR")
                    fail_background_job(job_id, e, done=True, success=False)
                finally:
                    clear_active_background_job("kometa_update", job_id=job_id)

            threading.Thread(target=worker, daemon=True).start()
            return jsonify(success=True, active=True, job_id=job_id, phase="queued"), 200

        logs = []
        logs.append(f"🔎 Quickstart branch: {qs_branch}")
        logs.append(f"📍 Kometa install mode: {install_mode}")
        logs.append(f"📁 Target Kometa root: {kometa_root}")
        if branch_override:
            logs.append(f"⚠️ Kometa branch override selected: {branch_override}")
        else:
            logs.append("ℹ️ Kometa branch selection: auto")
        logs.append(f"⚙️ Kometa branch selected: {kometa_branch} (ZIP mode)")
        if force_update:
            logs.append("Force update enabled.")

        if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING:
            result = helpers.perform_kometa_update_zip_only_at_root(kometa_root, branch=kometa_branch, force=force_update, logs=logs)
        else:
            result = helpers.perform_kometa_update_zip_only(helpers.CONFIG_DIR, branch=kometa_branch, force=force_update, logs=logs)
        try:
            invalidate_target = kometa_root if install_mode == kometa_install.KOMETA_INSTALL_MODE_EXISTING else helpers.CONFIG_DIR
            helpers.invalidate_cached_kometa_update(invalidate_target)
        except Exception:
            pass
        status = 200 if result.get("success") else 500

        return (
            jsonify(
                {
                    "success": result.get("success", False),
                    "log": list(logs),
                    "qs_branch": qs_branch,
                    "kometa_branch": kometa_branch,
                    "up_to_date": result.get("up_to_date", False),
                    "skipped": result.get("skipped", False),
                    "force": force_update,
                }
            ),
            status,
        )

    except Exception as e:
        helpers.ts_log(f"Kometa update failed: {e}", level="ERROR")
        return jsonify({"success": False, "log": ["Exception during Kometa update."]}), 500


@bp.route("/update-kometa-progress", methods=["GET"])
def update_kometa_progress():
    job_id = request.args.get("job_id", "").strip()
    since = request.args.get("since", "0").strip()
    if not job_id:
        return jsonify(success=False, error="Missing job_id."), 400
    info = get_background_job(job_id)
    if not info:
        return jsonify(success=False, error="Unknown job_id."), 404
    try:
        start_idx = max(int(since or "0"), 0)
    except ValueError:
        start_idx = 0
    lines = list(info.get("logs") or [])
    return jsonify(
        success=True,
        job_id=job_id,
        phase=info.get("phase"),
        done=bool(info.get("done")) or info.get("status") in {"complete", "error"},
        update_success=bool(info.get("success")),
        up_to_date=bool(info.get("up_to_date")),
        skipped=bool(info.get("skipped")),
        force=bool(info.get("force")),
        qs_branch=info.get("qs_branch"),
        kometa_branch=info.get("kometa_branch"),
        lines=lines[start_idx:],
        next_index=len(lines),
    )
