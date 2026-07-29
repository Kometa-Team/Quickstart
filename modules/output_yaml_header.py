"""YAML header rendering for the generated Kometa config.

Extracted from ``modules.output.build_config``.

The Quickstart-generated ``config.yml`` opens with a large banner of
metadata comments: system info, versions, plex summary, library
inventory, etc.  This module owns the string that appears before the
first YAML section.

Public entry point:

* :func:`render_yaml_header(header_style, config_name, movie_libraries,
  show_libraries, version_info)` returns the header string, including
  the trailing blank lines before the first section.

Everything else in this module is a private helper used only by
:func:`render_yaml_header`.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import datetime

import psutil
from flask import current_app as app, has_request_context, session

from modules import helpers
from modules.output_headers import add_border_to_ascii_art, section_heading

# Header styles that skip the ASCII art border wrapping.
_STYLES_WITHOUT_BORDER = frozenset({"none", "single line"})


# Static comment appended right before the auto-generation footer.
_EDITOR_HINT_COMMENT = (
    "### \n"
    "# We highly recommend using Visual Studio Code with indent-rainbow "
    "by oderwat extension and YAML by Red Hat extension. Visual Studio "
    "Code will also leverage the above link (yaml-language-server) to "
    "enhance Kometa yml edits.\n"
    "###"
)


def _get_git_version():
    """Return the local ``git --version`` string or ``\"Unavailable\"``.

    Silently returns ``\"Unavailable\"`` when git isn't on PATH or when
    the invocation raises.  Never propagates errors -- the YAML header
    is best-effort informational metadata; a broken git shouldn't
    break config generation.
    """
    git_path = shutil.which("git")
    if not git_path:
        return "Unavailable"
    try:
        git_result = subprocess.run(
            [git_path, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        git_output = (git_result.stdout or git_result.stderr or "").strip()
        return git_output or "Unavailable"
    except Exception:
        return "Unavailable"


def _get_memory_summary():
    """Return ``(used_mb, total_mb, available_mb, percent)`` from psutil.

    All four values are ints in MB (or percent).  Kept together so
    the caller doesn't have to remember the ordering.
    """
    vm = psutil.virtual_memory()
    mb = 1024 * 1024
    used_mb = int((vm.total - vm.available) / mb)
    total_mb = int(vm.total / mb)
    available_mb = int(vm.available / mb)
    percent = int(vm.percent)
    return used_mb, total_mb, available_mb, percent


def _get_browser_line():
    """Return a one-line browser summary read from the Flask session.

    Falls back through:

    1. ``qs_user_agent_browser`` + optional ``_version`` + ``_platform``.
    2. Raw ``qs_user_agent_raw`` / ``qs_user_agent``.
    3. ``\"Unknown\"``.

    Returns ``\"Unknown\"`` when there is no request context.
    """
    if not has_request_context():
        return "Unknown"

    browser_name = session.get("qs_user_agent_browser") or ""
    if browser_name:
        line = browser_name
        browser_version = session.get("qs_user_agent_version") or ""
        if browser_version:
            line = f"{line} {browser_version}"
        browser_platform = session.get("qs_user_agent_platform") or ""
        if browser_platform:
            line = f"{line} ({browser_platform})"
        return line

    return session.get("qs_user_agent_raw") or session.get("qs_user_agent") or "Unknown"


def _render_kometa_ascii_art(header_style):
    """Return the KOMETA ASCII art block for the top of the YAML file."""
    heading = section_heading("KOMETA", font=header_style)
    if header_style in _STYLES_WITHOUT_BORDER:
        return heading
    return add_border_to_ascii_art(heading)


def _sorted_library_display_names(libraries):
    """Return ``libraries.values()`` sorted case-insensitively.

    Empty / whitespace-only names are dropped.  ``libraries`` is the
    ``{key: display_name}`` dict shape used throughout ``build_config``.
    """
    return sorted(
        (str(name) for name in libraries.values() if str(name).strip()),
        key=lambda value: value.strip().casefold(),
    )


def _get_kometa_schema_header(kometa_branch):
    """Return the yaml-language-server pragma line for VSCode."""
    return "# yaml-language-server: " f"$schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/" f"{kometa_branch}/json-schema/config-schema.json"


def render_yaml_header(header_style, config_name, movie_libraries, show_libraries, version_info):
    """Render the metadata comment banner that opens the generated config.

    Includes:

    * yaml-language-server ``$schema`` pragma
    * ASCII art ``KOMETA`` heading (respects ``header_style``)
    * ``config_name`` divider + creation timestamp
    * System info: OS, Docker, CPU, memory, Python, git, browser
    * Quickstart settings summary + Plex summary
    * Version/branch/environment line
    * Library inventory (movie/show counts + names)
    * Editor-hint comment + auto-generation notice
    * Trailing blank lines before the first section
    """
    # Version + environment metadata (all from the shared update snapshot).
    kometa_branch = version_info.get("kometa_branch", "nightly")
    quickstart_branch = version_info.get("branch", "unknown")
    quickstart_version = version_info.get("local_version", "unknown")
    quickstart_environment = version_info.get("running_on", "unknown")

    # Host metadata.
    system_name = platform.system() or "Unknown OS"
    system_release = platform.release() or ""
    cpu_name = platform.processor() or platform.uname().processor or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=True) or 0
    mem_used, mem_total, mem_available, mem_percent = _get_memory_summary()
    is_docker = bool(app.config.get("QUICKSTART_DOCKER")) or "Docker" in str(quickstart_environment)
    python_version = platform.python_version() or platform.python_version_tuple()[0]
    git_version = _get_git_version()
    os_line = f"# OS: {system_name} {system_release}".strip()
    browser_line = _get_browser_line()

    # Runtime snapshot / library summaries.
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plex_summary = helpers.get_plex_summary()
    qs_settings_lines = helpers.get_quickstart_settings_summary()
    qs_settings_block = "\n".join(qs_settings_lines) if qs_settings_lines else ""

    library_names = _sorted_library_display_names(movie_libraries) + _sorted_library_display_names(show_libraries)
    library_details = helpers.get_library_summaries(library_names)

    schema_header = _get_kometa_schema_header(kometa_branch)
    ascii_heading = _render_kometa_ascii_art(header_style)

    # Interpolating chr(10) into the plex/library blocks turns internal
    # newlines into '\n# ' so every wrapped line stays commented.
    plex_lines = "# " + plex_summary.replace(chr(10), chr(10) + "# ")
    library_detail_lines = "# " + library_details.replace(chr(10), chr(10) + "# ")

    return (
        f"{schema_header}\n\n"
        f"{ascii_heading}\n\n"
        f"#==================== {config_name} ====================#\n"
        f"# {config_name} config created by Quickstart on {timestamp}\n"
        f"# System Information\n"
        f"{os_line}\n"
        f"# Docker: {is_docker}\n"
        f"# CPU: {cpu_name} ({cpu_cores} cores)\n"
        f"# Memory: {mem_used} MB / {mem_total} MB ({mem_percent}%) | {mem_available} MB Free\n"
        f"# Python: {python_version}\n"
        f"# Git: {git_version}\n"
        f"# Browser: {browser_line}\n"
        f"{qs_settings_block}\n"
        f"{plex_lines}\n"
        f"# Quickstart: {quickstart_version} | Branch: {quickstart_branch} | Environment: {quickstart_environment}\n"
        f"###\n"
        f"# Libraries configured with Quickstart: {len(movie_libraries)} movie, {len(show_libraries)} show\n"
        f"{library_detail_lines}\n"
        f"{_EDITOR_HINT_COMMENT}\n\n"
        f"# This file is auto-generated by Quickstart. Do not edit manually unless you know what you are doing.\n"
        f"#==================== {config_name} ====================#\n"
        f"\n\n"
    )
