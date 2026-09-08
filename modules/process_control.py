"""Kometa/ImageMaid subprocess control -- launch, stop, and monitor.

This module used to be a 1250-line grab-bag.  Sprint 4 split it into
thematic siblings, all re-exported from here for backward compat:

* ``modules.process_control_state`` -- runtime state dicts + locks +
  the shared ``normalize_kometa_start_mode`` helper.  The bottom
  layer everything else imports from.
* ``modules.process_metrics`` -- CPU / IO stat calculators.
* ``modules.process_markers`` -- marker-file writers for both Kometa
  and ImageMaid runs.
* ``modules.process_maintenance`` -- maintenance-window resolution
  from the DB / from Plex live.
* ``modules.process_pending_start`` -- the pending-Kometa-start queue.
* ``modules.process_discovery`` -- psutil scans that find running
  Kometa / ImageMaid subprocesses.
* ``modules.process_lifecycle`` -- launch / stop / suspend / resume
  verbs.
* ``modules.process_run_context`` -- ``RUN_CONTEXT`` and
  ``IMAGEMAID_RUN_CONTEXT`` accessor functions.

The one function that still LIVES here is ``maintenance_guard_loop``
-- a 200-line background thread that ties every other cluster
together.  It's the natural owner of the top-level orchestration
and keeping it in ``process_control.py`` makes ``quickstart.py``'s
import line unchanged (``from modules.process_control import
maintenance_guard_loop``).

All 43 imports in ``quickstart.py`` (using ``X as _X`` aliases) reach
their target functions through the re-export blocks below without
caring which extracted module they live in.
"""

import os
import time
from datetime import datetime, timezone

import psutil

from modules import helpers, imagemaid

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
    append_imagemaid_pending_marker_line,
    append_kometa_maintenance_sidecar_line,
    append_kometa_pending_marker_line,
    append_quickstart_imagemaid_log_line,
    append_quickstart_meta_log_line,
    extract_kometa_config_path,
    flush_imagemaid_pending_markers,
    flush_quickstart_pending_markers,
    get_imagemaid_maintenance_sidecar_path,
    get_imagemaid_pending_marker_path,
    get_kometa_maintenance_sidecar_path,
    get_kometa_pending_marker_path,
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

# Maintenance-window resolution (parse/lookup/refresh) extracted to
# modules.process_maintenance.
from modules.process_maintenance import (  # noqa: F401
    get_active_maintenance_lookup_config_name,
    get_maintenance_window_from_db,
    get_maintenance_window_live,
    get_plex_credentials_from_db,
    is_within_maintenance_window,
    parse_maintenance_window_minutes,
    refresh_maintenance_window_availability,
    resolve_maintenance_window_from_db,
    resolve_maintenance_window_live,
)

# Pending Kometa-start queue extracted to modules.process_pending_start.
from modules.process_pending_start import (  # noqa: F401
    clear_pending_kometa_start,
    peek_pending_kometa_start,
    pop_pending_kometa_start,
    set_pending_kometa_start,
)

# Process discovery (psutil scans) extracted to modules.process_discovery.
from modules.process_discovery import (  # noqa: F401
    find_running_imagemaid_process,
    find_running_imagemaid_processes,
    find_running_kometa_process,
    find_running_kometa_processes,
)

# Process lifecycle (launch/stop/suspend/resume/env-reset) extracted to
# modules.process_lifecycle.
from modules.process_lifecycle import (  # noqa: F401
    launch_imagemaid_command,
    launch_kometa_command,
    reset_imagemaid_runtime_env,
    resume_process_tree,
    stop_process_tree,
    stop_launched_processes,
    suspend_process_tree,
)

# Run-context state accessors extracted to modules.process_run_context.
from modules.process_run_context import (  # noqa: F401
    clear_imagemaid_run_context,
    clear_run_context,
    extract_selected_libraries,
    get_imagemaid_run_context,
    get_run_context,
    normalize_imagemaid_command_text,
    update_imagemaid_run_context,
    update_run_context,
)


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
                        quickstart._clear_logscan_progress_snapshot()
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
                                if not quickstart._write_quickstart_maintenance_marker(
                                    helpers.get_kometa_root_path(),
                                    "paused",
                                    window=window_str,
                                    mirror_to_meta_log=True,
                                ):
                                    helpers.ts_log("Failed to record Quickstart paused maintenance marker.", level="WARNING")
                            except Exception:
                                helpers.ts_log("Failed to record Quickstart paused maintenance marker.", level="WARNING")
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
                                    mirror_to_meta_log=True,
                                ):
                                    helpers.ts_log("Failed to record Quickstart resumed maintenance marker.", level="WARNING")
                            except Exception:
                                helpers.ts_log("Failed to record Quickstart resumed maintenance marker.", level="WARNING")
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
                            mirror_to_live_log=True,
                        ):
                            helpers.ts_log("Failed to record Quickstart paused ImageMaid maintenance marker.", level="WARNING")
                    except Exception:
                        helpers.ts_log("Failed to record Quickstart paused ImageMaid maintenance marker.", level="WARNING")
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
                        mirror_to_live_log=True,
                    ):
                        helpers.ts_log("Failed to record Quickstart resumed ImageMaid maintenance marker.", level="WARNING")
                except Exception:
                    helpers.ts_log("Failed to record Quickstart resumed ImageMaid maintenance marker.", level="WARNING")
                with MAINTENANCE_STATE_LOCK:
                    MAINTENANCE_STATE["imagemaid_paused"] = False
                    MAINTENANCE_STATE["imagemaid_paused_since"] = None
