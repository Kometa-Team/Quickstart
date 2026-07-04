"""Maintenance-marker and quiet-period analysis for LogscanAnalyzer.

Extracted from :class:`modules.logscan.LogscanAnalyzer`.

Kometa's runtime emits ``[Quickstart] Run marker:`` and
``[Quickstart] Maintenance marker:`` events into its log output.
These functions parse those markers plus the surrounding log
timestamps to answer three related questions:

1. What Quickstart marker (with its embedded fields + capability
   flags) was present in this log?
   -- :func:`extract_quickstart_marker`,
      :func:`extract_quickstart_marker_fields`,
      :func:`extract_quickstart_marker_capabilities`.

2. What maintenance pause/resume events did we see?
   -- :func:`extract_maintenance_summary` returns a dict of pause
   counts, total paused seconds, and per-event details.

3. What "quiet gaps" (stretches of time with no log lines) show up
   in the run, and how many overlap the known maintenance windows?
   -- :func:`extract_quiet_period_summary` returns gap statistics
   including the longest overall gap and the longest *unexplained*
   gap (i.e. not overlapping a maintenance window).

Companion helper :func:`parse_log_timestamp` returns a
:class:`datetime` from a leading ``[YYYY-MM-DD HH:MM:SS,mmm]``
prefix or ``None``.  Reused by other logscan modules.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Basic timestamp parsing (also useful outside this module)
# ---------------------------------------------------------------------------


_LOG_TIMESTAMP_RE = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]")


def parse_log_timestamp(line: Optional[str]) -> Optional[datetime]:
    """Return a naive :class:`datetime` parsed from ``[YYYY-MM-DD HH:MM:SS,mmm]``.

    Returns ``None`` when *line* is falsy, doesn't start with ``[``,
    or doesn't contain the expected prefix.  Never raises.
    """
    if not line or not line.startswith("["):
        return None
    match = _LOG_TIMESTAMP_RE.match(line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Quickstart run-marker parsers
# ---------------------------------------------------------------------------


_RUN_MARKER_RE = re.compile(r"\[Quickstart\]\s+Run marker:.*")
_MARKER_KEY_VALUE_RE = re.compile(r"(\w+)=([^\s]+)")
_MAINTENANCE_MARKERS_FLAG_RE = re.compile(r"\bmaintenance_markers=1\b")


def extract_quickstart_marker(content: Optional[str]) -> Optional[str]:
    """Return the raw ``[Quickstart] Run marker: ...`` line, else None."""
    if not content:
        return None
    match = _RUN_MARKER_RE.search(content)
    return match.group(0) if match else None


_VALID_START_MODES = {"current", "recovery", "logged"}


def extract_quickstart_marker_fields(content: Optional[str]) -> dict[str, str]:
    """Parse ``key=value`` fields out of the Quickstart run marker.

    Returns an empty dict when no marker is present.  The
    ``start_mode`` value is validated against the allowed set;
    unknown values are coerced to the empty string.
    """
    marker = extract_quickstart_marker(content)
    if not marker:
        return {}
    fields: dict[str, str] = {}
    for match in _MARKER_KEY_VALUE_RE.finditer(marker):
        key = str(match.group(1) or "").strip().lower()
        value = str(match.group(2) or "").strip()
        if key:
            fields[key] = value

    start_mode = str(fields.get("start_mode") or "").strip().lower()
    fields["start_mode"] = start_mode if start_mode in _VALID_START_MODES else ""
    return fields


def extract_quickstart_marker_capabilities(content: Optional[str]) -> dict[str, bool]:
    """Return capability flags declared in the Quickstart run marker.

    Currently just ``maintenance_markers`` -- Kometa runtimes with
    maintenance-marker support set ``maintenance_markers=1`` in the
    marker line.  Older runtimes omit the field entirely (interpret
    as False).
    """
    capabilities = {"maintenance_markers": False}
    marker = extract_quickstart_marker(content)
    if not marker:
        return capabilities
    if _MAINTENANCE_MARKERS_FLAG_RE.search(marker):
        capabilities["maintenance_markers"] = True
    return capabilities


# ---------------------------------------------------------------------------
# Maintenance summary: pause/resume events
# ---------------------------------------------------------------------------


_MAINTENANCE_MARKER_RE = re.compile(
    r"\[Quickstart\]\s+Maintenance marker:\s+event=(paused|resumed)\s+at=([^\s]+)" r"(?:\s+local_at=([^\s]+))?" r"(?:\s+window=([^\s]+))?" r"(?:\s+paused_seconds=(\d+))?",
    re.IGNORECASE,
)


def _empty_maintenance_summary() -> dict[str, Any]:
    return {
        "had_pause": False,
        "pause_count": 0,
        "pause_seconds": 0,
        "open_pause": False,
        "window": None,
        "events": [],
    }


def _parse_maintenance_event_line(line: str) -> Optional[dict[str, Any]]:
    """Return a parsed maintenance-event dict for *line*, else None."""
    match = _MAINTENANCE_MARKER_RE.search(line)
    if not match:
        return None

    event = str(match.group(1) or "").strip().lower()
    raw_ts = str(match.group(2) or "").strip()
    local_at = str(match.group(3) or "").strip() or None
    window = str(match.group(4) or "").strip() or None
    paused_seconds_raw = match.group(5)

    event_ts: Optional[datetime] = None
    try:
        event_ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        if event_ts.tzinfo is not None:
            event_ts = event_ts.astimezone(timezone.utc)
    except Exception:
        event_ts = None

    paused_seconds: Optional[int] = None
    if paused_seconds_raw is not None:
        try:
            paused_seconds = max(0, int(paused_seconds_raw))
        except Exception:
            paused_seconds = None

    return {
        "event": event,
        "at": raw_ts,
        "event_ts": event_ts,
        "local_at": local_at,
        "window": window,
        "paused_seconds": paused_seconds,
    }


def extract_maintenance_summary(content: Optional[str]) -> dict[str, Any]:
    """Aggregate ``[Quickstart] Maintenance marker:`` events into a summary.

    Returns a dict with keys:
        * ``had_pause``     -- True if any pause events seen
        * ``pause_count``   -- number of ``event=paused`` markers
        * ``pause_seconds`` -- total paused seconds (from ``paused_seconds=``
                               on resume events, or computed from paused/
                               resumed timestamps when the field is absent)
        * ``open_pause``    -- True if the last pause has no matching resume
        * ``window``        -- last ``window=`` value seen
        * ``events``        -- list of per-event dicts (without event_ts)

    Empty/None *content* returns an empty summary with defaults.
    """
    summary = _empty_maintenance_summary()
    if not content:
        return summary

    open_pause_ts: Optional[datetime] = None
    open_pause_window: Optional[str] = None
    open_pause_local_at: Optional[str] = None

    for line in content.splitlines():
        parsed = _parse_maintenance_event_line(line)
        if parsed is None:
            continue

        event = parsed["event"]
        event_ts = parsed["event_ts"]
        window = parsed["window"]
        local_at = parsed["local_at"]
        paused_seconds = parsed["paused_seconds"]

        # Emit the event with the wire-format keys (drop event_ts).
        summary["events"].append(
            {
                "event": event,
                "at": parsed["at"],
                "local_at": local_at,
                "window": window,
                "paused_seconds": paused_seconds,
            }
        )
        if window:
            summary["window"] = window

        if event == "paused":
            summary["had_pause"] = True
            summary["pause_count"] += 1
            open_pause_ts = event_ts
            open_pause_window = window
            open_pause_local_at = local_at
            continue

        if event == "resumed":
            summary["had_pause"] = True
            # If the marker didn't include paused_seconds, derive it
            # from the pause/resume timestamps we recorded.
            if paused_seconds is None and open_pause_ts and event_ts:
                try:
                    paused_seconds = max(0, int((event_ts - open_pause_ts).total_seconds()))
                except Exception:
                    paused_seconds = None
            if paused_seconds is not None:
                summary["pause_seconds"] += paused_seconds
            open_pause_ts = None
            open_pause_window = None
            open_pause_local_at = None

    # Handle an unclosed pause (no matching resume before EOF).
    if open_pause_ts is not None:
        summary["open_pause"] = True
        summary["had_pause"] = True
        if not summary["window"] and open_pause_window:
            summary["window"] = open_pause_window
        if summary["events"] and not summary["events"][-1].get("local_at") and open_pause_local_at:
            summary["events"][-1]["local_at"] = open_pause_local_at

    return summary


# ---------------------------------------------------------------------------
# Quiet-period summary: gaps between consecutive log timestamps
# ---------------------------------------------------------------------------


def _empty_quiet_period_summary() -> dict[str, Any]:
    return {
        "longest_gap_seconds": 0,
        "longest_gap_started_at": None,
        "longest_gap_ended_at": None,
        "longest_gap_start_line": None,
        "longest_gap_end_line": None,
        "longest_gap_last_line": None,
        "longest_gap_first_line": None,
        "gaps_over_300": 0,
        "gaps_over_900": 0,
        "gaps_over_1800": 0,
        "longest_gap_maintenance_overlap": "unknown",
        "longest_unexplained_gap_seconds": 0,
        "longest_unexplained_gap_started_at": None,
        "longest_unexplained_gap_ended_at": None,
        "longest_unexplained_gap_start_line": None,
        "longest_unexplained_gap_end_line": None,
        "longest_unexplained_gap_last_line": None,
        "longest_unexplained_gap_first_line": None,
        "longest_unexplained_gap_maintenance_overlap": "unknown",
        "confirmed_maintenance_gaps_over_300": 0,
        "unexplained_gaps_over_300": 0,
        "notable_gaps": [],
    }


def _build_maintenance_intervals(events: list[dict[str, Any]]) -> list[tuple[datetime, Optional[datetime]]]:
    """Turn maintenance events into [(start, end_or_None), ...] intervals.

    Uses each event's ``local_at`` field (a naive ISO string).  Events
    without a parseable ``local_at`` are skipped.  A trailing pause
    without a matching resume produces an open-ended interval
    ``(start, None)`` -- treated by the overlap checker as extending
    to infinity.
    """
    intervals: list[tuple[datetime, Optional[datetime]]] = []
    open_start: Optional[datetime] = None
    for event in events:
        if not isinstance(event, dict):
            continue
        local_at = str(event.get("local_at") or "").strip()
        event_name = str(event.get("event") or "").strip().lower()
        event_ts = None
        if local_at:
            try:
                event_ts = datetime.fromisoformat(local_at)
            except Exception:
                event_ts = None
        if event_ts is None:
            continue
        if event_name == "paused":
            open_start = event_ts
        elif event_name == "resumed" and open_start is not None:
            intervals.append((open_start, event_ts))
            open_start = None
    if open_start is not None:
        intervals.append((open_start, None))
    return intervals


def _classify_gap_overlap(
    start_ts: datetime,
    end_ts: datetime,
    intervals: list[tuple[datetime, Optional[datetime]]],
    maintenance_supported: bool,
) -> str:
    """Return "confirmed" / "none" / "unknown" for a gap vs maintenance intervals.

    * ``"confirmed"`` -- gap overlaps with a known maintenance window
    * ``"none"``      -- runtime supports maintenance markers, and this
                         gap didn't overlap any recorded window
    * ``"unknown"``   -- runtime doesn't support maintenance markers
                         (older Kometa), so we can't tell either way
    """
    for interval_start, interval_end in intervals:
        if interval_end is None:
            # Open-ended maintenance -- overlaps any gap ending after start.
            if end_ts > interval_start:
                return "confirmed"
            continue
        if start_ts < interval_end and end_ts > interval_start:
            return "confirmed"
    return "none" if maintenance_supported else "unknown"


def _collect_timestamped_lines(content: str) -> list[dict[str, Any]]:
    """Return per-line entries for every line with a parseable ISO timestamp."""
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        line_ts = parse_log_timestamp(line)
        if line_ts is not None:
            entries.append(
                {
                    "timestamp": line_ts,
                    "line_number": line_number,
                    "line": line.strip(),
                }
            )
    return entries


def _populate_longest_gap(summary: dict[str, Any], key_prefix: str, start_ts, end_ts, prev_entry, curr_entry, overlap_label: str) -> None:
    """Write the longest-gap fields for either the overall or unexplained gap."""
    summary[f"{key_prefix}_started_at"] = start_ts.isoformat()
    summary[f"{key_prefix}_ended_at"] = end_ts.isoformat()
    if prev_entry:
        summary[f"{key_prefix}_start_line"] = prev_entry.get("line_number")
        summary[f"{key_prefix}_last_line"] = prev_entry.get("line")
    if curr_entry:
        summary[f"{key_prefix}_end_line"] = curr_entry.get("line_number")
        summary[f"{key_prefix}_first_line"] = curr_entry.get("line")
    summary[f"{key_prefix}_maintenance_overlap"] = overlap_label


def extract_quiet_period_summary(
    content: Optional[str],
    maintenance_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Summarize quiet gaps (no log lines) in *content*.

    Cross-references gaps against known maintenance windows (from
    *maintenance_summary*'s events) so that expected gaps aren't
    counted as "unexplained".

    Returns a dict containing overall and "unexplained" longest-gap
    fields plus counts of gaps over 5/15/30-minute thresholds.
    See :func:`_empty_quiet_period_summary` for the full field list.
    """
    summary = _empty_quiet_period_summary()
    if not content:
        return summary

    capabilities = extract_quickstart_marker_capabilities(content)
    maintenance_supported = bool(capabilities.get("maintenance_markers"))

    timestamp_entries = _collect_timestamped_lines(content)
    if len(timestamp_entries) < 2:
        if maintenance_supported:
            summary["longest_gap_maintenance_overlap"] = "none"
        return summary

    maintenance_summary = maintenance_summary if isinstance(maintenance_summary, dict) else {}
    maintenance_intervals = _build_maintenance_intervals(maintenance_summary.get("events") or [])

    longest_start = longest_end = None
    longest_previous_entry = longest_current_entry = None
    longest_unexplained_start = longest_unexplained_end = None
    longest_unexplained_previous_entry = longest_unexplained_current_entry = None

    for previous_entry, current_entry in zip(timestamp_entries, timestamp_entries[1:]):
        previous_ts = previous_entry["timestamp"]
        current_ts = current_entry["timestamp"]
        gap_seconds = max(0, int((current_ts - previous_ts).total_seconds()))
        if gap_seconds <= 0:
            continue

        if gap_seconds >= 300:
            summary["gaps_over_300"] += 1
        if gap_seconds >= 900:
            summary["gaps_over_900"] += 1
        if gap_seconds >= 1800:
            summary["gaps_over_1800"] += 1

        overlap_label = _classify_gap_overlap(previous_ts, current_ts, maintenance_intervals, maintenance_supported)

        if gap_seconds >= 300:
            summary["notable_gaps"].append(
                {
                    "gap_seconds": gap_seconds,
                    "started_at": previous_ts.isoformat(),
                    "ended_at": current_ts.isoformat(),
                    "start_line": previous_entry.get("line_number"),
                    "end_line": current_entry.get("line_number"),
                    "last_line": previous_entry.get("line"),
                    "first_line": current_entry.get("line"),
                    "maintenance_overlap": overlap_label,
                }
            )
            if overlap_label == "confirmed":
                summary["confirmed_maintenance_gaps_over_300"] += 1
            else:
                summary["unexplained_gaps_over_300"] += 1

        if gap_seconds > summary["longest_gap_seconds"]:
            summary["longest_gap_seconds"] = gap_seconds
            longest_start, longest_end = previous_ts, current_ts
            longest_previous_entry, longest_current_entry = previous_entry, current_entry

        if overlap_label != "confirmed" and gap_seconds > summary["longest_unexplained_gap_seconds"]:
            summary["longest_unexplained_gap_seconds"] = gap_seconds
            longest_unexplained_start, longest_unexplained_end = previous_ts, current_ts
            longest_unexplained_previous_entry, longest_unexplained_current_entry = previous_entry, current_entry

    if longest_start is not None and longest_end is not None:
        _populate_longest_gap(
            summary,
            "longest_gap",
            longest_start,
            longest_end,
            longest_previous_entry,
            longest_current_entry,
            _classify_gap_overlap(longest_start, longest_end, maintenance_intervals, maintenance_supported),
        )

    if longest_unexplained_start is not None and longest_unexplained_end is not None:
        _populate_longest_gap(
            summary,
            "longest_unexplained_gap",
            longest_unexplained_start,
            longest_unexplained_end,
            longest_unexplained_previous_entry,
            longest_unexplained_current_entry,
            _classify_gap_overlap(
                longest_unexplained_start,
                longest_unexplained_end,
                maintenance_intervals,
                maintenance_supported,
            ),
        )
    elif maintenance_supported and summary["longest_gap_seconds"] > 0:
        summary["longest_unexplained_gap_maintenance_overlap"] = "none"

    return summary
