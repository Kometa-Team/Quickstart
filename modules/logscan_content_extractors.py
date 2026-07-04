"""Pure content-parsing helpers for LogscanAnalyzer.

Extracted from :class:`modules.logscan.LogscanAnalyzer`.

Every function in this module takes raw log-file text and pulls a
specific piece of information back out (memory value, DB cache size,
scheduled run time, maintenance window, WSL platform indicator, ...).
No state -- ``LogscanAnalyzer`` still owns the ``global_divider``
attribute; :func:`extract_divider` returns the parsed value but
doesn't persist it.

The extractions collapse several near-identical parsers via shared
helpers:

* :func:`_extract_gb_value_with_prefix` -- given a labeled numeric
  value like ``"Memory: 8 GB"`` or ``"Plex DB cache setting: 512 MB"``,
  returns the value normalized to GB.  Was duplicated verbatim
  across ``extract_memory_value`` and ``extract_db_cache_value``.

* :func:`_kometa_or_pmm_alternation` -- builds the standard
  ``[KOMETA_X, PMM_X]`` regex-pattern list for the various Kometa
  CLI flags that got renamed from PMM.  Was duplicated across
  ``set_global_divider`` and ``extract_scheduled_run_time``.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

mylogger = logging.getLogger("logscan")


# ---------------------------------------------------------------------------
# WSL memory recommendation icons -- kept as escape codes to survive the
# repo's emoji-filter hook.
# ---------------------------------------------------------------------------

_ICON_SPEECH = "\U0001f4ac"  # speech balloon
_ICON_WINDOW = "\U0001fa9f"  # window
_ICON_PENGUIN = "\U0001f427"  # penguin


# ---------------------------------------------------------------------------
# Shared parsing primitives
# ---------------------------------------------------------------------------


def _extract_gb_value_with_prefix(content: str, label_pattern: str) -> Optional[float]:
    """Return the numeric value labeled by *label_pattern*, normalized to GB.

    Expects log lines of the form:

        "<label>: <number> <unit>"

    where *label_pattern* is a regex fragment matching the label
    (e.g. ``"Memory:"`` or ``"Plex DB cache setting:"``).  Recognized
    units (case-insensitive): ``mb`` / ``gb`` / ``tb``.  Anything
    else (or no match) returns ``None``.

    Used to be duplicated between :func:`extract_memory_value` and
    :func:`extract_db_cache_value`.
    """
    pattern = rf"{label_pattern}\s*([\d.]+)\s*(\w+)"
    match = re.search(pattern, content)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2).lower()

    if unit == "gb":
        return value
    if unit == "mb":
        return value / 1024
    if unit == "tb":
        return value * 1024
    return None


def _kometa_or_pmm_alternation(flag_pattern: str, env_stem: str, capture_body: str) -> list[str]:
    """Build the KOMETA_X / PMM_X pattern pair for a Kometa CLI flag.

    Kometa's CLI flags support both the new (``KOMETA_``) and legacy
    (``PMM_``) environment-variable names.  Log lines record which
    the user passed, so a scanner needs to accept either.  This
    helper produces the two-element list of regex patterns.

    Arguments:
        flag_pattern -- the regex for the CLI flag as it appears in
                        the log line (e.g. ``r"divider"``,
                        ``r"times?"``).
        env_stem -- the env-var name AFTER the ``KOMETA_`` / ``PMM_``
                    prefix, including any regex quantifier
                    (e.g. ``"DIVIDER"``, ``"TIMES?"``).
        capture_body -- the regex fragment for what to capture, WITH
                        the surrounding capture group
                        (e.g. ``r"([^\"']{1})"`` for a single char).
                        This will appear as group 1 in the resulting
                        pattern.

    Returns a list of two regex strings; the value capture is
    group 1 in each.  Scanners should try each in order and use the
    first match.
    """
    return [
        rf'--{flag_pattern} \(KOMETA_{env_stem}\): ?["\']?{capture_body}["\']?',
        rf'--{flag_pattern} \(PMM_{env_stem}\): ?["\']?{capture_body}["\']?',
    ]


# ---------------------------------------------------------------------------
# Memory / DB cache
# ---------------------------------------------------------------------------


def extract_memory_value(content: str) -> Optional[float]:
    """Extract total container/host memory (in GB) from a Kometa log."""
    return _extract_gb_value_with_prefix(content, r"Memory:")


def extract_db_cache_value(content: str) -> Optional[float]:
    """Extract the Plex ``db_cache`` setting (in GB) from a Kometa log."""
    return _extract_gb_value_with_prefix(content, r"Plex DB cache setting:")


# ---------------------------------------------------------------------------
# Divider (single character used to draw section banners in log output)
# ---------------------------------------------------------------------------


DEFAULT_DIVIDER = "="


def extract_divider(content: str, fallback: str = DEFAULT_DIVIDER) -> str:
    """Return the divider character declared in *content*, else *fallback*.

    Kometa passes ``--divider <char>`` and echoes it back into log
    output; several parsers need this to know how to strip banner
    lines.  Supports the legacy ``PMM_DIVIDER`` name.
    """
    patterns = _kometa_or_pmm_alternation("divider", "DIVIDER", r'([^"\']{1})')
    for pattern in patterns:
        divider_match = re.search(pattern, content)
        if divider_match:
            divider = divider_match.group(1)
            mylogger.debug(f"Divider found and set to: {divider}")
            return divider

    mylogger.debug(f"Divider not found, using default divider: {fallback}")
    return fallback


# ---------------------------------------------------------------------------
# Scheduled run time / maintenance window
# ---------------------------------------------------------------------------


def extract_scheduled_run_time(content: str) -> Optional[str]:
    """Return the ``KOMETA_TIMES`` scheduled run time as ``HH:MM``, else None.

    Supports the legacy ``PMM_TIMES`` name.
    """
    patterns = _kometa_or_pmm_alternation("times?", "TIMES?", r"(\d{1,2}:\d{2})")
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            scheduled_run_time = match.group(1)
            mylogger.debug(f"Scheduled run time found: {scheduled_run_time}")
            return scheduled_run_time

    mylogger.debug("Scheduled run time not found in content.")
    return None


def extract_maintenance_times(content: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(start, end)`` for Plex's scheduled maintenance window.

    Returns ``(None, None)`` when the "Scheduled maintenance running
    between..." line isn't present in *content*.
    """
    match = re.search(r"Scheduled maintenance running between (\d+:\d+) and (\d+:\d+)", content)
    if match:
        start_time = match.group(1)
        end_time = match.group(2)
        mylogger.debug(f"Scheduled maintenance times found: Start time: {start_time}, End time: {end_time}")
        return start_time, end_time

    mylogger.debug("Scheduled maintenance times not found in content.")
    return None, None


# ---------------------------------------------------------------------------
# Overlay-config detection (used to gate memory recommendations)
# ---------------------------------------------------------------------------


def contains_overlay_path(content: str) -> bool:
    """Return True when *content* mentions an ``overlay_path:`` config key."""
    return bool(re.search(r"\boverlay_path:\s*", content, re.IGNORECASE))


def contains_overlay_files(content: str) -> bool:
    """Return True when *content* mentions an ``overlay_files:`` config key."""
    return bool(re.search(r"\boverlay_files:\s*", content, re.IGNORECASE))


# ---------------------------------------------------------------------------
# WSL platform detection + recommendation
# ---------------------------------------------------------------------------


_WSL_RECOMMENDATION = (
    f"{_ICON_SPEECH}{_ICON_WINDOW}{_ICON_PENGUIN} **WSL MEMORY RECOMMENDATION**\n"
    "According to Microsoft\u2019s documentation, the amount of system memory (RAM) that gets "
    "allocated to WSL is limited to either 50% of your total memory or 8GB, whichever happens "
    "to be smaller.\n\n"
    "It is possible to override the maximum RAM allocation, we suggest googling 'WSL memory limit' "
    "to learn more otherwise the following may work for you:"
    "To override the maximum RAM allocation when running Windows Subsystem for Linux (WSL), you "
    "need to modify the configuration settings. Here are the steps to do this:\n"
    "1. Open a PowerShell window as an administrator.\n"
    "2. Run the command: `wsl --set-default-version 2` to set WSL version to 2 (WSL 2).\n"
    "3. Run the command: `wsl --set-memory <your_memory_limit>` to set the maximum memory limit "
    "for WSL (replace `<your_memory_limit>` with the desired memory limit, e.g., `4GB`).\n"
    "4. Restart WSL by running the command: `wsl --shutdown`.\n\n"
    "It is important to note that modifying these settings may require a reboot of your system."
)


def detect_wsl_recommendation(content: str) -> Optional[str]:
    """Return the WSL memory-config advisory when *content* is from a WSL host.

    Detects Kometa's ``"Platform: <name>-WSL"`` line.  Returns ``None``
    when no WSL platform is detected.
    """
    if re.search(r"Platform: .*-WSL", content):
        return _WSL_RECOMMENDATION
    return None
