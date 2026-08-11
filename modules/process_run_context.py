"""Run-context state for the Kometa and ImageMaid subprocesses.

Split out of ``modules.process_control`` -- owns the two ``*_RUN_CONTEXT``
dicts (from ``modules.process_control_state``) that record what the
last-launched subprocess is doing.  The status API reads these to
render "Kometa is running --run-libraries=Movies|Shows since 2 minutes
ago".

## What lives here

Kometa side:

* ``extract_selected_libraries(command)`` -- parses ``--run-libraries``
  or ``--times`` out of a Kometa command line.  Returns
  ``(run_option, [library, ...])``.
* ``update_run_context(command, config_name, start_mode)`` -- writes
  the current Kometa run into ``RUN_CONTEXT`` (locked).  Also picks
  a ``run_mode`` (all / metadata / operations / playlists / overlays /
  collections) by inspecting flags in the command.
* ``get_run_context()`` -- returns a copy of ``RUN_CONTEXT``.
* ``clear_run_context()`` -- resets ``RUN_CONTEXT`` to the empty state.

ImageMaid side (mirrors Kometa but simpler -- ImageMaid has no
run-mode flags):

* ``normalize_imagemaid_command_text(command)`` -- accepts either a
  list or a string and returns a single command-line string.
* ``update_imagemaid_run_context(command, mode, config_name)``.
* ``get_imagemaid_run_context()``.
* ``clear_imagemaid_run_context()``.

## Cross-cluster dependencies

* Shared state from ``modules.process_control_state``.
* ``normalize_kometa_start_mode`` -- from the state module.
* ``extract_kometa_config_path`` from ``modules.process_markers`` --
  needed by ``update_run_context`` to record the config file path
  next to the run.
"""

from __future__ import annotations

import shlex
import sys
from datetime import datetime, timezone

from flask import has_request_context, session

from modules import helpers
from modules.process_control_state import (
    IMAGEMAID_RUN_CONTEXT,
    IMAGEMAID_RUN_CONTEXT_LOCK,
    RUN_CONTEXT,
    RUN_CONTEXT_LOCK,
    normalize_kometa_start_mode,
)
from modules.process_markers import extract_kometa_config_path


def _strip_outer_quotes(value):
    text = str(value or "")
    if len(text) >= 2 and ((text[0] == '"' and text[-1] == '"') or (text[0] == "'" and text[-1] == "'")):
        return text[1:-1]
    return text


def _parse_run_libraries_value(value):
    text = str(value or "")
    if not text:
        return []

    parts = []
    current = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "|":
            token = "".join(current)
            if token and token.strip():
                parts.append(token)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    token = "".join(current)
    if token and token.strip():
        parts.append(token)
    return parts


def extract_selected_libraries(command):
    if not command:
        return None, None

    is_win = sys.platform.startswith("win")
    try:
        parts = shlex.split(str(command), posix=not is_win)
    except ValueError:
        parts = str(command).split()

    run_option = None
    selected = None
    for idx, part in enumerate(parts):
        if part in ("--run", "--run-libraries", "--times"):
            run_option = part
        if part.startswith("--run-libraries="):
            raw_value = _strip_outer_quotes(part.split("=", 1)[1])
            selected = _parse_run_libraries_value(raw_value)
            break
        if part == "--run-libraries" and idx + 1 < len(parts):
            raw_value = _strip_outer_quotes(parts[idx + 1])
            selected = _parse_run_libraries_value(raw_value)
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
