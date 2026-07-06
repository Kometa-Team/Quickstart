"""Maintenance-window helpers for the Kometa/ImageMaid run scheduler.

Split out of ``modules.process_control`` -- this cluster owns everything
about "is now a Plex maintenance window?".  The maintenance guard loop
uses these to decide when to pause / resume the running subprocess.

## What lives here

* ``parse_maintenance_window_minutes(window_str)`` -- accepts strings
  like ``"03:00 - 05:00"`` and returns ``(start_min, end_min)`` or
  ``None``.
* ``is_within_maintenance_window(now_dt, start_min, end_min)`` --
  clock arithmetic that handles wrapping past midnight.
* ``get_maintenance_window_from_db(config_name)`` -- reads the
  ``plex_telemetry.maintenance_window`` value from the DB (with two
  legacy-key fallbacks) and parses it.
* ``get_plex_credentials_from_db(config_name)`` -- helper for the
  live variant (below).
* ``get_maintenance_window_live(config_name)`` -- asks the running
  Plex server directly via ``helpers.get_plex_maintenance_hours``.
* ``get_active_maintenance_lookup_config_name()`` -- picks the config
  name to consult based on what's currently running (Kometa run
  context wins, then ImageMaid, then pending start, then last-used).
* ``resolve_maintenance_window_live/from_db(config_name)`` -- thin
  test seams that route through ``quickstart._get_maintenance_window_*``
  so the monkeypatchable aliases in ``quickstart.py`` win.
* ``refresh_maintenance_window_availability(preserve_active_state)``
  -- writes the current window + active flag into ``MAINTENANCE_STATE``
  (locked).  Called from both the guard loop and the status API.

## Cross-cluster dependencies

* Uses shared state from ``modules.process_control_state``
  (``MAINTENANCE_STATE`` + lock).
* Calls ``peek_pending_kometa_start`` from
  ``modules.process_pending_start``.
* Reaches ``quickstart._get_maintenance_window_*`` via a lazy
  ``import quickstart`` inside the resolve functions (established
  pattern for reaching back into ``quickstart.py`` for test-monkey-
  patchable aliases).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from modules import database, helpers, persistence
from modules.process_control_state import MAINTENANCE_STATE, MAINTENANCE_STATE_LOCK
from modules.process_pending_start import peek_pending_kometa_start


def parse_maintenance_window_minutes(window_str):
    if not window_str or "Unavailable" in str(window_str):
        return None
    matches = re.findall(r"(\d{1,2}):(\d{2})", str(window_str))
    if len(matches) < 2:
        return None
    try:
        start_h, start_m = (int(v) for v in matches[0])
        end_h, end_m = (int(v) for v in matches[1])
    except Exception:
        return None
    if not (0 <= start_h <= 23 and 0 <= end_h <= 23 and 0 <= start_m <= 59 and 0 <= end_m <= 59):
        return None
    return (start_h * 60 + start_m, end_h * 60 + end_m)


def is_within_maintenance_window(now_dt, start_min, end_min):
    if start_min is None or end_min is None or start_min == end_min:
        return False
    now_min = now_dt.hour * 60 + now_dt.minute
    if start_min < end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def get_maintenance_window_from_db(config_name=None):
    config_name = helpers.normalize_config_name_for_storage(config_name) or database.get_last_used_config_name()
    if not config_name:
        return None, None, None
    try:
        _validated, _user_entered, data = database.retrieve_section_data(name=config_name, section="plex_telemetry")
        telemetry = data.get("plex_telemetry", {}) if isinstance(data, dict) else {}
        window_str = telemetry.get("maintenance_window")
        if not window_str:
            legacy_telemetry = persistence.retrieve_settings("plex_telemetry")
            if isinstance(legacy_telemetry, dict):
                window_str = legacy_telemetry.get("plex_telemetry", {}).get("maintenance_window")
        if not window_str:
            legacy_plex = persistence.retrieve_settings("010-plex")
            if isinstance(legacy_plex, dict):
                window_str = legacy_plex.get("plex", {}).get("telemetry", {}).get("maintenance_window")
        minutes = parse_maintenance_window_minutes(window_str)
        if not minutes:
            return None, None, None
        return minutes[0], minutes[1], window_str
    except Exception as e:
        helpers.ts_log(f"Failed to read Plex maintenance window: {e}", level="DEBUG")
        return None, None, None


def get_plex_credentials_from_db(config_name=None):
    config_name = helpers.normalize_config_name_for_storage(config_name) or database.get_last_used_config_name()
    if not config_name:
        return None, None
    try:
        _validated, _user_entered, data = database.retrieve_section_data(name=config_name, section="plex")
        plex_data = data.get("plex", {}) if isinstance(data, dict) else {}
        plex_url = plex_data.get("url") or plex_data.get("plex_url")
        plex_token = plex_data.get("token") or plex_data.get("plex_token")
        return plex_url, plex_token
    except Exception as e:
        helpers.ts_log(f"Failed to read Plex credentials: {e}", level="DEBUG")
        return None, None


def get_maintenance_window_live(config_name=None):
    plex_url, plex_token = get_plex_credentials_from_db(config_name=config_name)
    if not plex_url or not plex_token:
        return None, None, None
    start_hour, end_hour = helpers.get_plex_maintenance_hours(plex_url, plex_token)
    if start_hour is None or end_hour is None:
        return None, None, None
    window_str = f"{start_hour:02d}:00 – {end_hour:02d}:00"
    return start_hour * 60, end_hour * 60, window_str


def get_active_maintenance_lookup_config_name():
    import quickstart

    def normalize_optional_config_name(value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        return helpers.normalize_config_name_for_storage(raw)

    kometa_running = bool(helpers.get_kometa_pid() and helpers.is_kometa_running())
    imagemaid_running = bool(helpers.get_imagemaid_pid() and helpers.is_imagemaid_running())

    try:
        kometa_ctx = quickstart._get_run_context()
    except Exception:
        kometa_ctx = {}
    kometa_config = normalize_optional_config_name((kometa_ctx or {}).get("config_name"))
    if kometa_running and kometa_config:
        return kometa_config

    try:
        imagemaid_ctx = quickstart._get_imagemaid_run_context()
    except Exception:
        imagemaid_ctx = {}
    imagemaid_config = normalize_optional_config_name((imagemaid_ctx or {}).get("config_name"))
    if imagemaid_running and imagemaid_config:
        return imagemaid_config

    pending = quickstart._peek_pending_kometa_start()
    pending_config = normalize_optional_config_name((pending or {}).get("config_name"))
    if pending_config:
        return pending_config

    return database.get_last_used_config_name()


def resolve_maintenance_window_live(config_name=None):
    import quickstart

    try:
        return quickstart._get_maintenance_window_live(config_name=config_name)
    except TypeError:
        return quickstart._get_maintenance_window_live()


def resolve_maintenance_window_from_db(config_name=None):
    import quickstart

    try:
        return quickstart._get_maintenance_window_from_db(config_name=config_name)
    except TypeError:
        return quickstart._get_maintenance_window_from_db()


def refresh_maintenance_window_availability(preserve_active_state=False):
    maintenance_config_name = get_active_maintenance_lookup_config_name()
    start_min, end_min, window_str = resolve_maintenance_window_live(config_name=maintenance_config_name)
    if start_min is None or end_min is None:
        start_min, end_min, window_str = resolve_maintenance_window_from_db(config_name=maintenance_config_name)
    window_unavailable = start_min is None or end_min is None

    kometa_running = bool(helpers.get_kometa_pid() and helpers.is_kometa_running())
    imagemaid_running = bool(helpers.get_imagemaid_pid() and helpers.is_imagemaid_running())
    has_pending = bool(peek_pending_kometa_start())
    active = is_within_maintenance_window(datetime.now(), start_min, end_min)

    with MAINTENANCE_STATE_LOCK:
        if preserve_active_state and (MAINTENANCE_STATE.get("paused") or MAINTENANCE_STATE.get("imagemaid_paused")):
            if window_str:
                MAINTENANCE_STATE["window"] = window_str
        else:
            MAINTENANCE_STATE["active"] = active
            MAINTENANCE_STATE["window"] = window_str
        if window_unavailable and (kometa_running or imagemaid_running or has_pending):
            if not MAINTENANCE_STATE.get("window_unavailable"):
                MAINTENANCE_STATE["window_unavailable_since"] = datetime.now(timezone.utc).isoformat()
            MAINTENANCE_STATE["window_unavailable"] = True
        else:
            MAINTENANCE_STATE["window_unavailable"] = False
            MAINTENANCE_STATE["window_unavailable_since"] = None
