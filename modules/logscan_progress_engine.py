"""Progress extraction engine for LogscanAnalyzer.

Extracted from :class:`modules.logscan.LogscanAnalyzer` to isolate
the 640-line ``extract_progress`` function.

This module parses a Kometa run log to compute a real-time
progress payload used by Quickstart's "Kometa is running..."
dashboard: which library is currently being processed, which
phases have completed for each library, aggregate playlist
timing, whether the run has finished, and so on.

The public entry point :func:`extract_progress` still takes the
:class:`LogscanAnalyzer` instance as its first argument
(``analyzer``) because the parser calls back into a handful of
helper methods on the analyzer:

* ``set_global_divider`` -- computes and caches the log's
  divider character run so log-line prefixes can be stripped.
* ``_strip_divider_wrappers`` (moved here) -- removes those
  divider prefixes/suffixes from a message body.
* ``_extract_mapping_library`` (moved here) -- picks out the
  library name from a "Mapping X Library" log line.
* ``_map_section_to_phase`` (moved here) -- maps a section
  header like "Overlays" to a phase key like "overlays".
* ``_normalize_library_name`` / ``_match_library_name`` --
  case/whitespace normalization for library-name comparisons
  (delegated to :mod:`modules.logscan_library_stats`).
* ``_parse_hms_to_seconds`` -- converts "1h 23m 45s" strings.
* ``extract_section_runtimes`` -- pulls per-section runtimes
  from the FINISHED-RUN block.

The three ``_strip_divider_wrappers`` / ``_extract_mapping_library``
/ ``_map_section_to_phase`` helpers are now module-level functions
here and are re-exposed on the analyzer as thin wrappers to
preserve the existing method-call surface for tests.
"""

from __future__ import annotations

import re
from datetime import datetime


def strip_divider_wrappers(analyzer, message):
    """Remove leading/trailing divider runs from *message*.

    Uses ``analyzer.global_divider`` (populated by
    :meth:`LogscanAnalyzer.set_global_divider`) to know which
    character sequence to strip.
    """
    if not message:
        return message
    cleaned = analyzer.remove_repeated_dividers(message)
    divider = analyzer.global_divider or ""
    cleaned = cleaned.strip()
    if divider:
        cleaned = cleaned.strip(divider).strip()
    return cleaned.strip("|").strip()


def extract_mapping_library(message):
    """Return the library name from a ``Mapping X Library`` log message, else None."""
    if not message:
        return None
    match = re.search(r"\bMapping\s+(.+?)\s+Library\b", message, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def is_finished_run_marker(message):
    """Return True for whole-run finished banners, including scheduled runs."""
    if not message:
        return False
    return bool(re.search(r"\bFinished(?:\s+(?:Libraries|\d{1,2}:\d{2}))?\s+Run\b", str(message), re.IGNORECASE))


def map_section_to_phase(section_name):
    """Map a section header like ``Overlays`` to a phase key like ``overlays``."""
    if not section_name:
        return None
    lowered = str(section_name).lower()
    if "operation" in lowered:
        return "operations"
    if "overlay" in lowered:
        return "overlays"
    if "collection" in lowered:
        return "collections"
    if "metadata" in lowered:
        return "metadata"
    return None


def extract_progress(
    analyzer,
    content,
    library_list=None,
    selected_libraries=None,
    previous=None,
    run_started_at=None,
    now_ts=None,
    is_running=False,
):
    """Parse *content* and return a progress payload dict.

    Long-running stateful parser that walks the log line-by-line
    tracking which library is currently being processed, which
    phases are open/complete/pending, playlist runtime, and
    whether a finished-run marker has been seen.

    Arguments:
        analyzer -- the :class:`LogscanAnalyzer` instance whose
                    ``global_divider`` (via ``set_global_divider``)
                    and helper methods drive the divider-stripping
                    and library-name matching.
        content -- the raw log text to scan.
        library_list -- optional list of ``{"name": ..., "type": ...}``
                        dicts describing the libraries configured in
                        the run.  Missing entries are added as
                        Pending on first sighting.
        selected_libraries -- optional list of library names to
                              consider; anything else is marked
                              ``Skipped``.
        previous -- optional dict of the previous poll's progress
                    payload; used to preserve durations, phase
                    starts, and current-library state across polls.
        run_started_at -- optional ISO string or datetime marking
                          when the run began (used for elapsed
                          calculations).
        now_ts -- optional "current time" datetime for testable
                  elapsed math.
        is_running -- whether Kometa is currently believed to be
                      running (affects elapsed / open-phase logic).

    Returns:
        A dict describing the current progress snapshot with keys
        like ``current_library``, ``libraries``, ``phase_starts``,
        ``playlist_total_seconds``, ``run_finished``, etc.
    """

    def _coerce_local_naive_datetime(value):
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            try:
                if value.tzinfo is not None:
                    return value.astimezone().replace(tzinfo=None)
            except Exception:
                pass
            return value
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if ts.tzinfo is not None:
                ts = ts.astimezone().replace(tzinfo=None)
            return ts
        except Exception:
            return None

    library_entries = []
    if library_list:
        for entry in library_list:
            name = entry.get("name")
            if not name:
                continue
            library_entries.append(
                {
                    "name": name,
                    "type": entry.get("type"),
                }
            )
    selected_norm = None
    if selected_libraries:
        selected_norm = {analyzer._normalize_library_name(name) for name in selected_libraries if name}

    def is_selected(name):
        if not selected_norm:
            return True
        return analyzer._normalize_library_name(name) in selected_norm

    statuses = {}
    for entry in library_entries:
        name = entry["name"]
        if selected_norm and not is_selected(name):
            statuses[name] = "Skipped"
        else:
            statuses[name] = "Pending"
    current_library = None
    library_hint = None
    library_durations = {}
    phase_start = {}
    phase_last_seen = {}
    phase_open = {}
    phase_start_from_previous = set()
    processing_started_at = None
    finished_run_seen = False
    preparation_seconds = None
    preparation_locked = False
    preparation_elapsed_seconds = None
    first_log_ts = None
    playlists_detected = False
    playlist_running = False
    playlist_started_at = None
    playlist_total_seconds = 0
    if isinstance(previous, dict):
        prev_current = previous.get("current_library")
        if prev_current and prev_current in statuses and statuses[prev_current] == "Pending":
            statuses[prev_current] = "In progress"
            current_library = prev_current
        prev_libs = previous.get("libraries")
        if isinstance(prev_libs, list):
            for entry in prev_libs:
                name = entry.get("name")
                status = entry.get("status")
                if name in statuses and status in ("Done", "In progress") and statuses[name] != "Skipped":
                    statuses[name] = status
                durations = entry.get("durations")
                if name and isinstance(durations, dict) and durations:
                    library_durations[name] = dict(durations)
        prev_phase_starts = previous.get("phase_starts")
        if isinstance(prev_phase_starts, dict):
            for key, value in prev_phase_starts.items():
                if not key or not value:
                    continue
                parts = str(key).split("||", 1)
                if len(parts) != 2:
                    continue
                lib_name, phase_key = parts
                if not lib_name or not phase_key:
                    continue
                if lib_name not in statuses or statuses.get(lib_name) == "Skipped":
                    continue
                try:
                    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                    if ts.tzinfo is not None:
                        ts = ts.astimezone().replace(tzinfo=None)
                except Exception:
                    continue
                phase_start[(lib_name, phase_key)] = ts
                phase_last_seen[(lib_name, phase_key)] = ts
                phase_open[lib_name] = phase_key
                phase_start_from_previous.add((lib_name, phase_key))
        if isinstance(previous.get("playlist_total_seconds"), (int, float)):
            playlist_total_seconds = int(previous.get("playlist_total_seconds") or 0)
        playlist_running = bool(previous.get("playlist_running"))
        prev_playlist_started_at = previous.get("playlist_started_at")
        if prev_playlist_started_at:
            try:
                ts = datetime.fromisoformat(str(prev_playlist_started_at).replace("Z", "+00:00"))
                if ts.tzinfo is not None:
                    ts = ts.astimezone().replace(tzinfo=None)
                playlist_started_at = ts
            except Exception:
                playlist_started_at = None
        prev_last_log_at = previous.get("last_log_at")
        if isinstance(previous.get("preparation_seconds"), (int, float)):
            preparation_seconds = int(previous.get("preparation_seconds") or 0)
            preparation_locked = True
    else:
        prev_last_log_at = None

    last_log_cutoff = None
    if prev_last_log_at:
        try:
            last_log_cutoff = datetime.fromisoformat(str(prev_last_log_at).replace("Z", "+00:00"))
            if last_log_cutoff.tzinfo is not None:
                last_log_cutoff = last_log_cutoff.astimezone().replace(tzinfo=None)
        except Exception:
            last_log_cutoff = None

    if not content:
        return {
            "phase_current": None,
            "phases_completed": [],
            "libraries": [
                {
                    "name": entry["name"],
                    "type": entry.get("type"),
                    "status": statuses.get(entry["name"], "Pending"),
                }
                for entry in library_entries
            ],
            "current_library": None,
            "completed_count": 0,
            "total_count": len(library_entries),
        }

    analyzer.set_global_divider(content)
    lines = content.splitlines()

    effective_started_at = _coerce_local_naive_datetime(run_started_at)
    effective_now = _coerce_local_naive_datetime(now_ts)
    if effective_started_at is None:
        marker_re = re.compile(r"\[Quickstart\]\s+Run marker:\s+started=([^\s]+)")
        for line in lines:
            match = marker_re.search(line)
            if not match:
                continue
            raw_ts = match.group(1)
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                if ts.tzinfo is not None:
                    ts = ts.astimezone().replace(tzinfo=None)
                effective_started_at = ts
                break
            except Exception:
                continue

    def parse_log_timestamp(line):
        if not line or not line.startswith("["):
            return None
        match = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\]", line)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    start_patterns = [
        re.compile(r"Processing Library:\s*(.+)", re.IGNORECASE),
        re.compile(r"Library:\s*(.+)", re.IGNORECASE),
        re.compile(r"Information on library:\s*(.+)", re.IGNORECASE),
    ]
    activity_patterns = [
        re.compile(r"Caching\s+(.+?)\s+Library Items", re.IGNORECASE),
        re.compile(r"Loading .* from Library:\s*(.+)", re.IGNORECASE),
    ]
    overlays_start_re = re.compile(r"^\s*(.+?)\s+Library\s+Overlays\b", re.IGNORECASE)
    overlays_end_re = re.compile(r"^Finished\s+(.+?)\s+Library\s+Overlays\b", re.IGNORECASE)
    operations_start_re = re.compile(r"^\s*(.+?)\s+Library\s+Operations\b", re.IGNORECASE)
    operations_end_re = re.compile(r"^Finished\s+(.+?)\s+Library\s+Operations\b", re.IGNORECASE)
    collections_start_re = re.compile(r"^Running\s+(.+?)\s+Collection\s+File\b", re.IGNORECASE)
    collections_end_re = re.compile(r"^Finished\s+(.+?)\s+Collection\b", re.IGNORECASE)
    metadata_start_re = re.compile(r"^Running\s+(.+?)\s+Metadata\s+File\b", re.IGNORECASE)
    playlists_header_re = re.compile(r"^Playlists$", re.IGNORECASE)
    playlist_runtime_re = re.compile(r"Playlist\s+Run\s+Time:\s*(\d+:\d{2}:\d{2})", re.IGNORECASE)
    playlist_finished_re = re.compile(r"^Finished\s+.+?\s+Playlist\b", re.IGNORECASE)
    library_done_re = re.compile(r"^Finished\s+(.+?)\s+Library\b(?!\s+Overlays|\s+Operations)", re.IGNORECASE)
    allow_unknown = not library_entries
    last_ts = None

    def _ensure_duration_entry(name):
        if name not in library_durations:
            library_durations[name] = {}

    def _apply_cutoff_delta(start_ts, end_ts):
        if not start_ts or not end_ts:
            return None
        if last_log_cutoff and end_ts <= last_log_cutoff:
            return None
        if last_log_cutoff and start_ts < last_log_cutoff < end_ts:
            return max(0, int((end_ts - last_log_cutoff).total_seconds()))
        return max(0, int((end_ts - start_ts).total_seconds()))

    def _finish_phase(name, phase_key, end_ts):
        key = (name, phase_key)
        start_ts = phase_start.get(key)
        if not start_ts:
            return
        if end_ts is None:
            end_ts = phase_last_seen.get(key) or last_ts
        if end_ts:
            if key in phase_start_from_previous:
                duration = max(0, int((end_ts - start_ts).total_seconds()))
            else:
                duration = _apply_cutoff_delta(start_ts, end_ts)
            if duration is not None:
                _ensure_duration_entry(name)
                existing = library_durations[name].get(phase_key, 0)
                library_durations[name][phase_key] = existing + duration
        phase_start.pop(key, None)
        phase_last_seen.pop(key, None)
        if key in phase_start_from_previous:
            phase_start_from_previous.discard(key)
        if phase_open.get(name) == phase_key:
            phase_open.pop(name, None)

    def _start_phase(name, phase_key, start_ts):
        if not name or start_ts is None:
            return
        _ensure_duration_entry(name)
        prior_phase = phase_open.get(name)
        if prior_phase and prior_phase != phase_key:
            _finish_phase(name, prior_phase, start_ts)
        elif prior_phase == phase_key and phase_key in ("collections", "metadata"):
            _finish_phase(name, phase_key, start_ts)
        key = (name, phase_key)
        if key not in phase_start:
            phase_start[key] = start_ts
        phase_last_seen[key] = start_ts
        phase_open[name] = phase_key

    def _set_current_library(name, ts):
        nonlocal current_library, library_hint, processing_started_at
        if not name:
            return
        library_hint = name
        if current_library and current_library != name:
            prior_phase = phase_open.get(current_library)
            if prior_phase:
                _finish_phase(current_library, prior_phase, ts)
        current_library = name
        if ts and processing_started_at is None:
            processing_started_at = ts

    for raw_line in lines:
        if not raw_line:
            continue
        line_ts = parse_log_timestamp(raw_line)
        if line_ts and first_log_ts is None:
            first_log_ts = line_ts
        if line_ts and (last_ts is None or line_ts > last_ts):
            last_ts = line_ts
        if effective_started_at and line_ts and line_ts < effective_started_at:
            continue
        if last_log_cutoff and line_ts and line_ts <= last_log_cutoff:
            continue
        msg = raw_line.split("|", 1)[1].strip() if "|" in raw_line else raw_line.strip()
        msg = strip_divider_wrappers(analyzer, msg)

        if playlists_header_re.match(msg):
            playlists_detected = True
            playlist_running = True
            if playlist_started_at is None and line_ts:
                playlist_started_at = line_ts
            if processing_started_at is None and line_ts:
                processing_started_at = line_ts
            continue

        if playlist_runtime_re.search(msg):
            playlists_detected = True
            match = playlist_runtime_re.search(msg)
            if match:
                seconds = analyzer._parse_hms_to_seconds(match.group(1))
                if seconds is not None:
                    playlist_total_seconds += int(seconds)
            continue

        if playlist_finished_re.search(msg):
            playlists_detected = True
            if playlist_started_at is None and line_ts:
                playlist_started_at = line_ts
            continue

        if "overlays.py" in raw_line and re.search(r"\bLibrary\s+Overlays\b", msg, re.IGNORECASE):
            match = overlays_start_re.search(msg)
            if match:
                name = match.group(1).strip()
                matched = analyzer._match_library_name(name, library_entries)
                if not matched:
                    if selected_norm or not allow_unknown:
                        continue
                    library_entries.append({"name": name, "type": None})
                    statuses.setdefault(name, "Pending")
                    matched = name
                if statuses.get(matched) not in ("Done", "Skipped"):
                    if current_library and current_library in statuses and current_library != matched and statuses[current_library] != "Skipped":
                        statuses[current_library] = "Done"
                    statuses[matched] = "In progress"
                    _set_current_library(matched, line_ts)
                    _start_phase(matched, "overlays", line_ts)
            continue

        if "overlays.py" in raw_line and overlays_end_re.search(msg):
            match = overlays_end_re.search(msg)
            if match:
                name = match.group(1).strip()
                matched = analyzer._match_library_name(name, library_entries)
                if matched:
                    _finish_phase(matched, "overlays", line_ts)
            continue

        if "operations.py" in raw_line and operations_start_re.search(msg):
            match = operations_start_re.search(msg)
            if match:
                name = match.group(1).strip()
                matched = analyzer._match_library_name(name, library_entries)
                if not matched:
                    if selected_norm or not allow_unknown:
                        continue
                    library_entries.append({"name": name, "type": None})
                    statuses.setdefault(name, "Pending")
                    matched = name
                if statuses.get(matched) not in ("Done", "Skipped"):
                    if current_library and current_library in statuses and current_library != matched and statuses[current_library] != "Skipped":
                        statuses[current_library] = "Done"
                    statuses[matched] = "In progress"
                    _set_current_library(matched, line_ts)
                    _start_phase(matched, "operations", line_ts)
            continue

        if "operations.py" in raw_line and operations_end_re.search(msg):
            match = operations_end_re.search(msg)
            if match:
                name = match.group(1).strip()
                matched = analyzer._match_library_name(name, library_entries)
                if matched and statuses.get(matched) != "Skipped":
                    statuses[matched] = "Done"
                    if current_library == matched:
                        current_library = None
                    _finish_phase(matched, "operations", line_ts)
            continue

        if "kometa.py" in raw_line and collections_start_re.search(msg):
            if current_library:
                if statuses.get(current_library) not in ("Done", "Skipped"):
                    statuses[current_library] = "In progress"
                _start_phase(current_library, "collections", line_ts)
            continue

        if "kometa.py" in raw_line and collections_end_re.search(msg):
            continue

        if "kometa.py" in raw_line and metadata_start_re.search(msg):
            if current_library:
                if statuses.get(current_library) not in ("Done", "Skipped"):
                    statuses[current_library] = "In progress"
                _start_phase(current_library, "metadata", line_ts)
            continue

        if "kometa.py" in raw_line and re.search(r"\bMapping\b", msg, re.IGNORECASE):
            name = extract_mapping_library(msg)
            if name:
                matched = analyzer._match_library_name(name, library_entries)
                if not matched:
                    if selected_norm or not allow_unknown:
                        continue
                    library_entries.append({"name": name, "type": None})
                    statuses.setdefault(name, "Pending")
                    matched = name
                if current_library and current_library in statuses and statuses[current_library] != "Skipped":
                    statuses[current_library] = "Done"
                statuses[matched] = "In progress"
                _set_current_library(matched, line_ts)
                if processing_started_at is None and line_ts:
                    processing_started_at = line_ts
            continue

        finished_match = library_done_re.search(msg)
        if finished_match:
            name = finished_match.group(1).strip()
            matched = analyzer._match_library_name(name, library_entries)
            if matched and statuses.get(matched) != "Skipped":
                statuses[matched] = "Done"
                if current_library == matched:
                    current_library = None
            continue

        if is_finished_run_marker(msg):
            if current_library and current_library in statuses and statuses[current_library] != "Skipped":
                statuses[current_library] = "Done"
            current_library = None
            finished_run_seen = True
            playlist_running = False
            continue

        for pattern in start_patterns:
            match = pattern.search(msg)
            if not match:
                continue
            name = match.group(1).strip()
            matched = analyzer._match_library_name(name, library_entries)
            if not matched:
                if selected_norm or not allow_unknown:
                    continue
                library_entries.append({"name": name, "type": None})
                statuses.setdefault(name, "Pending")
                matched = name
            library_hint = matched
            break

        for pattern in activity_patterns:
            match = pattern.search(msg)
            if not match:
                continue
            name = match.group(1).strip()
            matched = analyzer._match_library_name(name, library_entries)
            if not matched:
                if selected_norm or not allow_unknown:
                    continue
                library_entries.append({"name": name, "type": None})
                statuses.setdefault(name, "Pending")
                matched = name
            library_hint = matched
            break

    section_runtimes = analyzer.extract_section_runtimes(content)
    # Fallback for playlist timing when runtime lines do not match the
    # stricter live parser patterns (for example continuation lines).
    if playlist_total_seconds <= 0 and isinstance(section_runtimes, dict):
        playlist_runtime_total = 0
        for section_name, seconds in section_runtimes.items():
            if not isinstance(section_name, str):
                continue
            if "playlist" not in section_name.lower():
                continue
            if isinstance(seconds, (int, float)):
                playlist_runtime_total += int(seconds)
        if playlist_runtime_total > 0:
            playlist_total_seconds = playlist_runtime_total
            playlists_detected = True
    phases_completed = []
    for section_name in section_runtimes.keys():
        phase = map_section_to_phase(section_name)
        if phase and phase not in phases_completed:
            phases_completed.append(phase)

    phase_patterns = [
        ("operations", re.compile(r"\bLibrary\s+Operations\b|\boperations\.py\b", re.IGNORECASE)),
        ("metadata", re.compile(r"\bMetadata\s+File\b|\bmeta\.py\b", re.IGNORECASE)),
        ("collections", re.compile(r"\bCollection\s+File\b|\bBuilding\s+.+\s+Collections\b", re.IGNORECASE)),
        ("overlays", re.compile(r"\bLibrary\s+Overlays\b|\boverlays\.py\b", re.IGNORECASE)),
        ("playlists", re.compile(r"^Playlists$|\bPlaylist\b", re.IGNORECASE)),
    ]
    phase_current = None
    phase_sequence = []
    for raw_line in lines:
        msg = raw_line.split("|", 1)[1].strip() if "|" in raw_line else raw_line.strip()
        msg = strip_divider_wrappers(analyzer, msg)
        line_ts = parse_log_timestamp(raw_line)
        if last_log_cutoff and line_ts and line_ts <= last_log_cutoff:
            continue
        if processing_started_at is not None and line_ts and line_ts < processing_started_at:
            continue
        for phase_key, pattern in phase_patterns:
            if pattern.search(msg):
                phase_current = phase_key
                phase_sequence.append(phase_key)
                break
    if processing_started_at is None:
        phase_current = None
        phase_sequence = []

    summary_header_re = re.compile(r"=+\s*(.+?)\s+Summary\s*=+", re.IGNORECASE)
    summary_runtime_re = re.compile(r"^(Library\s+.+?)\s*\|\s*(\d+:\d{2}:\d{2})", re.IGNORECASE)
    summary_library = None
    for raw_line in lines:
        msg = raw_line.split("|", 1)[1].strip() if "|" in raw_line else raw_line.strip()
        msg = strip_divider_wrappers(analyzer, msg)
        header_match = summary_header_re.search(msg)
        if header_match:
            name = header_match.group(1).strip()
            matched = analyzer._match_library_name(name, library_entries)
            summary_library = matched
            continue
        if not summary_library:
            continue
        runtime_match = summary_runtime_re.search(msg)
        if not runtime_match:
            continue
        label = runtime_match.group(1).strip().lower()
        seconds = analyzer._parse_hms_to_seconds(runtime_match.group(2))
        if seconds is None:
            continue
        phase_key = None
        if "operations" in label:
            phase_key = "operations"
        elif "collections" in label:
            phase_key = "collections"
        elif "metadata" in label:
            phase_key = "metadata"
        elif "overlays" in label:
            phase_key = "overlays"
        if phase_key:
            _ensure_duration_entry(summary_library)
            existing = library_durations[summary_library].get(phase_key, 0)
            library_durations[summary_library][phase_key] = max(existing, int(seconds))
    if phase_sequence:
        completed_from_sequence = set()
        last_phase = phase_sequence[-1]
        for phase in phase_sequence:
            if phase != last_phase:
                completed_from_sequence.add(phase)
        for phase in completed_from_sequence:
            if phase not in phases_completed:
                phases_completed.append(phase)
    if is_finished_run_marker(content) and phase_current and phase_current not in phases_completed:
        phases_completed.append(phase_current)

    if finished_run_seen and phase_start:
        for name, phase_key in list(phase_start.keys()):
            _finish_phase(name, phase_key, last_ts)

    current_phase_elapsed = None
    live_reference_ts = effective_now if is_running and effective_now is not None else last_ts
    if current_library and live_reference_ts:
        open_phase = phase_open.get(current_library)
        if open_phase:
            start_ts = phase_start.get((current_library, open_phase))
            if start_ts:
                effective_start = start_ts
                if last_log_cutoff and start_ts < last_log_cutoff and live_reference_ts > last_log_cutoff:
                    effective_start = last_log_cutoff
                delta = max(0, int((live_reference_ts - effective_start).total_seconds()))
                base = 0
                if current_library in library_durations:
                    base = int(library_durations[current_library].get(open_phase, 0) or 0)
                current_phase_elapsed = base + delta

    if not preparation_locked and processing_started_at:
        prep_start = effective_started_at or first_log_ts
        if prep_start and processing_started_at > prep_start:
            preparation_seconds = max(0, int((processing_started_at - prep_start).total_seconds()))
            preparation_locked = True
    elif not preparation_locked and preparation_seconds is None:
        prep_start = effective_started_at or first_log_ts
        prep_reference_ts = effective_now if is_running and effective_now is not None else last_ts
        if prep_start and prep_reference_ts and prep_reference_ts > prep_start:
            preparation_elapsed_seconds = max(0, int((prep_reference_ts - prep_start).total_seconds()))

    playlist_elapsed_seconds = None
    playlist_reference_ts = effective_now if is_running and effective_now is not None else last_ts
    if playlist_running and playlist_reference_ts and playlist_started_at:
        effective_start = playlist_started_at
        if last_log_cutoff and playlist_started_at < last_log_cutoff and playlist_reference_ts > last_log_cutoff:
            effective_start = last_log_cutoff
        delta = max(0, int((playlist_reference_ts - effective_start).total_seconds()))
        playlist_elapsed_seconds = playlist_total_seconds + delta

    if finished_run_seen:
        for name, status in list(statuses.items()):
            if status in ("Pending", "In progress"):
                if selected_norm and not is_selected(name):
                    continue
                statuses[name] = "Done"

    libraries_payload = []
    completed_count = 0
    total_count = 0
    for entry in library_entries:
        name = entry["name"]
        status = statuses.get(name, "Pending")
        if is_selected(name):
            total_count += 1
            if status == "Done":
                completed_count += 1
        libraries_payload.append(
            {
                "name": name,
                "type": entry.get("type"),
                "status": status,
                "durations": library_durations.get(name, {}),
            }
        )

    phase_starts_payload = {}
    for (lib_name, phase_key), start_ts in phase_start.items():
        if not lib_name or not phase_key or not start_ts:
            continue
        phase_starts_payload[f"{lib_name}||{phase_key}"] = start_ts.isoformat()

    return {
        "phase_current": phase_current,
        "phases_completed": phases_completed,
        "libraries": libraries_payload,
        "current_library": current_library,
        "completed_count": completed_count,
        "total_count": total_count if selected_norm else len(library_entries),
        "current_phase_elapsed_seconds": current_phase_elapsed,
        "phase_starts": phase_starts_payload,
        "playlist_total_seconds": playlist_total_seconds,
        "playlist_running": playlist_running,
        "playlist_started_at": playlist_started_at.isoformat() if playlist_started_at else None,
        "playlist_elapsed_seconds": playlist_elapsed_seconds,
        "playlists_detected": playlists_detected,
        "run_finished": finished_run_seen,
        "preparation_seconds": preparation_seconds,
        "preparation_elapsed_seconds": preparation_elapsed_seconds,
    }
