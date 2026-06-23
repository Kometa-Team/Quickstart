import os
import re
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
from flask import current_app as app, has_app_context, has_request_context, session

from modules import database, helpers, imagemaid, persistence

KOMETA_CPU_CACHE = {}
SYSTEM_CPU_CACHE = {"total": None, "idle": None}
PROCESS_IO_CACHE = {"kometa": {}, "imagemaid": {}}
MAINTENANCE_STATE = {
    "paused": False,
    "paused_since": None,
    "imagemaid_paused": False,
    "imagemaid_paused_since": None,
    "active": False,
    "window": None,
    "queued_started_at": None,
    "window_unavailable": False,
    "window_unavailable_since": None,
}
MAINTENANCE_STATE_LOCK = threading.Lock()
MAINTENANCE_GUARD_INTERVAL = 45
PENDING_KOMETA_START = {"command": None, "config_name": None, "requested_at": None, "start_mode": "current"}
PENDING_KOMETA_START_LOCK = threading.Lock()

RUN_CONTEXT_LOCK = threading.Lock()
RUN_CONTEXT = {
    "command": None,
    "selected_libraries": None,
    "run_option": None,
    "run_mode": "all",
    "start_mode": "current",
    "config_name": None,
    "config_path": None,
    "started_at": None,
    "updated_at": None,
    "stop_requested_at": None,
}
IMAGEMAID_RUN_CONTEXT_LOCK = threading.Lock()
IMAGEMAID_RUN_CONTEXT = {
    "command": None,
    "mode": None,
    "config_name": None,
    "started_at": None,
    "updated_at": None,
}


def _get_version_info():
    if not has_app_context():
        return {}
    return app.config.get("VERSION_CHECK") or {}


def calculate_process_cpu_percent(proc):
    try:
        cpu_times = proc.cpu_times()
    except Exception:
        return None
    total_cpu = cpu_times.user + cpu_times.system
    try:
        for child in proc.children(recursive=True):
            try:
                child_times = child.cpu_times()
                total_cpu += child_times.user + child_times.system
            except Exception:
                continue
    except Exception:
        pass
    now = time.time()
    entry = KOMETA_CPU_CACHE.get(proc.pid)
    KOMETA_CPU_CACHE[proc.pid] = {"time": now, "cpu": total_cpu}
    if not entry:
        return None
    elapsed = now - entry.get("time", now)
    if elapsed <= 0:
        return None
    delta_cpu = total_cpu - entry.get("cpu", total_cpu)
    if delta_cpu < 0:
        return None
    percent = (delta_cpu / elapsed) * 100.0
    return max(0.0, percent)


def calculate_system_cpu_percent():
    try:
        cpu_times = psutil.cpu_times()
    except Exception:
        return None
    total = sum(cpu_times)
    idle = getattr(cpu_times, "idle", 0)
    last_total = SYSTEM_CPU_CACHE.get("total")
    last_idle = SYSTEM_CPU_CACHE.get("idle")
    SYSTEM_CPU_CACHE["total"] = total
    SYSTEM_CPU_CACHE["idle"] = idle
    if last_total is None or last_idle is None:
        return None
    delta_total = total - last_total
    if delta_total <= 0:
        return None
    delta_idle = idle - last_idle
    busy = max(0.0, delta_total - delta_idle)
    percent = (busy / delta_total) * 100.0
    return max(0.0, min(100.0, percent))


def calculate_process_io_stats(proc, cache_name):
    bucket = PROCESS_IO_CACHE.setdefault(cache_name, {})
    total_read = 0
    total_write = 0
    saw_counters = False

    def _accumulate_io(target_proc):
        nonlocal total_read, total_write, saw_counters
        try:
            counters = target_proc.io_counters()
        except Exception:
            return
        read_bytes = getattr(counters, "read_bytes", None)
        write_bytes = getattr(counters, "write_bytes", None)
        if read_bytes is None or write_bytes is None:
            return
        saw_counters = True
        total_read += max(0, int(read_bytes))
        total_write += max(0, int(write_bytes))

    _accumulate_io(proc)
    try:
        for child in proc.children(recursive=True):
            _accumulate_io(child)
    except Exception:
        pass

    if not saw_counters:
        return None

    now = time.time()
    entry = bucket.get(proc.pid)
    bucket[proc.pid] = {"time": now, "read": total_read, "write": total_write}

    read_rate_mb_s = None
    write_rate_mb_s = None
    if entry:
        elapsed = now - entry.get("time", now)
        if elapsed > 0:
            delta_read = total_read - entry.get("read", total_read)
            delta_write = total_write - entry.get("write", total_write)
            if delta_read >= 0:
                read_rate_mb_s = delta_read / (1024 * 1024) / elapsed
            if delta_write >= 0:
                write_rate_mb_s = delta_write / (1024 * 1024) / elapsed

    return {
        "disk_read_mb": total_read / (1024 * 1024),
        "disk_write_mb": total_write / (1024 * 1024),
        "disk_read_rate_mb_s": read_rate_mb_s,
        "disk_write_rate_mb_s": write_rate_mb_s,
    }


def clear_process_metric_cache(pid, cache_name=None):
    if pid is None:
        return
    KOMETA_CPU_CACHE.pop(pid, None)
    if cache_name:
        PROCESS_IO_CACHE.setdefault(cache_name, {}).pop(pid, None)


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


def normalize_kometa_start_mode(raw_mode):
    mode = str(raw_mode or "current").strip().lower()
    return mode if mode in {"current", "recovery", "logged"} else "current"


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


def write_quickstart_run_marker(kometa_root, config_name=None, start_mode="current"):
    try:
        version_info = _get_version_info()
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_config = (config_name or "default").strip() or "default"
        safe_start_mode = normalize_kometa_start_mode(start_mode)
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        marker = (
            f"[Quickstart] Run marker: started={timestamp} "
            f"config={safe_config} quickstart={qs_version} branch={qs_branch} "
            f"maintenance_markers=1 start_mode={safe_start_mode}"
        )
        reset_kometa_maintenance_sidecar(kometa_root)
        append_quickstart_meta_log_line(kometa_root, marker)
    except Exception:
        pass


def append_quickstart_meta_log_line(kometa_root, line):
    if not line:
        return False
    try:
        log_dir = Path(kometa_root) / "config" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "meta.log"
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def get_kometa_maintenance_sidecar_path(kometa_root):
    return Path(kometa_root) / "config" / "logs" / "meta.quickstart-maintenance.log"


def reset_kometa_maintenance_sidecar(kometa_root):
    try:
        sidecar_path = get_kometa_maintenance_sidecar_path(kometa_root)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False


def append_kometa_maintenance_sidecar_line(kometa_root, line):
    if not line:
        return False
    try:
        sidecar_path = get_kometa_maintenance_sidecar_path(kometa_root)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        with sidecar_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def is_logscan_maintenance_sidecar(path):
    try:
        name = Path(path).name.lower()
    except Exception:
        return False
    return name in {"meta.quickstart-maintenance.log", "imagemaid.quickstart-maintenance.log"}


def append_quickstart_imagemaid_log_line(imagemaid_root, line, log_path=None):
    if not line:
        return False
    try:
        root = Path(imagemaid_root)
        log_dir = root / "config" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        target = Path(log_path) if log_path else (log_dir / "imagemaid.log")
        with target.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def get_imagemaid_maintenance_sidecar_path(imagemaid_root):
    return Path(imagemaid_root) / "config" / "logs" / "imagemaid.quickstart-maintenance.log"


def reset_imagemaid_maintenance_sidecar(imagemaid_root):
    try:
        sidecar_path = get_imagemaid_maintenance_sidecar_path(imagemaid_root)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        sidecar_path.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False


def append_imagemaid_maintenance_sidecar_line(imagemaid_root, line):
    if not line:
        return False
    try:
        sidecar_path = get_imagemaid_maintenance_sidecar_path(imagemaid_root)
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        with sidecar_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def write_quickstart_maintenance_marker(kometa_root, event, window=None, paused_seconds=None):
    event_name = str(event or "").strip().lower()
    if event_name not in {"paused", "resumed"}:
        return False
    local_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    parts = [
        "[Quickstart] Maintenance marker:",
        f"event={event_name}",
        f"at={datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"local_at={local_at}",
    ]
    if window:
        parts.append(f"window={str(window).strip()}")
    if event_name == "resumed" and isinstance(paused_seconds, (int, float)):
        parts.append(f"paused_seconds={max(0, int(paused_seconds))}")
    import quickstart

    line = " ".join(parts)
    meta_ok = quickstart._append_quickstart_meta_log_line(kometa_root, line)
    sidecar_ok = append_kometa_maintenance_sidecar_line(kometa_root, line) if not meta_ok else False
    if not meta_ok and sidecar_ok:
        helpers.ts_log("Quickstart maintenance marker could not be appended to meta.log; preserved in sidecar instead.", level="WARNING")
    return bool(meta_ok or sidecar_ok)


def write_quickstart_imagemaid_run_marker(imagemaid_root, mode=None, config_name=None, log_path=None):
    try:
        version_info = _get_version_info()
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_mode = (mode or "report").strip().lower() or "report"
        safe_config = (config_name or "default").strip() or "default"
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        marker = f"[Quickstart] Run marker: started={timestamp} " f"config={safe_config} quickstart={qs_version} branch={qs_branch} " f"tool=imagemaid mode={safe_mode}"
        reset_imagemaid_maintenance_sidecar(imagemaid_root)
        return append_quickstart_imagemaid_log_line(imagemaid_root, marker, log_path=log_path)
    except Exception:
        return False


def write_quickstart_stop_marker(kometa_root, config_name=None, reason="user_stop"):
    try:
        version_info = _get_version_info()
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_config = (config_name or "default").strip() or "default"
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        marker = (
            f"[Quickstart] Run event: event=stopped at={timestamp} "
            f"config={safe_config} quickstart={qs_version} branch={qs_branch} "
            f"tool=kometa reason={str(reason or 'user_stop').strip() or 'user_stop'}"
        )
        return append_quickstart_meta_log_line(kometa_root, marker)
    except Exception:
        return False


def write_quickstart_imagemaid_stop_marker(imagemaid_root, mode=None, config_name=None, log_path=None, reason="user_stop"):
    try:
        version_info = _get_version_info()
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_mode = (mode or "report").strip().lower() or "report"
        safe_config = (config_name or "default").strip() or "default"
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        marker = (
            f"[Quickstart] Run event: event=stopped at={timestamp} "
            f"config={safe_config} quickstart={qs_version} branch={qs_branch} "
            f"tool=imagemaid mode={safe_mode} reason={str(reason or 'user_stop').strip() or 'user_stop'}"
        )
        return append_quickstart_imagemaid_log_line(imagemaid_root, marker, log_path=log_path)
    except Exception:
        return False


def write_quickstart_imagemaid_maintenance_marker(imagemaid_root, event, mode=None, config_name=None, window=None, log_path=None, paused_seconds=None):
    event_name = str(event or "").strip().lower()
    if event_name not in {"blocked_start", "paused", "resumed"}:
        return False
    try:
        version_info = _get_version_info()
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_mode = (mode or "report").strip().lower() or "report"
        safe_config = (config_name or "default").strip() or "default"
        local_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        parts = [
            "[Quickstart] Maintenance marker:",
            f"event={event_name}",
            f"at={datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            f"local_at={local_at}",
            f"config={safe_config}",
            "tool=imagemaid",
            f"mode={safe_mode}",
            f"quickstart={qs_version}",
            f"branch={qs_branch}",
        ]
        if window:
            parts.append(f"window={str(window).strip()}")
        if event_name == "resumed" and isinstance(paused_seconds, (int, float)):
            parts.append(f"paused_seconds={max(0, int(paused_seconds))}")
        line = " ".join(parts)
        meta_ok = append_quickstart_imagemaid_log_line(imagemaid_root, line, log_path=log_path)
        sidecar_ok = append_imagemaid_maintenance_sidecar_line(imagemaid_root, line) if not meta_ok else False
        if not meta_ok and sidecar_ok:
            helpers.ts_log("ImageMaid maintenance marker could not be appended to the live log; preserved in sidecar instead.", level="WARNING")
        return bool(meta_ok or sidecar_ok)
    except Exception:
        return False


def schedule_quickstart_run_marker(kometa_root, config_name=None, timeout_seconds=20, start_mode="current"):
    log_path = Path(kometa_root) / "config" / "logs" / "meta.log"
    state = {"mtime": None, "size": None}
    if log_path.exists():
        try:
            stat = log_path.stat()
            state["mtime"] = stat.st_mtime
            state["size"] = stat.st_size
        except OSError:
            pass

    def worker():
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if log_path.exists():
                    stat = log_path.stat()
                    if state["mtime"] is None:
                        if stat.st_size > 0:
                            write_quickstart_run_marker(kometa_root, config_name, start_mode=start_mode)
                            return
                    else:
                        if stat.st_mtime != state["mtime"] and stat.st_size > 0:
                            write_quickstart_run_marker(kometa_root, config_name, start_mode=start_mode)
                            return
            except OSError:
                pass
            time.sleep(0.5)
        write_quickstart_run_marker(kometa_root, config_name, start_mode=start_mode)

    threading.Thread(target=worker, daemon=True).start()


def extract_kometa_config_path(command_parts, kometa_root):
    config_value = None
    for idx, part in enumerate(command_parts):
        if part in {"-c", "--config"} and idx + 1 < len(command_parts):
            config_value = command_parts[idx + 1]
            break
        if part.startswith("--config="):
            config_value = part.split("=", 1)[1]
            break
        if part.startswith("-c="):
            config_value = part.split("=", 1)[1]
            break
    if not config_value:
        return None
    try:
        path = Path(config_value)
    except Exception:
        return None
    if not path.is_absolute():
        path = Path(kometa_root) / path
    return path


def stamp_quickstart_config_marker(config_path, config_name=None):
    if not config_path:
        return False
    path = Path(config_path)
    if not path.exists() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = content.splitlines()
    lines = [line for line in lines if not line.lstrip().startswith("# Quickstart run marker:")]
    version_info = _get_version_info()
    qs_version = version_info.get("local_version") or "unknown"
    qs_branch = version_info.get("branch") or "unknown"
    safe_config = (config_name or "default").strip() or "default"
    timestamp = datetime.now(timezone.utc).isoformat()
    marker = f"# Quickstart run marker: started={timestamp} " f"config={safe_config} quickstart={qs_version} branch={qs_branch}"
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(marker)
    try:
        path.write_text(newline.join(lines) + newline, encoding="utf-8")
        return True
    except Exception:
        return False
