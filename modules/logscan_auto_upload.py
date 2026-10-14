"""Opt-in uploads of newly completed logs; local analysis stays independent."""

import math
import os
import time

from flask import current_app, has_app_context

from modules import helpers
from modules.logscan_upload import portal_uploader

AUTO_UPLOAD_KEYS = {tool: f"QS_LOGSCAN_AUTO_UPLOAD_{tool.upper()}" for tool in ("kometa", "imagemaid")}


def initialize_auto_upload_settings(app):
    for key in AUTO_UPLOAD_KEYS.values():
        enabled = str(os.getenv(key, "0")).strip().lower() in {"1", "true", "yes"}
        app.config[key] = enabled
        try:
            since = float(os.getenv(f"{key}_SINCE", "0"))
        except ValueError:
            since = 0
        app.config[f"{key}_SINCE"] = since if math.isfinite(since) and since > 0 else time.time()


def update_auto_upload_setting(tool, enabled):
    key = AUTO_UPLOAD_KEYS[tool]
    if enabled == current_app.config.get(key, False):
        return False
    if enabled:
        since = time.time()
        helpers.update_env_variable(f"{key}_SINCE", str(since))
        current_app.config[f"{key}_SINCE"] = since
    helpers.update_env_variable(key, "1" if enabled else "0")
    current_app.config[key] = enabled
    return True


def queue_completed_log(path, summary, tool, *, source_mtime=None):
    key = AUTO_UPLOAD_KEYS.get(tool)
    if not key or not current_app.config.get(key, False) or not summary.get("run_complete") or not summary.get("run_key"):
        return False
    try:
        updated_at = float(path.stat().st_mtime if source_mtime is None else source_mtime)
        since = float(current_app.config[f"{key}_SINCE"])
    except (OSError, KeyError, TypeError, ValueError, OverflowError):
        return False
    # Filesystem timestamps are timezone-independent; use the pre-archive value
    # so flushing local markers cannot opt an old log into an upload.
    if not math.isfinite(updated_at) or not math.isfinite(since) or since <= 0 or updated_at < since:
        return False
    app = current_app._get_current_object()
    return portal_uploader.enqueue_auto(
        path,
        config_name=summary.get("config_name"),
        run_key=summary["run_key"],
        tool_name=tool,
        enabled=lambda: bool(app.config.get(key, False)),
    )


def ingest_auto_upload_logs():
    import quickstart

    for tool, key in AUTO_UPLOAD_KEYS.items():
        if current_app.config.get(key, False):
            quickstart._start_logscan_live_ingest(tool)


def queue_saved_completed_log(path, cache_entry, tool):
    key = AUTO_UPLOAD_KEYS.get(tool)
    if not has_app_context() or not key or not current_app.config.get(key, False):
        return False
    from modules import database

    summary = database.get_log_run(cache_entry.get("run_key"))
    if not summary or not summary.get("finished_at"):
        return False
    return queue_completed_log(path, {**summary, "run_complete": True}, tool, source_mtime=cache_entry.get("mtime"))
