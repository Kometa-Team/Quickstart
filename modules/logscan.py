import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules import (
    logscan_command,
    logscan_content_extractors,
    logscan_finished_runs,
    logscan_library_stats,
    logscan_maintenance,
    logscan_people,
    logscan_progress_engine,
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
        self.validation_summary = {}

    def reset_server_versions(self):
        """Reset the server_versions list to an empty list."""
        self.server_versions = []

    def remove_repeated_dividers(self, line):
        return logscan_content_extractors.remove_repeated_dividers(line, self.global_divider)

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
        return logscan_content_extractors.cleanup_content(content)

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

    def extract_validation_summary(self, content):
        return logscan_finished_runs.extract_validation_summary(content)

    def extract_log_timestamp_bounds(self, content):
        return logscan_finished_runs.extract_log_timestamp_bounds(content)

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
        logscan_recommendations_engine.ensure_recommendation_icons(recommendations)

    def reorder_recommendations(self, recommendations):
        return logscan_recommendations_engine.reorder_recommendations(recommendations)

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
        return logscan_finished_runs.parse_finished_datetime(value)

    def _normalize_finished_at(self, finished_at, log_mtime):
        return logscan_finished_runs.normalize_finished_at(finished_at, log_mtime)

    def _normalize_started_at(self, started_at):
        return logscan_finished_runs.normalize_started_at(started_at)

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
        return logscan_progress_engine.strip_divider_wrappers(self, message)

    def _extract_mapping_library(self, message):
        return logscan_progress_engine.extract_mapping_library(message)

    def _map_section_to_phase(self, section_name):
        return logscan_progress_engine.map_section_to_phase(section_name)

    def extract_progress(
        self,
        content,
        library_list=None,
        selected_libraries=None,
        previous=None,
        run_started_at=None,
        now_ts=None,
        is_running=False,
    ):
        return logscan_progress_engine.extract_progress(
            self,
            content,
            library_list=library_list,
            selected_libraries=selected_libraries,
            previous=previous,
            run_started_at=run_started_at,
            now_ts=now_ts,
            is_running=is_running,
        )

    def extract_analyze_issue_counts(self, content):
        return logscan_recommendations_engine.extract_analyze_issue_counts(content)

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
        validation_summary=None,
        timestamp_bounds=None,
    ):
        started_at = self._normalize_started_at(self.started_at)
        finished_at = self.finished_at
        validation_summary = validation_summary if isinstance(validation_summary, dict) else {}
        timestamp_bounds = timestamp_bounds if isinstance(timestamp_bounds, dict) else {}
        validation_run = bool(validation_summary.get("validation_run"))
        validation_result = validation_summary.get("validation_result")
        validation_complete = validation_run and bool(validation_result)
        if not started_at and timestamp_bounds.get("started_at"):
            started_at = timestamp_bounds.get("started_at")
        if not finished_at and validation_summary.get("finished_at"):
            finished_at = validation_summary.get("finished_at")
        if not finished_at and finished_runs:
            last_run = finished_runs[-1]
            if " - " in last_run:
                finished_at = last_run.split(" - ", 1)[0].strip()
            else:
                finished_at = last_run.strip()
            if finished_at.lower().startswith("finished at:"):
                finished_at = finished_at.split(":", 1)[1].strip()

        run_time_seconds = None
        run_time_source = None
        if isinstance(self.run_time, timedelta):
            run_time_seconds = int(self.run_time.total_seconds())
            run_time_source = "kometa"
        if not finished_at and timestamp_bounds.get("finished_at"):
            finished_at = timestamp_bounds.get("finished_at")
        run_complete = run_time_source == "kometa" or validation_complete
        if run_time_seconds is None and isinstance(timestamp_bounds.get("elapsed_seconds"), int):
            run_time_seconds = timestamp_bounds.get("elapsed_seconds")
            run_time_source = "log_timestamps"
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

        summary = {
            "run_key": run_key,
            "started_at": started_at,
            "finished_at": finished_at,
            "run_time_seconds": run_time_seconds,
            "run_time_source": run_time_source,
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
        if validation_run:
            summary["validation_run"] = True
            summary["validation_level"] = validation_summary.get("validation_level")
            summary["validation_result"] = validation_result
        return summary

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
        self.validation_summary = {}

        raw_content = content or ""
        self._raw_content = raw_content
        self.set_global_divider(raw_content)
        cleaned_content = self.cleanup_content(raw_content)

        header_lines = self.extract_header_lines(cleaned_content)
        finished_lines = self.extract_last_lines(cleaned_content)
        finished_runs = self.extract_finished_runs(cleaned_content)
        validation_summary = self.extract_validation_summary(raw_content)
        self.validation_summary = validation_summary if isinstance(validation_summary, dict) else {}
        timestamp_bounds = self.extract_log_timestamp_bounds(raw_content)
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
            validation_summary=validation_summary,
            timestamp_bounds=timestamp_bounds,
        )
        if summary:
            summary["analysis_counts"] = analysis_counts
            summary["quickstart_run_marker"] = bool(quickstart_marker)
            summary["quickstart_version"] = quickstart_marker_fields.get("quickstart") or None
            summary["quickstart_branch"] = quickstart_marker_fields.get("branch") or None
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
