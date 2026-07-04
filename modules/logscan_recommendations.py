"""System-tuning recommendation builders for LogscanAnalyzer.

Extracted from :class:`modules.logscan.LogscanAnalyzer`.

Kometa's log-scan output includes advice on system-level settings
that Kometa itself can't reconfigure, but the user should:

* Plex DB cache size vs total available memory
  (:func:`db_cache_recommendation`)
* Container/host memory allocation
  (:func:`memory_recommendation`)
* Kometa vs Plex maintenance-window scheduling
  (:func:`maintenance_time_recommendation`)

All functions are pure -- they take the already-extracted numeric
values / strings / timedeltas as arguments and return either a
markdown-formatted advisory string or ``None`` (nothing to
recommend).  ``LogscanAnalyzer`` still owns the content-parsing
methods that pull those values out of raw log text; the recommendation
methods on the class now delegate here.

Helper :func:`format_time_value` renders a :class:`datetime.time`
object into a compact ``HH:MM`` display, trimming a leading zero.
It's kept public here because two other :mod:`modules.logscan`
methods use it via the class wrapper.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

mylogger = logging.getLogger("logscan")

# ---------------------------------------------------------------------------
# Unicode symbols used in advisory strings.  Kept here (via escape codes
# so this file stays emoji-free on disk) so a single search catches every
# usage across the module.
# ---------------------------------------------------------------------------

_ICON_ERROR = "\u274c"  # cross mark
_ICON_ALARM = "\u23f0"  # alarm clock
_ICON_WARN = "\u26a0\ufe0f"  # warning sign + emoji-presentation selector
_ICON_SPEECH = "\U0001f4ac"  # speech balloon
_ICON_BULB = "\U0001f4a1\ufe0f"  # light bulb + emoji-presentation selector

# ---------------------------------------------------------------------------
# Constants + disclaimers reused across the recommendation builders
# ---------------------------------------------------------------------------

_DB_CACHE_DISCLAIMER = (
    "**NOTE**:The number you choose can vary wildly based on a number of factors "
    "(such as the size and number of libraries, and the amount of files/operations/overlays "
    "that are being utilized)."
)

_MEMORY_DISCLAIMER = (
    "These numbers are purely estimates and can vary wildly based on a number of factors "
    "(such as the size and number of libraries, and the amount of files/operations/overlays "
    "that are being utilized)."
)

_DB_CACHE_URL = "https://kometa.wiki/en/latest/config/plex#plex-attributes"
_PLEX_MAINTENANCE_URL = "https://support.plex.tv/articles/202197488-scheduled-server-maintenance/"


# ---------------------------------------------------------------------------
# Simple time formatting
# ---------------------------------------------------------------------------


def format_time_value(time_value) -> str:
    """Return ``time_value`` as ``H:MM`` or ``HH:MM`` (never leading zero).

    ``time(hour=8, minute=30)  -> '8:30'``
    ``time(hour=14, minute=05) -> '14:05'``

    Falsy input (``None`` / zero-length string) returns ``"N/A"``.
    Anything that duck-types ``.strftime("%H:%M")`` is accepted.
    """
    if not time_value:
        return "N/A"
    formatted = time_value.strftime("%H:%M")
    return formatted[1:] if formatted.startswith("0") else formatted


# ---------------------------------------------------------------------------
# Plex DB cache advice
# ---------------------------------------------------------------------------


def db_cache_recommendation(db_cache_value: Optional[float], total_memory_value: Optional[float]) -> Optional[str]:
    """Advise on the Plex ``db_cache`` setting given DB-cache and total-memory values.

    Both values are in GB.  ``None`` for either short-circuits to
    ``None`` (missing data = no advice).

    Returns a markdown advisory when:

    * ``db_cache_value >= total_memory_value`` -- outright bad config
    * ``db_cache_value < 1`` -- suboptimal default worth flagging

    Otherwise ``None`` (config is reasonable, no advice needed).
    """
    if db_cache_value is None or total_memory_value is None:
        return None

    if db_cache_value >= total_memory_value:
        return (
            f"{_ICON_ERROR} **PLEX DB CACHE ISSUE**\n"
            f"The Plex DB cache setting (**{db_cache_value:.2f} GB**) is equal to or greater than the total memory "
            f"(**{total_memory_value:.2f} GB**). Consider adjusting the Plex DB cache setting to a value **below** "
            "the total memory.\n"
            f"For more info on this setting: {_DB_CACHE_URL}\n"
            f"{_DB_CACHE_DISCLAIMER}"
        )

    if db_cache_value < 1:
        return (
            f"{_ICON_SPEECH}{_ICON_BULB} **PLEX DB CACHE ADVICE**\n"
            f"Consider updating the Plex DB cache setting from **{db_cache_value:.2f} GB**, to a value **greater** "
            f"than **1 GB** based on the total memory of **{total_memory_value:.2f} GB**.\n"
            "Setting `db_cache: 1024` within the plex settings in your config.yml is effectively 1024MB which is 1GB. "
            f"For more info on this setting: {_DB_CACHE_URL}\n"
            f"{_DB_CACHE_DISCLAIMER}"
        )

    return None


# ---------------------------------------------------------------------------
# Total memory advice
# ---------------------------------------------------------------------------


def memory_recommendation(memory_value: Optional[float], has_overlays: bool) -> Optional[str]:
    """Advise on total container/host memory given the detected value.

    * ``memory_value`` in GB -- ``None`` returns an error string
      (matches legacy behavior so ``make_recommendations`` can render
      the "could not detect" case).
    * ``has_overlays`` -- whether the run detected overlay usage
      (raises the RAM recommendation from 4 GB to 8 GB).

    Threshold behavior (aligned with legacy):

    * ``< 4 GB``  -- warning, target=8GB with overlays or 4GB without
    * ``< 8 GB with overlays``  -- warning, target=8GB
    * ``< 8 GB without overlays`` -- no advice (silent)
    * ``>= 8 GB`` -- no advice
    """
    if memory_value is None:
        return "Error: Memory value not found in content."

    if memory_value < 4:
        target_ram = "8GB" if has_overlays else "4GB"
        overlay_context = "with overlays (we have detected overlays)" if has_overlays else "without overlays (we have NOT detected overlays)"
        return (
            f"{_ICON_WARN} **MEMORY RECOMMENDATION**\n"
            f"The memory value is {memory_value:.2f} GB, which is less than 4 GB. "
            f"We advise having at least {target_ram} of RAM when running Kometa {overlay_context} "
            "to avoid potential out-of-memory issues.\n\n"
            f"{_MEMORY_DISCLAIMER}"
        )

    if memory_value < 8 and has_overlays:
        return (
            f"{_ICON_WARN} **MEMORY RECOMMENDATION**\n"
            f"The memory value is {memory_value:.2f} GB, which is less than 8 GB. "
            "We advise having at least 8GB of RAM when running Kometa with overlays (we have detected overlays) "
            "for optimal performance.\n\n"
            f"{_MEMORY_DISCLAIMER}"
        )

    return None


# ---------------------------------------------------------------------------
# Kometa-vs-Plex maintenance-window scheduling advice
# ---------------------------------------------------------------------------


def _parse_hhmm(value: Optional[str]):
    """Return a :class:`datetime.time` from an ``"HH:MM"`` string or ``None``."""
    if value is None:
        return None
    return datetime.strptime(value, "%H:%M").time()


def _build_scheduling_advisory(
    banner: str,
    trailing: str,
    *,
    run_time,
    time_buffer,
    kometa_scheduled_time,
    maintenance_start_time,
    maintenance_end_time,
) -> str:
    """Assemble the shared body of a scheduling advisory.

    All four scheduling advisories share the exact same header
    (``This Run took: ... Time between ... start: ... end: ...``);
    only the closing paragraph differs.  This helper cuts ~60 lines
    of duplicated f-strings down to four short callers.
    """
    return (
        f"{_ICON_ERROR}{_ICON_ALARM} **{banner}**\n"
        f"This Run took: `{run_time}`\n"
        f"Time between Kometa Scheduled time and Plex Maintenance start: `{time_buffer}`\n"
        f"Kometa scheduled start time: `{format_time_value(kometa_scheduled_time)}`\n"
        f"Plex Scheduled Maintenance start time: `{format_time_value(maintenance_start_time)}`\n"
        f"Plex Scheduled Maintenance end time: `{format_time_value(maintenance_end_time)}`\n"
        f"{trailing}\n"
        f"For more information on Plex Maintenance, see {_PLEX_MAINTENANCE_URL}"
    )


def maintenance_time_recommendation(
    kometa_scheduled_time_str: Optional[str],
    maintenance_start_time_str: Optional[str],
    maintenance_end_time_str: Optional[str],
    run_time: timedelta,
) -> Optional[str]:
    """Advise on Kometa-vs-Plex-maintenance scheduling conflicts.

    Arguments:
        kometa_scheduled_time_str -- ``"HH:MM"`` from Kometa config or None
        maintenance_start_time_str -- ``"HH:MM"`` from Plex or None
        maintenance_end_time_str -- ``"HH:MM"`` from Plex or None
        run_time -- observed run :class:`timedelta` for this run

    Returns:
        * Error string when ``kometa_scheduled_time_str`` is None
        * ``None`` when either maintenance time is missing (can't compute)
        * A markdown advisory when any of four conflict rules trigger:
            - Kometa run > 24 hours (always a problem)
            - Kometa run > buffer-until-next-maintenance
            - Kometa scheduled inside the maintenance window
            - Kometa run > time-before-maintenance
        * ``None`` when no rule triggers.

    The four "warning" branches build the same base advisory body
    with just a different trailing paragraph -- see
    :func:`_build_scheduling_advisory`.
    """
    if not kometa_scheduled_time_str:
        return "Error: Plex scheduled time is missing."

    kometa_scheduled_time = _parse_hhmm(kometa_scheduled_time_str)

    if maintenance_start_time_str is None or maintenance_end_time_str is None:
        return None

    maintenance_start_time = _parse_hhmm(maintenance_start_time_str)
    maintenance_end_time = _parse_hhmm(maintenance_end_time_str)

    today = datetime.today()
    plex_scheduled_datetime = datetime.combine(today, kometa_scheduled_time)
    maintenance_start_datetime = datetime.combine(today, maintenance_start_time)
    maintenance_end_datetime = datetime.combine(today, maintenance_end_time)

    # NOTE: the two branches of this if/else produce the same value
    # (this is a legacy dead branch preserved verbatim); .seconds is
    # always non-negative and wraps for overnight schedules.
    if maintenance_start_datetime > plex_scheduled_datetime:
        time_before_plex_maintenance = (maintenance_start_datetime - plex_scheduled_datetime).seconds // 60
    else:
        time_before_plex_maintenance = (maintenance_start_datetime - plex_scheduled_datetime).seconds // 60

    buffer_until_next_plex_maintenance = ((24 + maintenance_start_time.hour - maintenance_end_time.hour) * 60) % 1440
    time_buffer = timedelta(minutes=buffer_until_next_plex_maintenance)
    run_time_in_minutes = run_time.total_seconds() / 60

    mylogger.info(f"time_before_plex_maintenance: {time_before_plex_maintenance}")
    mylogger.info(f"buffer_until_next_plex_maintenance: {buffer_until_next_plex_maintenance}")
    mylogger.info(f"time_buffer until next Plex maintenance: {time_buffer}")
    mylogger.info(f"run_time_in_minutes: {run_time_in_minutes}")

    shared_kwargs = dict(
        run_time=run_time,
        time_buffer=time_buffer,
        kometa_scheduled_time=kometa_scheduled_time,
        maintenance_start_time=maintenance_start_time,
        maintenance_end_time=maintenance_end_time,
    )

    if run_time_in_minutes > 1440:
        trailing = (
            f"If your Kometa runs typically take this long [this run took `{run_time}`], "
            "your Kometa run time will coincide with the next Plex maintenance period as this run is "
            "greater than 24 hours.\n\n"
            "The suggestion we can make at this point is to find ways to break down your run into smaller "
            "chunks and schedule them on different days."
        )
        return _build_scheduling_advisory("KOMETA RUN TIME > 24 HOURS", trailing, **shared_kwargs)

    if run_time_in_minutes > buffer_until_next_plex_maintenance:
        trailing = (
            f"If your Kometa runs typically take this long [this run took `{run_time}`], "
            "your Kometa run time will coincide with the next Plex maintenance period. "
            f"Adjust the Kometa Scheduled start time to `{format_time_value(maintenance_end_time)}` "
            "(if needed) AND adjust the Plex Scheduled Maintenance start time to be later."
        )
        return _build_scheduling_advisory("KOMETA RUN TIME > BUFFER BEFORE MAINTENANCE", trailing, **shared_kwargs)

    if maintenance_start_datetime <= plex_scheduled_datetime < maintenance_end_datetime:
        trailing = (
            "You are within the maintenance window between Plex maintenance start time: "
            f"`{format_time_value(maintenance_start_time)}` and end time: "
            f"`{format_time_value(maintenance_end_time)}`. "
            f"Adjust the Kometa Scheduled start time to `{format_time_value(maintenance_end_time)}` "
            "or adjust the Plex Scheduled Maintenance times to end prior to the Kometa Scheduled run time."
        )
        return _build_scheduling_advisory("KOMETA SCHEDULED TIME CONFLICT", trailing, **shared_kwargs)

    if run_time_in_minutes > time_before_plex_maintenance:
        trailing = (
            f"If your Kometa runs typically take this long [this run took `{run_time}`], "
            "your Kometa run time will coincide with the next Plex maintenance period. "
            f"Consider moving the Kometa scheduled start time to `{format_time_value(maintenance_end_time)}` "
            "or adjust the Plex Scheduled Maintenance times to end prior to the Kometa Scheduled run time."
        )
        return _build_scheduling_advisory("KOMETA RUN TIME > TIME BEFORE MAINTENANCE", trailing, **shared_kwargs)

    return None
