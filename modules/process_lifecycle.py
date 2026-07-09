"""Process lifecycle: launch, stop, suspend, resume, env-reset.

Split out of ``modules.process_control`` -- owns the imperative "actually
do something to the subprocess" verbs.

## What lives here

* ``stop_process_tree(proc)`` -- resumes-then-terminates a process
  tree; falls back to SIGKILL if anything's still alive after 5s.
* ``suspend_process_tree(proc)`` / ``resume_process_tree(proc)`` --
  used by the maintenance guard loop to pause / unpause Kometa while
  Plex is inside its scheduled maintenance window.
* ``launch_kometa_command(command, config_name, start_mode)`` --
  wraps the UI-built command with the correct venv python + kometa.py,
  writes the PID file, stamps run/config markers, and launches via
  ``subprocess.Popen``.
* ``launch_imagemaid_command(command, mode, config_name)`` -- same
  shape for ImageMaid, plus a poll-after-1s liveness check because
  ImageMaid can exit immediately on config errors.
* ``reset_imagemaid_runtime_env(imagemaid_root)`` -- wipes the
  ImageMaid ``.env`` file before launch so stale overrides don't
  leak across runs.

## Cross-cluster dependencies

* ``normalize_kometa_start_mode`` -- from ``process_control_state``.
* ``extract_kometa_config_path`` / ``stamp_quickstart_config_marker`` /
  ``schedule_quickstart_run_marker`` -- from ``process_markers``.
* ``update_imagemaid_run_context`` -- from ``process_run_context``
  (used by ``launch_imagemaid_command`` to record the run before
  spawning).
* ``quickstart._reset_imagemaid_runtime_env`` / ``_schedule_quickstart_imagemaid_run_marker``
  -- reached via lazy ``import quickstart`` so the monkeypatchable
  aliases in ``quickstart.py`` win (established test-seam pattern).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

from modules import helpers
from modules.process_control_state import normalize_kometa_start_mode
from modules.process_markers import (
    extract_kometa_config_path,
    schedule_quickstart_run_marker,
    stamp_quickstart_config_marker,
)
from modules.process_run_context import update_imagemaid_run_context

_KOMETA_RUNTIME_BRANCHES = {"master", "develop", "nightly"}


def _normalize_kometa_runtime_branch(value):
    branch = str(value or "").strip().lower()
    return branch if branch in _KOMETA_RUNTIME_BRANCHES else None


def _resolve_kometa_runtime_branch(kometa_root):
    branch = _normalize_kometa_runtime_branch(helpers.get_kometa_local_branch(kometa_root))
    if branch:
        return branch
    return _normalize_kometa_runtime_branch(helpers.detect_git_branch(kometa_root, default=None))


def _build_kometa_runtime_env(kometa_root):
    env = os.environ.copy()
    branch = _resolve_kometa_runtime_branch(kometa_root)
    if branch:
        env["BRANCH_NAME"] = branch
    else:
        env.pop("BRANCH_NAME", None)
    return env, branch


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
    runtime_env, runtime_branch = _build_kometa_runtime_env(kometa_root)
    if runtime_branch:
        helpers.ts_log(f"Kometa launch BRANCH_NAME={runtime_branch}", level="DEBUG")
    else:
        helpers.ts_log("Kometa launch BRANCH_NAME cleared", level="DEBUG")

    proc = subprocess.Popen(
        command_parts,
        cwd=str(kometa_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=runtime_env,
    )

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
