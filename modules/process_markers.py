"""Marker-file writers for Kometa & ImageMaid runs.

Split out of ``modules.process_control`` -- this cluster owns the
"annotate this run with metadata sidecars" logic: writing marker
files, pending journals, meta.log entries, and helper lookups for
their locations.

## What lives here

Grouped roughly by target:

### Kometa markers
* ``write_quickstart_run_marker`` -- ``.quickstart-run`` file next to
  Kometa's config.
* ``write_quickstart_maintenance_marker`` -- appends ``paused`` /
  ``resumed`` events to the run marker + pending journal + meta.log.
* ``write_quickstart_stop_marker`` -- records a user-requested stop.
* ``schedule_quickstart_run_marker`` -- fires a background thread
  that writes the run marker once Kometa creates its meta.log.
* ``append_quickstart_meta_log_line`` -- appends a single line to
  Kometa's meta.log.
* ``extract_kometa_config_path`` / ``stamp_quickstart_config_marker``
  -- resolves the config path from a command and writes the config
  marker next to it.
* ``get_kometa_pending_marker_path`` / ``append_kometa_pending_marker_line`` /
  ``flush_quickstart_pending_markers`` -- pending journal plumbing.
* ``get_kometa_maintenance_sidecar_path`` / ``reset_kometa_maintenance_sidecar`` /
  ``append_kometa_maintenance_sidecar_line`` -- legacy sidecar compatibility.
* ``is_logscan_maintenance_sidecar`` -- classifier for legacy/pending
  Quickstart log artifacts.

### ImageMaid markers
Same shape as Kometa but written next to ImageMaid's runtime dir:

* ``write_quickstart_imagemaid_run_marker``
* ``write_quickstart_imagemaid_maintenance_marker``
* ``write_quickstart_imagemaid_stop_marker``
* ``append_quickstart_imagemaid_log_line``
* ``get_imagemaid_pending_marker_path`` /
  ``append_imagemaid_pending_marker_line`` /
  ``flush_imagemaid_pending_markers``
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
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app as app, has_app_context

from modules import helpers
from modules.process_control_state import normalize_kometa_start_mode

QS_CONFIG_MARKER_PREFIX = "# [Quickstart] Run marker:"
LEGACY_QS_CONFIG_MARKER_PREFIX = "# Quickstart run marker:"
QS_CONFIG_MARKER_PREFIXES = (QS_CONFIG_MARKER_PREFIX, LEGACY_QS_CONFIG_MARKER_PREFIX)
QS_MARKER_REPLAY_START = "# [Quickstart] Marker replay start"
QS_MARKER_REPLAY_END = "# [Quickstart] Marker replay end"


def _get_version_info():
    if not has_app_context():
        return {}
    return app.config.get("VERSION_CHECK") or {}


def _resolve_version_fields(version_info=None):
    data = version_info if version_info is not None else _get_version_info()
    return data.get("local_version") or "unknown", data.get("branch") or "unknown"


def _get_tool_log_dir(root):
    return Path(root) / "config" / "logs"


def _append_text_line(path, line):
    if not line:
        return False
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def _reset_text_file(path):
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False


def _delete_text_file(path):
    try:
        target = Path(path)
        if target.exists():
            target.unlink()
        return True
    except Exception:
        return False


def _read_marker_lines(path):
    try:
        target = Path(path)
        if not target.exists() or not target.is_file():
            return []
        return [line.strip() for line in target.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    except Exception:
        return []


def _append_marker_to_pending_journal(pending_writer, root, line, marker_label):
    pending_ok = pending_writer(root, line)
    if not pending_ok:
        helpers.ts_log(f"Failed to append {marker_label} marker to the pending journal.", level="WARNING")
    return bool(pending_ok)


def _collect_unique_pending_marker_lines(*paths):
    collected = []
    seen = set()
    for path in paths:
        for line in _read_marker_lines(path):
            if line in seen:
                continue
            seen.add(line)
            collected.append(line)
    return collected


def _clear_marker_artifacts(*paths):
    for path in paths:
        _delete_text_file(path)


def _logger_body(line):
    if "|" not in line:
        return str(line).strip()
    return line.split("|", 1)[1].rsplit("|", 1)[0].strip()


def _is_config_marker_continuation(line):
    body = _logger_body(line)
    if not body or body.startswith("#") or "[Quickstart]" in body:
        return False
    return "=" in body and ("[config.py:" in line.lower() or line.startswith(" "))


def _has_config_marker(line):
    stripped = str(line).lstrip()
    body = _logger_body(line)
    return any(stripped.startswith(prefix) or body.startswith(prefix) for prefix in QS_CONFIG_MARKER_PREFIXES)


def _flush_pending_marker_file(log_path, pending_paths, marker_label):
    try:
        log_path = Path(log_path)
        pending_paths = [Path(path) for path in pending_paths if path]
        pending_lines = _collect_unique_pending_marker_lines(*pending_paths)
        if not pending_lines:
            _clear_marker_artifacts(*pending_paths)
            return {"flushed": True, "inserted": 0, "anchor": None}
        if not log_path.exists() or not log_path.is_file():
            return {"flushed": False, "inserted": 0, "anchor": "missing_log"}

        content = log_path.read_text(encoding="utf-8", errors="replace")
        existing_lines = {line.strip() for line in content.splitlines() if line.strip()}
        lines_to_insert = [line for line in pending_lines if line not in existing_lines]
        if not lines_to_insert:
            _clear_marker_artifacts(*pending_paths)
            return {"flushed": True, "inserted": 0, "anchor": "deduped"}

        newline = "\r\n" if "\r\n" in content else "\n"
        replay_block = [QS_MARKER_REPLAY_START, *lines_to_insert, QS_MARKER_REPLAY_END]
        file_lines = content.splitlines()
        anchor_index = None
        anchor_name = "eof"

        for idx, line in enumerate(file_lines):
            if _has_config_marker(line):
                anchor_index = idx + 1
                while anchor_index < len(file_lines) and _is_config_marker_continuation(file_lines[anchor_index]):
                    anchor_index += 1
                anchor_name = "config_marker"
                break

        if anchor_index is None:
            for idx, line in enumerate(file_lines):
                if "[Quickstart]" in line:
                    anchor_index = idx + 1
                    if _has_config_marker(line):
                        while anchor_index < len(file_lines) and _is_config_marker_continuation(file_lines[anchor_index]):
                            anchor_index += 1
                    anchor_name = "quickstart_line"
                    break

        if anchor_index is None:
            updated_lines = file_lines[:]
            if updated_lines and updated_lines[-1].strip():
                updated_lines.append("")
            updated_lines.extend(replay_block)
        else:
            updated_lines = file_lines[:anchor_index] + replay_block + file_lines[anchor_index:]

        updated_text = newline.join(updated_lines)
        if updated_text and not updated_text.endswith(newline):
            updated_text += newline
        log_path.write_text(updated_text, encoding="utf-8")
        _clear_marker_artifacts(*pending_paths)
        helpers.ts_log(
            f"Replayed {len(lines_to_insert)} pending {marker_label} marker(s) into {log_path.name} via {anchor_name}.",
            level="INFO",
        )
        return {"flushed": True, "inserted": len(lines_to_insert), "anchor": anchor_name}
    except Exception as exc:
        helpers.ts_log(f"Failed to replay pending {marker_label} markers into {Path(log_path).name}: {exc}", level="WARNING")
        return {"flushed": False, "inserted": 0, "anchor": "error"}


def append_quickstart_meta_log_line(kometa_root, line):
    if not line:
        return False
    try:
        log_dir = _get_tool_log_dir(kometa_root)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "meta.log"
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def get_kometa_maintenance_sidecar_path(kometa_root):
    return _get_tool_log_dir(kometa_root) / "meta.quickstart-maintenance.log"


def get_kometa_pending_marker_path(kometa_root):
    return _get_tool_log_dir(kometa_root) / "meta.quickstart-pending.log"


def reset_kometa_maintenance_sidecar(kometa_root):
    return _reset_text_file(get_kometa_maintenance_sidecar_path(kometa_root))


def append_kometa_maintenance_sidecar_line(kometa_root, line):
    return _append_text_line(get_kometa_maintenance_sidecar_path(kometa_root), line)


def append_kometa_pending_marker_line(kometa_root, line):
    return _append_text_line(get_kometa_pending_marker_path(kometa_root), line)


def is_logscan_maintenance_sidecar(path):
    try:
        name = Path(path).name.lower()
    except Exception:
        return False
    return name in {
        "meta.quickstart-maintenance.log",
        "imagemaid.quickstart-maintenance.log",
        "meta.quickstart-pending.log",
        "imagemaid.quickstart-pending.log",
    }


def _write_quickstart_marker_line(kometa_root, line, marker_kind="marker"):
    return _append_marker_to_pending_journal(
        append_kometa_pending_marker_line,
        kometa_root,
        line,
        f"Quickstart {marker_kind}",
    )


def flush_quickstart_pending_markers(kometa_root, require_process_stopped=True):
    if require_process_stopped and helpers.is_kometa_running():
        return {"flushed": False, "inserted": 0, "anchor": "running"}
    return _flush_pending_marker_file(
        _get_tool_log_dir(kometa_root) / "meta.log",
        [
            get_kometa_pending_marker_path(kometa_root),
            get_kometa_maintenance_sidecar_path(kometa_root),
        ],
        "Kometa",
    )


def append_quickstart_imagemaid_log_line(imagemaid_root, line, log_path=None):
    if not line:
        return False
    try:
        log_dir = _get_tool_log_dir(imagemaid_root)
        log_dir.mkdir(parents=True, exist_ok=True)
        target = Path(log_path) if log_path else (log_dir / "imagemaid.log")
        with target.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(str(line).rstrip() + "\n")
        return True
    except Exception:
        return False


def get_imagemaid_maintenance_sidecar_path(imagemaid_root):
    return _get_tool_log_dir(imagemaid_root) / "imagemaid.quickstart-maintenance.log"


def get_imagemaid_pending_marker_path(imagemaid_root):
    return _get_tool_log_dir(imagemaid_root) / "imagemaid.quickstart-pending.log"


def reset_imagemaid_maintenance_sidecar(imagemaid_root):
    return _reset_text_file(get_imagemaid_maintenance_sidecar_path(imagemaid_root))


def append_imagemaid_maintenance_sidecar_line(imagemaid_root, line):
    return _append_text_line(get_imagemaid_maintenance_sidecar_path(imagemaid_root), line)


def append_imagemaid_pending_marker_line(imagemaid_root, line):
    return _append_text_line(get_imagemaid_pending_marker_path(imagemaid_root), line)


def _write_imagemaid_marker_line(imagemaid_root, line, log_path=None, marker_kind="marker"):
    return _append_marker_to_pending_journal(
        append_imagemaid_pending_marker_line,
        imagemaid_root,
        line,
        f"ImageMaid {marker_kind}",
    )


def flush_imagemaid_pending_markers(imagemaid_root, log_path=None, require_process_stopped=True):
    if require_process_stopped and helpers.is_imagemaid_running():
        return {"flushed": False, "inserted": 0, "anchor": "running"}
    target_log_path = Path(log_path) if log_path else (_get_tool_log_dir(imagemaid_root) / "imagemaid.log")
    return _flush_pending_marker_file(
        target_log_path,
        [
            get_imagemaid_pending_marker_path(imagemaid_root),
            get_imagemaid_maintenance_sidecar_path(imagemaid_root),
        ],
        "ImageMaid",
    )


def write_quickstart_run_marker(kometa_root, config_name=None, start_mode="current", version_info=None):
    try:
        qs_version, qs_branch = _resolve_version_fields(version_info)
        safe_config = (config_name or "default").strip() or "default"
        safe_start_mode = normalize_kometa_start_mode(start_mode)
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        marker = (
            f"[Quickstart] Run marker: started={timestamp} "
            f"config={safe_config} quickstart={qs_version} branch={qs_branch} "
            f"maintenance_markers=1 start_mode={safe_start_mode}"
        )
        return _write_quickstart_marker_line(kometa_root, marker, marker_kind="run")
    except Exception as exc:
        helpers.ts_log(f"Failed to write Quickstart run marker: {exc}", level="WARNING")
        return False


def _build_quickstart_maintenance_marker_line(event, window=None, paused_seconds=None):
    event_name = str(event or "").strip().lower()
    if event_name not in {"paused", "resumed"}:
        return None
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
    return " ".join(parts)


def write_quickstart_maintenance_marker(kometa_root, event, window=None, paused_seconds=None, mirror_to_meta_log=False):
    line = _build_quickstart_maintenance_marker_line(event, window=window, paused_seconds=paused_seconds)
    if not line:
        return False
    pending_ok = _write_quickstart_marker_line(kometa_root, line, marker_kind="maintenance")
    if mirror_to_meta_log:
        meta_ok = append_quickstart_meta_log_line(kometa_root, line)
        return bool(pending_ok and meta_ok)
    return pending_ok


def write_quickstart_imagemaid_run_marker(imagemaid_root, mode=None, config_name=None, log_path=None):
    try:
        version_info = _get_version_info()
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_mode = (mode or "report").strip().lower() or "report"
        safe_config = (config_name or "default").strip() or "default"
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        marker = f"[Quickstart] Run marker: started={timestamp} " f"config={safe_config} quickstart={qs_version} branch={qs_branch} " f"tool=imagemaid mode={safe_mode}"
        return _write_imagemaid_marker_line(imagemaid_root, marker, log_path=log_path, marker_kind="run")
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
        return _write_quickstart_marker_line(kometa_root, marker, marker_kind="run event")
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
        return _write_imagemaid_marker_line(imagemaid_root, marker, log_path=log_path, marker_kind="run event")
    except Exception:
        return False


def _build_quickstart_imagemaid_maintenance_marker_line(event, mode=None, config_name=None, window=None, paused_seconds=None, version_info=None):
    event_name = str(event or "").strip().lower()
    if event_name not in {"blocked_start", "paused", "resumed"}:
        return None
    version_info = version_info if version_info is not None else _get_version_info()
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
    return " ".join(parts)


def write_quickstart_imagemaid_maintenance_marker(
    imagemaid_root,
    event,
    mode=None,
    config_name=None,
    window=None,
    log_path=None,
    paused_seconds=None,
    mirror_to_live_log=False,
):
    try:
        line = _build_quickstart_imagemaid_maintenance_marker_line(
            event,
            mode=mode,
            config_name=config_name,
            window=window,
            paused_seconds=paused_seconds,
        )
        if not line:
            return False
        pending_ok = _write_imagemaid_marker_line(imagemaid_root, line, log_path=log_path, marker_kind="maintenance")
        if mirror_to_live_log:
            live_ok = append_quickstart_imagemaid_log_line(imagemaid_root, line, log_path=log_path)
            return bool(pending_ok and live_ok)
        return pending_ok
    except Exception:
        return False


def schedule_quickstart_run_marker(kometa_root, config_name=None, timeout_seconds=20, start_mode="current"):
    version_info = dict(_get_version_info())

    def worker():
        write_quickstart_run_marker(kometa_root, config_name, start_mode=start_mode, version_info=version_info)

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
    lines = [line for line in lines if not any(line.lstrip().startswith(prefix) for prefix in QS_CONFIG_MARKER_PREFIXES)]
    version_info = _get_version_info()
    qs_version = version_info.get("local_version") or "unknown"
    qs_branch = version_info.get("branch") or "unknown"
    safe_config = (config_name or "default").strip() or "default"
    timestamp = datetime.now(timezone.utc).isoformat()
    marker = f"{QS_CONFIG_MARKER_PREFIX} started={timestamp} " f"config={safe_config} quickstart={qs_version} branch={qs_branch}"
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(marker)
    try:
        path.write_text(newline.join(lines) + newline, encoding="utf-8")
        return True
    except Exception:
        return False
