"""Process discovery via psutil.

Split out of ``modules.process_control`` -- finds already-running
Kometa or ImageMaid subprocesses by scanning the OS process list.
Used by the status API to reattach to a running process and by the
maintenance guard loop to know whether to pause/resume anything.

## What lives here

* ``find_running_kometa_processes()`` -- scans ``psutil.process_iter``
  for anything with ``kometa.py`` in its cmdline, sorts matches so
  processes whose cmdline includes the configured kometa_root come
  first (with ties broken by newest ``create_time``), returns the
  full list.
* ``find_running_kometa_process()`` -- convenience wrapper returning
  the top of the list or ``None``.
* ``find_running_imagemaid_processes()`` / ``find_running_imagemaid_process()``
  -- same shape, but for ``imagemaid.py``.

## Design notes

The scans are best-effort: any per-process error (dead process, race,
access-denied) is caught and the entry is skipped rather than raising.
The root-path preference means Quickstart will attach to a Kometa
started FROM Quickstart's managed root even if some other Kometa is
also running on the machine.
"""

from __future__ import annotations

import psutil

from modules import helpers


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
