"""Pending Kometa-start queue.

Split out of ``modules.process_control`` -- tiny cluster that manages
the "there's a Kometa command waiting for the maintenance window to
end" queue.  The maintenance guard loop pops from this queue when the
window closes so the requested run can start.

## What lives here

Four functions guarded by ``PENDING_KOMETA_START_LOCK`` (from
``modules.process_control_state``) that all read/write the single
``PENDING_KOMETA_START`` dict:

* ``set_pending_kometa_start(command, config_name, start_mode)``
* ``peek_pending_kometa_start()`` -- non-destructive read, returns
  a *copy* so the caller can't accidentally mutate module state.
* ``pop_pending_kometa_start()`` -- destructive read that clears
  the slot.
* ``clear_pending_kometa_start()`` -- resets the slot without
  reading it.

The ``normalize_kometa_start_mode`` helper that used to live with
these functions moved to ``modules.process_control_state`` because
4 different clusters call it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from modules.process_control_state import (
    PENDING_KOMETA_START,
    PENDING_KOMETA_START_LOCK,
    normalize_kometa_start_mode,
)


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
