import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from flask import has_request_context, session

from modules import database, helpers, imagemaid, persistence

# Process-metric calculators (CPU / IO stats) extracted to modules.process_metrics.
# Re-exported here so callers using ``from modules.process_control import ...``
# and ``modules.process_control.<name>`` continue to work.
from modules.process_metrics import (  # noqa: F401
    KOMETA_CPU_CACHE,
    PROCESS_IO_CACHE,
    SYSTEM_CPU_CACHE,
    calculate_process_cpu_percent,
    calculate_process_io_stats,
    calculate_system_cpu_percent,
    clear_process_metric_cache,
)

# Shared module-level state (dicts, locks, constants) and the
# ``normalize_kometa_start_mode`` helper live in modules.process_control_state
# to avoid circular imports between process_control and its extractions.
from modules.process_control_state import (  # noqa: F401
    IMAGEMAID_RUN_CONTEXT,
    IMAGEMAID_RUN_CONTEXT_LOCK,
    MAINTENANCE_GUARD_INTERVAL,
    MAINTENANCE_STATE,
    MAINTENANCE_STATE_LOCK,
    PENDING_KOMETA_START,
    PENDING_KOMETA_START_LOCK,
    RUN_CONTEXT,
    RUN_CONTEXT_LOCK,
    normalize_kometa_start_mode,
)

# Marker-file writers (run markers, maintenance sidecars, meta.log
# helpers, config-path resolution) extracted to modules.process_markers.
from modules.process_markers import (  # noqa: F401
    _get_version_info,
    append_imagemaid_maintenance_sidecar_line,
    append_kometa_maintenance_sidecar_line,
    append_quickstart_imagemaid_log_line,
    append_quickstart_meta_log_line,
    extract_kometa_config_path,
    get_imagemaid_maintenance_sidecar_path,
    get_kometa_maintenance_sidecar_path,
    is_logscan_maintenance_sidecar,
    reset_imagemaid_maintenance_sidecar,
    reset_kometa_maintenance_sidecar,
    schedule_quickstart_run_marker,
    stamp_quickstart_config_marker,
    write_quickstart_imagemaid_maintenance_marker,
    write_quickstart_imagemaid_run_marker,
    write_quickstart_imagemaid_stop_marker,
    write_quickstart_maintenance_marker,
    write_quickstart_run_marker,
    write_quickstart_stop_marker,
)


def parse_maintenance_window_minutes(window_str):
    if not window_str or "Unavailable" in str(window_str):
        return None
    matches = re.findall(r"(\d{1,2}):(\d{2})", str(window_str))
    if len(matches) < 2:
        return None
    try:
        start_h, start_m = (int(v) for v in matches[0])
        end_h, end_m = (int(v) for v in matches[1])
    except Exception:
        return None
    if not (0 <= start_h <= 23 and 0 <= end_h <= 23 and 0 <= start_m <= 59 and 0 <= end_m <= 59):
        return None
    return (start_h * 60 + start_m, end_h * 60 + end_m)


def is_within_maintenance_window(now_dt, start_min, end_min):
    if start_min is None or end_min is None or start_min == end_min:
        return False
    now_min = now_dt.hour * 60 + now_dt.minute
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def get_maintenance_window_from_db(config_name=None):
    config_name = helpers.normalize_config_name_for_storage(config_name) or database.get_last_used_config_name()
    if not config_name:
        return None, None, None
    try:
        _validated, _user_entered, data = database.retrieve_section_data(name=config_name, section="plex_telemetry")
        telemetry = data.get("plex_telemetry", {}) if isinstance(data, dict) else {}
        window_str = telemetry.get("maintenance_window")
        if not window_str:
            legacy_telemetry = persistence.retrieve_settings("plex_telemetry")
            if isinstance(legacy_telemetry, dict):
                window_str = legacy_telemetry.get("plex_telemetry", {}).get("maintenance_window")
        if not window_str:
            legacy_plex = persistence.retrieve_settings("010-plex")
            if isinstance(legacy_plex, dict):
                window_str = legacy_plex.get("plex", {}).get("telemetry", {}).get("maintenance_window")
        minutes = parse_maintenance_window_minutes(window_str)
        if not minutes:
            return None, None, None
        return minutes[0], minutes[1], window_str
    except Exception as e:
        helpers.ts_log(f"Failed to read Plex maintenance window: {e}", level="DEBUG")
        return None, None, None


def get_plex_credentials_from_db(config_name=None):
    config_name = helpers.normalize_config_name_for_storage(config_name) or database.get_last_used_config_name()
    if not config_name:
        return None, None
    try:
        _validated, _user_entered, data = database.retrieve_section_data(name=config_name, section="plex")
        plex_data = data.get("plex", {}) if isinstance(data, dict) else {}
        plex_url = plex_data.get("url") or plex_data.get("plex_url")
        plex_token = plex_data.get("token") or plex_data.get("plex_token")
        return plex_url, plex_token
    except Exception as e:
        helpers.ts_log(f"Failed to read Plex credentials: {e}", level="DEBUG")
        return None, None


def get_maintenance_window_live(config_name=None):
    plex_url, plex_token = get_plex_credentials_from_db(config_name=config_name)
    if not plex_url or not plex_token:
        return None, None, None
    start_hour, end_hour = helpers.get_plex_maintenance_hours(plex_url, plex_token)
    if start_hour is None or end_hour is None:
        return None, None, None
    window_str = f"{start_hour:02d}:00 – {end_hour:02d}:00"
    return start_hour * 60, end_hour * 60, window_str


def get_active_maintenance_lookup_config_name():
    import quickstart

    def normalize_optional_config_name(value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        return helpers.normalize_config_name_for_storage(raw)

    kometa_running = bool(helpers.get_kometa_pid() and helpers.is_kometa_running())
    imagemaid_running = bool(helpers.get_imagemaid_pid() and helpers.is_imagemaid_running())

    try:
        kometa_ctx = quickstart._get_run_context()
    except Exception:
        kometa_ctx = {}
    kometa_config = normalize_optional_config_name((kometa_ctx or {}).get("config_name"))
    if kometa_running and kometa_config:
        return kometa_config

    try:
        imagemaid_ctx = quickstart._get_imagemaid_run_context()
    except Exception:
        imagemaid_ctx = {}
    imagemaid_config = normalize_optional_config_name((imagemaid_ctx or {}).get("config_name"))
    if imagemaid_running and imagemaid_config:
        return imagemaid_config

    pending = quickstart._peek_pending_kometa_start()
    pending_config = normalize_optional_config_name((pending or {}).get("config_name"))
    if pending_config:
        return pending_config

    return database.get_last_used_config_name()


def resolve_maintenance_window_live(config_name=None):
    import quickstart

    try:
        return quickstart._get_maintenance_window_live(config_name=config_name)
    except TypeError:
        return quickstart._get_maintenance_window_live()


def resolve_maintenance_window_from_db(config_name=None):
    import quickstart

    try:
        return quickstart._get_maintenance_window_from_db(config_name=config_name)
    except TypeError:
        return quickstart._get_maintenance_window_from_db()


def refresh_maintenance_window_availability(preserve_active_state=False):
    maintenance_config_name = get_active_maintenance_lookup_config_name()
    start_min, end_min, window_str = resolve_maintenance_window_live(config_name=maintenance_config_name)
    if start_min is None or end_min is None:
        start_min, end_min, window_str = resolve_maintenance_window_from_db(config_name=maintenance_config_name)
    window_unavailable = start_min is None or end_min is None

    kometa_running = bool(helpers.get_kometa_pid() and helpers.is_kometa_running())
    imagemaid_running = bool(helpers.get_imagemaid_pid() and helpers.is_imagemaid_running())
    has_pending = bool(peek_pending_kometa_start())
    active = is_within_maintenance_window(datetime.now(), start_min, end_min)

    with MAINTENANCE_STATE_LOCK:
        if preserve_active_state and (MAINTENANCE_STATE.get("paused") or MAINTENANCE_STATE.get("imagemaid_paused")):
            if window_str:
                MAINTENANCE_STATE["window"] = window_str
        else:
            MAINTENANCE_STATE["active"] = active
            MAINTENANCE_STATE["window"] = window_str
        if window_unavailable and (kometa_running or imagemaid_running or has_pending):
            if not MAINTENANCE_STATE.get("window_unavailable"):
                MAINTENANCE_STATE["window_unavailable_since"] = datetime.now(timezone.utc).isoformat()
            MAINTENANCE_STATE["window_unavailable"] = True
        else:
            MAINTENANCE_STATE["window_unavailable"] = False
            MAINTENANCE_STATE["window_unavailable_since"] = None


def set_pending_kometa_start(command, config_name, start_mode="current"):
    with PENDING_KOMETA_START_LOCK:
        PENDING_KOMETA_START["command"] = command
        PENDING_KOMETA_START["config_name"] = config_name
        PENDING_KOMETA_START["requested_at"] = datetime.now(timezone.utc).isoformat()
        PENDING_KOMETA_START["start_mode"] = normalize_kometa_start_mode(start_mode)


def peek_pending_kometa_start():
    with PENDING_KOMETA_START_LOCK:
        if not PENDING_KOMETA_START.get("command"):
            return None
        return dict(PENDING_KOMETA_START)


def pop_pending_kometa_start():
    with PENDING_KOMETA_START_LOCK:
        if not PENDING_KOMETA_START.get("command"):
            return None
        pending = dict(PENDING_KOMETA_START)
        PENDING_KOMETA_START["command"] = None
        PENDING_KOMETA_START["config_name"] = None
        PENDING_KOMETA_START["requested_at"] = None
        PENDING_KOMETA_START["start_mode"] = "current"
        return pending


def clear_pending_kometa_start():
    with PENDING_KOMETA_START_LOCK:
        PENDING_KOMETA_START["command"] = None
        PENDING_KOMETA_START["config_name"] = None
        PENDING_KOMETA_START["requested_at"] = None
        PENDING_KOMETA_START["start_mode"] = "current"


def find_running_kometa_processes():
    kometa_root = None
    try:
        kometa_root = str(helpers.get_kometa_root_path())
    except Exception:
        kometa_root = None
    matches = []
    for proc in psutil.process_iter():
        try:
            cmdline = []
            if hasattr(proc, "info"):
                cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                cmdline = proc.cmdline() or []
            joined = " ".join(cmdline)
        except Exception:
            continue
        if "kometa.py" not in joined:
            continue
        has_root = bool(kometa_root and kometa_root in joined)
        try:
            create_time = proc.info.get("create_time") if hasattr(proc, "info") else None
        except Exception:
            create_time = None
        if create_time is None:
            try:
                create_time = proc.create_time()
            except Exception:
                create_time = 0
        matches.append((has_root, create_time, proc))
    matches.sort(key=lambda item: (1 if item[0] else 0, item[1]), reverse=True)
    return [entry[2] for entry in matches]


def find_running_kometa_process():
    procs = find_running_kometa_processes()
    return procs[0] if procs else None


def find_running_imagemaid_processes():
    imagemaid_root = None
    try:
        imagemaid_root = str(helpers.get_imagemaid_root_path())
    except Exception:
        imagemaid_root = None
    matches = []
    for proc in psutil.process_iter():
        try:
            cmdline = []
            if hasattr(proc, "info"):
                cmdline = proc.info.get("cmdline") or []
            if not cmdline:
                cmdline = proc.cmdline() or []
            joined = " ".join(cmdline)
        except Exception:
            continue
        if "imagemaid.py" not in joined:
            continue
        has_root = bool(imagemaid_root and imagemaid_root in joined)
        try:
            create_time = proc.info.get("create_time") if hasattr(proc, "info") else None
        except Exception:
            create_time = None
        if create_time is None:
            try:
                create_time = proc.create_time()
            except Exception:
                create_time = 0
        matches.append((has_root, create_time, proc))
    matches.sort(key=lambda item: (1 if item[0] else 0, item[1]), reverse=True)
    return [entry[2] for entry in matches]


def find_running_imagemaid_process():
    procs = find_running_imagemaid_processes()
    return procs[0] if procs else None


def stop_process_tree(proc):
    try:
        children = proc.children(recursive=True)
    except Exception:
        children = []
    # Ensure suspended processes can receive signals
    for target in [proc] + children:
        try:
            target.resume()
        except Exception:
            pass
    for child in children:
        try:
            child.terminate()
        except Exception:
            pass
    try:
        proc.terminate()
    except Exception:
        pass
    gone, alive = psutil.wait_procs([proc] + children, timeout=5)
    if alive:
        for target in alive:
            try:
                target.kill()
            except Exception:
                pass
        _, alive = psutil.wait_procs(alive, timeout=3)
    return alive


def launch_kometa_command(command, config_name=None, start_mode="current"):
    if not command:
        return False, "No command provided"

    kometa_root = helpers.get_kometa_root_path()  # unified source of truth
    is_win = sys.platform.startswith("win")
    venv_python = kometa_root / "kometa-venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python3")
    kometa_py = kometa_root / "kometa.py"

    if not kometa_py.exists():
        return False, f"kometa.py not found at: {kometa_py}"
    if not venv_python.exists():
        return False, f"Kometa venv python not found at: {venv_python}"

    # Use posix=False so Windows backslashes/quotes are preserved
    command_parts = shlex.split(command, posix=not is_win)

    # Clean up double-wrapped args (affects --run-libraries, --times, etc.)
    helpers.normalize_cli_args_inplace(command_parts)

    # If the UI-built command already starts with python, replace it with our venv python
    if command_parts and os.path.basename(command_parts[0]).lower() in {"python", "python3", "python.exe"}:
        command_parts[0] = str(venv_python)
    else:
        command_parts.insert(0, str(venv_python))

    # Make sure kometa.py is the script, even if the UI command omitted it
    if not any(p.endswith("kometa.py") for p in command_parts):
        command_parts.insert(1, str(kometa_py))

    helpers.normalize_flag_values(command_parts)

    config_path = extract_kometa_config_path(command_parts, kometa_root)
    stamp_quickstart_config_marker(config_path, config_name)

    helpers.ts_log(f"argv={command_parts!r}", level="DEBUG")

    proc = subprocess.Popen(command_parts, cwd=str(kometa_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    with open(helpers.get_kometa_pid_file(), "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    schedule_quickstart_run_marker(kometa_root, config_name, start_mode=normalize_kometa_start_mode(start_mode))
    return True, proc.pid


def launch_imagemaid_command(command, mode=None, config_name=None):
    import quickstart

    if not command:
        return False, "No command provided"

    imagemaid_root = helpers.get_imagemaid_root_path()
    is_win = sys.platform.startswith("win")
    venv_python = imagemaid_root / "imagemaid-venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python3")
    imagemaid_py = imagemaid_root / "imagemaid.py"

    if not imagemaid_py.exists():
        return False, f"imagemaid.py not found at: {imagemaid_py}"
    if not venv_python.exists():
        return False, f"ImageMaid venv python not found at: {venv_python}"

    if isinstance(command, (list, tuple)):
        command_parts = [str(part) for part in command]
    else:
        command_parts = shlex.split(command, posix=not is_win)
        cleaned = []
        for part in command_parts:
            text = str(part)
            if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
                text = text[1:-1]
            cleaned.append(text)
        command_parts = cleaned

    if command_parts and os.path.basename(command_parts[0]).lower() in {"python", "python3", "python.exe"}:
        command_parts[0] = str(venv_python)
    else:
        command_parts.insert(0, str(venv_python))

    if not any(p.endswith("imagemaid.py") for p in command_parts):
        command_parts.insert(1, str(imagemaid_py))

    env_ready, env_result = quickstart._reset_imagemaid_runtime_env(imagemaid_root)
    if not env_ready:
        return False, env_result or "Quickstart could not reset the ImageMaid runtime .env file."

    helpers.ts_log(f"argv={command_parts!r}", level="DEBUG")
    update_imagemaid_run_context(command_parts, mode=mode, config_name=config_name)
    launch_log_path = Path(helpers.get_imagemaid_launch_log_file())
    launch_log_path.parent.mkdir(parents=True, exist_ok=True)

    with launch_log_path.open("w", encoding="utf-8", errors="replace") as launch_log:
        launch_log.write(f"[Quickstart] ImageMaid launch started at {datetime.now().isoformat()}\n")
        launch_log.flush()

        proc = subprocess.Popen(
            command_parts,
            cwd=str(imagemaid_root),
            stdout=launch_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        with open(helpers.get_imagemaid_pid_file(), "w", encoding="utf-8") as f:
            f.write(str(proc.pid))

        time.sleep(1.0)
        return_code = proc.poll()
        if return_code is not None:
            launch_log.flush()
            try:
                os.remove(helpers.get_imagemaid_pid_file())
            except Exception:
                pass
            return False, f"ImageMaid exited immediately with code {return_code}. Review the run log for details."

    quickstart._schedule_quickstart_imagemaid_run_marker(imagemaid_root, mode=mode, config_name=config_name)
    return True, proc.pid


def reset_imagemaid_runtime_env(imagemaid_root):
    try:
        env_path = Path(imagemaid_root) / "config" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text("", encoding="utf-8")
        helpers.ts_log(f"Reset ImageMaid runtime env override file: {env_path}", level="DEBUG")
        return True, str(env_path)
    except Exception as exc:
        return False, f"Quickstart could not reset ImageMaid env file before launch: {exc}"


def extract_selected_libraries(command):
    if not command:
        return None, None
    is_win = sys.platform.startswith("win")
    try:
        parts = shlex.split(command, posix=not is_win)
    except Exception:
        parts = command.split()

    run_option = None
    selected = None
    for idx, part in enumerate(parts):
        if part in ("--run", "--run-libraries", "--times"):
            run_option = part
        if part.startswith("--run-libraries="):
            value = part.split("=", 1)[1].strip().strip('"').strip("'")
            selected = [v for v in value.split("|") if v.strip()]
            break
        if part == "--run-libraries" and idx + 1 < len(parts):
            value = parts[idx + 1].strip().strip('"').strip("'")
            selected = [v for v in value.split("|") if v.strip()]
            run_option = "--run-libraries"
            break
    return run_option, selected


def update_run_context(command, config_name=None, start_mode="current"):
    run_option, selected = extract_selected_libraries(command)
    config_path = None
    run_mode = "all"
    if command:
        is_win = sys.platform.startswith("win")
        try:
            parts = shlex.split(command, posix=not is_win)
        except Exception:
            parts = command.split()
        if "--metadata-only" in parts:
            run_mode = "metadata"
        elif "--operations-only" in parts:
            run_mode = "operations"
        elif "--playlists-only" in parts:
            run_mode = "playlists"
        elif "--overlays-only" in parts:
            run_mode = "overlays"
        elif "--collections-only" in parts:
            run_mode = "collections"
        kometa_root = helpers.get_kometa_root_path()
        config_path = extract_kometa_config_path(parts, kometa_root)
    with RUN_CONTEXT_LOCK:
        RUN_CONTEXT["command"] = command
        RUN_CONTEXT["run_option"] = run_option
        RUN_CONTEXT["selected_libraries"] = selected
        RUN_CONTEXT["run_mode"] = run_mode
        RUN_CONTEXT["start_mode"] = normalize_kometa_start_mode(start_mode)
        if config_name is None and has_request_context():
            config_name = session.get("config_name")
        RUN_CONTEXT["config_name"] = config_name
        RUN_CONTEXT["config_path"] = str(config_path) if config_path else None
        RUN_CONTEXT["started_at"] = datetime.now()
        RUN_CONTEXT["updated_at"] = datetime.now(timezone.utc).isoformat()
        RUN_CONTEXT["stop_requested_at"] = None


def get_run_context():
    with RUN_CONTEXT_LOCK:
        return dict(RUN_CONTEXT)


def clear_run_context():
    with RUN_CONTEXT_LOCK:
        RUN_CONTEXT["command"] = None
        RUN_CONTEXT["selected_libraries"] = None
        RUN_CONTEXT["run_option"] = None
        RUN_CONTEXT["run_mode"] = "all"
        RUN_CONTEXT["start_mode"] = "current"
        RUN_CONTEXT["config_name"] = None
        RUN_CONTEXT["config_path"] = None
        RUN_CONTEXT["started_at"] = None
        RUN_CONTEXT["updated_at"] = None
        RUN_CONTEXT["stop_requested_at"] = None


def normalize_imagemaid_command_text(command):
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command if str(part).strip())
    return str(command or "").strip()


def update_imagemaid_run_context(command, mode=None, config_name=None):
    with IMAGEMAID_RUN_CONTEXT_LOCK:
        IMAGEMAID_RUN_CONTEXT["command"] = normalize_imagemaid_command_text(command)
        IMAGEMAID_RUN_CONTEXT["mode"] = str(mode or "").strip().lower() or None
        IMAGEMAID_RUN_CONTEXT["config_name"] = str(config_name or "").strip() or None
        IMAGEMAID_RUN_CONTEXT["started_at"] = datetime.now()
        IMAGEMAID_RUN_CONTEXT["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_imagemaid_run_context():
    with IMAGEMAID_RUN_CONTEXT_LOCK:
        return dict(IMAGEMAID_RUN_CONTEXT)


def clear_imagemaid_run_context():
    with IMAGEMAID_RUN_CONTEXT_LOCK:
        IMAGEMAID_RUN_CONTEXT["command"] = None
        IMAGEMAID_RUN_CONTEXT["mode"] = None
        IMAGEMAID_RUN_CONTEXT["config_name"] = None
        IMAGEMAID_RUN_CONTEXT["started_at"] = None
        IMAGEMAID_RUN_CONTEXT["updated_at"] = None


def suspend_process_tree(proc):
    try:
        for child in proc.children(recursive=True):
            try:
                child.suspend()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        proc.suspend()
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def resume_process_tree(proc):
    try:
        proc.resume()
        for child in proc.children(recursive=True):
            try:
                child.resume()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def maintenance_guard_loop(app_in):
    import quickstart

    interval = MAINTENANCE_GUARD_INTERVAL
    env_override = os.getenv("QS_MAINTENANCE_GUARD_INTERVAL")
    if env_override:
        try:
            interval = max(30, min(int(str(env_override).strip()), 300))
        except Exception:
            interval = MAINTENANCE_GUARD_INTERVAL

    with app_in.app_context():
        while True:
            time.sleep(interval)
            maintenance_config_name = get_active_maintenance_lookup_config_name()
            start_min, end_min, window_str = resolve_maintenance_window_live(config_name=maintenance_config_name)
            if start_min is None or end_min is None:
                start_min, end_min, window_str = resolve_maintenance_window_from_db(config_name=maintenance_config_name)
            window_unavailable = start_min is None or end_min is None
            pid = helpers.get_kometa_pid()
            kometa_running = pid and helpers.is_kometa_running()
            imagemaid_pid = helpers.get_imagemaid_pid()
            imagemaid_running = imagemaid_pid and helpers.is_imagemaid_running()
            if not imagemaid_running:
                imagemaid_proc = quickstart._find_running_imagemaid_process()
                if imagemaid_proc:
                    imagemaid_running = True
                    imagemaid_pid = imagemaid_proc.pid
                    try:
                        with open(helpers.get_imagemaid_pid_file(), "w", encoding="utf-8") as handle:
                            handle.write(str(imagemaid_pid))
                    except Exception:
                        pass
            has_pending = bool(quickstart._peek_pending_kometa_start())
            if window_unavailable and (kometa_running or imagemaid_running or has_pending):
                with MAINTENANCE_STATE_LOCK:
                    if not MAINTENANCE_STATE.get("window_unavailable"):
                        MAINTENANCE_STATE["window_unavailable"] = True
                        MAINTENANCE_STATE["window_unavailable_since"] = datetime.now(timezone.utc).isoformat()
                        helpers.ts_log(
                            "Plex maintenance window unavailable; keeping Quickstart work paused/queued until Plex is reachable.",
                            level="WARNING",
                        )
            else:
                with MAINTENANCE_STATE_LOCK:
                    if MAINTENANCE_STATE.get("window_unavailable"):
                        MAINTENANCE_STATE["window_unavailable"] = False
                        MAINTENANCE_STATE["window_unavailable_since"] = None
                        helpers.ts_log("Plex maintenance window available again.", level="INFO")
            active = quickstart._is_within_maintenance_window(datetime.now(), start_min, end_min)
            with MAINTENANCE_STATE_LOCK:
                MAINTENANCE_STATE["active"] = active
                MAINTENANCE_STATE["window"] = window_str

            if not kometa_running:
                with MAINTENANCE_STATE_LOCK:
                    if MAINTENANCE_STATE["paused"]:
                        MAINTENANCE_STATE["paused"] = False
                        MAINTENANCE_STATE["paused_since"] = None

                pending = quickstart._peek_pending_kometa_start()
                if pending and not active and start_min is not None and end_min is not None:
                    pending = quickstart._pop_pending_kometa_start()
                    if pending:
                        start_mode = quickstart._normalize_kometa_start_mode(pending.get("start_mode"))
                        quickstart._update_run_context(pending.get("command"), config_name=pending.get("config_name"), start_mode=start_mode)
                        ok, result = quickstart._launch_kometa_command(pending.get("command"), pending.get("config_name"), start_mode=start_mode)
                        if ok:
                            helpers.ts_log("Kometa started after Plex maintenance window ended.", level="INFO")
                            with MAINTENANCE_STATE_LOCK:
                                MAINTENANCE_STATE["queued_started_at"] = datetime.now(timezone.utc).isoformat()
                        else:
                            helpers.ts_log(f"Failed to start Kometa after maintenance: {result}", level="ERROR")
            elif start_min is not None and end_min is not None:
                try:
                    proc = psutil.Process(pid)
                except psutil.NoSuchProcess:
                    with MAINTENANCE_STATE_LOCK:
                        MAINTENANCE_STATE["paused"] = False
                        MAINTENANCE_STATE["paused_since"] = None
                else:
                    if active:
                        with MAINTENANCE_STATE_LOCK:
                            already_paused = MAINTENANCE_STATE["paused"]
                        if not already_paused and quickstart._suspend_process_tree(proc):
                            window_label = f" ({window_str})" if window_str else ""
                            helpers.ts_log(f"Kometa paused due to Plex maintenance window{window_label}.", level="INFO")
                            try:
                                if not quickstart._write_quickstart_maintenance_marker(helpers.get_kometa_root_path(), "paused", window=window_str):
                                    helpers.ts_log("Failed to append Quickstart paused maintenance marker to meta.log.", level="WARNING")
                            except Exception:
                                helpers.ts_log("Failed to append Quickstart paused maintenance marker to meta.log.", level="WARNING")
                            with MAINTENANCE_STATE_LOCK:
                                MAINTENANCE_STATE["paused"] = True
                                MAINTENANCE_STATE["paused_since"] = datetime.now(timezone.utc).isoformat()
                    else:
                        with MAINTENANCE_STATE_LOCK:
                            was_paused = MAINTENANCE_STATE["paused"]
                            paused_since = MAINTENANCE_STATE["paused_since"]
                        if was_paused and quickstart._resume_process_tree(proc):
                            window_label = f" ({window_str})" if window_str else ""
                            helpers.ts_log(f"Plex maintenance ended{window_label}. Kometa resumed.", level="INFO")
                            paused_seconds = None
                            if paused_since:
                                try:
                                    paused_at = datetime.fromisoformat(str(paused_since).replace("Z", "+00:00"))
                                    if paused_at.tzinfo is None:
                                        paused_at = paused_at.replace(tzinfo=timezone.utc)
                                    paused_seconds = max(0, int((datetime.now(timezone.utc) - paused_at).total_seconds()))
                                except Exception:
                                    paused_seconds = None
                            try:
                                if not quickstart._write_quickstart_maintenance_marker(
                                    helpers.get_kometa_root_path(),
                                    "resumed",
                                    window=window_str,
                                    paused_seconds=paused_seconds,
                                ):
                                    helpers.ts_log("Failed to append Quickstart resumed maintenance marker to meta.log.", level="WARNING")
                            except Exception:
                                helpers.ts_log("Failed to append Quickstart resumed maintenance marker to meta.log.", level="WARNING")
                            with MAINTENANCE_STATE_LOCK:
                                MAINTENANCE_STATE["paused"] = False
                                MAINTENANCE_STATE["paused_since"] = None

            if not imagemaid_running:
                with MAINTENANCE_STATE_LOCK:
                    MAINTENANCE_STATE["imagemaid_paused"] = False
                    MAINTENANCE_STATE["imagemaid_paused_since"] = None
                continue

            if start_min is None or end_min is None:
                continue

            try:
                imagemaid_proc = psutil.Process(imagemaid_pid)
            except psutil.NoSuchProcess:
                with MAINTENANCE_STATE_LOCK:
                    MAINTENANCE_STATE["imagemaid_paused"] = False
                    MAINTENANCE_STATE["imagemaid_paused_since"] = None
                continue

            imagemaid_ctx = quickstart._get_imagemaid_run_context()
            imagemaid_mode = imagemaid_ctx.get("mode")
            imagemaid_config_name = imagemaid_ctx.get("config_name")
            imagemaid_log_path = imagemaid.get_latest_imagemaid_log_path()

            if active:
                with MAINTENANCE_STATE_LOCK:
                    imagemaid_already_paused = MAINTENANCE_STATE["imagemaid_paused"]
                if not imagemaid_already_paused and quickstart._suspend_process_tree(imagemaid_proc):
                    window_label = f" ({window_str})" if window_str else ""
                    helpers.ts_log(f"ImageMaid paused due to Plex maintenance window{window_label}.", level="INFO")
                    try:
                        if not quickstart._write_quickstart_imagemaid_maintenance_marker(
                            helpers.get_imagemaid_root_path(),
                            "paused",
                            mode=imagemaid_mode,
                            config_name=imagemaid_config_name,
                            window=window_str,
                            log_path=imagemaid_log_path,
                        ):
                            helpers.ts_log("Failed to append Quickstart paused ImageMaid maintenance marker to the live log.", level="WARNING")
                    except Exception:
                        helpers.ts_log("Failed to append Quickstart paused ImageMaid maintenance marker to the live log.", level="WARNING")
                    with MAINTENANCE_STATE_LOCK:
                        MAINTENANCE_STATE["imagemaid_paused"] = True
                        MAINTENANCE_STATE["imagemaid_paused_since"] = datetime.now(timezone.utc).isoformat()
                continue

            with MAINTENANCE_STATE_LOCK:
                imagemaid_was_paused = MAINTENANCE_STATE["imagemaid_paused"]
                imagemaid_paused_since = MAINTENANCE_STATE["imagemaid_paused_since"]
            if imagemaid_was_paused and quickstart._resume_process_tree(imagemaid_proc):
                window_label = f" ({window_str})" if window_str else ""
                helpers.ts_log(f"Plex maintenance ended{window_label}. ImageMaid resumed.", level="INFO")
                imagemaid_paused_seconds = None
                if imagemaid_paused_since:
                    try:
                        paused_at = datetime.fromisoformat(str(imagemaid_paused_since).replace("Z", "+00:00"))
                        if paused_at.tzinfo is None:
                            paused_at = paused_at.replace(tzinfo=timezone.utc)
                        imagemaid_paused_seconds = max(0, int((datetime.now(timezone.utc) - paused_at).total_seconds()))
                    except Exception:
                        imagemaid_paused_seconds = None
                try:
                    if not quickstart._write_quickstart_imagemaid_maintenance_marker(
                        helpers.get_imagemaid_root_path(),
                        "resumed",
                        mode=imagemaid_mode,
                        config_name=imagemaid_config_name,
                        window=window_str,
                        log_path=imagemaid_log_path,
                        paused_seconds=imagemaid_paused_seconds,
                    ):
                        helpers.ts_log("Failed to append Quickstart resumed ImageMaid maintenance marker to the live log.", level="WARNING")
                except Exception:
                    helpers.ts_log("Failed to append Quickstart resumed ImageMaid maintenance marker to the live log.", level="WARNING")
                with MAINTENANCE_STATE_LOCK:
                    MAINTENANCE_STATE["imagemaid_paused"] = False
                    MAINTENANCE_STATE["imagemaid_paused_since"] = None
