"""People-poster detection helpers extracted from ``modules.logscan``.

These functions scan a Kometa log for ``Collection Warning: No Poster Found
at <people-images-url>`` lines, look up the names against a cached copy of the
People-Images repo README, and surface the genuinely-missing people for the
recommendation panel.

The functions are pure (no analyzer state); ``LogscanAnalyzer`` retains thin
wrapper methods that delegate here and manage the cached people index on the
analyzer instance so callers like ``quickstart.py`` keep working unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import unquote

import requests

_logger = logging.getLogger("logscan")


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

PEOPLE_README_URLS = ("https://raw.githubusercontent.com/Kometa-Team/People-Images/refs/heads/master/README.md",)

PEOPLE_MISSING_WARNING_REGEX = (
    r"Collection Warning: No Poster Found at "
    r"(https://raw\.githubusercontent\.com/"
    r"(?:Kometa-Team/People-Images(?:-[^/]+)?|meisnate12/Plex-Meta-Manager-People(?:-[^/]+)?)"
    r"/[^\s\]]+)"
)
PEOPLE_MISSING_WARNING_RE = re.compile(PEOPLE_MISSING_WARNING_REGEX, re.IGNORECASE)

PEOPLE_SECTION_START_STRONG = (
    r"^(.+?) Collection in .+$",
    r"^Running .+ Collection$",
)
PEOPLE_SECTION_START_WEAK = (
    r"^Updating Details of .+ Collection$",
    r"^Validating .+ Attributes$",
)
PEOPLE_SECTION_END_PATTERNS = (r"^Finished .+ Collection$",)

_PEOPLE_README_FILENAME_RE = re.compile(r"([A-Za-z0-9_./%\-]+\.(?:jpg|jpeg|png|webp))", re.IGNORECASE)
_KEY_NAME_PATTERNS = (
    r"^Validating\s+(.+?)\s+Attributes$",
    r"^Running\s+(.+?)\s+Collection$",
    r"^Finished\s+(.+?)\s+Collection$",
    r"^(.+?)\s+Collection\s+in\s+.+$",
)


# ---------------------------------------------------------------------------
# URL / filename helpers
# ---------------------------------------------------------------------------


def extract_filename_from_url(url: str) -> str:
    """Return the URL-decoded basename of ``url`` with its extension stripped."""
    return unquote(os.path.splitext(os.path.basename(url))[0])


# ---------------------------------------------------------------------------
# People cache (README mirror) management
# ---------------------------------------------------------------------------


def get_people_cache_path(log_path=None) -> Path:
    """Return the on-disk path used to cache the People-Images README.

    Prefers the project-wide ``config/cache/logscan/`` directory; falls back to
    a sidecar in the log's directory, and finally to the current working
    directory.
    """
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


def load_people_cache(cache_path) -> dict:
    """Load and return the cached README payload, or ``{}`` on any failure."""
    try:
        if not cache_path or not Path(cache_path).exists():
            return {}
        with open(cache_path, "r", encoding="utf-8") as handle:
            return json.load(handle) or {}
    except Exception:
        return {}


def save_people_cache(cache_path, payload: dict) -> None:
    """Write ``payload`` to ``cache_path``. Silently swallows any I/O error."""
    try:
        if not cache_path:
            return
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
    except Exception:
        return


def fetch_people_readme(cache_path) -> tuple[str | None, bool]:
    """Fetch the People-Images README, honoring HTTP cache headers stored in
    ``cache_path``. Returns ``(text, used_cache)``.

    When the network is unavailable the cached text is returned with
    ``used_cache=True``. When neither network nor cache yield content the
    return is ``(None, False)``.
    """
    cache = load_people_cache(cache_path)
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
            _logger.debug(f"People-Images README fetch failed for {url}: {exc}")
            continue

        if response.status_code == 304 and cached_content:
            return cached_content, True
        if response.status_code == 200 and response.text:
            payload = {
                "url": url,
                "etag": response.headers.get("ETag"),
                "last_modified": response.headers.get("Last-Modified"),
                "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "content": response.text,
            }
            save_people_cache(cache_path, payload)
            return response.text, False
        if response.status_code in (404, 410):
            continue

    return cached_content, True if cached_content else False


def build_people_index(readme_text: str | None) -> set[str]:
    """Parse the README text and return a lowercased set of image basenames
    (the keys we match log warnings against)."""
    if not readme_text:
        return set()
    filenames = _PEOPLE_README_FILENAME_RE.findall(readme_text)
    names: set[str] = set()
    for name in filenames:
        cleaned = extract_filename_from_url(name)
        if cleaned:
            names.add(cleaned.lower())
    return names


# ---------------------------------------------------------------------------
# Log-line structural helpers
# ---------------------------------------------------------------------------


def is_blank_log_line(line: str) -> bool:
    return not line.strip()


def is_divider_log_line(line: str) -> bool:
    """Return True when ``line`` is a Kometa divider (all same character,
    ignoring spaces, at least 8 chars long)."""
    stripped = line.strip()
    if not stripped:
        return False
    compact = stripped.replace(" ", "")
    if len(compact) < 8:
        return False
    return len(set(compact)) == 1


def is_section_break(line: str) -> bool:
    return is_blank_log_line(line) or is_divider_log_line(line)


def matches_any_pattern(normalized: str, patterns: Iterable[str]) -> bool:
    return any(re.match(pattern, normalized) for pattern in patterns)


def normalize_name_line(line: str) -> str:
    """Strip whitespace and divider-edge characters from a log line so its
    semantic content is easier to pattern-match."""
    if not line:
        return ""
    return line.strip().strip("= ").strip()


def find_log_section_bounds(cleaned_lines: list[str], index: int, max_span: int = 300) -> tuple[int, int]:
    """Locate the start/end indices of the collection block containing
    ``cleaned_lines[index]``.

    First tries strong section-start markers, then weak ones, then end markers.
    Falls back to scanning for surrounding blank/divider lines when no marker
    matches within ``max_span`` lines.
    """
    start = None
    end = None

    min_index = max(0, index - max_span)
    for idx in range(index, min_index - 1, -1):
        normalized = normalize_name_line(cleaned_lines[idx])
        if not normalized:
            continue
        if matches_any_pattern(normalized, PEOPLE_SECTION_START_STRONG):
            start = idx
            break

    if start is None:
        for idx in range(index, min_index - 1, -1):
            normalized = normalize_name_line(cleaned_lines[idx])
            if not normalized:
                continue
            if matches_any_pattern(normalized, PEOPLE_SECTION_START_WEAK):
                start = idx
                break

    if start is not None:
        while start > 0 and is_divider_log_line(cleaned_lines[start - 1]):
            start -= 1

    max_index = len(cleaned_lines) - 1
    max_end = min(max_index, index + max_span)
    for idx in range(index, max_end + 1):
        normalized = normalize_name_line(cleaned_lines[idx])
        if not normalized:
            continue
        if matches_any_pattern(normalized, PEOPLE_SECTION_END_PATTERNS):
            end = idx
            break

    if end is not None:
        while end < max_index and is_divider_log_line(cleaned_lines[end + 1]):
            end += 1

    if start is None or end is None:
        fallback_start = index
        while fallback_start > 0 and (index - fallback_start) < max_span:
            if is_section_break(cleaned_lines[fallback_start - 1]):
                if is_divider_log_line(cleaned_lines[fallback_start - 1]):
                    fallback_start -= 1
                break
            fallback_start -= 1

        fallback_end = index
        while fallback_end < max_index and (fallback_end - index) < max_span:
            if is_section_break(cleaned_lines[fallback_end + 1]):
                if is_divider_log_line(cleaned_lines[fallback_end + 1]):
                    fallback_end += 1
                break
            fallback_end += 1

        start = fallback_start if start is None else start
        end = fallback_end if end is None else end

    return start, end


def extract_key_name_from_block(cleaned_lines: list[str], start: int, end: int) -> str | None:
    """Pull the collection's logical name from a section block, preferring an
    explicit ``Validating Method: key_name`` / ``Value: <name>`` pair, then
    falling back to the Collection-named markers."""
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

    for line in block:
        normalized = normalize_name_line(line)
        if not normalized:
            continue
        for pattern in _KEY_NAME_PATTERNS:
            match = re.match(pattern, normalized)
            if match:
                return match.group(1).strip()
    return None


def extract_missing_people_names(lines: Iterable[str], available: set[str] | None, name_hint: str | None = None) -> set[str]:
    """For each log line that matches the People-Images missing-poster warning,
    add the (lowercased) person name to the result set — unless the name is
    already present in ``available``.

    When ``name_hint`` is provided it overrides the URL-derived name (used when
    the surrounding block reveals the canonical collection key)."""
    names: set[str] = set()
    for line in lines:
        match = PEOPLE_MISSING_WARNING_RE.search(line)
        if not match:
            continue
        name = name_hint
        if not name:
            url = match.group(1)
            name = extract_filename_from_url(url)
        if not name:
            continue
        key = name.lower()
        if available and key in available:
            continue
        names.add(key)
    return names


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def collect_missing_people_lines(
    content: str,
    available_index: set[str] | None = None,
    max_block_lines: int = 300,
    cleanup_fn: Callable[[str], str] | None = None,
) -> list[dict]:
    """Walk the full log content and return a list of
    ``{"names": set[str], "block": str}`` entries — one per distinct
    collection block that mentions a genuinely-missing People-Images poster.

    ``cleanup_fn`` is the analyzer's ``cleanup_content`` method; it is injected
    rather than imported so this module stays free of the broader analyzer.
    Defaults to a passthrough when not provided.
    """
    if not content:
        return []
    available = available_index if available_index is not None else set()
    raw_lines = content.splitlines()
    cleaned_source = cleanup_fn(content) if cleanup_fn else content
    cleaned_lines = cleaned_source.splitlines()
    items: list[dict] = []
    seen_blocks: set[str] = set()

    for idx, line in enumerate(raw_lines):
        if not PEOPLE_MISSING_WARNING_RE.search(line):
            continue

        if idx < len(cleaned_lines):
            start, end = find_log_section_bounds(cleaned_lines, idx, max_span=max_block_lines)
        else:
            start = max(0, idx - 2)
            end = min(len(raw_lines) - 1, idx + 2)

        block_lines = raw_lines[start : end + 1]
        name_hint = None
        if idx < len(cleaned_lines):
            name_hint = extract_key_name_from_block(cleaned_lines, start, end)
        names = extract_missing_people_names(block_lines, available, name_hint=name_hint)
        if not names:
            continue

        block_text = "\n".join(block_lines)
        if block_text in seen_blocks:
            continue
        seen_blocks.add(block_text)
        items.append({"names": names, "block": block_text})

    return items
