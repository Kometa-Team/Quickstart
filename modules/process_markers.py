"""Marker-file writers for Kometa & ImageMaid runs.

Split out of ``modules.process_control`` -- this cluster owns the
"annotate this run with metadata sidecars" logic: writing marker
files, maintenance sidecars, meta.log entries, and helper lookups
for their locations.

## What lives here

Grouped roughly by target:

### Kometa markers
* ``write_quickstart_run_marker`` -- ``.quickstart-run`` file next to
  Kometa's config.
* ``write_quickstart_maintenance_marker`` -- appends ``paused`` /
  ``resumed`` events to the run marker + sidecar + meta.log.
* ``write_quickstart_stop_marker`` -- records a user-requested stop.
* ``schedule_quickstart_run_marker`` -- fires a background thread
  that writes the run marker once Kometa creates its meta.log.
* ``append_quickstart_meta_log_line`` -- appends a single line to
  Kometa's meta.log.
* ``extract_kometa_config_path`` / ``stamp_quickstart_config_marker``
  -- resolves the config path from a command and writes the config
  marker next to it.
* ``get_kometa_maintenance_sidecar_path`` / ``reset_kometa_maintenance_sidecar``
  / ``append_kometa_maintenance_sidecar_line`` -- sidecar plumbing.
* ``is_logscan_maintenance_sidecar`` -- classifier for logscan.

### ImageMaid markers
Same shape as Kometa but written next to ImageMaid's runtime dir:

* ``write_quickstart_imagemaid_run_marker``
* ``write_quickstart_imagemaid_maintenance_marker``
* ``write_quickstart_imagemaid_stop_marker``
* ``append_quickstart_imagemaid_log_line``
* ``get_imagemaid_maintenance_sidecar_path`` /
  ``reset_imagemaid_maintenance_sidecar`` /
  ``append_imagemaid_maintenance_sidecar_line``

## Cross-cluster dependencies

* ``normalize_kometa_start_mode`` -- imported from
  ``modules.process_control_state`` (bottom layer).
* ``schedule_quickstart_run_marker`` fires a background thread that
  calls ``quickstart._find_running_kometa_process`` and
  ``quickstart._is_kometa_meta_log_ready`` -- accessed via lazy
  ``import quickstart`` inside the thread body (established pattern
  for reaching back into ``quickstart.py`` for test-monkeypatchable
  aliases).

## Backward compatibility

``modules.process_control`` re-exports every public name so callers
in ``quickstart.py`` (which imports many of these via alias) keep
working unchanged.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app as app, has_app_context

from modules import helpers
from modules.process_control_state import normalize_kometa_start_mode


def _get_version_info():
    if not has_app_context():
        return {}
    return app.config.get("VERSION_CHECK") or {}


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
