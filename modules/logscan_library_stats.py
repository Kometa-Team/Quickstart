"""Library / section statistics extraction for LogscanAnalyzer.

Extracted from :class:`modules.logscan.LogscanAnalyzer`.

The functions in this module scan raw Kometa log text and pull out
per-library and per-section statistics:

* :func:`extract_library_counts` -- items/movies/shows/episodes per
  library, tracking which "source" line each count came from so that
  higher-priority sources (``Content Count:``) aren't overwritten by
  lower-priority ones later in the log.

* :func:`extract_section_runtimes` -- accumulates runtime seconds per
  Kometa section (Movies, Shows, Overlays, ...).  Handles both the
  inline ``Finished X in HH:MM:SS`` form and the older split
  ``Finished X`` + ``Run Time:`` two-line form.

* :func:`count_log_levels` -- one-pass counter for DEBUG/INFO/
  WARNING/ERROR/CRITICAL + TRACEBACK occurrences.

* :func:`extract_config_line_count` -- counts non-blank/non-comment
  YAML lines inside the ``Redacted Config`` block that Kometa
  echoes at the top of every log.

* :func:`normalize_library_name` / :func:`match_library_name` --
  fuzzy-ish name matcher used to reconcile library-config entries
  with library names as they appear in logs (dashes, underscores,
  and case can differ).

* :func:`parse_hms_to_seconds` -- ``"HH:MM:SS"`` / ``"MM:SS"`` /
  int-string parser that returns an ``int`` seconds count or None.
  Public because :mod:`modules.logscan_progress` may benefit.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Small time-parsing helper
# ---------------------------------------------------------------------------


def parse_hms_to_seconds(value: object) -> Optional[int]:
    """Parse a duration string into an int seconds count, else None.

    Accepted forms:
        * ``"HH:MM:SS"`` -- three colon-separated integers
        * ``"MM:SS"``    -- two colon-separated integers
        * ``"NNN"``      -- bare integer seconds (in a string)

    Whitespace is stripped.  Anything else -- including negative
    numbers or non-integer components -- returns ``None`` rather
    than raising.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = text.split(":")
        if len(parts) == 1:
            return int(parts[0])
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
    except ValueError:
        return None
    return None


# ---------------------------------------------------------------------------
# Section runtimes (Movies / Shows / Overlays / ...)
# ---------------------------------------------------------------------------


_INLINE_RUNTIME_RE = re.compile(r"Finished (?P<section>.+?) in (?P<time>\d+:\d{2}:\d{2})")
_FINISHED_ONLY_RE = re.compile(r"Finished (?P<section>.+?)\s*$")
_RUN_TIME_RE = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z ]+?) Run Time:\s*(?P<time>\d+:\d{2}:\d{2})\s*$")

_MAX_FINISHED_TO_RUNTIME_LINE_DISTANCE = 3


def extract_section_runtimes(content: Optional[str]) -> dict[str, int]:
    """Return a ``{section_name: total_seconds}`` dict.

    Kometa reports section runtimes in one of two forms:

    * Inline: ``"Finished Movies in 0:02:14"`` on a single line.
    * Split : ``"Finished Movies"`` on one line, then a
      ``"Something Run Time: 0:02:14"`` line within 3 lines.

    When the inline form is present, the section name comes straight
    from the ``Finished X`` capture.  For the split form, the
    section from the preceding ``Finished X`` line wins over the
    label prefix of the ``Run Time:`` line.  Multiple runtimes for
    the same section are summed.
    """
    section_times: dict[str, int] = {}
    if not content:
        return section_times

    last_section: Optional[str] = None
    last_section_index: Optional[int] = None

    for idx, line in enumerate(content.splitlines()):
        if not line:
            continue

        # Case 1: inline "Finished X in HH:MM:SS"
        inline_match = _INLINE_RUNTIME_RE.search(line)
        if inline_match:
            section = inline_match.group("section").strip()
            if section.lower().startswith("at:"):
                continue
            seconds = parse_hms_to_seconds(inline_match.group("time"))
            if seconds is not None:
                section_times[section] = section_times.get(section, 0) + seconds
            continue

        # Case 2a: "Finished X" without a time -- remember for pairing
        finished_match = _FINISHED_ONLY_RE.search(line)
        if finished_match:
            section = finished_match.group("section").strip()
            lowered = section.lower()
            if lowered == "run" or lowered.startswith("run "):
                # "Finished Run" is the whole-log marker, not a section.
                continue
            last_section = section
            last_section_index = idx
            continue

        # Case 2b: standalone "X Run Time: HH:MM:SS"
        runtime_match = _RUN_TIME_RE.search(line)
        if not runtime_match:
            continue
        seconds = parse_hms_to_seconds(runtime_match.group("time"))
        if seconds is None:
            continue

        section = None
        if last_section and last_section_index is not None and (idx - last_section_index) <= _MAX_FINISHED_TO_RUNTIME_LINE_DISTANCE:
            section = last_section
        else:
            label = runtime_match.group("label").strip()
            if label and label.lower() != "run":
                section = label

        if section:
            section_times[section] = section_times.get(section, 0) + seconds

        # Reset the pairing state whether or not we used it.
        last_section = None
        last_section_index = None

    return section_times


# ---------------------------------------------------------------------------
# Log-level counting
# ---------------------------------------------------------------------------


_LOG_LEVEL_TAGS: tuple[tuple[str, str], ...] = (
    ("debug", "[DEBUG]"),
    ("info", "[INFO]"),
    ("warning", "[WARNING]"),
    ("error", "[ERROR]"),
    ("critical", "[CRITICAL]"),
    ("trace", "TRACEBACK"),
)


def count_log_levels(content: Optional[str]) -> dict[str, int]:
    """Return a per-level count of log lines.

    Keys: ``debug``, ``info``, ``warning``, ``error``, ``critical``,
    ``trace`` (matches ``TRACEBACK`` anywhere in the line).

    Matching is case-insensitive.  A line with multiple tags counts
    once per tag (rare in practice).
    """
    counts = {key: 0 for key, _tag in _LOG_LEVEL_TAGS}
    if not content:
        return counts

    for line in content.splitlines():
        upper = line.upper()
        for key, tag in _LOG_LEVEL_TAGS:
            if tag in upper:
                counts[key] += 1

    return counts


# ---------------------------------------------------------------------------
# Library-name normalization + matching
# ---------------------------------------------------------------------------


def normalize_library_name(value: object) -> str:
    """Return a normalized comparison key for library names.

    Applies:
    * Lower-casing.
    * Underscore/dash -> space.
    * Strip anything that isn't alphanumeric or whitespace.
    * Collapse multiple spaces.

    Falsy input returns the empty string.
    """
    if not value:
        return ""
    text = str(value).lower()
    text = text.replace("_", " ").replace("-", " ")
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch.isspace())
    return " ".join(cleaned.split())


def match_library_name(raw_name: str, library_entries: list[dict]) -> Optional[str]:
    """Find the config library-entry name that best matches *raw_name*.

    * Exact normalized match wins.
    * Otherwise, the LONGEST substring match wins (both directions:
      ``needle in candidate`` and ``candidate in needle``).

    Returns the entry's ``name`` field, or ``None`` when nothing
    matches.
    """
    needle = normalize_library_name(raw_name)
    if not needle:
        return None

    candidates: list[tuple[int, str]] = []
    for entry in library_entries:
        name = entry.get("name")
        if not name:
            continue
        normalized = normalize_library_name(name)
        if not normalized:
            continue
        if needle == normalized:
            return name
        if needle in normalized or normalized in needle:
            candidates.append((len(normalized), name))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]
    return None


# ---------------------------------------------------------------------------
# Config-line counting (Redacted Config block)
# ---------------------------------------------------------------------------


def extract_config_line_count(content: Optional[str]) -> int:
    """Count effective lines in Kometa's ``Redacted Config`` block.

    Skips:
    * Blank lines.
    * YAML comments (``# ...``).
    * Divider lines composed entirely of ``=``.

    Stops when we exit the config block (line without ``config.py:``)
    or hit the ``Quickstart run marker``.
    """
    if not content:
        return 0

    in_block = False
    count = 0
    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not in_block:
            if "Redacted Config" in line:
                in_block = True
            continue

        if "config.py:" not in line:
            break

        message = line.split("|", 1)[1].strip() if "|" in line else line
        if not message:
            continue
        if "Quickstart run marker" in message:
            break
        if message.startswith("#"):
            continue
        if set(message.strip()) <= {"="}:
            continue

        count += 1

    return count


# ---------------------------------------------------------------------------
# Per-library item counts
# ---------------------------------------------------------------------------


# Header patterns identify "Processing Library:" style lines that
# switch the current library context.
_HEADER_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"Processing Library:\s*(.+)", re.IGNORECASE),
    re.compile(r"Library:\s*(.+)", re.IGNORECASE),
    re.compile(r"Information on library:\s*(.+)", re.IGNORECASE),
)

_TYPE_PATTERN = re.compile(r"\b(Movie|Show)\b", re.IGNORECASE)

# Direct pattern: "Library X has N items" -- assigns without touching context.
_LIBRARY_ITEMS_PATTERN = re.compile(r"Library\s+(.+?)\s+has\s+(\d+)\s+items", re.IGNORECASE)

# Content Count: winning pattern -- higher priority than the others,
# and once assigned it blocks lower-priority overwrites.
_CONTENT_MOVIES_PATTERN = re.compile(r"Content Count:\s*(\d+)\s+movies?", re.IGNORECASE)
_CONTENT_SHOWS_PATTERN = re.compile(r"Content Count:\s*(\d+)\s+shows?\s*/\s*(\d+)\s+episodes", re.IGNORECASE)

# Fallback patterns -- overwritable by anything else EXCEPT after a
# Content Count entry has already been recorded for this library.
_ITEMS_PATTERN = re.compile(r"Items Found:\s*(\d+)", re.IGNORECASE)
_MOVIES_PATTERN = re.compile(r"Movies Found:\s*(\d+)", re.IGNORECASE)
_SHOWS_PATTERN = re.compile(r"Shows Found:\s*(\d+)", re.IGNORECASE)
_EPISODES_PATTERN = re.compile(r"Episodes Found:\s*(\d+)", re.IGNORECASE)


def _try_switch_current_library(line: str) -> Optional[tuple[str, Optional[str]]]:
    """Scan *line* for a library-header pattern; return (name, type) or None.

    The type comes from the same line if it contains ``Movie`` or
    ``Show``; otherwise ``type`` is None (to be filled in later).
    """
    for pattern in _HEADER_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        name = match.group(1).strip()
        # Handle "Library X -> Y" forms by taking the Y half.
        if "->" in name:
            name = name.split("->", 1)[-1].strip()
        name = name.strip("- ").strip()
        if not name:
            return None
        type_match = _TYPE_PATTERN.search(line)
        current_type = type_match.group(1).lower() if type_match else None
        return name, current_type
    return None


def extract_library_counts(content: Optional[str]) -> dict[str, dict]:
    """Extract per-library item counts from a Kometa log.

    Returns ``{library_name: {items: N, [type: 'movie'|'show'], [episodes: N]}}``.

    Priority order for assigning counts to a library:

    1. ``"Library X has N items"`` -- direct assignment, no context needed.
    2. ``"Content Count: N movies"`` / ``"Content Count: N shows / N episodes"``
       -- highest priority.  Locks the library so lower-priority
       patterns won't overwrite it later.
    3. ``"Items Found: N"`` / ``"Movies Found: N"`` -- overwrites in
       full (single number, single type).
    4. ``"Shows Found: N"`` / ``"Episodes Found: N"`` -- merges into
       existing entry (keeping the other count/type).

    All 3-4 require a preceding library-header line to establish context.
    """
    library_counts: dict[str, dict] = {}
    if not content:
        return library_counts

    # Tracks which counts came from a Content Count line -- these
    # are "locked" and can't be overwritten by lower-priority forms.
    library_sources: dict[str, str] = {}
    current_library: Optional[str] = None
    current_type: Optional[str] = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if not line:
            continue

        # Header line? Switch the current library context.
        header = _try_switch_current_library(line)
        if header is not None:
            current_library, current_type = header

        # Direct assignment: "Library X has N items"
        direct_match = _LIBRARY_ITEMS_PATTERN.search(line)
        if direct_match:
            name = direct_match.group(1).strip()
            library_counts[name] = {"items": int(direct_match.group(2))}
            continue

        if not current_library:
            continue

        # Highest priority: Content Count lines
        content_movies_match = _CONTENT_MOVIES_PATTERN.search(line)
        if content_movies_match:
            library_counts[current_library] = {
                "items": int(content_movies_match.group(1)),
                "type": "movie",
            }
            library_sources[current_library] = "content_count"
            continue

        content_shows_match = _CONTENT_SHOWS_PATTERN.search(line)
        if content_shows_match:
            library_counts[current_library] = {
                "items": int(content_shows_match.group(1)),
                "episodes": int(content_shows_match.group(2)),
                "type": "show",
            }
            library_sources[current_library] = "content_count"
            continue

        # Lower-priority patterns -- skipped if Content Count already set.
        if library_sources.get(current_library) == "content_count":
            continue

        items_match = _ITEMS_PATTERN.search(line)
        if items_match:
            library_counts[current_library] = {
                "items": int(items_match.group(1)),
                "type": current_type,
            }
            continue

        movies_match = _MOVIES_PATTERN.search(line)
        if movies_match:
            library_counts[current_library] = {
                "items": int(movies_match.group(1)),
                "type": "movie",
            }
            continue

        shows_match = _SHOWS_PATTERN.search(line)
        if shows_match:
            entry = library_counts.get(current_library, {})
            entry["items"] = int(shows_match.group(1))
            entry["type"] = entry.get("type") or "show"
            library_counts[current_library] = entry
            continue

        episodes_match = _EPISODES_PATTERN.search(line)
        if episodes_match:
            entry = library_counts.get(current_library, {})
            entry["episodes"] = int(episodes_match.group(1))
            entry["type"] = entry.get("type") or "show"
            library_counts[current_library] = entry

    return library_counts
