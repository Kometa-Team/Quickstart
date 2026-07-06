"""Shared module-level state for the process_control cluster.

Bottom-layer module used by every extracted sibling
(``process_maintenance``, ``process_pending_start``, ``process_discovery``,
``process_lifecycle``, ``process_run_context``, ``process_markers``) plus
the original ``process_control`` module itself.

Contains only:

* Module-level dicts that hold in-memory runtime state (``MAINTENANCE_STATE``,
  ``PENDING_KOMETA_START``, ``RUN_CONTEXT``, ``IMAGEMAID_RUN_CONTEXT``).
* Their ``threading.Lock`` companions (each state dict has exactly one).
* ``MAINTENANCE_GUARD_INTERVAL`` -- the seconds-between-ticks constant
  read only by ``maintenance_guard_loop``.
* ``normalize_kometa_start_mode`` -- a tiny pure-function normalizer
  called from 4 different clusters, so parking it here avoids
  cross-cluster import chains.

## Why a dedicated bottom layer?

Every state dict is mutated by exactly ONE cluster's functions:

* ``MAINTENANCE_STATE`` <- ``process_maintenance`` + ``guard_loop``
* ``PENDING_KOMETA_START`` <- ``process_pending_start``
* ``RUN_CONTEXT`` <- ``process_run_context``
* ``IMAGEMAID_RUN_CONTEXT`` <- ``process_run_context``

But those dicts are also *read* by callers in other clusters (and by
``quickstart.py`` for the API surface).  Instead of scattering the
"where does this dict live?" answer across N modules, we keep a single
canonical home in this bottom module and everyone imports from here.

This also sidesteps circular-import pain: ``process_control.py``
re-exports names from every sibling for backward compatibility, so
if a sibling tried to import back FROM ``process_control`` it would
create a cycle.  Importing from ``process_control_state`` breaks
the cycle cleanly -- this file imports nothing from any sibling.
"""

from __future__ import annotations

import threading

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

PENDING_KOMETA_START = {
    "command": None,
    "config_name": None,
    "requested_at": None,
    "start_mode": "current",
}
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


def normalize_kometa_start_mode(raw_mode):
    mode = str(raw_mode or "current").strip().lower()
    return mode if mode in {"current", "recovery", "logged"} else "current"
