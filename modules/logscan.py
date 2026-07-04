import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules import (
    logscan_command,
    logscan_content_extractors,
    logscan_finished_runs,
    logscan_library_stats,
    logscan_maintenance,
    logscan_people,
    logscan_recommendations,
    logscan_recommendations_engine,
)

# Re-exported for back-compat with tests / quickstart imports.
from modules.logscan_people import (  # noqa: F401
    PEOPLE_MISSING_WARNING_RE,
    PEOPLE_MISSING_WARNING_REGEX,
    PEOPLE_README_URLS,
    PEOPLE_SECTION_END_PATTERNS,
    PEOPLE_SECTION_START_STRONG,
    PEOPLE_SECTION_START_WEAK,
)

# Create logger
mylogger = logging.getLogger("logscan")
mylogger.setLevel(logging.INFO)


class LogscanAnalyzer:
    def __init__(self):
        self._raw_content = None
        self.global_divider = "="
        self.current_plexapi_version = None
        self.current_kometa_version = None
        self.kometa_newest_version = None
        self.run_time = None
        self.started_at = None
        self.finished_at = None
        self.plex_timeout = None
        self.checkfiles_flg = None
        self.server_versions = []
        self.people_index_available = False
        self._people_index = None

    def reset_server_versions(self):
        """Reset the server_versions list to an empty list."""
        self.server_versions = []

    def remove_repeated_dividers(self, line):
        divider = self.global_divider

        # Ensure that line is a string
        line = str(line)

        # Use regular expression to find and replace repeated dividers
        line = re.sub(f"({re.escape(divider)}){{10,}}", "", line)

        return line

    async def parse_attachment_content(self, content_bytes):
        try:
            content = content_bytes.decode("utf-8")
        except Exception as e:
            mylogger.error(f"Error decoding attachment content: {str(e)}")
            content = content_bytes.decode("utf-8", errors="replace")

        # Keep raw content for config extraction logic
        self._raw_content = content

        # Detect divider on raw content (so global_divider is correct)
        self.set_global_divider(content)

        # You can still return cleaned content for the rest of your features
        cleaned_content = self.cleanup_content(content)
        return cleaned_content

    def set_global_divider(self, content):
        """Search *content* for a KOMETA/PMM divider and store it on self."""
        divider = logscan_content_extractors.extract_divider(content, fallback=getattr(self, "global_divider", None) or logscan_content_extractors.DEFAULT_DIVIDER)
        self.global_divider = divider

    def extract_memory_value(self, content):
        return logscan_content_extractors.extract_memory_value(content)

    def extract_db_cache_value(self, content):
        return logscan_content_extractors.extract_db_cache_value(content)

    def extract_scheduled_run_time(self, content):
        return logscan_content_extractors.extract_scheduled_run_time(content)

    def extract_maintenance_times(self, content):
        return logscan_content_extractors.extract_maintenance_times(content)

    def contains_overlay_path(self, content):
        return logscan_content_extractors.contains_overlay_path(content)

    def contains_overlay_files(self, content):
        return logscan_content_extractors.contains_overlay_files(content)

    def detect_wsl_and_recommendation(self, content):
        return logscan_content_extractors.detect_wsl_recommendation(content)

    def make_db_cache_recommendations(self, parsed_content):
        return logscan_recommendations.db_cache_recommendation(
            self.extract_db_cache_value(parsed_content),
            self.extract_memory_value(parsed_content),
        )

    def calculate_memory_recommendation(self, content):
        memory_value = self.extract_memory_value(content)
        has_overlays = bool(self.contains_overlay_path(content) or self.contains_overlay_files(content))
        return logscan_recommendations.memory_recommendation(memory_value, has_overlays)

    def calculate_recommendation(self, kometa_scheduled_time, maintenance_start_time=None, maintenance_end_time=None):
        return logscan_recommendations.maintenance_time_recommendation(
            kometa_scheduled_time,
            maintenance_start_time,
            maintenance_end_time,
            run_time=self.run_time,
        )

    def _format_time_value(self, time_value):
        return logscan_recommendations.format_time_value(time_value)

    def cleanup_content(self, content):
        """
        Clean up the content by removing unnecessary lines and trailing characters.
        """
        cleanup_regex = r"\[(202[0-9])-\d+-\d+ \d+:\d+:\d+,\d+\] \[.*\.py:\d+\] +\[[INFODEBUGWARCTL]*\] +\||^[ ]{65}\|"
        cleaned_content = re.sub(cleanup_regex, "", content)

        # mylogger.info(f"content:\n{content}")
        # mylogger.info(f"cleaned_content:\n{cleaned_content}")

        # Second pass to remove trailing '|'
        lines = cleaned_content.splitlines()
        cleaned_lines = [line.rstrip("|") if line.rstrip().endswith("|") else line for line in lines]
        cleaned_content = "\n".join(cleaned_lines)

        # Third pass to remove trailing spaces
        cleaned_lines = [line.rstrip() for line in cleaned_content.splitlines()]
        cleaned_content = "\n".join(cleaned_lines)
        # mylogger.info(f"cleaned_content3rdpass:\n{cleaned_content}")

        return cleaned_content

    def extract_filename_from_url(self, url):
        return logscan_people.extract_filename_from_url(url)

    def _get_people_cache_path(self, log_path):
        return logscan_people.get_people_cache_path(log_path)

    def _load_people_cache(self, cache_path):
        return logscan_people.load_people_cache(cache_path)

    def _save_people_cache(self, cache_path, payload):
        return logscan_people.save_people_cache(cache_path, payload)

    def _fetch_people_readme(self, cache_path):
        return logscan_people.fetch_people_readme(cache_path)

    def _build_people_index(self, readme_text):
        return logscan_people.build_people_index(readme_text)

    def preload_people_index(self, log_path=None):
        cache_path = logscan_people.get_people_cache_path(log_path)
        readme_text, _used_cache = logscan_people.fetch_people_readme(cache_path)
        self._people_index = logscan_people.build_people_index(readme_text)
        self.people_index_available = bool(self._people_index)
        return self._people_index

    def _ensure_people_index(self, log_path=None, available_index=None):
        if available_index is not None:
            self.people_index_available = bool(available_index)
            return available_index
        if self._people_index is not None:
            self.people_index_available = bool(self._people_index)
            return self._people_index
        return self.preload_people_index(log_path=log_path)

    def _is_blank_log_line(self, line):
        return logscan_people.is_blank_log_line(line)

    def _is_divider_log_line(self, line):
        return logscan_people.is_divider_log_line(line)

    def _is_section_break(self, line):
        return logscan_people.is_section_break(line)

    def _matches_any_pattern(self, normalized, patterns):
        return logscan_people.matches_any_pattern(normalized, patterns)

    def _find_log_section_bounds(self, cleaned_lines, index, max_span=300):
        return logscan_people.find_log_section_bounds(cleaned_lines, index, max_span=max_span)

    def _normalize_name_line(self, line):
        return logscan_people.normalize_name_line(line)

    def _extract_key_name_from_block(self, cleaned_lines, start, end):
        return logscan_people.extract_key_name_from_block(cleaned_lines, start, end)

    def _extract_missing_people_names(self, lines, available, name_hint=None):
        return logscan_people.extract_missing_people_names(lines, available, name_hint=name_hint)

    def collect_missing_people_lines(self, content, available_index=None, max_block_lines=300, log_path=None):
        """Resolve the people index (caching it on ``self``) then delegate to
        :func:`modules.logscan_people.collect_missing_people_lines`."""
        if not content:
            return []
        available = self._ensure_people_index(log_path=log_path, available_index=available_index)
        return logscan_people.collect_missing_people_lines(
            content,
            available_index=available,
            max_block_lines=max_block_lines,
            cleanup_fn=self.cleanup_content,
        )

    def scan_file_for_people_posters(self, content, log_path=None):
        if not content:
            return []

        items = self.collect_missing_people_lines(content, log_path=log_path)
        names = set()
        for item in items:
            names.update(item.get("names", set()))
        if not names:
            return []
        return sorted(names, key=str.lower)

    def extract_finished_runs(self, content):
        return logscan_finished_runs.extract_finished_runs(content)

    def _parse_run_time_from_line(self, line):
        return logscan_finished_runs.parse_run_time_from_line(line)

    def extract_last_lines(self, content):
        tail_text, metadata = logscan_finished_runs.extract_last_lines(content)
        if metadata:
            # Persist final-run metadata onto the analyzer; interim
            # Run Time: lines return metadata=None and leave state alone.
            if "run_time" in metadata:
                self.run_time = metadata["run_time"]
            if "started_at" in metadata:
                self.started_at = metadata["started_at"]
            if "finished_at" in metadata:
                self.finished_at = metadata["finished_at"]
        return tail_text

    def format_contiguous_lines(self, line_numbers):
        return logscan_finished_runs.format_contiguous_lines(line_numbers)

    def make_recommendations(self, content, incomplete_message):
        return logscan_recommendations_engine.make_recommendations(self, content, incomplete_message)

    def _ensure_recommendation_icons(self, recommendations):
        priority_icons = {"🚀", "💥", "❌", "⚠", "💬", "ℹ"}
        for rec in recommendations:
            first_line = rec.get("first_line", "") or ""
            trimmed = first_line.lstrip()
            if not trimmed:
                rec["first_line"] = "💬 Recommendation"
                continue
            first_symbol = trimmed[0].rstrip("\ufe0f")
            if first_symbol not in priority_icons:
                rec["first_line"] = f"💬 {trimmed}"

    def reorder_recommendations(self, recommendations):
        # Define the priority order of symbols
        priority_order = {"🚀": 1, "💥": 2, "❌": 3, "⚠": 4, "💬": 5, "ℹ": 5}

        def sort_key(recommendation):
            # Get the first symbol in the message
            first_symbol = recommendation.get("first_line", "No first line available")[0]

            # Remove variation selector if present
            first_symbol = first_symbol.rstrip("\ufe0f")

            # Check if the first symbol is in the priority_order dictionary
            if first_symbol in priority_order:
                priority = priority_order[first_symbol]
                # mylogger.info(f"Original Message: {recommendation.get('first_line', 'No first line available')}")
                # mylogger.info(f"First Symbol: {first_symbol}")
                # mylogger.info(f"Priority: {priority}")
                return priority
            else:
                # mylogger.info(f"Priority not found for symbol {first_symbol}, using default priority")
                return float("inf")

        # Sort recommendations based on the custom key
        sorted_recommendations = sorted(recommendations, key=sort_key)

        return sorted_recommendations

    def extract_plex_config(self, content):
        """Extract Plex configuration sections from ``content``.

        Delegates to :mod:`modules.logscan_command` and folds any flagged
        server versions onto ``self.server_versions`` so the legacy
        ``make_recommendations`` lookup keeps working.
        """
        result = logscan_command.extract_plex_config(content)
        self.server_versions.extend(result["server_versions"])
        return result["plex_config_content"]

    def extract_plex_config_section(self, lines, start_index, end_markers):
        return logscan_command.extract_plex_config_section(lines, start_index, end_markers)

    def parse_server_info(self, config_section):
        return logscan_command.parse_server_info(config_section)

    def extract_header_lines(self, content):
        """Capture the header block and stash the Kometa versions on ``self``."""
        header_text, current_version, newest_version = logscan_command.extract_header_lines(content)
        if current_version is not None:
            self.current_kometa_version = current_version
        if newest_version is not None:
            self.kometa_newest_version = newest_version
        return header_text

    def extract_run_command(self, content):
        return logscan_command.extract_run_command(content)

    def _split_command(self, command):
        return logscan_command.split_command(command)

    def compute_command_signature(self, run_command):
        return logscan_command.compute_command_signature(run_command)

    def _extract_config_path_from_command(self, run_command):
        return logscan_command.extract_config_path_from_command(run_command)

    def _derive_config_name_from_path(self, config_path):
        return logscan_command.derive_config_name_from_path(config_path)

    def sanitize_run_command(self, run_command, config_path=None):
        return logscan_command.sanitize_run_command(run_command, config_path=config_path)

    def _hash_file(self, path):
        return logscan_command.hash_file(path)

    def _parse_finished_datetime(self, value):
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

    def _normalize_finished_at(self, finished_at, log_mtime):
        parsed = self._parse_finished_datetime(finished_at)
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

    def _normalize_started_at(self, started_at):
        parsed = self._parse_finished_datetime(started_at)
        now = datetime.now()
        if parsed and parsed > now + timedelta(days=1):
            parsed = None
        if parsed:
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        return started_at

    def _parse_hms_to_seconds(self, value):
        return logscan_library_stats.parse_hms_to_seconds(value)

    def extract_section_runtimes(self, content):
        return logscan_library_stats.extract_section_runtimes(content)

    def count_log_levels(self, content):
        return logscan_library_stats.count_log_levels(content)

    def _normalize_library_name(self, value):
        return logscan_library_stats.normalize_library_name(value)

    def _match_library_name(self, raw_name, library_entries):
        return logscan_library_stats.match_library_name(raw_name, library_entries)

    def _strip_divider_wrappers(self, message):
        if not message:
            return message
        cleaned = self.remove_repeated_dividers(message)
        divider = self.global_divider or ""
        cleaned = cleaned.strip()
        if divider:
            cleaned = cleaned.strip(divider).strip()
        return cleaned.strip("|").strip()

    def _extract_mapping_library(self, message):
        if not message:
            return None
        match = re.search(r"\bMapping\s+(.+?)\s+Library\b", message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _map_section_to_phase(self, section_name):
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

    def extract_progress(self, content, library_list=None, selected_libraries=None, previous=None, run_started_at=None, now_ts=None, is_running=False):
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
            selected_norm = {self._normalize_library_name(name) for name in selected_libraries if name}

        def is_selected(name):
            if not selected_norm:
                return True
            return self._normalize_library_name(name) in selected_norm

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

        self.set_global_divider(content)
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
            msg = self._strip_divider_wrappers(msg)

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
                    seconds = self._parse_hms_to_seconds(match.group(1))
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
                    matched = self._match_library_name(name, library_entries)
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
                    matched = self._match_library_name(name, library_entries)
                    if matched:
                        _finish_phase(matched, "overlays", line_ts)
                continue

            if "operations.py" in raw_line and operations_start_re.search(msg):
                match = operations_start_re.search(msg)
                if match:
                    name = match.group(1).strip()
                    matched = self._match_library_name(name, library_entries)
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
                    matched = self._match_library_name(name, library_entries)
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
                name = self._extract_mapping_library(msg)
                if name:
                    matched = self._match_library_name(name, library_entries)
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
                matched = self._match_library_name(name, library_entries)
                if matched and statuses.get(matched) != "Skipped":
                    statuses[matched] = "Done"
                    if current_library == matched:
                        current_library = None
                continue

            if "Finished Libraries Run" in msg:
                finished_run_seen = True
                if current_library and current_library in statuses and statuses[current_library] != "Skipped":
                    statuses[current_library] = "Done"
                current_library = None
                playlist_running = False
                continue

            if "Finished Run" in msg:
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
                matched = self._match_library_name(name, library_entries)
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
                matched = self._match_library_name(name, library_entries)
                if not matched:
                    if selected_norm or not allow_unknown:
                        continue
                    library_entries.append({"name": name, "type": None})
                    statuses.setdefault(name, "Pending")
                    matched = name
                library_hint = matched
                break

        section_runtimes = self.extract_section_runtimes(content)
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
            phase = self._map_section_to_phase(section_name)
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
            msg = self._strip_divider_wrappers(msg)
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
            msg = self._strip_divider_wrappers(msg)
            header_match = summary_header_re.search(msg)
            if header_match:
                name = header_match.group(1).strip()
                matched = self._match_library_name(name, library_entries)
                summary_library = matched
                continue
            if not summary_library:
                continue
            runtime_match = summary_runtime_re.search(msg)
            if not runtime_match:
                continue
            label = runtime_match.group(1).strip().lower()
            seconds = self._parse_hms_to_seconds(runtime_match.group(2))
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
        if "Finished Run" in content and phase_current and phase_current not in phases_completed:
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

    def extract_analyze_issue_counts(self, content):
        patterns = {
            "analyze_convert": re.compile(r"\bconvert\s+(warning|error)\b", re.IGNORECASE),
            "analyze_anidb": re.compile(r"\banidb\b.*\b(error|warning|failed)\b", re.IGNORECASE),
            "analyze_regex": re.compile(r"\bregex\b.*\b(error|warning|invalid|failed)\b", re.IGNORECASE),
        }
        counts = {key: 0 for key in patterns}
        if not content:
            counts["convert"] = 0
            counts["anidb"] = 0
            counts["regex"] = 0
            return counts
        for line in content.splitlines():
            for key, pattern in patterns.items():
                if pattern.search(line):
                    counts[key] += 1
        counts["convert"] = counts["analyze_convert"]
        counts["anidb"] = counts["analyze_anidb"]
        counts["regex"] = counts["analyze_regex"]
        return counts

    def extract_quickstart_marker(self, content):
        return logscan_maintenance.extract_quickstart_marker(content)

    def extract_quickstart_marker_fields(self, content):
        return logscan_maintenance.extract_quickstart_marker_fields(content)

    def extract_quickstart_marker_capabilities(self, content):
        return logscan_maintenance.extract_quickstart_marker_capabilities(content)

    def _parse_log_timestamp(self, line):
        return logscan_maintenance.parse_log_timestamp(line)

    def extract_maintenance_summary(self, content):
        return logscan_maintenance.extract_maintenance_summary(content)

    def extract_quiet_period_summary(self, content, maintenance_summary=None):
        return logscan_maintenance.extract_quiet_period_summary(content, maintenance_summary)

    def extract_config_line_count(self, content):
        return logscan_library_stats.extract_config_line_count(content)

    def extract_library_counts(self, content):
        return logscan_library_stats.extract_library_counts(content)

    def _build_summary(
        self,
        finished_runs,
        log_path,
        counts,
        config_name=None,
        config_hash=None,
        run_command=None,
        command_signature=None,
        section_runtimes=None,
    ):
        started_at = self._normalize_started_at(self.started_at)
        finished_at = self.finished_at
        if not finished_at and finished_runs:
            last_run = finished_runs[-1]
            if " - " in last_run:
                finished_at = last_run.split(" - ", 1)[0].strip()
            else:
                finished_at = last_run.strip()
            if finished_at.lower().startswith("finished at:"):
                finished_at = finished_at.split(":", 1)[1].strip()

        run_time_seconds = None
        if isinstance(self.run_time, timedelta):
            run_time_seconds = int(self.run_time.total_seconds())
        run_complete = run_time_seconds is not None
        section_total_seconds = None
        section_delta_seconds = None
        if section_runtimes:
            section_total_seconds = int(sum(value for value in section_runtimes.values() if isinstance(value, (int, float))))
            if run_time_seconds is not None:
                section_delta_seconds = section_total_seconds - run_time_seconds

        log_mtime = None
        log_size = None
        if log_path:
            try:
                stats = Path(log_path).stat()
                log_mtime = stats.st_mtime
                log_size = stats.st_size
            except Exception as exc:
                mylogger.debug(f"Failed to stat log file {log_path}: {exc}")

        finished_at = self._normalize_finished_at(finished_at, log_mtime)

        run_key = None
        if finished_at or run_time_seconds is not None:
            run_key_parts = [
                finished_at or "",
                str(run_time_seconds or ""),
                config_name or "",
                command_signature or "",
                self.current_kometa_version or "",
            ]
            run_key_seed = "|".join(run_key_parts)
            run_key = hashlib.sha256(run_key_seed.encode("utf-8")).hexdigest()

        return {
            "run_key": run_key,
            "started_at": started_at,
            "finished_at": finished_at,
            "run_time_seconds": run_time_seconds,
            "run_complete": run_complete,
            "section_runtime_total_seconds": section_total_seconds,
            "section_runtime_delta_seconds": section_delta_seconds,
            "kometa_version": self.current_kometa_version,
            "kometa_newest_version": self.kometa_newest_version,
            "config_name": config_name,
            "config_hash": config_hash,
            "run_command": run_command,
            "command_signature": command_signature,
            "section_runtimes": section_runtimes or {},
            "log_mtime": log_mtime,
            "log_size": log_size,
            "log_counts": counts,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def analyze_content(self, content, log_path=None, config_name=None, config_path=None, include_people_scan=True):
        self.reset_server_versions()
        self.checkfiles_flg = None
        self.run_time = None
        self.started_at = None
        self.finished_at = None
        self.plex_timeout = None
        self.current_kometa_version = None
        self.kometa_newest_version = None
        self.people_index_available = False

        raw_content = content or ""
        self._raw_content = raw_content
        self.set_global_divider(raw_content)
        cleaned_content = self.cleanup_content(raw_content)

        header_lines = self.extract_header_lines(cleaned_content)
        finished_lines = self.extract_last_lines(cleaned_content)
        finished_runs = self.extract_finished_runs(cleaned_content)
        self.extract_plex_config(cleaned_content)
        run_command_raw = self.extract_run_command(cleaned_content)
        command_signature = self.compute_command_signature(run_command_raw)
        if not config_path:
            parsed_path = self._extract_config_path_from_command(run_command_raw)
            if parsed_path:
                config_path = Path(parsed_path)
        if not config_name and config_path:
            config_name = self._derive_config_name_from_path(config_path)
        run_command = self.sanitize_run_command(run_command_raw, config_path=config_path)
        config_hash = self._hash_file(config_path)
        section_runtimes = self.extract_section_runtimes(cleaned_content)

        recommendations, issue_counts = self.make_recommendations(cleaned_content, "")

        analysis_counts = self.extract_analyze_issue_counts(cleaned_content)
        quickstart_marker = self.extract_quickstart_marker(raw_content)
        quickstart_marker_fields = self.extract_quickstart_marker_fields(raw_content)
        config_line_count = self.extract_config_line_count(raw_content)
        cache_line_count = sum(1 for line in raw_content.splitlines() if "from Cache" in line)
        library_counts = self.extract_library_counts(cleaned_content)
        maintenance_summary = self.extract_maintenance_summary(raw_content)
        quiet_period_summary = self.extract_quiet_period_summary(raw_content, maintenance_summary=maintenance_summary)

        missing_people = []
        missing_people_message = None
        if include_people_scan:
            missing_people = self.scan_file_for_people_posters(cleaned_content, log_path=log_path)
            if missing_people:
                if self.people_index_available:
                    missing_people_message = (
                        "Missing people posters detected. Drop your meta.log in the Kometa Discord #bot-spam channel "
                        "and answer Yes to the Logscan prompt to request poster creation."
                    )
                else:
                    missing_people_message = "People-Images index unavailable; showing all people poster references from the log."
                missing_people_lines = "\n".join(f"- {name}" for name in missing_people)
                recommendations.append(
                    {
                        "first_line": "INFO - Missing people posters",
                        "message": f"{missing_people_message}\n\nMissing names:\n{missing_people_lines}",
                    }
                )
        if issue_counts is None:
            issue_counts = {}
        issue_counts["people_posters"] = len(missing_people)
        analysis_counts.update(issue_counts)

        counts = self.count_log_levels(raw_content)
        summary = self._build_summary(
            finished_runs,
            log_path,
            counts,
            config_name=config_name,
            config_hash=config_hash,
            run_command=run_command,
            command_signature=command_signature,
            section_runtimes=section_runtimes,
        )
        if summary:
            summary["analysis_counts"] = analysis_counts
            summary["quickstart_run_marker"] = bool(quickstart_marker)
            summary["start_mode"] = quickstart_marker_fields.get("start_mode") or None
            summary["library_counts"] = library_counts
            summary["maintenance_summary"] = maintenance_summary
            summary["quiet_period_summary"] = quiet_period_summary
            summary["config_line_count"] = config_line_count
            summary["cache_line_count"] = cache_line_count
        if summary and not summary.get("run_complete"):
            recommendations.append(
                {
                    "first_line": "INFO - Run incomplete",
                    "message": (
                        "This log does not include a completed Finished Run block yet. "
                        "Live logscan will still show findings, but trends ingestion is skipped until the run completes."
                    ),
                }
            )

        if recommendations:
            self._ensure_recommendation_icons(recommendations)
            recommendations = self.reorder_recommendations(recommendations)

        return {
            "summary": summary,
            "recommendations": recommendations,
            "missing_people": missing_people,
            "missing_people_message": missing_people_message,
            "header_lines": header_lines,
            "finished_lines": finished_lines,
        }

    def analyze_log_file(self, log_path, config_name=None, config_path=None, include_people_scan=True):
        log_path = Path(log_path)
        if not log_path.exists():
            raise FileNotFoundError(f"Log file not found at: {log_path}")
        content = log_path.read_text(encoding="utf-8", errors="replace")
        return self.analyze_content(
            content,
            log_path=log_path,
            config_name=config_name,
            config_path=config_path,
            include_people_scan=include_people_scan,
        )
