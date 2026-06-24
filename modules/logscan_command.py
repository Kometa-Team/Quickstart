"""Plex-config, header, and run-command parsing helpers extracted from
``modules.logscan``.

These are stateless utilities that read a log's text and pull out the
"who/what/where" details — Plex server identity, Kometa version, and the CLI
invocation — without depending on any analyzer instance state.

`LogscanAnalyzer` retains thin wrapper methods that delegate here so that the
class-method call sites (``analyze_content`` and friends) keep working
unchanged.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shlex
from pathlib import Path
from typing import Iterable

_logger = logging.getLogger("logscan")


# ---------------------------------------------------------------------------
# Plex configuration / server-version parsing
# ---------------------------------------------------------------------------

_PLEX_CONFIG_START_MARKER = "Plex Configuration"
_PLEX_CONFIG_END_MARKERS = (" Scanning ", "Library Connection Failed")
_PLEX_TRACEBACK_MARKER = "Traceback (most recent call last):"
_SERVER_INFO_RE = re.compile(r"Connected to server\s+([\w\s]+)\s+version\s+(\d+\.\d+\.\d+\.\d+-[\w\d]+)")

# Versions inside (stable_version, good_version) are flagged as potentially
# affected by the Plex "rounding issue" that older logscan recommendations call
# out. The boundary versions themselves are considered safe.
_PLEX_STABLE_VERSION = "1.40.0.7998-c29d4c0c8"
_PLEX_GOOD_VERSION = "1.40.3.8555-fef15d30c"


def extract_plex_config_section(lines: list[str], start_index: int, end_markers: Iterable[str]) -> str | None:
    """Pull a single Plex Configuration block from ``lines`` and strip out any
    traceback noise that landed inside it.

    Returns ``None`` when the section is empty.
    """
    config_section: list[str] = []

    for i in range(start_index, len(lines)):
        line = lines[i].strip()
        if any(marker in line for marker in end_markers):
            break
        if line:
            config_section.append(line)

    traceback_line_number = -1
    for i, line in enumerate(config_section):
        if _PLEX_TRACEBACK_MARKER in line:
            traceback_line_number = i
            break

    if traceback_line_number >= 0:
        total_lines = len(config_section)
        start_remove = traceback_line_number + 1
        end_remove = total_lines - 2
        config_section = config_section[:start_remove] + config_section[end_remove + 1 :]

    return "\n".join(config_section) if config_section else None


def parse_server_info(config_section: str) -> tuple[dict, list[str]]:
    """Parse the server name + version from a single Plex configuration block.

    Returns ``(server_info_dict, all_lines)``. ``server_info_dict`` is empty
    when no "Connected to server ... version ..." line is present.
    """
    server_info: dict = {}
    all_lines: list[str] = []

    for line in config_section.splitlines():
        all_lines.append(line)
        match = _SERVER_INFO_RE.search(line)
        if match:
            server_info["server_name"] = match.group(1).strip()
            server_info["version"] = match.group(2).strip()

    if not server_info:
        _logger.debug("Failed to extract server info from config_section")

    return server_info, all_lines


def extract_plex_config(content: str) -> dict:
    """Walk the full log content and return every Plex Configuration block
    along with the (server_name, server_version) tuples that fall in the
    "rounding issue" version range.

    Returns ``{"plex_config_content": [...], "server_versions": [...]}``.
    ``plex_config_content`` is ``None`` when no Plex Configuration block is
    found — matching the legacy ``LogscanAnalyzer.extract_plex_config``
    return shape.
    """
    lines = content.splitlines()
    plex_config_content: list[str] = []
    server_versions: list[tuple[str, str]] = []

    _logger.debug("extract_plex_config")

    i = 0
    while i < len(lines):
        if _PLEX_CONFIG_START_MARKER in lines[i]:
            config_section = extract_plex_config_section(lines, i + 1, _PLEX_CONFIG_END_MARKERS)
            if config_section:
                server_info, _all_lines = parse_server_info(config_section)
                plex_config_content.append(config_section)

                if server_info:
                    my_server_name = server_info["server_name"]
                    my_server_version = server_info["version"]

                    if _PLEX_STABLE_VERSION < my_server_version < _PLEX_GOOD_VERSION:
                        _logger.debug(
                            f"Server Name: {my_server_name} has Version: "
                            f"{my_server_version}. Potential Rounding Issue "
                            f"because > {_PLEX_STABLE_VERSION} and < {_PLEX_GOOD_VERSION}"
                        )
                        server_versions.append((my_server_name, my_server_version))
                    else:
                        _logger.debug(f"Server Name: {my_server_name} has Version: " f"{my_server_version}. ALL GOOD")
        i += 1

    return {
        "plex_config_content": plex_config_content if plex_config_content else None,
        "server_versions": server_versions,
    }


# ---------------------------------------------------------------------------
# Header / Kometa-version parsing
# ---------------------------------------------------------------------------

_HEADER_CURRENT_MARKER = "Version: "
_HEADER_NEWEST_MARKER = "Newest Version: "
_HEADER_END_MARKER = "Run Command: "


def extract_header_lines(content: str) -> tuple[str, str | None, str | None]:
    """Capture the header block from the start of a Kometa run, returning
    ``(header_text, current_kometa_version, newest_kometa_version)``.

    The text is joined with ``"\\n"`` separators and has ``"(redacted)"``
    markers stripped, matching the original behavior. Versions are ``None``
    when the corresponding marker is absent.
    """
    lines = content.splitlines()
    header_lines: list[str] = []
    current_version: str | None = None
    newest_version: str | None = None

    for i, line in enumerate(lines):
        if _HEADER_CURRENT_MARKER in line:
            current_version = line.split(_HEADER_CURRENT_MARKER)[1].strip()
            while line and _HEADER_END_MARKER not in line:
                header_lines.append(line.strip())
                i += 1
                line = lines[i] if i < len(lines) else ""
                if _HEADER_NEWEST_MARKER in line:
                    newest_version = line.split(_HEADER_NEWEST_MARKER)[1].strip()
            header_lines.append(line.strip())  # the "Run Command" line
            break  # only the first occurrence matters

    # Two passes preserve the original behavior of stripping "(redacted)"
    # markers that may have been duplicated by the source log.
    header_lines = [line.replace("(redacted)", "") for line in header_lines]
    header_lines = [line.replace("(redacted)", "") for line in header_lines]

    return "\n".join(header_lines), current_version, newest_version


# ---------------------------------------------------------------------------
# Run command parsing / sanitization
# ---------------------------------------------------------------------------

_RUN_COMMAND_RE = re.compile(r"Run Command:\s*(.+)$")
_SENSITIVE_FLAG_RE = re.compile(r"(?i)(--?[\w-]*(token|apikey|api-key|api_key|secret)\w*)(=|\s+)(\S+)")


def extract_run_command(content: str) -> str | None:
    """Return the first ``Run Command:`` value from the log, or ``None``."""
    if not content:
        return None
    for line in content.splitlines():
        match = _RUN_COMMAND_RE.search(line)
        if match:
            return match.group(1).strip()
    return None


def split_command(command: str | None) -> list[str]:
    """Split a CLI command into tokens. Falls back to whitespace split when
    ``shlex`` chokes (e.g. on Windows-style quoting)."""
    if not command:
        return []
    try:
        return shlex.split(command, posix=False)
    except Exception:
        return command.split()


def compute_command_signature(run_command: str | None) -> str | None:
    """Reduce a run command to its space-joined sequence of flag names — a
    stable identifier for "the same kind of run" regardless of values.

    ``--config=foo --run`` and ``--config=bar --run`` share the same signature.
    """
    if not run_command:
        return None
    tokens = split_command(run_command)
    flags = [token.split("=", 1)[0] for token in tokens if token.startswith("-")]
    return " ".join(flags)


def extract_config_path_from_command(run_command: str | None) -> str | None:
    """Pull the ``--config`` argument out of a run command, supporting both
    ``--config=path`` and ``--config path`` syntaxes."""
    if not run_command:
        return None
    tokens = split_command(run_command)
    for idx, token in enumerate(tokens):
        if token.startswith("--config="):
            return token.split("=", 1)[1].strip('"')
        if token == "--config" and idx + 1 < len(tokens):
            return tokens[idx + 1].strip('"')
    return None


def derive_config_name_from_path(config_path) -> str | None:
    """Turn ``/path/to/my_config.yml`` into ``"my"`` — strip directory, drop
    the extension, and remove a trailing ``_config`` suffix when present."""
    try:
        config_path = Path(config_path)
    except Exception:
        return None
    stem = config_path.stem
    if stem.endswith("_config"):
        stem = stem[: -len("_config")]
    return stem or None


def sanitize_run_command(run_command: str | None, config_path=None) -> str | None:
    """Redact a run command for safe display: replace the config path with
    ``<config>`` and redact token/apikey/secret flag values with ``<redacted>``.

    Handles both forward and back slash variants of the path so logs from any
    OS render consistently.
    """
    if not run_command:
        return None
    cleaned = run_command
    if config_path:
        config_path = str(config_path)
        cleaned = cleaned.replace(config_path, "<config>")
        cleaned = cleaned.replace(config_path.replace("\\", "/"), "<config>")
        cleaned = cleaned.replace(config_path.replace("/", "\\"), "<config>")
    cleaned = _SENSITIVE_FLAG_RE.sub(r"\1\3<redacted>", cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Config-file hashing
# ---------------------------------------------------------------------------


def hash_file(path) -> str | None:
    """Return the SHA-256 hex digest of ``path``, or ``None`` if it cannot be
    read. Logs a warning on read errors but never raises."""
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
        _logger.warning(f"Failed to hash config file {path}: {exc}")
        return None
