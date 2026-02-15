import hashlib
import json
import logging
import os
import re
import shlex
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import requests

# Create logger
mylogger = logging.getLogger("logscan")
mylogger.setLevel(logging.DEBUG)  # Set the logging level to DEBUG


# --- PMS security vulnerability helpers (non-invasive; keep existing checks as-is) ---


def _parse_pms_version_tuple(ver: str):
    """Return a 4-int tuple for PMS versions like '1.41.7.9100' (trims any '-xyz')."""
    ver = ver.split("-", 1)[0].strip()  # drop any '-whatever' suffix if present
    parts = ver.split(".")
    nums = []
    for i in range(4):
        try:
            nums.append(int(parts[i]))
        except Exception:
            nums.append(0)
    return tuple(nums[:4])


def _version_in_inclusive_range(ver: str, low: tuple, high: tuple) -> bool:
    v = _parse_pms_version_tuple(ver)
    return low <= v <= high


# Vulnerable range you want to flag (adjust as needed)
_PMS_VULN_LOW = (1, 41, 7, 0)  # 1.41.7.x
_PMS_VULN_HIGH = (1, 42, 0, 99999)  # through 1.42.0.x

PEOPLE_README_URLS = [
    "https://raw.githubusercontent.com/Kometa-Team/People-Images/refs/heads/master/README.md",
]
PEOPLE_MISSING_WARNING_REGEX = (
    r"Collection Warning: No Poster Found at "
    r"(https://raw\.githubusercontent\.com/"
    r"(?:Kometa-Team/People-Images|meisnate12/Plex-Meta-Manager-People(?:-[^/]+)?)"
    r"/[^\s\]]+)"
)
PEOPLE_MISSING_WARNING_RE = re.compile(PEOPLE_MISSING_WARNING_REGEX, re.IGNORECASE)
PEOPLE_SECTION_START_STRONG = [
    r"^(.+?) Collection in .+$",
    r"^Running .+ Collection$",
]
PEOPLE_SECTION_START_WEAK = [
    r"^Updating Details of .+ Collection$",
    r"^Validating .+ Attributes$",
]
PEOPLE_SECTION_END_PATTERNS = [
    r"^Finished .+ Collection$",
]


class LogscanAnalyzer:
    def __init__(self):
        self._raw_content = None
        self.global_divider = "="
        self.current_plexapi_version = None
        self.current_kometa_version = None
        self.kometa_newest_version = None
        self.run_time = None
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
        """
        Search for the divider string in the content and set the global divider.
        """
        # Define the patterns to search for
        patterns = [
            r'--divider \(KOMETA_DIVIDER\): ?["\']?([^"\']{1})["\']?',  # KOMETA_DIVIDER pattern
            r'--divider \(PMM_DIVIDER\): ?["\']?([^"\']{1})["\']?',  # PMM_DIVIDER pattern
        ]

        # Try each pattern and set global_divider if a match is found
        for pattern in patterns:
            divider_match = re.search(pattern, content)
            if divider_match:
                divider = divider_match.group(1)
                self.global_divider = divider
                mylogger.info(f"Divider found and set to: {divider}")
                return  # Exit the function once a divider is found

        # If no match is found for any pattern, use default divider
        self.global_divider = "="
        mylogger.info(f"Divider not found, using default divider: {self.global_divider}")

    def extract_memory_value(self, content):
        """
        Extract the memory value from the given content.
        """
        # Regular expression to match the memory value
        memory_match = re.search(r"Memory:\s*([\d.]+)\s*(\w+)", content)

        if memory_match:
            value = float(memory_match.group(1))
            unit = memory_match.group(2).lower()

            # Convert value to gigabytes (GB)
            if unit == "gb":
                return value
            elif unit == "mb":
                return value / 1024  # Convert MB to GB
            elif unit == "tb":
                return value * 1024  # Convert TB to GB

        return None  # Return None if no valid memory value is found

    def extract_db_cache_value(self, content):
        """
        Extract the db_cache value from the given content.
        """
        # Regular expression to match the memory value
        memory_match = re.search(r"Plex DB cache setting:\s*([\d.]+)\s*(\w+)", content)

        if memory_match:
            value = float(memory_match.group(1))
            unit = memory_match.group(2).lower()

            # Convert value to gigabytes (GB)
            if unit == "gb":
                return value
            elif unit == "mb":
                return value / 1024  # Convert MB to GB
            elif unit == "tb":
                return value * 1024  # Convert TB to GB

        return None  # Return None if no valid memory value is found

    def extract_scheduled_run_time(self, content):
        """
        Extract the scheduled run time from the content.
        """
        # Define the patterns to search for
        patterns = [
            r'--times? \((KOMETA_TIMES?)\): ?["\']?(\d{1,2}:\d{2})["\']?',  # KOMETA_TIMES pattern
            r'--times? \((PMM_TIMES?)\): ?["\']?(\d{1,2}:\d{2})["\']?',  # PMM_TIMES pattern
        ]

        # Try each pattern and return the first match found
        for pattern in patterns:
            scheduled_run_time_match = re.search(pattern, content)
            if scheduled_run_time_match:
                scheduled_run_time = scheduled_run_time_match.group(2)
                mylogger.info(f"Scheduled run time found: {scheduled_run_time}")
                return scheduled_run_time

        # If no match is found
        mylogger.info("Scheduled run time not found in content.")
        return None

    def extract_maintenance_times(self, content):
        """
        Extract the start and end times of the maintenance from the content.
        """
        maintenance_times_match = re.search(r"Scheduled maintenance running between (\d+:\d+) and (\d+:\d+)", content)

        if maintenance_times_match:
            start_time = maintenance_times_match.group(1)
            end_time = maintenance_times_match.group(2)
            mylogger.info(f"Scheduled maintenance times found: Start time: {start_time}, End time: {end_time}")
            return start_time, end_time
        else:
            mylogger.info("Scheduled maintenance times not found in content.")
            return None, None

    def contains_overlay_path(self, content):
        # Regular expression to search for overlay_path
        return bool(re.search(r"\boverlay_path:\s*", content, re.IGNORECASE))

    def contains_overlay_files(self, content):
        # Regular expression to search for overlay_files
        return bool(re.search(r"\boverlay_files:\s*", content, re.IGNORECASE))

    def detect_wsl_and_recommendation(self, content):
        # Regular expression to check if the content contains information about WSL platform
        wsl_pattern = r"Platform: .*-WSL"

        if re.search(wsl_pattern, content):
            recommendation = (
                "💬🪟🐧 **WSL MEMORY RECOMMENDATION**\n"
                "According to Microsoft’s documentation, the amount of system memory (RAM) that gets allocated to WSL is limited to "
                "either 50% of your total memory or 8GB, whichever happens to be smaller.\n\n"
                "It is possible to override the maximum RAM allocation, we suggest googling 'WSL memory limit' to learn more otherwise the following may work for you:"
                "To override the maximum RAM allocation when running Windows Subsystem for Linux (WSL), you need to modify the configuration settings. Here are the steps to do this:\n"
                "1. Open a PowerShell window as an administrator.\n"
                "2. Run the command: `wsl --set-default-version 2` to set WSL version to 2 (WSL 2).\n"
                "3. Run the command: `wsl --set-memory <your_memory_limit>` to set the maximum memory limit for WSL (replace `<your_memory_limit>` with the desired memory limit, e.g., `4GB`).\n"
                "4. Restart WSL by running the command: `wsl --shutdown`.\n\n"
                "It is important to note that modifying these settings may require a reboot of your system."
            )
            return recommendation

        return None  # Return None if WSL is not detected in the content

    def make_db_cache_recommendations(self, parsed_content):
        disclaimer = (
            "**NOTE**:The number you choose can vary wildly based on a number of factors "
            "(such as the size and number of libraries, and the amount of files/operations/overlays that are being utilized)."
        )
        url_info = "https://kometa.wiki/en/latest/config/plex#plex-attributes"

        # Extract db_cache value and total memory value
        db_cache_value = self.extract_db_cache_value(parsed_content)
        total_memory_value = self.extract_memory_value(parsed_content)

        if db_cache_value is None or total_memory_value is None:
            return None  # Unable to determine recommendations due to missing data

        if db_cache_value >= total_memory_value:
            # db_cache should not be greater than or equal to total memory
            return (
                f"❌ **PLEX DB CACHE ISSUE**\n"
                f"The Plex DB cache setting (**{db_cache_value:.2f} GB**) is equal to or greater than the total memory "
                f"(**{total_memory_value:.2f} GB**). Consider adjusting the Plex DB cache setting to a value **below** the total memory.\n"
                f"For more info on this setting: {url_info}\n"
                f"{disclaimer}"
            )

        elif db_cache_value < 1:
            # db_cache is less than 1 GB, recommend updating based on total memory
            return (
                f"💬💡️ **PLEX DB CACHE ADVICE**\n"
                f"Consider updating the Plex DB cache setting from **{db_cache_value:.2f} GB**, to a value **greater** than **1 GB** based on the total memory of **{total_memory_value:.2f} GB**.\nSetting `db_cache: 1024` within the plex settings in your config.yml is effectively 1024MB which is 1GB. "
                f"For more info on this setting: {url_info}\n"
                f"{disclaimer}"
            )

        return None  # No issues or recommendations

    def calculate_memory_recommendation(self, content):
        disclaimer = (
            "These numbers are purely estimates and can vary wildly based on a number of factors "
            "(such as the size and number of libraries, and the amount of files/operations/overlays that are being utilized)."
        )

        # Extract memory value from the content
        memory_value = self.extract_memory_value(content)
        overlay_value = self.contains_overlay_path(content)

        # Check if overlay_value is still empty before updating it the second time
        if not overlay_value:
            overlay_value = self.contains_overlay_files(content)

        if memory_value is None:
            return "Error: Memory value not found in content."

        if memory_value < 4:
            if overlay_value:
                return (
                    f"⚠️ **MEMORY RECOMMENDATION**\n"
                    f"The memory value is {memory_value:.2f} GB, which is less than 4 GB. "
                    f"We advise having at least 8GB of RAM when running Kometa with overlays (we have detected overlays) to avoid potential out-of-memory issues.\n\n"
                    f"{disclaimer}"
                )
            else:
                return (
                    f"⚠️ **MEMORY RECOMMENDATION**\n"
                    f"The memory value is {memory_value:.2f} GB, which is less than 4 GB. "
                    f"We advise having at least 4GB of RAM when running Kometa without overlays (we have NOT detected overlays) to avoid potential out-of-memory issues.\n\n"
                    f"{disclaimer}"
                )

        elif memory_value < 8:
            if overlay_value:
                return (
                    f"⚠️ **MEMORY RECOMMENDATION**\n"
                    f"The memory value is {memory_value:.2f} GB, which is less than 8 GB. "
                    f"We advise having at least 8GB of RAM when running Kometa with overlays (we have detected overlays) for optimal performance.\n\n"
                    f"{disclaimer}"
                )
            else:
                return None  # No specific recommendation for memory < 8GB without overlays

        return None  # No specific recommendation for memory >= 8GB

    def calculate_recommendation(self, kometa_scheduled_time, maintenance_start_time=None, maintenance_end_time=None):
        if not kometa_scheduled_time:
            return "Error: Plex scheduled time is missing."

        kometa_scheduled_time = datetime.strptime(kometa_scheduled_time, "%H:%M").time()

        # Check if maintenance times are provided
        if maintenance_start_time is None or maintenance_end_time is None:
            return None  # Cannot provide recommendations without maintenance times

        maintenance_start_time = datetime.strptime(maintenance_start_time, "%H:%M").time()
        maintenance_end_time = datetime.strptime(maintenance_end_time, "%H:%M").time()

        plex_scheduled_datetime = datetime.combine(datetime.today(), kometa_scheduled_time)
        maintenance_start_datetime = datetime.combine(datetime.today(), maintenance_start_time)
        maintenance_end_datetime = datetime.combine(datetime.today(), maintenance_end_time)

        if maintenance_start_datetime > plex_scheduled_datetime:
            # Plex maintenance period starts on the next day
            time_before_plex_maintenance = (maintenance_start_datetime - plex_scheduled_datetime).seconds // 60
        else:
            # Plex maintenance period starts on the same day
            time_before_plex_maintenance = (maintenance_start_datetime - plex_scheduled_datetime).seconds // 60
        # Calculate the buffer until the next plex maintenance in minutes
        buffer_until_next_plex_maintenance = ((24 + maintenance_start_time.hour - maintenance_end_time.hour) * 60) % 1440  # 1440 minutes in a day

        run_time_in_minutes = self.run_time.total_seconds() / 60
        time_buffer = timedelta(minutes=buffer_until_next_plex_maintenance)
        mylogger.info(f"time_before_plex_maintenance: {time_before_plex_maintenance}")
        mylogger.info(f"buffer_until_next_plex_maintenance: {buffer_until_next_plex_maintenance}")
        mylogger.info(f"time_buffer until next Plex maintenance: {time_buffer}")
        mylogger.info(f"run_time_in_minutes: {run_time_in_minutes}")
        plex_maint_url = "https://support.plex.tv/articles/202197488-scheduled-server-maintenance/"

        if run_time_in_minutes > 1440:
            return f"❌⏰ **KOMETA RUN TIME > 24 HOURS**\nThis Run took: `{self.run_time}`\nTime between Kometa scheduled time and Plex Maintenance start: `{time_buffer}`\nKometa scheduled start time: `{self._format_time_value(kometa_scheduled_time)}`\nPlex Scheduled Maintenance start time: `{self._format_time_value(maintenance_start_time)}`\nPlex Scheduled Maintenance end time: `{self._format_time_value(maintenance_end_time)}`\nIf your Kometa runs typically take this long [this run took `{self.run_time}`], your Kometa run time will coincide with the next Plex maintenance period as this run is greater than 24 hours.\n\nThe suggestion we can make at this point is to find ways to break down your run into smaller chunks and schedule them on different days.\nFor more information on Plex Maintenance, see {plex_maint_url}"

        if run_time_in_minutes > buffer_until_next_plex_maintenance:
            return f"❌⏰ **KOMETA RUN TIME > BUFFER BEFORE MAINTENANCE**\nThis Run took: `{self.run_time}`\nTime between Kometa Scheduled time and Plex Maintenance start: `{time_buffer}`\nKometa scheduled start time: `{self._format_time_value(kometa_scheduled_time)}`\nPlex Scheduled Maintenance start time: `{self._format_time_value(maintenance_start_time)}`\nPlex Scheduled Maintenance end time: `{self._format_time_value(maintenance_end_time)}`\nIf your Kometa runs typically take this long [this run took `{self.run_time}`], your Kometa run time will coincide with the next Plex maintenance period. Adjust the Kometa Scheduled start time to `{self._format_time_value(maintenance_end_time)}` (if needed) AND adjust the Plex Scheduled Maintenance start time to be later.\nFor more information on Plex Maintenance, see {plex_maint_url}"

        if maintenance_start_datetime <= plex_scheduled_datetime < maintenance_end_datetime:
            # Provide a message for the case when kometa_scheduled_time is between maintenance start and end times
            return f"❌⏰ **KOMETA SCHEDULED TIME CONFLICT**\nThis Run took: `{self.run_time}`\nTime between Kometa Scheduled time and Plex Maintenance start: `{time_buffer}`\nKometa scheduled start time: `{self._format_time_value(kometa_scheduled_time)}`\nPlex Scheduled Maintenance start time: `{self._format_time_value(maintenance_start_time)}`\nPlex Scheduled Maintenance end time: `{self._format_time_value(maintenance_end_time)}`\nYou are within the maintenance window between Plex maintenance start time: `{self._format_time_value(maintenance_start_time)}` and end time: `{self._format_time_value(maintenance_end_time)}`. Adjust the Kometa Scheduled start time to `{self._format_time_value(maintenance_end_time)}` or adjust the Plex Scheduled Maintenance times to end prior to the Kometa Scheduled run time.\nFor more information on Plex Maintenance, see {plex_maint_url}"

        if run_time_in_minutes > time_before_plex_maintenance:
            return f"❌⏰ **KOMETA RUN TIME > TIME BEFORE MAINTENANCE**\nThis Run took: `{self.run_time}`\nTime between Kometa Scheduled time and Plex Maintenance start: `{time_buffer}`\nKometa scheduled start time: `{self._format_time_value(kometa_scheduled_time)}`\nPlex Scheduled Maintenance start time: `{self._format_time_value(maintenance_start_time)}`\nPlex Scheduled Maintenance end time: `{self._format_time_value(maintenance_end_time)}`\nIf your Kometa runs typically take this long [this run took `{self.run_time}`], your Kometa run time will coincide with the next Plex maintenance period. Consider moving the Kometa scheduled start time to `{self._format_time_value(maintenance_end_time)}` or adjust the Plex Scheduled Maintenance times to end prior to the Kometa Scheduled run time.\nFor more information on Plex Maintenance, see {plex_maint_url}"

        return None

    def _format_time_value(self, time_value):
        if not time_value:
            return "N/A"
        formatted = time_value.strftime("%H:%M")
        return formatted[1:] if formatted.startswith("0") else formatted

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
        return unquote(os.path.splitext(os.path.basename(url))[0])

    def _get_people_cache_path(self, log_path):
        cache_dir = Path(__file__).resolve().parent.parent / "config" / "cache" / "logscan"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir / "logscan_people_readme.json"
        except Exception:
            pass
        if log_path:
            try:
                log_path = Path(log_path)
                if log_path.is_file():
                    return log_path.parent / ".logscan_people_cache.json"
            except Exception:
                pass
        return Path.cwd() / ".logscan_people_cache.json"

    def _load_people_cache(self, cache_path):
        try:
            if not cache_path or not Path(cache_path).exists():
                return {}
            with open(cache_path, "r", encoding="utf-8") as handle:
                return json.load(handle) or {}
        except Exception:
            return {}

    def _save_people_cache(self, cache_path, payload):
        try:
            if not cache_path:
                return
            with open(cache_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, indent=2)
        except Exception:
            return

    def _fetch_people_readme(self, cache_path):
        cache = self._load_people_cache(cache_path)
        cached_content = cache.get("content")

        for url in PEOPLE_README_URLS:
            headers = {"User-Agent": "Quickstart-Logscan"}
            if cache.get("url") == url:
                if cache.get("etag"):
                    headers["If-None-Match"] = cache["etag"]
                if cache.get("last_modified"):
                    headers["If-Modified-Since"] = cache["last_modified"]
            try:
                response = requests.get(url, headers=headers, timeout=5)
            except Exception as exc:
                mylogger.debug(f"People-Images README fetch failed for {url}: {exc}")
                continue

            if response.status_code == 304 and cached_content:
                return cached_content, True
            if response.status_code == 200 and response.text:
                payload = {
                    "url": url,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "fetched_at": datetime.utcnow().isoformat(),
                    "content": response.text,
                }
                self._save_people_cache(cache_path, payload)
                return response.text, False
            if response.status_code in (404, 410):
                continue

        return cached_content, True if cached_content else False

    def _build_people_index(self, readme_text):
        if not readme_text:
            return set()
        filenames = re.findall(r"([A-Za-z0-9_./%\-]+\.(?:jpg|jpeg|png|webp))", readme_text, flags=re.IGNORECASE)
        names = set()
        for name in filenames:
            cleaned = self.extract_filename_from_url(name)
            if cleaned:
                names.add(cleaned.lower())
        return names

    def preload_people_index(self, log_path=None):
        cache_path = self._get_people_cache_path(log_path)
        readme_text, _used_cache = self._fetch_people_readme(cache_path)
        self._people_index = self._build_people_index(readme_text)
        self.people_index_available = bool(self._people_index)
        return self._people_index

    def _ensure_people_index(self, log_path=None, available_index=None):
        if available_index is not None:
            self.people_index_available = bool(available_index)
            return available_index
        if self._people_index is not None:
            self.people_index_available = bool(self._people_index)
            return self._people_index
        cache_path = self._get_people_cache_path(log_path)
        readme_text, _used_cache = self._fetch_people_readme(cache_path)
        self._people_index = self._build_people_index(readme_text)
        self.people_index_available = bool(self._people_index)
        return self._people_index

    def _is_blank_log_line(self, line):
        return not line.strip()

    def _is_divider_log_line(self, line):
        stripped = line.strip()
        if not stripped:
            return False
        compact = stripped.replace(" ", "")
        if len(compact) < 8:
            return False
        return len(set(compact)) == 1

    def _is_section_break(self, line):
        return self._is_blank_log_line(line) or self._is_divider_log_line(line)

    def _matches_any_pattern(self, normalized, patterns):
        for pattern in patterns:
            if re.match(pattern, normalized):
                return True
        return False

    def _find_log_section_bounds(self, cleaned_lines, index, max_span=300):
        start = None
        end = None

        min_index = max(0, index - max_span)
        for idx in range(index, min_index - 1, -1):
            normalized = self._normalize_name_line(cleaned_lines[idx])
            if not normalized:
                continue
            if self._matches_any_pattern(normalized, PEOPLE_SECTION_START_STRONG):
                start = idx
                break

        if start is None:
            for idx in range(index, min_index - 1, -1):
                normalized = self._normalize_name_line(cleaned_lines[idx])
                if not normalized:
                    continue
                if self._matches_any_pattern(normalized, PEOPLE_SECTION_START_WEAK):
                    start = idx
                    break

        if start is not None:
            while start > 0 and self._is_divider_log_line(cleaned_lines[start - 1]):
                start -= 1

        max_index = len(cleaned_lines) - 1
        max_end = min(max_index, index + max_span)
        for idx in range(index, max_end + 1):
            normalized = self._normalize_name_line(cleaned_lines[idx])
            if not normalized:
                continue
            if self._matches_any_pattern(normalized, PEOPLE_SECTION_END_PATTERNS):
                end = idx
                break

        if end is not None:
            while end < max_index and self._is_divider_log_line(cleaned_lines[end + 1]):
                end += 1

        if start is None or end is None:
            fallback_start = index
            while fallback_start > 0 and (index - fallback_start) < max_span:
                if self._is_section_break(cleaned_lines[fallback_start - 1]):
                    if self._is_divider_log_line(cleaned_lines[fallback_start - 1]):
                        fallback_start -= 1
                    break
                fallback_start -= 1

            fallback_end = index
            while fallback_end < max_index and (fallback_end - index) < max_span:
                if self._is_section_break(cleaned_lines[fallback_end + 1]):
                    if self._is_divider_log_line(cleaned_lines[fallback_end + 1]):
                        fallback_end += 1
                    break
                fallback_end += 1

            start = fallback_start if start is None else start
            end = fallback_end if end is None else end

        return start, end

    def _normalize_name_line(self, line):
        if not line:
            return ""
        return line.strip().strip("= ").strip()

    def _extract_key_name_from_block(self, cleaned_lines, start, end):
        block = cleaned_lines[start : end + 1]
        for idx, line in enumerate(block):
            if "Validating Method: key_name" in line:
                for offset in range(1, 6):
                    if idx + offset >= len(block):
                        break
                    candidate = block[idx + offset].strip()
                    if not candidate:
                        continue
                    if "Value:" in candidate:
                        value = candidate.split("Value:", 1)[1].strip()
                        if value:
                            return value
                break

        patterns = [
            r"^Validating\s+(.+?)\s+Attributes$",
            r"^Running\s+(.+?)\s+Collection$",
            r"^Finished\s+(.+?)\s+Collection$",
            r"^(.+?)\s+Collection\s+in\s+.+$",
        ]
        for line in block:
            normalized = self._normalize_name_line(line)
            if not normalized:
                continue
            for pattern in patterns:
                match = re.match(pattern, normalized)
                if match:
                    return match.group(1).strip()
        return None

    def _extract_missing_people_names(self, lines, available, name_hint=None):
        names = set()
        for line in lines:
            match = PEOPLE_MISSING_WARNING_RE.search(line)
            if not match:
                continue
            name = name_hint
            if not name:
                url = match.group(1)
                name = self.extract_filename_from_url(url)
            if not name:
                continue
            key = name.lower()
            if available and key in available:
                continue
            names.add(key)
        return names

    def collect_missing_people_lines(self, content, available_index=None, max_block_lines=300, log_path=None):
        if not content:
            return []
        available = self._ensure_people_index(log_path=log_path, available_index=available_index)
        raw_lines = content.splitlines()
        cleaned_lines = self.cleanup_content(content).splitlines()
        items = []
        seen_blocks = set()

        for idx, line in enumerate(raw_lines):
            if not PEOPLE_MISSING_WARNING_RE.search(line):
                continue

            if idx < len(cleaned_lines):
                start, end = self._find_log_section_bounds(cleaned_lines, idx, max_span=max_block_lines)
            else:
                start = max(0, idx - 2)
                end = min(len(raw_lines) - 1, idx + 2)

            block_lines = raw_lines[start : end + 1]
            name_hint = None
            if idx < len(cleaned_lines):
                name_hint = self._extract_key_name_from_block(cleaned_lines, start, end)
            names = self._extract_missing_people_names(block_lines, available, name_hint=name_hint)
            if not names:
                continue

            block_text = "\n".join(block_lines)
            if block_text in seen_blocks:
                continue
            seen_blocks.add(block_text)
            items.append(
                {
                    "names": names,
                    "block": block_text,
                }
            )

        return items

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
        lines = content.splitlines()
        finished_runs = []

        # Iterate through lines to find pairs
        for i in range(len(lines) - 1):
            line = lines[i]
            next_line = lines[i + 1]

            if "Finished " in line and " Run Time: " in next_line:
                # mylogger.info(f"Pair Found L1: {line}")
                # mylogger.info(f"Pair Found L2: {next_line}")
                finished_match = re.search(r".*Finished\s+(.*?)\s*$", line)
                run_time_match = re.search(r".*Run Time:(.*?)\s*$", next_line)

                finished_text = finished_match.group(1).strip() if finished_match else "N/A"
                run_time_text = run_time_match.group(1).strip() if run_time_match else "N/A"
                # mylogger.info(f"finished_text L1: {finished_text}")
                # mylogger.info(f"run_time_text L2: {run_time_text}")

                # Join the pair into one line
                combined_line = f"{finished_text} - {run_time_text}"
                # mylogger.info(f"combined_line: {combined_line}")
                finished_runs.append(combined_line)

            # Check if there's a line with "Finished:" and "Run Time:" at the end
            if "Finished: " in line and " Run Time: " in line:
                finished_match = re.search(r".*Finished:\s+(.*?)\s*$", line)
                run_time_match = re.search(r".*Run Time:(.*?)\s*$", line)

                finished_text = finished_match.group(1).strip() if finished_match else "N/A"
                run_time_text = run_time_match.group(1).strip() if run_time_match else "N/A"
                # Join the pair into one line
                combined_line = f"Finished at:{finished_text} - {run_time_text}"
                # mylogger.info(f"FINAL:combined_line: {combined_line}")
                # Add the line to the result
                finished_runs.append(combined_line)

        return finished_runs

    def _parse_run_time_from_line(self, line):
        if not line:
            return None
        match = re.search(r"Run Time:\s*(\d+):(\d{1,2}):(\d{1,2})", line)
        if not match:
            return None
        try:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
        except ValueError:
            return None
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)

    def extract_last_lines(self, content):
        lines = content.splitlines()

        run_time_index = None
        run_time_is_final = False
        fallback_index = None
        for idx in range(len(lines) - 1, -1, -1):
            line = lines[idx]
            if "Run Time:" not in line:
                continue
            if fallback_index is None:
                fallback_index = idx
            if "Finished:" in line or "Start Time:" in line or (idx > 0 and "Finished " in lines[idx - 1]):
                run_time_index = idx
                run_time_is_final = True
                break

        if run_time_index is None:
            run_time_index = fallback_index

        if run_time_index is None:
            return None

        start_index = max(0, run_time_index - 5)
        extracted_lines = [line.lstrip() for line in lines[start_index:]]
        run_time_line = lines[run_time_index]
        parsed_run_time = self._parse_run_time_from_line(run_time_line)
        if parsed_run_time and run_time_is_final:
            self.run_time = parsed_run_time
            timestamp_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),", run_time_line)
            if timestamp_match:
                self.finished_at = timestamp_match.group(1).strip()
            else:
                finished_match = re.search(r"Finished:\s*(.*?)\s+Run Time:", run_time_line)
                if not finished_match:
                    finished_match = re.search(r"Finished:\s*(.*?)\s*$", run_time_line)
                if finished_match:
                    self.finished_at = finished_match.group(1).strip()
        return "\n".join(extracted_lines)

    def format_contiguous_lines(self, line_numbers):
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

    def make_recommendations(self, content, incomplete_message):
        self.checkfiles_flg = None
        lines = content.splitlines()
        special_check_lines = []
        anidb69_errors = []
        anidb_auth_errors = []
        api_blank_errors = []
        bad_version_found_errors = []
        cache_false = []
        checkFiles = []
        current_year = []
        other_award = []
        convert_errors = []
        corrupt_image_errors = []
        critical_errors = []
        error_errors = []
        warning_errors = []
        delete_unmanaged_collections_errors = []
        flixpatrol_errors = []
        flixpatrol_paywall = []
        git_kometa_errors = []
        pmm_legacy_errors = []
        image_size = []
        incomplete_errors = []
        internal_server_errors = []
        lsio_errors = []
        mal_connection_errors = []
        mass_update_errors = []
        mdblist_attr_errors = []
        mdblist_errors = []
        mdblist_api_limit_errors = []
        metadata_attribute_errors = []
        metadata_load_errors = []
        missing_path_errors = []
        new_version_found_errors = []
        new_plexapi_version_found_errors = []
        no_items_found_errors = []
        omdb_errors = []
        omdb_api_limit_errors = []
        overlays_bloat = []
        overlay_font_missing = []
        overlay_apply_errors = []
        overlay_image_missing = []
        overlay_level_errors = []
        overlay_load_errors = []
        playlist_load_errors = []
        playlist_errors = []
        plex_lib_errors = []
        plex_regex_errors = []
        plex_url_errors = []
        rounding_errors = []
        ruamel_errors = []
        run_order_errors = []
        security_vuln_hits = []
        traceback_errors = []
        tautulli_url_errors = []
        tautulli_apikey_errors = []
        timeout_errors = []
        to_be_configured_errors = []
        tmdb_api_errors = []
        tmdb_fail_errors = []
        trakt_connection_errors = []

        for idx, line in enumerate(lines, start=1):
            if "run_order:" in line:
                next_line = lines[idx] if idx < len(lines) else None
                if next_line and "- operations" not in next_line:
                    run_order_errors.append(idx)
            if "No Anime Found for AniDB ID: 69" in line:
                anidb69_errors.append(idx)
            if re.search(r"\bcache: false\b", line):
                cache_false.append(idx)
            if self.server_versions and ("mass_user_rating_update" in line or "mass_episode_user_ratings_update" in line):

                # Set to keep track of unique (server_name, server_version, idx) combinations
                unique_entries = set()

                # Iterate through each (server_name, server_version) tuple in self.server_versions
                for server_name, server_version in self.server_versions:

                    # Create a unique identifier for the tuple
                    identifier = (server_name, server_version, idx)

                    # Check if the identifier is not in unique_entries (i.e., it's a new entry)
                    if identifier not in unique_entries:
                        # Append server info to rounding_errors
                        rounding_errors.append((server_name, server_version, idx))
                        # Add the identifier to unique_entries set to mark it as processed
                        unique_entries.add(identifier)

            # Detect PMS versions in "Connected to server ..." lines and flag the vulnerable range
            m = re.search(r"Connected to server\s+(.+?)\s+(?:\(?\s*(?:version|Version:)\s+)(\d+\.\d+\.\d+\.\d+(?:-[A-Za-z0-9]+)?)", line)
            if m:
                sn = m.group(1).strip()
                ver = m.group(2).strip()
                if _version_in_inclusive_range(ver, _PMS_VULN_LOW, _PMS_VULN_HIGH):
                    security_vuln_hits.append((sn, ver, idx))

            if "Config Error: anidb sub-attribute" in line or "AniDB Error: Login failed" in line:
                anidb_auth_errors.append(idx)
            elif "apikey is blank" in line:
                api_blank_errors.append(idx)
            elif "1.32.7" in line and "Connected to server " in line:
                bad_version_found_errors.append(idx)
            elif "Convert Warning: No " in line and "ID Found for" in line:
                convert_errors.append(idx)
            elif "PIL.UnidentifiedImageError: cannot" in line:
                corrupt_image_errors.append(idx)
            elif "checkFiles=1" in line:
                checkFiles.append(idx)
            elif "current_year" in line:
                current_year.append(idx)
            elif "other_award" in line:
                other_award.append(idx)
            elif "delete_unmanaged_collections" in line:
                delete_unmanaged_collections_errors.append(idx)
            elif "internal_server_error" in line:
                internal_server_errors.append(idx)
            elif "FlixPatrol Error: " in line and "failed to parse" in line:
                flixpatrol_errors.append(idx)
            elif "flixpatrol" in line and "- pmm:" in line:
                flixpatrol_paywall.append(idx)
            elif "- git: PMM" in line:
                git_kometa_errors.append(idx)
            elif "- pmm: " in line:
                pmm_legacy_errors.append(idx)
            elif ", in _upload_image" in line:
                image_size.append(idx)
            elif "(Linuxserver" in line and "Version:" in line:
                lsio_errors.append(idx)
            elif "My Anime List Connection Failed" in line:
                mal_connection_errors.append(idx)
            elif "Config Error: Operation mass_" in line and "without a successful" in line:
                mass_update_errors.append(idx)
            elif "mdblist_list attribute not allowed with Collection Level: Season" in line:
                mdblist_attr_errors.append(idx)
            elif "MdbList Error: Invalid API key" in line:
                mdblist_errors.append(idx)
            elif "MDBList Error: API Limit Reached" in line or "MDBList Error: API Rate Limit Reached" in line:
                mdblist_api_limit_errors.append(idx)
            elif "metadata attribute is required" in line:
                metadata_attribute_errors.append(idx)
            elif "Metadata File Failed To Load" in line:
                metadata_load_errors.append(idx)
            elif "Overlay File Failed To Load" in line:
                overlay_load_errors.append(idx)
            elif "Playlist File Failed To Load" in line:
                playlist_load_errors.append(idx)
            elif "missing_path" in line or "save_missing" in line:
                missing_path_errors.append(idx)
            elif "Newest Version: " in line:
                new_version_found_errors.append(idx)
            elif "requires an update to:" in line:
                new_plexapi_version_found_errors.append(idx)
            elif "OMDb Error: Invalid API key" in line:
                omdb_errors.append(idx)
            elif "OMDb Error: Request limit reached" in line:
                omdb_api_limit_errors.append(idx)
            elif "Overlay Error: Poster already has an Overlay" in line:
                overlay_apply_errors.append(idx)
            elif "| Overlay Error: Overlay Image not found" in line:
                overlay_image_missing.append(idx)
            elif "overlay_level:" in line:
                overlay_level_errors.append(idx)
            elif "Plex Error: No Items found in Plex" in line:
                no_items_found_errors.append(idx)
            elif "Overlay Error: font:" in line:
                overlay_font_missing.append(idx)
            elif "Reapply Overlays: True" in line or "Reset Overlays: [" in line:
                overlays_bloat.append(idx)
            elif "Playlist Error: Library: " in line and "not defined" in line:
                playlist_errors.append(idx)
            elif "Plex Error: Plex Library " in line and "not found" in line:
                plex_lib_errors.append(idx)
            elif "Plex Error: " in line and "No matches found with regex pattern" in line:
                plex_regex_errors.append(idx)
            elif "Plex Error: Plex url is invalid" in line:
                plex_url_errors.append(idx)
            elif "ruamel.yaml." in line:
                ruamel_errors.append(idx)
            elif "TMDb Error: Invalid API key" in line:
                tmdb_api_errors.append(idx)
            elif "Traceback (most recent call last):" in line:
                traceback_errors.append(idx)
            elif "Tautulli Error: Invalid apikey" in line:
                tautulli_apikey_errors.append(idx)
            elif "Tautulli Error: Invalid URL" in line:
                tautulli_url_errors.append(idx)
            elif "timed out." in line:
                timeout_errors.append(idx)
            elif "Failed to Connect to https://api.themoviedb.org/3" in line:
                tmdb_fail_errors.append(idx)
            elif "Error: " in line and " requires " in line and " to be configured" in line:
                to_be_configured_errors.append(idx)
            elif "Trakt Connection Failed" in line:
                trakt_connection_errors.append(idx)
            elif "[CRITICAL]" in line:
                critical_errors.append(idx)
            elif "[ERROR]" in line:
                error_errors.append(idx)
            elif "[WARNING]" in line:
                warning_errors.append(idx)

        if anidb69_errors:
            url_line = "[https://kometa.wiki/en/latest/config/anidb]"
            formatted_errors = self.format_contiguous_lines(anidb69_errors)
            anidb69_error_message = (
                "❌ **ANIDB69 ERROR**\n"
                "Kometa uses AniDB ID 69 to test that it can connect to AniDB.\n"
                "This error indicates that the test request sent to AniDB failed and AniDB could not be reached.\n"
                f"For more information on configuring AniDB, {url_line}\n"
                f"{len(anidb69_errors)} line(s) with ANIDB69 errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(anidb69_error_message)

        if anidb_auth_errors:
            url_line = "[https://kometa.wiki/en/latest/config/anidb]"
            formatted_errors = self.format_contiguous_lines(anidb_auth_errors)
            anidb_auth_errors_message = (
                "❌ **ANIDB AUTH ERRORS**\n"
                "Kometa uses AniDB settings to connect to AniDB.\n"
                "This error indicates that the setting is not correctly setup in config.yml.\n"
                f"For more information on configuring AniDB, {url_line}\n"
                f"{len(anidb_auth_errors)} line(s) with ANIDB AUTH errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(anidb_auth_errors_message)

        if api_blank_errors:
            url_line = "[https://kometa.wiki/en/latest/config/trakt/?q=api]"
            formatted_errors = self.format_contiguous_lines(api_blank_errors)
            api_blank_error_message = (
                "❌🔒 **BLANK API KEY ERROR**\n"
                "An API key is required for certain services, and it appears to be blank in your configuration.\n"
                "Make sure to provide the required API key to enable proper functionality.\n"
                f"For more information on configuring API keys, {url_line}\n"
                "In the Kometa discord thread, type `!wiki` for more information and search for the service with the missing apikey \n"
                f"{len(api_blank_errors)} line(s) with BLANK API KEY errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(api_blank_error_message)

        if bad_version_found_errors:
            url_line = "[https://forums.plex.tv/t/refresh-endpoint-put-post-requests-started-throwing-404s-in-version-1-32-7-7484/853588]"
            formatted_errors = self.format_contiguous_lines(bad_version_found_errors)
            bad_version_found_errors_message = (
                "💥 **BAD PLEX VERSION ERROR**\n"
                "You are running a version of Plex that is known to have issues with Kometa.\n"
                "You should downgrade/upgrade to a version that is not `1.32.7.*`.\n"
                f"For more information on this issue, {url_line}\n"
                f"{len(bad_version_found_errors)} line(s) with Plex Version 1.32.7.*. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(bad_version_found_errors_message)

        if cache_false:
            url_line = "[https://kometa.wiki/en/latest/config/settings#cache]"
            formatted_errors = self.format_contiguous_lines(cache_false)
            cache_false_message = (
                "💬 **Kometa CACHE**\n"
                "Kometa cache setting is set to false(`cache: false`). Normally, you would want this set to true to improve performance.\n"
                f"For more information on handling this, {url_line}\n"
                f"{len(cache_false)} line(s) with `cache: false`. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(cache_false_message)

        if checkFiles:
            formatted_errors = self.format_contiguous_lines(checkFiles)
            checkFiles_message = (
                "⚠️ **CHECKFILES=1 DETECTED**\n"
                "`checkFiles=1` detected. Notifying Kometa staff.\n"
                f"{len(checkFiles)} line(s) with `checkFiles=1` messages. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(checkFiles_message)

        # if current_year:
        #     url_line = "[https://kometa.wiki/en/latest/files/dynamic_types/?h=latest#imdb-awards]"
        #     formatted_errors = self.format_contiguous_lines(current_year)
        #     current_year_message = (
        #             "⚠️ **LEGACY SCHEMA DETECTED**\n"
        #             "As of 1.20 `current_year` is no longer used and should be replaced with `latest`.\n"
        #             f"For more information on handling these, {url_line}\n"
        #             f"{len(current_year)} line(s) with `current_year` issues. Line number(s): {formatted_errors}"
        #     )
        #     special_check_lines.append(current_year_message)

        if other_award:
            url_line = "[https://kometa.wiki/en/latest/kometa/faqs/?h=other_award#pmm-120-release-changes]"
            formatted_errors = self.format_contiguous_lines(other_award)
            other_award_message = (
                "⚠️ **LEGACY SCHEMA DETECTED**\n"
                "As of 1.20 `other_award` is no longer used and should be removed. All of those awards now have their own individual files.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(other_award)} line(s) with `other_award` issues. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(other_award_message)

        if critical_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Bcritical%5D#critical]"
            formatted_errors = self.format_contiguous_lines(critical_errors)
            critical_error_message = (
                "💥 **[CRITICAL]**\n"
                f"Critical messages found in your attached log.\n"
                f"There is a very strong likelihood that Kometa aborted the run or part of the run early thus not all of what you wanted was applied.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(critical_errors)} line(s) with [CRITICAL] messages. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(critical_error_message)

        if error_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
            formatted_errors = self.format_contiguous_lines(error_errors)
            error_error_message = (
                "❌ **[ERROR]**\n"
                f"Error messages found in your attached log.\n"
                f"There is a very strong likelihood that Kometa did not complete all of what you wanted. Some [ERROR] lines can be ignored.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(error_errors)} line(s) with [ERROR] messages. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(error_error_message)

        if warning_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Bwarning%5D#warning]"
            formatted_errors = self.format_contiguous_lines(warning_errors)
            warning_error_message = (
                f"⚠️ **[WARNING]**\n"
                f"Warning messages found in your attached log.\n"
                f"This is a Kometa warning and usually does not require any immediate action. Most [WARNING] lines can be ignored.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(warning_errors)} line(s) with [WARNING] messages. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(warning_error_message)

        if convert_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/#warning]"
            formatted_errors = self.format_contiguous_lines(convert_errors)
            convert_error_message = (
                "💬 **CONVERT WARNING**\n"
                "Convert Warning: No * ID Found for * ID.\n"
                "These sorts of errors indicate that the thing can't be cross-referenced between sites.  For example:\n\n"
                "Convert Warning: No TVDb ID Found for TMDb ID: 15733\n\n"
                "In the above scenario, the TMDB record for `The Two Mrs. Grenvilles` `ID 15733` didn't contain a TVDB ID. This could be because the record just hasn't been updated, or because `The Two Mrs. Grenvilles` isn't listed on TVDB.\n\n"
                "The fix is for someone `like you, perhaps` to go to the relevant site and fill in the missing data.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(convert_errors)} line(s) with Convert Warnings. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(convert_error_message)

        if corrupt_image_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/#error]"
            formatted_errors = self.format_contiguous_lines(corrupt_image_errors)
            corrupt_image_message = (
                "❌ **CORRUPT FILE ERROR**\n"
                "Likely, when processing overlays, Kometa encountered a file that it could not process because it was corrupt.\n"
                "Review the lines in your log file and based on the lines shown here and determine if those files are ok or not with your favorite image editor.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(corrupt_image_errors)} line(s) with `PIL.UnidentifiedImageError` reported. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(corrupt_image_message)

        if delete_unmanaged_collections_errors:
            url_line = "[https://kometa.wiki/en/latest/config/operations/#delete-collections]"
            formatted_errors = self.format_contiguous_lines(delete_unmanaged_collections_errors)
            delete_unmanaged_collections_errors_message = (
                "⚠️ **LEGACY SCHEMA DETECTED**\n"
                "`delete_unmanaged_collections` is a Library operation and should be adjusted in your config file accordingly.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(delete_unmanaged_collections_errors)} line(s) with `delete_unmanaged_collections` errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(delete_unmanaged_collections_errors_message)

        if flixpatrol_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/faqs/?h=flixpatrol#flixpatrol]"
            formatted_errors = self.format_contiguous_lines(flixpatrol_errors)
            flixpatrol_error_message = (
                "❌ **FLIXPATROL ERROR**\n"
                "There was an issue with FlixPatrol data.\n"
                "This is a known issue with Kometa 1.19.0 (master/latest branch).\n"
                "Switch to the 1.19.1 nightly21 or greater Kometa release for a fix.\n"
                "In the Kometa discord thread, for more information on how to switch branches, type `!branch`.\n"
                f"For more information on handling FlixPatrol errors, {url_line}\n"
                "If the problem persists, your IP address might be banned by FlixPatrol. Contact their support to have it unbanned.\n"
                f"{len(flixpatrol_errors)} line(s) with FlixPatrol errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(flixpatrol_error_message)

        if flixpatrol_paywall:
            url_line = "[https://flixpatrol.com/about/premium/]"
            url_line2 = "[https://discord.com/channels/822460010649878528/1099773891733377065/1214929432754651176]"
            formatted_errors = self.format_contiguous_lines(flixpatrol_paywall)
            flixpatrol_paywall_message = (
                "❌💰 **FLIXPATROL PAYWALL ERROR**\n"
                "FlixPatrol decided to implement a Paywall which causes Kometa to no longer gather data from them.\n"
                "Even if you pay, this will not work with Kometa.\n"
                f"For more information on the FlixPatrol paywall, {url_line}\n"
                f"As of Kometa 1.20.0-nightly34 (you are on {self.current_kometa_version}), we have eliminated FlixPatrol. See this announcement: {url_line2}\n"
                f"{len(flixpatrol_paywall)} line(s) with `- pmm: flixpatrol` detected. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(flixpatrol_paywall_message)

        if git_kometa_errors:
            url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
            formatted_errors = self.format_contiguous_lines(git_kometa_errors)
            git_kometa_error_message = (
                "💬 **OLD Kometa YAML**\n"
                "You are using an old config.yml with references to metadata files that date to a version of Kometa that is pre 1.18\n"
                "In the Kometa discord thread, type `!118` for more information.\n"
                f"For more information on handling this, {url_line}\n"
                f"{len(git_kometa_errors)} line(s) with OLD Kometa YAML. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(git_kometa_error_message)

        if pmm_legacy_errors:
            url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
            formatted_errors = self.format_contiguous_lines(pmm_legacy_errors)
            pmm_legacy_error_message = (
                "💬 **PRE KOMETA YAML**\n"
                "You are using an old config.yml with references to metadata files that date to a version of this script that is pre Kometa\n"
                "In your config.yml, search for `- pmm: ` and replace with `- default: ` .\n"
                f"For more information on handling this, {url_line}\n"
                f"{len(pmm_legacy_errors)} line(s) with PRE Kometa YAML. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(pmm_legacy_error_message)

        if image_size:
            url_line = "[https://www.google.com]"
            formatted_errors = self.format_contiguous_lines(image_size)
            image_size_message = (
                "❌ **IMAGE SIZE ERRORS**\n"
                "It seems that you are attempting to upload or apply artwork and it's greater than the maximum `10MB`.\n"
                f"This usually means that you have internal server errors (500) as well in this log. Change the image to one that is less than 10MB. For more information on handling this, {url_line}\n"
                f"{len(image_size)} line(s) with IMAGE SIZE errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(image_size_message)

        if incomplete_message:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/#providing-log-files-on-discord]"
            incomplete_errors_message = (
                "❌🛠️ **INCOMPLETE LOGS**\n"
                f"{incomplete_message}\n"
                "**The attached file seems incomplete. Without a complete log file troubleshooting is limited as we might be missing valuable information!**\n"
                "Type `!logs` for more information about providing logs."
                f"For more information on providing logs, {url_line}\n"
            )
            special_check_lines.append(incomplete_errors_message)

        if internal_server_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/faqs/?h=errors+issues#errors-issues]"
            formatted_errors = self.format_contiguous_lines(internal_server_errors)
            internal_server_error_message = (
                "💥 **INTERNAL SERVER ERROR**\n"
                "An internal server error has occurred. This could be due to an issue with the service's server.\n"
                "In the Kometa discord thread, type `!500` for more information.\n"
                f"For more information on handling internal server errors, {url_line}\n"
                f"{len(internal_server_errors)} line(s) with INTERNAL SERVER errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(internal_server_error_message)

        if lsio_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/install/images/?h=linuxserver#linuxserver]"
            formatted_errors = self.format_contiguous_lines(lsio_errors)
            lsio_error_message = (
                "⚠️🖥️ **LINUXSERVER IMAGE DETECTED**\n"
                "You are not using the official Kometa container image.\n"
                "In the Kometa discord thread, type `!lsio` for more information.\n"
                f"For more information on this, {url_line}\n"
                f"{len(lsio_errors)} line(s) with LINUXSERVER IMAGE issues. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(lsio_error_message)

        if mal_connection_errors:
            url_line = "[https://kometa.wiki/en/latest/config/myanimelist]"
            formatted_errors = self.format_contiguous_lines(mal_connection_errors)
            mal_connection_error_message = (
                "❌ **MY ANIME LIST CONNECTION ERROR**\n"
                "There was an issue connecting to My Anime List (MAL) service.\n"
                "This will affect any functionality that relies on MAL data.\n"
                "In the Kometa discord thread, type `!mal` for more information\n"
                f"For more information on configuring the My Anime List (MAL) service, {url_line}\n"
                f"{len(mal_connection_errors)} line(s) with MY ANIME LIST CONNECTION errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(mal_connection_error_message)

        if mass_update_errors:
            url_line = "[https://kometa.wiki/en/latest/config/operations]"
            formatted_errors = self.format_contiguous_lines(mass_update_errors)
            mass_update_errors_message = (
                "❌ **MASS_*_UPDATE ERROR**\n"
                "You have specified a `mass_*_update` operation in your config file however you have not configured the corresponding service so this will never work.\n"
                "Review each of the lines mentioned in this message to understand what all the config issues are.\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on `mass_*_update` operations, {url_line}\n"
                f"{len(mass_update_errors)} line(s) with `mass_*_update` config errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(mass_update_errors_message)

        if mdblist_attr_errors:
            url_line = "[https://kometa.wiki/en/latest/files/builders/mdblist/?h=mdblist+builders]"
            formatted_errors = self.format_contiguous_lines(mdblist_attr_errors)
            mdblist_attr_error_message = (
                f"❌ **MDBLIST ATTRIBUTE ERROR**\n"
                f"MDBList functionality does not currently support season-level collections.\n"
                f"In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on MDBList configuration, {url_line}\n"
                f"{len(mdblist_attr_errors)} line(s) with MDBList attribute errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(mdblist_attr_error_message)

        if mdblist_errors:
            url_line = "[https://kometa.wiki/en/latest/config/mdblist/?h=mdblist+attributes#mdblist-attributes]"
            formatted_errors = self.format_contiguous_lines(mdblist_errors)
            mdblist_error_message = (
                f"❌ **MDBLIST ERROR**\n"
                f"Your configuration contains an invalid API key for MdbList.\n"
                f"This will cause any services that rely on MdbList to fail.\n"
                f"In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on configuring MdbList, {url_line}\n"
                f"{len(mdblist_errors)} line(s) with MDBLIST errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(mdblist_error_message)

        if mdblist_api_limit_errors:
            url_line = "[https://kometa.wiki/en/latest/config/mdblist/?h=mdblist+attributes#mdblist-attributes]"
            formatted_errors = self.format_contiguous_lines(mdblist_api_limit_errors)
            mdblist_api_limit_error_message = (
                f"❌ **MDBLIST API LIMIT ERROR**\n"
                f"You have hit the MDBLIST API LIMIT. The free apikey is limited to 1000 requests per day so if you hit your limit Kometa should be able to pick up where it left off the next day as long as the Kometa cache setting is enabled in yur config.yml file.\n"
                f"This will cause any metadata updates that rely on MdbList to fail until the limit is reset (usually daily).\n"
                f"For more information on configuring MdbList, {url_line}\n"
                f"{len(mdblist_api_limit_errors)} line(s) with MDBLIST API Limit errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(mdblist_api_limit_error_message)

        if metadata_attribute_errors:
            url_line = "[https://kometa.wiki/en/latest/config/files/#example]"
            formatted_errors = self.format_contiguous_lines(metadata_attribute_errors)
            metadata_attribute_errors_message = (
                f"❌ **METADATA ATTRIBUTE ERRORS**\n"
                f"If you are using Kometa nightly48 or newer, this is expected behaviour.\n"
                f"`metadata_path` and `overlay_path` are now legacy attributes, and using them will cause the `YAML Error: metadata attribute is required` error.\n"
                f"The error can be ignored as it won't cause any issues, or you can update your config.yml to use the new `collection_files`, `overlay_files` and `metadata_files` attributes.\n\n"
                f"The steps to take are:\n"
                f":one: - Look at every file referred to within your config.yml and see what the first level indentation yaml file attributes are. They should be one of these(`collections:, dynamic_collections:, overlays:, metadata:, playlists:, templates:, external_templates:`) and can contain more than 1. For now, ignore the `templates:` and `external_templates:` attributes.\n"
                f":two: - if it's `metadata:`, file it under the `metadata_file:` section of your config.yml\n"
                f":three: - if it's `collections:` or `dynamic_collections:`, file it under the `collection_files:` section of your config.yml\n"
                f":four: - if it's `playlists:`,  file it under the `playlist_files:` section of your config.yml\n"
                f":five: - if it's `overlays:`,  file it under the `overlay_files:` section of your config.yml\n\n"
                f"`*NOTE:` If you only see `templates:` or `external_templates:`, this is a special case and you typically would not be referring to it directly in your config.yml file.\n\n"
                f"Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
                f"For more information on this, {url_line}\n"
                f"{len(metadata_attribute_errors)} line(s) with METADATA ATTRIBUTE errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(metadata_attribute_errors_message)

        if metadata_load_errors:
            url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
            formatted_errors = self.format_contiguous_lines(metadata_load_errors)
            metadata_load_errors_message = (
                f"❌ **METADATA LOAD ERRORS**\n"
                f"Kometa is trying to load a file from your config file.\n"
                f"This error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\n"
                f"Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
                f"For more information on this, {url_line}\n"
                f"{len(metadata_load_errors)} line(s) with METADATA LOAD errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(metadata_load_errors_message)

        if overlay_load_errors:
            url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
            formatted_errors = self.format_contiguous_lines(overlay_load_errors)
            overlay_load_errors_message = (
                "❌ **OVERLAY LOAD ERRORS**\n"
                "Kometa is trying to load a file from your config file.\n"
                "This error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\n"
                "Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
                f"For more information on this, {url_line}\n"
                f"{len(overlay_load_errors)} line(s) with OVERLAY LOAD errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(overlay_load_errors_message)

        if playlist_load_errors:
            url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
            formatted_errors = self.format_contiguous_lines(playlist_load_errors)
            playlist_load_errors_message = (
                "❌ **PLAYLIST LOAD ERRORS**\n"
                "Kometa is trying to load a file from your config file.\n"
                "This error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\n"
                "Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
                f"For more information on this, {url_line}\n"
                f"{len(playlist_load_errors)} line(s) with PLAYLIST LOAD errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(playlist_load_errors_message)

        if missing_path_errors:
            url_line = "[https://kometa.wiki/en/latest/config/libraries/?h=report_path#attributes]"
            formatted_errors = self.format_contiguous_lines(missing_path_errors)
            missing_path_errors_message = (
                "⚠️ **LEGACY SCHEMA DETECTED**\n"
                "`missing_path` or `save_missing` is no longer used and should be replaced/removed. Use `report_path` instead.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(missing_path_errors)} line(s) with `missing_path` or `save_missing` errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(missing_path_errors_message)

        if new_plexapi_version_found_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/#checking-kometa-version]"
            formatted_errors = self.format_contiguous_lines(new_plexapi_version_found_errors)
            new_plexapi_version_found_errors_message = (
                "🚀 **PYTHON MODULE UPDATE NEEDED**\n"
                # f"PlexAPI: {self.current_plexapi_version}\n\n"
                "In the Kometa discord thread, type `!update` for instructions on how to update your requirements.\n"
                f"For more information on updating, {url_line}\n"
                f"{len(new_plexapi_version_found_errors)} line(s) with New Python Module Updates. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(new_plexapi_version_found_errors_message)

        if new_version_found_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/#checking-kometa-version]"
            formatted_errors = self.format_contiguous_lines(new_version_found_errors)
            new_version_found_errors_message = (
                "🚀 **VERSION UPDATE AVAILABLE**\n"
                f"**Current Version:** {self.current_kometa_version}\n"
                f"**Newest Version (at the time of this log):** {self.kometa_newest_version}\n\n"
                "In the Kometa discord thread, type `!update` for instructions on how to update.\n"
                f"For more information on updating, {url_line}\n"
                f"{len(new_version_found_errors)} line(s) with New Version errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(new_version_found_errors_message)

        if no_items_found_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
            formatted_errors = self.format_contiguous_lines(no_items_found_errors)
            no_items_error_message = (
                "⚠️ **NO ITEMS FOUND IN PLEX**\n"
                "The criteria defined by a search/filter returned 0 results.\n"
                "This is often expected - for example, if you try to apply a 1080P overlay to a 4K library then no items will get the overlay since no items have a 1080P resolution.\n"
                "It is worth noting that search and filters are case-sensitive, so `1080P` and `1080p` are treated as two separate things.\n"
                f"For more information on this error, {url_line}\n"
                f"{len(no_items_found_errors)} line(s) with 'No Items found in Plex' errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(no_items_error_message)

        if omdb_errors:
            url_line = "[https://kometa.wiki/en/latest/config/omdb/#omdb-attributes]"
            formatted_errors = self.format_contiguous_lines(omdb_errors)
            omdb_error_message = (
                "❌ **OMDB ERROR**\n"
                "Your configuration contains an invalid API key for OMDb.\n"
                "This will cause any services that rely on OMDb to fail.\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on configuring OMDb, {url_line}\n"
                f"{len(omdb_errors)} line(s) with OMDb errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(omdb_error_message)

        if omdb_api_limit_errors:
            url_line = "[https://kometa.wiki/en/latest/config/omdb/?h=omdb#omdb-attributes]"
            formatted_errors = self.format_contiguous_lines(omdb_api_limit_errors)
            omdb_api_limit_error_message = (
                f"❌ **OMDB API LIMIT ERROR**\n"
                f"You have hit the OMDB API LIMIT. The free apikey is limited to 1000 requests per day so if you hit your limit Kometa should be able to pick up where it left off the next day as long as the Kometa cache setting is enabled in yur config.yml file.\n"
                f"This will cause any metadata updates that rely on OMDB to fail until the limit is reset (usually daily).\n"
                f"For more information on configuring OMDB, {url_line}\n"
                f"{len(omdb_api_limit_errors)} line(s) with OMDB API Limit errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(omdb_api_limit_error_message)

        if overlay_font_missing:
            url_line = "[https://kometa.wiki/en/latest/showcase/overlays/?h=font#example-2]"
            formatted_errors = self.format_contiguous_lines(overlay_font_missing)
            overlay_font_missing_message = (
                "❌ **OVERLAY FONT MISSING**\n"
                "We detected that you are referencing a font that Kometa cannot find.\n"
                "This can lead to overlays not being applied when a font is required.\n"
                f"In the Kometa discord thread, type `!wiki` for more information or follow this link: {url_line}\n"
                f"{len(overlay_font_missing)} line(s) with `Overlay Error: font:` errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(overlay_font_missing_message)

        if overlays_bloat:
            url_line = "[https://kometa.wiki/en/latest/kometa/scripts/imagemaid]"
            formatted_errors = self.format_contiguous_lines(overlays_bloat)
            overlays_bloat_message = (
                "⚠️ **REAPPLY / RESET OVERLAYS**\n\n"
                "We detected that you are using either reapply_overlays OR reset_overlays within your config.\n\n"
                "**You should NOT be using reapply_overlays unless you have a specific reason to. If you are not sure do NOT enable it.**\n\n"
                "This can lead to your system creating additional posters within Plex causing bloat\n\n"
                "Typically these config lines are only used for very specific cases so if this is your case, then you can ignore this recommendation\n\n"
                f"In the Kometa discord thread, type `!bloat` for more information or follow this link: {url_line}\n\n"
                f"{len(overlays_bloat)} line(s) with reapply_overlays or reset_overlays. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(overlays_bloat_message)

        if overlay_apply_errors:
            url_line = "[https://kometa.wiki/en/latest/defaults/overlays]"
            url_line2 = "[https://kometa.wiki/en/latest/kometa/guides/assets]"
            formatted_errors = self.format_contiguous_lines(overlay_apply_errors)
            overlay_apply_errors_message = (
                "⚠️ **OVERLAY APPLY ERROR**\n"
                "Kometa attempts to apply an overlay to things, but finds that the art on the item is already an overlaid poster from Kometa with an EXIF tag:\n"
                "```Abraham Season 1\n  Overlay Error: Poster already has an Overlay\nArchie Bunker''s Place S03E14\n  Overlay Error: Poster already has an Overlay\nAs Time Goes By Season 10\n  Overlay Error: Poster already has an Overlay\nCHiPs Season 3\n  Overlay Error: Poster already has an Overlay```\n\n"
                "For `Season` posters, this is often because Plex has assigned higher-level art [like the show poster to a season that has no art of its own].\n"
                "For `Movies`, `Show`, and `Episode` posters, this is often because an art item was selected or part of the assets pipeline that already had an overlay image on it.\n\n"
                "You can fix this by going to each item in Plex, hitting the pencil icon, selecting Poster, and choosing art that does not have an overlay.\n"
                "Alternatively if you are using the asset pipeline in Kometa, updating your asset pipeline with the art that does not have an overlay.\n"
                "In the Kometa discord thread, type `!overlaylabel` for more information.\n\n"
                f"For more information on overlays, {url_line}\n"
                f"For more information on the asset pipeline, {url_line2}\n"
                f"{len(overlay_apply_errors)} line(s) with OVERLAY APPLY errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(overlay_apply_errors_message)

        if overlay_image_missing:
            url_line = "[https://kometa.wiki/en/latest/defaults/overlays]"
            formatted_errors = self.format_contiguous_lines(overlay_image_missing)
            overlay_image_missing_message = (
                "❌ **OVERLAY IMAGE MISSING ERROR**\n"
                "Kometa attempts to apply an overlay to things, but finds that the overlay itself is not found and thus cannot be applied to the art.\n"
                "Validate the path and also ensure that the case of the file(i.e. `4K.png` is NOT the same as `4k.png`) is the same as found in the line within the log.\n"
                f"For more information on overlays, {url_line}\n"
                f"{len(overlay_image_missing)} line(s) with OVERLAY IMAGE MISSING errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(overlay_image_missing_message)

        if overlay_level_errors:
            url_line = "[https://kometa.wiki/en/latest/files/settings/?h=builder_level]"
            formatted_errors = self.format_contiguous_lines(overlay_level_errors)
            overlay_level_errors_message = (
                "⚠️ **LEGACY SCHEMA DETECTED**\n"
                "`overlay_level:` is no longer used and should be replaced by `builder_level:`.\n"
                f"For more information on handling these, {url_line}\n"
                f"{len(overlay_level_errors)} line(s) with `overlay_level` errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(overlay_level_errors_message)

        if playlist_errors:
            url_line = "[https://kometa.wiki/en/latest/defaults/playlist/?h=playlist]"
            formatted_errors = self.format_contiguous_lines(playlist_errors)
            playlist_error_message = (
                "❌ **PLAYLIST ERROR**\n"
                "A playlist is trying to use a library that does not exist in Plex.\n"
                "Ensure that all libraries being defined actually exist.\n"
                "The Kometa Defaults `playlist` file expects libraries called `Movies` and `TV Shows`, template variables can be used to change this.\n"
                f"For more information: {url_line}\n"
                f"{len(playlist_errors)} line(s) with playlist errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(playlist_error_message)

        # Extract scheduled run time
        kometa_scheduled_time = self.extract_scheduled_run_time(content)
        maintenance_start_time, maintenance_end_time = self.extract_maintenance_times(content)
        kometa_time_recommendation = None
        if isinstance(self.run_time, timedelta):
            kometa_time_recommendation = self.calculate_recommendation(
                kometa_scheduled_time,
                maintenance_start_time,
                maintenance_end_time,
            )
        if kometa_time_recommendation:
            special_check_lines.append(kometa_time_recommendation)

        # Extract Memory value:
        kometa_mem_recommendation = self.calculate_memory_recommendation(content)
        if kometa_mem_recommendation:
            special_check_lines.append(kometa_mem_recommendation)

        # Extract DB Cache value:
        kometa_db_cache_recommendation = self.make_db_cache_recommendations(content)
        if kometa_db_cache_recommendation:
            special_check_lines.append(kometa_db_cache_recommendation)

        # Extract WSL information
        wsl_recommendation = self.detect_wsl_and_recommendation(content)
        if wsl_recommendation:
            special_check_lines.append(wsl_recommendation)

        if plex_regex_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
            formatted_errors = self.format_contiguous_lines(plex_regex_errors)
            plex_regex_error_message = (
                "⚠️ **PLEX REGEX ERROR**\n"
                "Kometa is trying to perform a regex search, and 0 items match the regex pattern.\n"
                "This is often an expected error and can be ignored in most cases.\n"
                "If you need assistance with this error, raise a support thread in `#kometa-help`.\n"
                f"For more information on handling regex issues, {url_line}\n"
                f"{len(plex_regex_errors)} line(s) with Plex regex errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(plex_regex_error_message)

        if plex_lib_errors:
            url_line = "[https://kometa.wiki/en/latest/config/settings/?h=show_options#show-options]"
            formatted_errors = self.format_contiguous_lines(plex_lib_errors)
            plex_lib_error_message = (
                "❌ **PLEX LIBRARY ERROR**\n"
                "Your configuration contains an invalid Plex Library Name.\n"
                "Kometa will not be able to update a library that does not exist.\n"
                "Check for spelling `case sensitive` and ensure that you have `show_options: true` within your settings within config.yml\n"
                f"For more information on configuring the show_options, {url_line}\n"
                f"{len(plex_lib_errors)} line(s) with PLEX LIBRARY errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(plex_lib_error_message)

        if plex_url_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/#getting-a-plex-url-and-token]"
            formatted_errors = self.format_contiguous_lines(plex_url_errors)
            plex_url_error_message = (
                "❌ **PLEX URL ERROR**\n"
                "Your configuration contains an invalid Plex URL.\n"
                "This will cause any services that rely on this URL to fail.\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on configuring the Plex URL, {url_line}\n"
                f"{len(plex_url_errors)} line(s) with PLEX URL errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(plex_url_error_message)

        if rounding_errors:
            url_line = "[https://forums.plex.tv/t/plex-rounding-down-user-ratings-when-set-via-api/875806/8]"

            # Construct the message with server names and versions
            rounding_errors_message = (
                "⚠️ **USER RATINGS ROUNDING ISSUE**\n"
                "We have detected that you are running `mass_user_rating_update` or `mass_episode_user_ratings_update` with Plex versions that will cause rounding issues with user ratings. To avoid this, downgrade your Plex Media server to `1.40.0.7998` or upgrade it to `1.40.3.8555` or later.\n"
                f"For more information on this issue, {url_line}\n"
                f"Detected issues on the following servers:\n"
            )
            # Append server names, versions, and line numbers to the message
            for server_name, server_version, line_num in rounding_errors:
                rounding_errors_message += f"- Server: {server_name}, Version: {server_version}, Line: {line_num}\n"

            special_check_lines.append(rounding_errors_message)

        if ruamel_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/yaml/]"
            formatted_errors = self.format_contiguous_lines(ruamel_errors)
            ruamel_error_message = (
                "💥 **YAML ERROR**\n"
                "YAML is very sensitive with regards to spaces and indentation.\n"
                "Search for `ruamel.yaml.` in your log file to get hints as to where the problem lies.\n"
                "In the Kometa discord thread, type `!yaml` and `!editors` for more information.\n"
                f"For more information on handling YAML issues, {url_line}\n"
                f"{len(ruamel_errors)} line(s) with YAML errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(ruamel_error_message)

        if run_order_errors:
            url_line = "[https://kometa.wiki/en/latest/config/settings/?h=run_order#run-order]"
            formatted_errors = self.format_contiguous_lines(run_order_errors)
            run_order_error_message = (
                "⚠️ **RUN_ORDER WARNING**\n"
                f"Typically, and in almost EVERY situation, you want ` - operations` to precede both metadata and overlays processing. To fix this, place `- operations` first in the `run_order` section of the config.yml file\n"
                f"For more information on this, {url_line}\n"
                f"{len(run_order_errors)} line(s) with RUN_ORDER warnings. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(run_order_error_message)

        if security_vuln_hits:
            seen = set()
            items = []
            for sn, ver, ln in security_vuln_hits:
                key = (sn, ver, ln)
                if key not in seen:
                    seen.add(key)
                    items.append((sn, ver, ln))

            vuln_low_str = ".".join(map(str, _PMS_VULN_LOW))
            vuln_high_str = ".".join(map(str, _PMS_VULN_HIGH))
            url_line = "[https://forums.plex.tv/t/plex-media-server-security-update/928341]"

            msg = (
                "🚀 **PMS SECURITY ALERT**\n"
                "A Plex Media Server version in a **known vulnerable range** was detected.\n"
                f"**Affected range:** `{vuln_low_str}` **through** `{vuln_high_str}`\n"
                "Please **upgrade Plex Media Server** to a safe release as soon as possible.\n"
                "Until then, Plex will block access from others reaching your server.\n"
                "UPGRADE IMMEDIATELY!\n"
                f"For more information on this see url: {url_line}\n"
                f"{len(security_vuln_hits)} line(s) with these errors."
                "Detected on:\n"
            )
            for sn, ver, ln in items:
                msg += f"- Server: {sn}, Version: `{ver}`, Line: {ln}\n"

            special_check_lines.append(msg)

        if traceback_errors:
            url_line = "[https://kometa.wiki/en/latest/config/tautulli]"
            formatted_errors = self.format_contiguous_lines(traceback_errors)
            traceback_errors_message = (
                "💥 **TRACEBACK ERROR**\n"
                "Your KOMETA run contains traceback errors.\n"
                "This likely means that the run ended prematurely or did not complete certain tasks (i.e. overlays ended early or did not apply).\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"{len(traceback_errors)} line(s) with Traceback errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(traceback_errors_message)

        if tautulli_apikey_errors:
            url_line = "[https://kometa.wiki/en/latest/config/tautulli]"
            formatted_errors = self.format_contiguous_lines(tautulli_apikey_errors)
            tautulli_apikey_errors_message = (
                "❌ **TAUTULLI API ERROR**\n"
                "Your configuration contains an invalid API key for Tautulli.\n"
                "This will cause any services that rely on Tautulli to fail.\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on configuring Tautulli, {url_line}\n"
                f"{len(tautulli_apikey_errors)} line(s) with Tautulli errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(tautulli_apikey_errors_message)

        if tautulli_url_errors:
            url_line = "[https://kometa.wiki/en/latest/config/tautulli#tautulli-attributes]"
            formatted_errors = self.format_contiguous_lines(tautulli_url_errors)
            tautulli_url_error_message = (
                "❌ **TAUTULLI URL ERROR**\n"
                "Your configuration contains an invalid Tautulli URL.\n"
                "This will cause any services that rely on this URL to fail.\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on configuring the Tautulli URL, {url_line}\n"
                f"{len(tautulli_url_errors)} line(s) with TAUTULLI URL errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(tautulli_url_error_message)

        if tmdb_api_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/#getting-a-tmdb-api-key]"
            formatted_errors = self.format_contiguous_lines(tmdb_api_errors)
            tmdb_api_errors_message = (
                "❌ **TMDB API ERROR**\n"
                "Your configuration contains an invalid API key for TMDb.\n"
                "This will cause any services that rely on TMDb to fail.\n"
                "In the Kometa discord thread, type `!wiki` for more information and search.\n"
                f"For more information on configuring TMDb, {url_line}\n"
                f"{len(tmdb_api_errors)} line(s) with TMDb errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(tmdb_api_errors_message)

        if timeout_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/install/overview/]"
            formatted_errors = self.format_contiguous_lines(timeout_errors)
            timeout_error_message = (
                "❌⏱️ **TIMEOUT ERROR**\n"
                "There were timeout issues while trying to connect to different services.\n"
                "Ensure that your network configuration allows Kometa to make internet calls.\n"
                f"Typically this is your Plex server timing out when Kometa tries to connect to it. There's nothing Kometa can do about this directly. Currently your timeout for plex is set to: `{self.plex_timeout}` seconds. You can try increasing the connection timeout in `config.yml`:\n"
                "```plex:\n  url: http://bing.bang.boing\n  token: REDACTED\n  timeout: 360   <<< right here```\n"
                "But that's not a guarantee.\n\nEffectively what's happening here is that you're ringing the doorbell and no one's answering. You can't do anything about that aside from waiting longer. You can't ring the doorbell differently.\n\n"
                "This seems to happen most often in an Appbox context, so perhaps contact your appbox provider to discuss it.\n\n"
                "In the Kometa discord thread, type `!timeout` for more information.\n"
                f"For more information on network configuration, {url_line}\n"
                f"{len(timeout_errors)} line(s) with timeout errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(timeout_error_message)

        if tmdb_fail_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/]"
            formatted_errors = self.format_contiguous_lines(tmdb_fail_errors)
            tmdb_fail_error_message = (
                "❌ **TMDB ERROR**\n"
                "This error appears when your host machine is unable to connect to TMDb.\n"
                "Ensure that your networking (particularly docker container) is configured to allow Kometa to make internet calls.\n"
                f"For more information on network configuration, {url_line}\n"
                f"{len(tmdb_fail_errors)} line(s) with TMDB errors. Line number location. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(tmdb_fail_error_message)

        if to_be_configured_errors:
            url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
            formatted_errors = self.format_contiguous_lines(to_be_configured_errors)
            to_be_configured_errors_message = (
                "❌ **TO BE CONFIGURED ERROR**\n"
                "You are using a builder that has not been configured yet.\n"
                "This will affect any functionality that relies on these connections. Review all lines below and resolve.\n"
                "In the Kometa discord thread, type `!wiki` and search for more information\n"
                f"For more information on configuring services, {url_line}\n"
                f"{len(to_be_configured_errors)} line(s) with `to be configured` errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(to_be_configured_errors_message)

        if trakt_connection_errors:
            url_line = "[https://kometa.wiki/en/latest/config/trakt/#trakt-attributes]"
            formatted_errors = self.format_contiguous_lines(trakt_connection_errors)
            trakt_connection_error_message = (
                "❌ **TRAKT CONNECTION ERROR**\n"
                "There was an issue connecting to the Trakt service.\n"
                "This will affect any functionality that relies on Trakt data.\n"
                "In the Kometa discord thread, type `!trakt` for more information\n"
                f"For more information on configuring the Trakt service, {url_line}\n"
                f"{len(trakt_connection_errors)} line(s) with TRAKT CONNECTION errors. Line number(s): {formatted_errors}"
            )
            special_check_lines.append(trakt_connection_error_message)

        if checkFiles:
            self.checkfiles_flg = 1

        # Initialize a list to store both the first line and full recommendation message
        recommendation_messages = []

        for idx, message in enumerate(special_check_lines, start=1):
            # Split the message into lines and log the first line with a label
            lines = message.split("\n")
            first_line = lines[0] if lines else ""
            mylogger.info(f"Kometa Recommendation {idx}: {first_line}")

            # Append both the first line and the full recommendation message to the list
            recommendation_messages.append({"first_line": first_line, "message": message})

        issue_counts = {
            "service_connectivity": (
                len(tmdb_api_errors)
                + len(tmdb_fail_errors)
                + len(trakt_connection_errors)
                + len(omdb_errors)
                + len(omdb_api_limit_errors)
                + len(mdblist_errors)
                + len(mdblist_api_limit_errors)
                + len(mdblist_attr_errors)
                + len(mal_connection_errors)
                + len(tautulli_url_errors)
                + len(tautulli_apikey_errors)
                + len(flixpatrol_errors)
                + len(flixpatrol_paywall)
                + len(lsio_errors)
            ),
            "config_setup": (
                len(to_be_configured_errors)
                + len(api_blank_errors)
                + len(bad_version_found_errors)
                + len(missing_path_errors)
                + len(cache_false)
                + len(mass_update_errors)
                + len(other_award)
                + len(delete_unmanaged_collections_errors)
            ),
            "plex_issues": len(plex_url_errors) + len(plex_regex_errors) + len(plex_lib_errors) + len(rounding_errors),
            "metadata_overlay_playlist": (
                len(metadata_attribute_errors)
                + len(metadata_load_errors)
                + len(overlay_load_errors)
                + len(overlay_apply_errors)
                + len(overlay_level_errors)
                + len(overlay_font_missing)
                + len(overlay_image_missing)
                + len(playlist_load_errors)
                + len(playlist_errors)
                + len(overlays_bloat)
            ),
            "convert_issues": len(convert_errors),
            "image_issues": len(corrupt_image_errors) + len(image_size),
            "runtime_behavior": len(run_order_errors) + len(checkFiles) + len(timeout_errors),
            "update_version": len(new_version_found_errors) + len(new_plexapi_version_found_errors) + len(git_kometa_errors),
            "platform_system": (
                (1 if wsl_recommendation else 0) + (1 if kometa_time_recommendation else 0) + (1 if kometa_mem_recommendation else 0) + (1 if kometa_db_cache_recommendation else 0)
            ),
            "anidb_issues": len(anidb69_errors) + len(anidb_auth_errors),
            "misc": len(internal_server_errors) + len(no_items_found_errors) + len(pmm_legacy_errors),
            "tmdb_api_errors": len(tmdb_api_errors),
            "tmdb_fail_errors": len(tmdb_fail_errors),
            "trakt_connection_errors": len(trakt_connection_errors),
            "omdb_errors": len(omdb_errors),
            "omdb_api_limit_errors": len(omdb_api_limit_errors),
            "mdblist_errors": len(mdblist_errors),
            "mdblist_api_limit_errors": len(mdblist_api_limit_errors),
            "mdblist_attr_errors": len(mdblist_attr_errors),
            "mal_connection_errors": len(mal_connection_errors),
            "tautulli_url_errors": len(tautulli_url_errors),
            "tautulli_apikey_errors": len(tautulli_apikey_errors),
            "flixpatrol_errors": len(flixpatrol_errors),
            "flixpatrol_paywall": len(flixpatrol_paywall),
            "lsio_errors": len(lsio_errors),
            "config_to_be_configured": len(to_be_configured_errors),
            "config_api_blank": len(api_blank_errors),
            "config_bad_version": len(bad_version_found_errors),
            "config_missing_path": len(missing_path_errors),
            "config_cache_false": len(cache_false),
            "config_mass_update": len(mass_update_errors),
            "config_other_award": len(other_award),
            "config_delete_unmanaged": len(delete_unmanaged_collections_errors),
            "plex_url_errors": len(plex_url_errors),
            "plex_regex_errors": len(plex_regex_errors),
            "plex_library_errors": len(plex_lib_errors),
            "plex_rounding_errors": len(rounding_errors),
            "metadata_attribute_errors": len(metadata_attribute_errors),
            "metadata_load_errors": len(metadata_load_errors),
            "overlay_load_errors": len(overlay_load_errors),
            "overlay_apply_errors": len(overlay_apply_errors),
            "overlay_level_errors": len(overlay_level_errors),
            "overlay_font_missing": len(overlay_font_missing),
            "overlay_image_missing": len(overlay_image_missing),
            "playlist_load_errors": len(playlist_load_errors),
            "playlist_errors": len(playlist_errors),
            "overlays_bloat": len(overlays_bloat),
            "image_corrupt": len(corrupt_image_errors),
            "image_size": len(image_size),
            "runtime_run_order": len(run_order_errors),
            "runtime_checkfiles": len(checkFiles),
            "runtime_timeout": len(timeout_errors),
            "update_kometa": len(new_version_found_errors),
            "update_plexapi": len(new_plexapi_version_found_errors),
            "update_git": len(git_kometa_errors),
            "platform_wsl": 1 if wsl_recommendation else 0,
            "platform_kometa_time": 1 if kometa_time_recommendation else 0,
            "platform_memory": 1 if kometa_mem_recommendation else 0,
            "platform_db_cache": 1 if kometa_db_cache_recommendation else 0,
            "anidb_69": len(anidb69_errors),
            "anidb_auth": len(anidb_auth_errors),
            "misc_internal_server": len(internal_server_errors),
            "misc_no_items": len(no_items_found_errors),
            "misc_pmm_legacy": len(pmm_legacy_errors),
        }

        return recommendation_messages, issue_counts

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

        # Print or log the sorted recommendations for debugging
        # mylogger.info("Sorted Recommendations:")
        for rec in sorted_recommendations:
            mylogger.info(rec.get("first_line", "No first line available"))

        return sorted_recommendations

    def extract_plex_config(self, content):
        """
        Extract Plex configuration sections from the content.
        """
        lines = content.splitlines()
        plex_config_content = []

        start_marker = "Plex Configuration"
        # end_markers = [" Scanning Metadata and", "Library Connection Failed"]
        end_markers = [" Scanning ", "Library Connection Failed"]
        mylogger.info(f"extract_plex_config")

        i = 0
        while i < len(lines):
            line = lines[i]
            if start_marker in line:
                config_section = self.extract_plex_config_section(lines, i + 1, end_markers)
                if config_section:
                    # Call parse_server_info
                    server_info, all_lines = self.parse_server_info(config_section)
                    plex_config_content.append(config_section)

                    # Store the extracted server info in a variable
                    if server_info:
                        my_server_name = server_info["server_name"]
                        my_server_version = server_info["version"]

                        stable_version = "1.40.0.7998-c29d4c0c8"
                        good_version = "1.40.3.8555-fef15d30c"

                        if stable_version < my_server_version < good_version:
                            mylogger.info(
                                f"Server Name: {my_server_name} has Version: {my_server_version}. Potential Rounding Issue because > {stable_version} and < {good_version}"
                            )
                            # Store the server version globally in a list
                            self.server_versions.append((my_server_name, my_server_version))
                        elif my_server_version >= good_version:
                            mylogger.info(f"Server Name: {my_server_name} has Version: {my_server_version}. ALL GOOD")
                        else:
                            mylogger.info(f"Server Name: {my_server_name} has Version: {my_server_version}. ALL GOOD")

            i += 1

        if plex_config_content:
            return plex_config_content  # Return the list of extracted server info
        else:
            return None

    def extract_plex_config_section(self, lines, start_index, end_markers):
        """
        Extract a Plex configuration section starting from a specific index.
        """
        config_section = []

        for i in range(start_index, len(lines)):
            line = lines[i].strip()
            if any(marker in line for marker in end_markers):
                break
            if line:
                config_section.append(line)

        # Find the index of "Traceback (most recent call last):"
        traceback_marker = "Traceback (most recent call last):"
        traceback_line_number = -1
        for i, line in enumerate(config_section):
            if traceback_marker in line:
                traceback_line_number = i
                break

        # Remove lines after traceback_marker + 1 and before (total_lines - 2)
        if traceback_line_number >= 0:
            total_lines = len(config_section)
            start_remove = traceback_line_number + 1
            end_remove = total_lines - 2
            config_section = config_section[:start_remove] + config_section[end_remove + 1 :]

        return "\n".join(config_section) if config_section else None

    def parse_server_info(self, config_section):
        """
        Parse the server name and version from the Plex configuration section.
        """
        server_info = {}

        # Initialize a list to keep all lines, including the ones not matched
        all_lines = []

        # Iterate through each line in the config_section
        for line in config_section.splitlines():
            # Add each line to the all_lines list
            all_lines.append(line)

            # Attempt to match the regex pattern in the current line
            match = re.search(r"Connected to server\s+([\w\s]+)\s+version\s+(\d+\.\d+\.\d+\.\d+-[\w\d]+)", line)
            if match:
                # Extract server name and version from the regex match
                server_name = match.group(1).strip()
                version = match.group(2).strip()

                # Store server name and version in dictionary
                server_info["server_name"] = server_name
                server_info["version"] = version

        # Log if server info extraction failed for all lines
        if not server_info:
            mylogger.info("Failed to extract server info from config_section")

        return server_info, all_lines

    def extract_header_lines(self, content):
        start_marker_current = "Version: "
        start_marker_newest = "Newest Version: "
        end_marker = "Run Command: "

        lines = content.splitlines()
        header_lines = []

        for i, line in enumerate(lines):
            if start_marker_current in line:
                version_value = line.split(start_marker_current)[1].strip()  # Extract version value
                self.current_kometa_version = version_value  # Store the version as a class variable
                while line and end_marker not in line:
                    header_lines.append(line.strip())  # Trim leading and trailing spaces
                    i += 1
                    line = lines[i] if i < len(lines) else ""
                    if start_marker_newest in line:
                        newest_version_value = line.split(start_marker_newest)[1].strip()  # Extract newest version value
                        self.kometa_newest_version = newest_version_value  # Store the newest version as a class variable
                header_lines.append(line.strip())  # Append the "Run Command" line
                # mylogger.info(f"header_lines bef replacement: {header_lines}")
                break  # Stop after the first occurrence

        # Perform the replacement after all lines have been added to header_lines
        header_lines = [line.replace("(redacted)", "") for line in header_lines]
        header_lines = [line.replace("(redacted)", "") for line in header_lines]
        # mylogger.info(f"header_lines aft replacement: {header_lines}")

        return "\n".join(header_lines)

    def extract_run_command(self, content):
        if not content:
            return None
        for line in content.splitlines():
            match = re.search(r"Run Command:\s*(.+)$", line)
            if match:
                return match.group(1).strip()
        return None

    def _split_command(self, command):
        if not command:
            return []
        try:
            return shlex.split(command, posix=False)
        except Exception:
            return command.split()

    def compute_command_signature(self, run_command):
        if not run_command:
            return None
        tokens = self._split_command(run_command)
        flags = []
        for token in tokens:
            if token.startswith("-"):
                flag = token.split("=", 1)[0]
                flags.append(flag)
        return " ".join(flags)

    def _extract_config_path_from_command(self, run_command):
        if not run_command:
            return None
        tokens = self._split_command(run_command)
        for idx, token in enumerate(tokens):
            if token.startswith("--config="):
                return token.split("=", 1)[1].strip('"')
            if token == "--config" and idx + 1 < len(tokens):
                return tokens[idx + 1].strip('"')
        return None

    def _derive_config_name_from_path(self, config_path):
        try:
            config_path = Path(config_path)
        except Exception:
            return None
        stem = config_path.stem
        if stem.endswith("_config"):
            stem = stem[: -len("_config")]
        return stem or None

    def sanitize_run_command(self, run_command, config_path=None):
        if not run_command:
            return None
        cleaned = run_command
        if config_path:
            config_path = str(config_path)
            cleaned = cleaned.replace(config_path, "<config>")
            cleaned = cleaned.replace(config_path.replace("\\", "/"), "<config>")
            cleaned = cleaned.replace(config_path.replace("/", "\\"), "<config>")
        cleaned = re.sub(
            r"(?i)(--?[\w-]*(token|apikey|api-key|api_key|secret)\w*)(=|\s+)(\S+)",
            r"\1\3<redacted>",
            cleaned,
        )
        return cleaned

    def _hash_file(self, path):
        if not path:
            return None
        try:
            path = Path(path)
        except Exception:
            return None
        if not path.exists():
            return None
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as exc:
            mylogger.warning(f"Failed to hash config file {path}: {exc}")
            return None

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

    def _parse_hms_to_seconds(self, value):
        if not value:
            return None
        parts = value.split(":")
        try:
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

    def extract_section_runtimes(self, content):
        section_times = {}
        if not content:
            return section_times
        inline_pattern = re.compile(r"Finished (?P<section>.+?) in (?P<time>\d+:\d{2}:\d{2})")
        finished_pattern = re.compile(r"Finished (?P<section>.+?)\s*$")
        runtime_pattern = re.compile(r"^\s*(?P<label>[A-Za-z][A-Za-z ]+?) Run Time:\s*(?P<time>\d+:\d{2}:\d{2})\s*$")
        last_section = None
        last_section_index = None
        lines = content.splitlines()
        for idx, line in enumerate(lines):
            if not line:
                continue
            inline_match = inline_pattern.search(line)
            if inline_match:
                section = inline_match.group("section").strip()
                if section.lower().startswith("at:"):
                    continue
                seconds = self._parse_hms_to_seconds(inline_match.group("time"))
                if seconds is not None:
                    section_times[section] = section_times.get(section, 0) + seconds
                continue
            finished_match = finished_pattern.search(line)
            if finished_match:
                section = finished_match.group("section").strip()
                lowered = section.lower()
                if lowered in ("run",) or lowered.startswith("run "):
                    continue
                last_section = section
                last_section_index = idx
                continue
            runtime_match = runtime_pattern.search(line)
            if not runtime_match:
                continue
            seconds = self._parse_hms_to_seconds(runtime_match.group("time"))
            if seconds is None:
                continue
            section = None
            if last_section and last_section_index is not None and (idx - last_section_index) <= 3:
                section = last_section
            else:
                label = runtime_match.group("label").strip()
                if label and label.lower() != "run":
                    section = label
            if section:
                section_times[section] = section_times.get(section, 0) + seconds
            last_section = None
            last_section_index = None
        return section_times

    def count_log_levels(self, content):
        counts = {
            "debug": 0,
            "info": 0,
            "warning": 0,
            "error": 0,
            "critical": 0,
            "trace": 0,
        }
        if not content:
            return counts
        for line in content.splitlines():
            upper = line.upper()
            if "[DEBUG]" in upper:
                counts["debug"] += 1
            if "[INFO]" in upper:
                counts["info"] += 1
            if "[WARNING]" in upper:
                counts["warning"] += 1
            if "[ERROR]" in upper:
                counts["error"] += 1
            if "[CRITICAL]" in upper:
                counts["critical"] += 1
            if "TRACEBACK" in upper:
                counts["trace"] += 1
        return counts

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
        if not content:
            return None
        match = re.search(r"\[Quickstart\]\s+Run marker:.*", content)
        return match.group(0) if match else None

    def extract_config_line_count(self, content):
        if not content:
            return 0
        lines = content.splitlines()
        in_block = False
        count = 0
        for raw_line in lines:
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

    def extract_library_counts(self, content):
        if not content:
            return {}
        lines = content.splitlines()
        library_counts = {}
        library_sources = {}
        current_library = None
        current_type = None

        header_patterns = [
            re.compile(r"Processing Library:\s*(.+)", re.IGNORECASE),
            re.compile(r"Library:\s*(.+)", re.IGNORECASE),
            re.compile(r"Information on library:\s*(.+)", re.IGNORECASE),
        ]
        type_pattern = re.compile(r"\b(Movie|Show)\b", re.IGNORECASE)
        items_pattern = re.compile(r"Items Found:\s*(\d+)", re.IGNORECASE)
        movies_pattern = re.compile(r"Movies Found:\s*(\d+)", re.IGNORECASE)
        shows_pattern = re.compile(r"Shows Found:\s*(\d+)", re.IGNORECASE)
        episodes_pattern = re.compile(r"Episodes Found:\s*(\d+)", re.IGNORECASE)
        content_movies_pattern = re.compile(r"Content Count:\s*(\d+)\s+movies?", re.IGNORECASE)
        content_shows_pattern = re.compile(r"Content Count:\s*(\d+)\s+shows?\s*/\s*(\d+)\s+episodes", re.IGNORECASE)
        library_items_pattern = re.compile(r"Library\s+(.+?)\s+has\s+(\d+)\s+items", re.IGNORECASE)

        for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("#"):
                line = line.lstrip("#").strip()
            if not line:
                continue
            for pattern in header_patterns:
                match = pattern.search(line)
                if match:
                    name = match.group(1).strip()
                    if "->" in name:
                        name = name.split("->", 1)[-1].strip()
                    name = name.strip("- ").strip()
                    if name:
                        current_library = name
                        current_type = None
                        type_match = type_pattern.search(line)
                        if type_match:
                            current_type = type_match.group(1).lower()
                    break

            direct_match = library_items_pattern.search(line)
            if direct_match:
                name = direct_match.group(1).strip()
                count = int(direct_match.group(2))
                library_counts[name] = {
                    "items": count,
                }
                continue

            if not current_library:
                continue

            content_match = content_movies_pattern.search(line)
            if content_match:
                library_counts[current_library] = {
                    "items": int(content_match.group(1)),
                    "type": "movie",
                }
                library_sources[current_library] = "content_count"
                continue

            content_match = content_shows_pattern.search(line)
            if content_match:
                library_counts[current_library] = {
                    "items": int(content_match.group(1)),
                    "episodes": int(content_match.group(2)),
                    "type": "show",
                }
                library_sources[current_library] = "content_count"
                continue

            items_match = items_pattern.search(line)
            if items_match:
                if library_sources.get(current_library) == "content_count":
                    continue
                library_counts[current_library] = {
                    "items": int(items_match.group(1)),
                    "type": current_type,
                }
                continue

            movies_match = movies_pattern.search(line)
            if movies_match:
                if library_sources.get(current_library) == "content_count":
                    continue
                library_counts[current_library] = {
                    "items": int(movies_match.group(1)),
                    "type": "movie",
                }
                continue

            shows_match = shows_pattern.search(line)
            if shows_match:
                if library_sources.get(current_library) == "content_count":
                    continue
                entry = library_counts.get(current_library, {})
                entry["items"] = int(shows_match.group(1))
                entry["type"] = entry.get("type") or "show"
                library_counts[current_library] = entry
                continue

            episodes_match = episodes_pattern.search(line)
            if episodes_match:
                if library_sources.get(current_library) == "content_count":
                    continue
                entry = library_counts.get(current_library, {})
                entry["episodes"] = int(episodes_match.group(1))
                entry["type"] = entry.get("type") or "show"
                library_counts[current_library] = entry

        return library_counts

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
            "created_at": datetime.utcnow().isoformat(),
        }

    def analyze_content(self, content, log_path=None, config_name=None, config_path=None, include_people_scan=True):
        self.reset_server_versions()
        self.checkfiles_flg = None
        self.run_time = None
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
        config_line_count = self.extract_config_line_count(raw_content)
        cache_line_count = sum(1 for line in raw_content.splitlines() if "from Cache" in line)
        library_counts = self.extract_library_counts(cleaned_content)

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
            summary["library_counts"] = library_counts
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
