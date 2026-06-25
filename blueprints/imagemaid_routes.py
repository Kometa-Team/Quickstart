"""Runtime routes for ImageMaid (validate, autosave, start, stop, status).

These five routes used to live in ``quickstart.py``.  They were extracted
as part of PR F in the quickstart.py refactor sprint -- the goal is to
keep ``quickstart.py`` to roughly 5,000 lines by moving cohesive route
clusters into dedicated blueprint modules.

Naming
------
A separate blueprint module already exists at
``blueprints/imagemaid_updates.py`` for the **install/probe/update**
flow (e.g. ``/probe-imagemaid-root``).  This module owns the **runtime**
flow -- everything that interacts with a *running* ImageMaid process
plus its config validation/autosave.  The two are kept separate because
they share no routes, only a common config and a common
``modules.imagemaid`` helper surface.

Test-patch boundary (why everything routes through ``_qs``)
----------------------------------------------------------
The existing test suite patches a large set of helpers via
``monkeypatch.setattr(qs_module, "_foo", ...)``.  Those patches only
mutate the ``quickstart`` module's namespace -- they do **not**
propagate to a blueprint module that imported the helper directly
from ``modules.imagemaid`` or ``modules.process_control``.

To keep the existing tests working without a 150-site rewrite, every
route below opens with::

    import quickstart as _qs
    _foo = _qs._foo  # for each leading-underscore helper the route uses

and then resolves *every* leading-underscore helper through ``_qs``.
This mirrors the pattern used by PR E (``import_config_routes``) for
its bundle helpers, and matches the convention already followed by
``modules.process_control.resolve_maintenance_window_live`` -- a
dispatch back into ``quickstart`` to honor monkeypatches.

The route *bodies* are therefore byte-for-byte identical to the
develop versions (only the decorator changed from ``@app.route`` to
``@bp.route`` and the ``_qs`` preamble was added).  AST-verified --
see PR description.

The pattern looks repetitive, but it's the smallest possible delta
that lets us:
  * keep tests untouched (158 ``qs_module.setattr`` calls in
    ``test_start_stop.py`` alone),
  * keep the route logic literally identical to the develop source,
  * still get the line-count win on ``quickstart.py``.
"""

from datetime import datetime
import os
import threading
import time
from pathlib import Path

import psutil
from flask import Blueprint, jsonify, request, session

from modules import helpers, persistence  # noqa: F401 (used inside routes via attribute access)
from modules.process_control import (
    MAINTENANCE_STATE,
    MAINTENANCE_STATE_LOCK,
)

bp = Blueprint("imagemaid_routes", __name__)


# Grace period after launch during which a still-spawning ImageMaid process
# is reported as "starting" rather than "not started" or "done".  Keeps the
# UI from flickering before the child process is fully up.
IMAGEMAID_STARTUP_GRACE_SECONDS = 10


# --- routes ---------------------------------------------------------------
@bp.route("/validate-imagemaid", methods=["POST"])
def validate_imagemaid():
    import quickstart as _qs

    _build_imagemaid_command = _qs._build_imagemaid_command
    _get_imagemaid_settings_section = _qs._get_imagemaid_settings_section
    _get_stored_plex_credentials_for_config = _qs._get_stored_plex_credentials_for_config
    _imagemaid_settings_to_form_payload = _qs._imagemaid_settings_to_form_payload
    _persist_imagemaid_validation = _qs._persist_imagemaid_validation
    _resolve_request_config_name = _qs._resolve_request_config_name
    _save_imagemaid_settings_for_config = _qs._save_imagemaid_settings_for_config
    _validate_imagemaid_settings = _qs._validate_imagemaid_settings

    payload = request.get_json(silent=True) or {}
    config_name = _resolve_request_config_name(payload)
    form_payload = _imagemaid_settings_to_form_payload(payload)
    if form_payload:
        _save_imagemaid_settings_for_config(config_name, form_payload)

    settings, section_data = _get_imagemaid_settings_section(config_name)
    is_valid, reason, details = _validate_imagemaid_settings(section_data, config_name=config_name)
    _persist_imagemaid_validation(config_name, section_data, is_valid, reason=reason, details=details)

    plex_url, plex_token = _get_stored_plex_credentials_for_config(config_name)
    preview_command = _build_imagemaid_command(section_data, plex_url or "", plex_token or "", redact=True)
    return jsonify(success=is_valid, validated=is_valid, reason=reason, details=details, command_preview=preview_command), (200 if is_valid else 400)


@bp.route("/autosave-imagemaid", methods=["POST"])
def autosave_imagemaid():
    import quickstart as _qs

    _get_imagemaid_settings_section = _qs._get_imagemaid_settings_section
    _imagemaid_settings_to_form_payload = _qs._imagemaid_settings_to_form_payload
    _persist_imagemaid_validation = _qs._persist_imagemaid_validation
    _resolve_request_config_name = _qs._resolve_request_config_name
    _save_imagemaid_settings_for_config = _qs._save_imagemaid_settings_for_config

    payload = request.get_json(silent=True) or {}
    config_name = _resolve_request_config_name(payload)
    form_payload = _imagemaid_settings_to_form_payload(payload)
    changed = False
    if form_payload:
        _saved_payload, changed = _save_imagemaid_settings_for_config(config_name, form_payload)

    settings, section_data = _get_imagemaid_settings_section(config_name)
    if changed and helpers.booler(settings.get("validated", False)):
        _persist_imagemaid_validation(
            config_name,
            section_data,
            False,
            reason="config_changed",
            details="Configuration changed. Validate ImageMaid again.",
        )
        validated = False
    else:
        validated = helpers.booler(settings.get("validated", False))

    return jsonify(success=True, changed=changed, validated=validated)


@bp.route("/start-imagemaid", methods=["POST"])
def start_imagemaid():
    import quickstart as _qs

    _build_imagemaid_command = _qs._build_imagemaid_command
    _build_imagemaid_command_parts = _qs._build_imagemaid_command_parts
    _find_running_imagemaid_process = _qs._find_running_imagemaid_process
    _get_active_work_blocker = _qs._get_active_work_blocker
    _get_imagemaid_settings_section = _qs._get_imagemaid_settings_section
    _get_latest_imagemaid_log_path = _qs._get_latest_imagemaid_log_path
    _get_stored_plex_credentials_for_config = _qs._get_stored_plex_credentials_for_config
    _imagemaid_settings_to_form_payload = _qs._imagemaid_settings_to_form_payload
    _is_within_maintenance_window = _qs._is_within_maintenance_window
    _launch_imagemaid_command = _qs._launch_imagemaid_command
    _persist_imagemaid_validation = _qs._persist_imagemaid_validation
    _resolve_maintenance_window_from_db = _qs._resolve_maintenance_window_from_db
    _resolve_maintenance_window_live = _qs._resolve_maintenance_window_live
    _resolve_request_config_name = _qs._resolve_request_config_name
    _save_imagemaid_settings_for_config = _qs._save_imagemaid_settings_for_config
    _validate_imagemaid_settings = _qs._validate_imagemaid_settings
    _write_quickstart_imagemaid_maintenance_marker = _qs._write_quickstart_imagemaid_maintenance_marker

    payload = request.get_json(silent=True) or {}
    config_name = _resolve_request_config_name(payload)
    form_payload = _imagemaid_settings_to_form_payload(payload)
    if form_payload:
        _save_imagemaid_settings_for_config(config_name, form_payload)

    if helpers.is_imagemaid_running():
        pid = helpers.get_imagemaid_pid()
        try:
            proc = psutil.Process(pid)
            started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            return jsonify({"error": f"ImageMaid is already running (PID: {pid}) since {started_at}.", "status": "running", "pid": pid, "started_at": started_at}), 400
        except Exception:
            return jsonify({"error": f"ImageMaid is already running (PID: {pid}).", "status": "running", "pid": pid}), 400
    else:
        proc = _find_running_imagemaid_process()
        if proc:
            try:
                with open(helpers.get_imagemaid_pid_file(), "w", encoding="utf-8") as f:
                    f.write(str(proc.pid))
                started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            except Exception:
                started_at = None
            payload = {"error": f"ImageMaid is already running (PID: {proc.pid}).", "status": "running", "pid": proc.pid}
            if started_at:
                payload["started_at"] = started_at
            return jsonify(payload), 400

    blocker = _get_active_work_blocker("imagemaid_run")
    if blocker:
        job = blocker.get("job") if isinstance(blocker.get("job"), dict) else {}
        response = {
            "error": blocker.get("message") or "Cannot start ImageMaid right now.",
            "status": "blocked",
            "blocked_by": blocker.get("blocked_by"),
            "target_page": blocker.get("target_page"),
        }
        if blocker.get("pid"):
            response["pid"] = blocker.get("pid")
        if job.get("job_id"):
            response["job_id"] = job.get("job_id")
        if job.get("phase"):
            response["phase"] = job.get("phase")
        return jsonify(response), 409

    settings, section_data = _get_imagemaid_settings_section(config_name)
    is_valid, reason, details = _validate_imagemaid_settings(section_data, config_name=config_name)
    _persist_imagemaid_validation(config_name, section_data, is_valid, reason=reason, details=details)
    if not is_valid:
        return jsonify({"error": details or "ImageMaid settings are not valid.", "status": "invalid", "reason": reason}), 400

    start_min, end_min, window_str = _resolve_maintenance_window_live(config_name=config_name)
    if start_min is None or end_min is None:
        start_min, end_min, window_str = _resolve_maintenance_window_from_db(config_name=config_name)
    if _is_within_maintenance_window(datetime.now(), start_min, end_min):
        try:
            _write_quickstart_imagemaid_maintenance_marker(
                helpers.get_imagemaid_root_path(),
                "blocked_start",
                mode=section_data.get("mode"),
                config_name=config_name,
                window=window_str,
                log_path=_get_latest_imagemaid_log_path(),
            )
        except Exception:
            pass
        window_label = f" ({window_str})" if window_str else ""
        return (
            jsonify(
                {
                    "error": f"ImageMaid cannot start during the Plex maintenance window{window_label}.",
                    "status": "maintenance_blocked",
                    "maintenance_window": window_str,
                }
            ),
            409,
        )

    plex_url, plex_token = _get_stored_plex_credentials_for_config(config_name)
    command = _build_imagemaid_command_parts(section_data, plex_url, plex_token, redact=False)
    ok, result = _launch_imagemaid_command(command, mode=section_data.get("mode"), config_name=config_name)
    if ok:
        return jsonify({"status": "ImageMaid started", "pid": result, "command_preview": _build_imagemaid_command(section_data, plex_url, plex_token, redact=True)})
    code = 500
    if isinstance(result, str):
        lowered = result.lower()
        if lowered.startswith("imagemaid.py not found"):
            code = 404
        elif "exited immediately" in lowered or "finished immediately" in lowered:
            code = 400
    return jsonify({"error": result}), code


@bp.route("/stop-imagemaid", methods=["POST"])
def stop_imagemaid():
    import quickstart as _qs

    _clear_imagemaid_run_context = _qs._clear_imagemaid_run_context
    _find_running_imagemaid_process = _qs._find_running_imagemaid_process
    _find_running_imagemaid_processes = _qs._find_running_imagemaid_processes
    _get_imagemaid_settings_section = _qs._get_imagemaid_settings_section
    _get_latest_imagemaid_log_path = _qs._get_latest_imagemaid_log_path
    _stop_process_tree = _qs._stop_process_tree
    _write_quickstart_imagemaid_stop_marker = _qs._write_quickstart_imagemaid_stop_marker

    config_name = session.get("config_name") or persistence.ensure_session_config_name()
    pid = helpers.get_imagemaid_pid()
    pid_file = helpers.get_imagemaid_pid_file()

    if not pid:
        procs = _find_running_imagemaid_processes()
        if not procs:
            return jsonify({"warning": "No active ImageMaid PID"}), 200
    else:
        proc = _find_running_imagemaid_process()
        procs = [proc] if proc is not None else []

    try:
        if not procs:
            return jsonify({"warning": "No active ImageMaid process found."}), 200

        _settings, section_data = _get_imagemaid_settings_section()
        imagemaid_mode = section_data.get("mode") if isinstance(section_data, dict) else None
        not_imagemaid = []
        alive_after = []
        for proc in procs:
            cmdline = " ".join(proc.cmdline() or [])
            if "imagemaid.py" not in cmdline:
                not_imagemaid.append(proc.pid)
                continue
            alive_after.extend(_stop_process_tree(proc))

        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_imagemaid_run_context()
        try:
            _write_quickstart_imagemaid_stop_marker(
                helpers.get_imagemaid_root_path(),
                mode=imagemaid_mode,
                config_name=config_name,
                log_path=_get_latest_imagemaid_log_path(),
                reason="user_stop",
            )
        except Exception:
            pass

        if alive_after:
            alive_pids = ", ".join(str(p.pid) for p in alive_after if p is not None)
            return jsonify({"warning": f"ImageMaid stop requested, but some processes are still running: {alive_pids}"}), 200
        if not_imagemaid:
            return jsonify({"warning": f"Cleaned PID file. Non-ImageMaid PIDs detected: {', '.join(map(str, not_imagemaid))}"}), 200
        return jsonify({"success": True, "message": "ImageMaid stopped and cleaned up."}), 200
    except psutil.NoSuchProcess:
        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_imagemaid_run_context()
        try:
            _settings, section_data = _get_imagemaid_settings_section()
            imagemaid_mode = section_data.get("mode") if isinstance(section_data, dict) else None
            _write_quickstart_imagemaid_stop_marker(
                helpers.get_imagemaid_root_path(),
                mode=imagemaid_mode,
                config_name=config_name,
                log_path=_get_latest_imagemaid_log_path(),
                reason="process_missing",
            )
        except Exception:
            pass
        return jsonify({"warning": "Process not found. Cleaned up PID file."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to stop ImageMaid: {str(e)}"}), 500


@bp.route("/imagemaid-status", methods=["GET"])
def imagemaid_status():
    import quickstart as _qs

    _calculate_process_cpu_percent = _qs._calculate_process_cpu_percent
    _calculate_process_io_stats = _qs._calculate_process_io_stats
    _calculate_system_cpu_percent = _qs._calculate_system_cpu_percent
    _clear_imagemaid_run_context = _qs._clear_imagemaid_run_context
    _clear_process_metric_cache = _qs._clear_process_metric_cache
    _find_running_imagemaid_process = _qs._find_running_imagemaid_process
    _get_imagemaid_run_context = _qs._get_imagemaid_run_context
    _ingest_completed_live_logs = _qs._ingest_completed_live_logs
    _refresh_maintenance_window_availability = _qs._refresh_maintenance_window_availability

    try:
        _refresh_maintenance_window_availability(preserve_active_state=True)
    except Exception:
        pass
    pid = helpers.get_imagemaid_pid()
    pid_file = Path(helpers.get_imagemaid_pid_file())
    imagemaid_ctx = _get_imagemaid_run_context()
    with MAINTENANCE_STATE_LOCK:
        maintenance_active = MAINTENANCE_STATE["active"]
        maintenance_window = MAINTENANCE_STATE["window"]
        maintenance_paused = MAINTENANCE_STATE["imagemaid_paused"]
        maintenance_paused_since = MAINTENANCE_STATE["imagemaid_paused_since"]

    def pid_file_age_seconds():
        try:
            if pid_file.exists():
                return max(0.0, time.time() - pid_file.stat().st_mtime)
        except Exception:
            return None
        return None

    if not pid:
        proc = _find_running_imagemaid_process()
        if proc:
            try:
                with open(pid_file, "w", encoding="utf-8") as f:
                    f.write(str(proc.pid))
                pid = proc.pid
            except Exception:
                pid = None
    if not pid:
        try:
            _ingest_completed_live_logs("imagemaid")
        except Exception:
            pass
        _clear_imagemaid_run_context()
        return jsonify(
            status="not started",
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
        )

    try:
        proc = psutil.Process(pid)
        started_at_ts = None
        elapsed_seconds = None
        within_grace = False
        try:
            started_at_ts = proc.create_time()
            elapsed_seconds = max(0, int(time.time() - started_at_ts))
            within_grace = elapsed_seconds < IMAGEMAID_STARTUP_GRACE_SECONDS
        except Exception:
            age = pid_file_age_seconds()
            if age is not None:
                elapsed_seconds = max(0, int(age))
                within_grace = age < IMAGEMAID_STARTUP_GRACE_SECONDS
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            try:
                cmdline = " ".join(proc.cmdline() or [])
            except Exception:
                cmdline = ""
            if "imagemaid.py" in cmdline:
                started_at = datetime.fromtimestamp(started_at_ts).isoformat()
                cpu_percent = _calculate_process_cpu_percent(proc)
                io_stats = _calculate_process_io_stats(proc, "imagemaid") or {}
                mem_rss = proc.memory_info().rss
                try:
                    for child in proc.children(recursive=True):
                        try:
                            mem_rss += child.memory_info().rss
                        except Exception:
                            continue
                except Exception:
                    pass
                mem_rss_mb = mem_rss / (1024 * 1024)
                system_cpu_percent = _calculate_system_cpu_percent()
                vm = psutil.virtual_memory()
                system_mem_used_mb = (vm.total - vm.available) / (1024 * 1024)
                system_mem_total_mb = vm.total / (1024 * 1024)
                mem_percent = (mem_rss / vm.total) * 100.0 if vm.total else None
                return jsonify(
                    status="running",
                    pid=pid,
                    started_at=started_at,
                    started_at_ts=started_at_ts,
                    elapsed_seconds=elapsed_seconds,
                    cpu_percent=round(cpu_percent, 1) if cpu_percent is not None else None,
                    memory_rss_mb=round(mem_rss_mb, 1),
                    memory_percent=round(mem_percent, 2) if mem_percent is not None else None,
                    disk_read_mb=round(io_stats.get("disk_read_mb"), 1) if io_stats.get("disk_read_mb") is not None else None,
                    disk_write_mb=round(io_stats.get("disk_write_mb"), 1) if io_stats.get("disk_write_mb") is not None else None,
                    disk_read_rate_mb_s=round(io_stats.get("disk_read_rate_mb_s"), 2) if io_stats.get("disk_read_rate_mb_s") is not None else None,
                    disk_write_rate_mb_s=round(io_stats.get("disk_write_rate_mb_s"), 2) if io_stats.get("disk_write_rate_mb_s") is not None else None,
                    system_cpu_percent=round(system_cpu_percent, 1) if system_cpu_percent is not None else None,
                    system_memory_percent=round(vm.percent, 1),
                    system_memory_used_mb=round(system_mem_used_mb, 1),
                    system_memory_total_mb=round(system_mem_total_mb, 1),
                    maintenance_active=maintenance_active,
                    maintenance_paused=maintenance_paused,
                    maintenance_window=maintenance_window,
                    maintenance_paused_since=maintenance_paused_since,
                    active_command=imagemaid_ctx.get("command"),
                    mode=imagemaid_ctx.get("mode"),
                    config_name=imagemaid_ctx.get("config_name"),
                )
            if within_grace:
                payload = {"status": "starting", "pid": pid, "elapsed_seconds": elapsed_seconds}
                if started_at_ts is not None:
                    payload["started_at"] = datetime.fromtimestamp(started_at_ts).isoformat()
                    payload["started_at_ts"] = started_at_ts
                payload["maintenance_active"] = maintenance_active
                payload["maintenance_paused"] = maintenance_paused
                payload["maintenance_window"] = maintenance_window
                payload["maintenance_paused_since"] = maintenance_paused_since
                return jsonify(payload)
        try:
            rc = proc.wait(timeout=0.1)
        except psutil.TimeoutExpired:
            if within_grace:
                payload = {"status": "starting", "pid": pid, "elapsed_seconds": elapsed_seconds}
                if started_at_ts is not None:
                    payload["started_at"] = datetime.fromtimestamp(started_at_ts).isoformat()
                    payload["started_at_ts"] = started_at_ts
                payload["maintenance_active"] = maintenance_active
                payload["maintenance_paused"] = maintenance_paused
                payload["maintenance_window"] = maintenance_window
                payload["maintenance_paused_since"] = maintenance_paused_since
                return jsonify(payload)
            rc = None
        finally:
            if not within_grace:
                try:
                    os.remove(pid_file)
                except Exception:
                    pass
                _clear_process_metric_cache(pid, "imagemaid")
                _clear_imagemaid_run_context()
        if not within_grace:
            try:
                _ingest_completed_live_logs("imagemaid")
            except Exception:
                pass
        return jsonify(
            status="done",
            return_code=rc if rc is not None else -1,
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
        )
    except psutil.NoSuchProcess:
        age = pid_file_age_seconds()
        if age is not None and age < IMAGEMAID_STARTUP_GRACE_SECONDS:
            return jsonify(
                status="starting",
                pid=pid,
                elapsed_seconds=max(0, int(age)),
                maintenance_active=maintenance_active,
                maintenance_paused=maintenance_paused,
                maintenance_window=maintenance_window,
                maintenance_paused_since=maintenance_paused_since,
            )
        try:
            os.remove(pid_file)
        except Exception:
            pass
        _clear_process_metric_cache(pid, "imagemaid")
        _clear_imagemaid_run_context()
        return jsonify(
            status="not started",
            maintenance_active=maintenance_active,
            maintenance_paused=maintenance_paused,
            maintenance_window=maintenance_window,
            maintenance_paused_since=maintenance_paused_since,
        )


def _schedule_quickstart_imagemaid_run_marker(imagemaid_root, mode=None, config_name=None, timeout_seconds=20):
    import quickstart as _qs

    _write_quickstart_imagemaid_run_marker = _qs._write_quickstart_imagemaid_run_marker

    root = Path(imagemaid_root)
    log_dir = root / "config" / "logs"
    initial = {}
    if log_dir.exists():
        for path in log_dir.glob("*.log"):
            try:
                stat = path.stat()
                initial[str(path)] = (stat.st_mtime, stat.st_size)
            except OSError:
                continue

    def worker():
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if log_dir.exists():
                    candidates = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
                    for path in candidates:
                        try:
                            stat = path.stat()
                        except OSError:
                            continue
                        prev = initial.get(str(path))
                        if prev is None:
                            if stat.st_size > 0:
                                _write_quickstart_imagemaid_run_marker(root, mode=mode, config_name=config_name, log_path=path)
                                return
                        elif (stat.st_mtime, stat.st_size) != prev and stat.st_size > 0:
                            _write_quickstart_imagemaid_run_marker(root, mode=mode, config_name=config_name, log_path=path)
                            return
            except Exception:
                pass
            time.sleep(0.5)
        _write_quickstart_imagemaid_run_marker(root, mode=mode, config_name=config_name)

    threading.Thread(target=worker, daemon=True).start()
