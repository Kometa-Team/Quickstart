"""Kometa "finished run" summary parsing.

Extracted from :class:`modules.logscan.LogscanAnalyzer`.

A Kometa run log ends with a summary section like::

    Finished: 2024-11-08 03:15:22 Run Time: 1:24:07
    ...
    Finished collections
     Run Time: 0:32:14

This module parses those tail sections and pulls out:

* the list of "Finished <phase> - <run time>" combined lines
  (:func:`extract_finished_runs`);
* the last-run time-delta (:func:`parse_run_time_from_line`);
* the last-line tail block plus its Start/Finished/Run-time metadata
  (:func:`find_last_run_time_index`, :func:`parse_final_run_metadata`,
  :func:`extract_last_lines`);
* human-friendly line-number range formatting for recommendation
  summaries (:func:`format_contiguous_lines`).

All functions are pure -- they take content or lines and return the
parsed values.  :class:`LogscanAnalyzer` still owns the stateful
attributes (``self.run_time``, ``self.started_at``, ``self.finished_at``);
the class methods now delegate to these pure helpers and assign the
results to ``self``.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# "Finished <phase>" line pair scanner
# ---------------------------------------------------------------------------


def extract_finished_runs(content: str) -> list[str]:
    """Scan *content* for "Finished <phase>" / "Run Time: ..." line pairs.

    Kometa emits its per-phase finish messages in two formats:

    1. **Two-line pair** -- ``"...Finished collections"`` immediately
       followed by ``" Run Time: 0:32:14"`` on the next line.
    2. **Single-line summary** -- one line containing both
       ``"Finished: <ts>"`` and ``"Run Time: ..."``.

    The two forms produce slightly different output strings:

    * pair form   -> ``"collections - 0:32:14"``
    * single-line -> ``"Finished at:<timestamp> - <run_time>"``

    Output order follows the input line order.  Malformed pairs
    (missing regex captures) resolve to ``"N/A"`` in the affected
    slot rather than being dropped -- callers rely on the position
    to correlate with the raw log.
    """
    lines = content.splitlines()
    finished_runs = []

    for i in range(len(lines) - 1):
        line = lines[i]
        next_line = lines[i + 1]

        if "Finished " in line and " Run Time: " in next_line:
            finished_match = re.search(r".*Finished\s+(.*?)\s*$", line)
            run_time_match = re.search(r".*Run Time:(.*?)\s*$", next_line)
            finished_text = finished_match.group(1).strip() if finished_match else "N/A"
            run_time_text = run_time_match.group(1).strip() if run_time_match else "N/A"
            finished_runs.append(f"{finished_text} - {run_time_text}")

        if "Finished: " in line and " Run Time: " in line:
            finished_match = re.search(r".*Finished:\s+(.*?)\s*$", line)
            run_time_match = re.search(r".*Run Time:(.*?)\s*$", line)
            finished_text = finished_match.group(1).strip() if finished_match else "N/A"
            run_time_text = run_time_match.group(1).strip() if run_time_match else "N/A"
            finished_runs.append(f"Finished at:{finished_text} - {run_time_text}")

    return finished_runs


# ---------------------------------------------------------------------------
# Run-time parsing
# ---------------------------------------------------------------------------


_RUN_TIME_REGEX = re.compile(
    r"Run Time:\s*(?:(\d+)\s+day(?:s)?(?:,\s*|\s+))?(\d+):(\d{1,2}):(\d{1,2})",
    re.IGNORECASE,
)


def parse_run_time_from_line(line: Optional[str]) -> Optional[timedelta]:
    """Return the ``Run Time: ...`` value from *line* as a :class:`timedelta`.

    Accepts both:

    * ``"Run Time: 0:32:14"``           (H:MM:SS)
    * ``"Run Time: 1 day, 2:20:31"``    (days, H:MM:SS)
    * ``"Run Time: 3 days 4:05:06"``    (plural, no comma)

    Returns ``None`` for a missing or malformed line -- never raises.
    """
    if not line:
        return None
    match = _RUN_TIME_REGEX.search(line)
    if not match:
        return None
    try:
        days = int(match.group(1) or 0)
        hours = int(match.group(2))
        minutes = int(match.group(3))
        seconds = int(match.group(4))
    except ValueError:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


# ---------------------------------------------------------------------------
# Last-run tail block extraction
# ---------------------------------------------------------------------------


def find_last_run_time_index(lines: list[str]) -> tuple[Optional[int], bool]:
    """Return ``(index, is_final_run)`` for the last "Run Time:" line in *lines*.

    Scans *lines* from the end backwards.  A "Run Time:" line is
    considered the **final** run marker when it's on the same line as
    ``"Finished:"`` / ``"Start Time:"`` OR when the previous line
    contains ``"Finished Run"``.  Other "Run Time:" occurrences (per-
    phase interim reports) become fallback candidates.

    Returns:
        * ``(index, True)`` when a final-run marker is found.
        * ``(fallback_index, False)`` when only interim run-time lines
          exist -- caller can still extract the tail block but the
          run-time metadata isn't the whole-run summary.
        * ``(None, False)`` when *lines* contains no "Run Time:" at all.
    """
    run_time_index: Optional[int] = None
    fallback_index: Optional[int] = None

    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        if "Run Time:" not in line:
            continue
        if fallback_index is None:
            fallback_index = idx
        previous_line = lines[idx - 1] if idx > 0 else ""
        previous_is_finished_run = re.search(r"\bFinished\s+Run\b", previous_line, re.IGNORECASE)
        if "Finished:" in line or "Start Time:" in line or previous_is_finished_run:
            run_time_index = idx
            return run_time_index, True

    return fallback_index, False


def parse_final_run_metadata(run_time_line: str) -> dict:
    """Extract ``started_at``, ``finished_at``, ``run_time`` from a final run-time line.

    Returns a dict with keys ``"started_at"``, ``"finished_at"``,
    ``"run_time"``.  Any key whose value can't be extracted is
    omitted from the result (never present as ``None``).

    IMPORTANT: This function returns metadata regardless of which
    fields matched.  Callers (like :func:`extract_last_lines`) may
    additionally gate on ``"run_time" in result`` to preserve the
    legacy behavior of only trusting a final-run marker when its
    ``Run Time:`` component parses successfully.

    The three fields are located by:

    * ``run_time``   -- via :func:`parse_run_time_from_line`
    * ``started_at`` -- ``Start Time: <value> Finished:`` capture
    * ``finished_at`` -- prefers the leading ``[YYYY-MM-DD HH:MM:SS,``
      log timestamp, else falls back to ``Finished: <value> Run Time:``
      or ``Finished: <value>`` at end of line.
    """
    result: dict = {}

    run_time = parse_run_time_from_line(run_time_line)
    if run_time is not None:
        result["run_time"] = run_time

    start_match = re.search(r"Start Time:\s*(.*?)\s+Finished:", run_time_line)
    if start_match:
        result["started_at"] = start_match.group(1).strip()

    timestamp_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),", run_time_line)
    if timestamp_match:
        result["finished_at"] = timestamp_match.group(1).strip()
    else:
        finished_match = re.search(r"Finished:\s*(.*?)\s+Run Time:", run_time_line)
        if not finished_match:
            finished_match = re.search(r"Finished:\s*(.*?)\s*$", run_time_line)
        if finished_match:
            result["finished_at"] = finished_match.group(1).strip()

    return result


def extract_last_lines(content: str) -> tuple[Optional[str], Optional[dict]]:
    """Extract the tail block ending at the last Run Time: line.

    Returns ``(tail_text, run_metadata)``:

    * ``tail_text`` -- the last ~6 lines (``run_time_index-5`` through end),
      left-stripped and joined with newlines.  ``None`` if *content*
      contains no "Run Time:" line at all.
    * ``run_metadata`` -- dict from :func:`parse_final_run_metadata`
      when the last "Run Time:" line is a final-run marker AND its
      ``Run Time:`` component successfully parses.  ``None``
      otherwise -- either the line is an interim per-phase report,
      or the ``Run Time:`` regex missed (malformed line).

    Callers that maintain persistent per-run state (like
    :class:`LogscanAnalyzer`) can assign the metadata dict entries
    to their own attributes; pure callers can ignore the second
    element entirely.
    """
    lines = content.splitlines()

    run_time_index, run_time_is_final = find_last_run_time_index(lines)
    if run_time_index is None:
        return None, None

    start_index = max(0, run_time_index - 5)
    extracted_lines = [line.lstrip() for line in lines[start_index:]]
    tail_text = "\n".join(extracted_lines)

    metadata: Optional[dict] = None
    if run_time_is_final:
        parsed = parse_final_run_metadata(lines[run_time_index])
        # Only expose metadata when Run Time itself parsed -- matches
        # the legacy behavior of "only trust started_at/finished_at
        # when we also have a run_time to anchor them".
        if "run_time" in parsed:
            metadata = parsed

    return tail_text, metadata


# ---------------------------------------------------------------------------
# Line-number range formatting
# ---------------------------------------------------------------------------


def format_contiguous_lines(line_numbers: list[int]) -> str:
    """Collapse contiguous integers into ``start-end`` ranges.

    ``[1, 2, 3, 5, 7, 8]``  -> ``"1-3, 5, 7-8"``.

    Used in recommendation summaries so instead of listing every
    error line (potentially hundreds) the user sees compact ranges.

    Preserves input order -- caller sorts if needed.  Raises
    ``IndexError`` on empty input (matches previous behavior; the
    caller in :class:`LogscanAnalyzer` guards with a length check).
    """
    formatted_ranges = []
    start_range = line_numbers[0]
    end_range = line_numbers[0]

    for i in range(1, len(line_numbers)):
        if line_numbers[i] == line_numbers[i - 1] + 1:
            end_range = line_numbers[i]
        else:
            if start_range == end_range:
                formatted_ranges.append(str(start_range))
            else:
                formatted_ranges.append(f"{start_range}-{end_range}")
            start_range = end_range = line_numbers[i]

    if start_range == end_range:
        formatted_ranges.append(str(start_range))
    else:
        formatted_ranges.append(f"{start_range}-{end_range}")

    return ", ".join(formatted_ranges)


# ---------------------------------------------------------------------------
# Datetime normalizers.
#
# The started_at / finished_at fields in the summary payload can arrive
# in several shapes: "2024-11-08 03:15:22", "2024-11-08T03:15:22",
# "03:15:22 2024-11-08", or already-parsed datetimes from Kometa's
# scheduler.  These helpers coerce them into the canonical
# "YYYY-MM-DD HH:MM:SS" string form and reject far-future dates that
# usually indicate a parse mistake.
# ---------------------------------------------------------------------------


def parse_finished_datetime(value) -> Optional[datetime]:
    """Parse *value* into a naive datetime, or return None if it can't.

    Accepts either ``YYYY-MM-DD[ T]HH:MM:SS`` or ``HH:MM:SS YYYY-MM-DD``
    in the string form; anything else -> None.  Falsy inputs -> None.
    """
    if not value:
        return None
    text = str(value).strip()
    match = re.search(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", text)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    match = re.search(r"(\d{2}:\d{2}:\d{2})\s+(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return datetime.strptime(f"{match.group(2)} {match.group(1)}", "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    return None


def normalize_finished_at(finished_at, log_mtime) -> Optional[str]:
    """Return *finished_at* as a canonical ``YYYY-MM-DD HH:MM:SS`` string.

    If parsing fails or the parsed value is more than a day in the
    future (typical when a log's clock is skewed), fall back to
    *log_mtime* (a POSIX timestamp).  If even that fails, return the
    original ``finished_at`` unchanged so the caller can decide what
    to do with garbage.
    """
    parsed = parse_finished_datetime(finished_at)
    now = datetime.now()
    if parsed and parsed > now + timedelta(days=1):
        parsed = None
    if not parsed and log_mtime:
        try:
            parsed = datetime.fromtimestamp(log_mtime)
        except Exception:
            parsed = None
    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    return finished_at


def normalize_started_at(started_at) -> Optional[str]:
    """Return *started_at* as a canonical ``YYYY-MM-DD HH:MM:SS`` string.

    Same shape as :func:`normalize_finished_at` but without the
    log-mtime fallback -- if the input can't be parsed or is too
    far in the future, the raw input is returned unchanged.
    """
    parsed = parse_finished_datetime(started_at)
    now = datetime.now()
    if parsed and parsed > now + timedelta(days=1):
        parsed = None
    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    return started_at
