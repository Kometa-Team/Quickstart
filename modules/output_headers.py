"""ASCII art / section header helpers for output.py.

Extracted from the original ``modules/output.py`` monolith.  Kometa
config files carry decorative section headers between YAML sections --
either single-line comments or pyfiglet-generated ASCII art wrapped in
a hash-mark border.  These helpers own that rendering.

Public surface: ``section_heading`` is called from ``quickstart.py`` as
``output.section_heading(...)``.  ``add_border_to_ascii_art`` is used
in several build_config / build_libraries_section contexts to wrap a
pre-generated pyfiglet block.  Both are re-exported from ``output.py``
so historical call sites keep working.

``render_section_header`` is the richer variant used inside
build_config -- it handles non-Latin titles (pyfiglet chokes on
non-ASCII) and defaults to an empty string when the style is
``"none"``.  Not currently called from outside output.py.
"""

from __future__ import annotations

import re

import pyfiglet

_NON_LATIN_RE = re.compile(r"[^\x00-\x7F]")


def _contains_non_latin(text):
    """Local copy of ``helpers.contains_non_latin`` to keep this module standalone."""
    return bool(_NON_LATIN_RE.search(text))


def add_border_to_ascii_art(art):
    lines = art.split("\n")
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    return "\n".join(bordered_art)


def _divider(title):
    """The '#===... TITLE ===...#' fallback used everywhere."""
    return f"#==================== {title} ====================#"


def section_heading(title, font="standard"):
    if font == "none":
        return ""
    if font == "single line":
        return _divider(title)
    try:
        return add_border_to_ascii_art(pyfiglet.figlet_format(title, font=font))
    except pyfiglet.FontNotFound:
        return _divider(title)


def render_section_header(title, style):
    """Full-featured section-header renderer used inside build_config.

    Differences from ``section_heading``:

    * Non-Latin titles fall back to the single-line divider because
      pyfiglet only handles ASCII cleanly.
    * All fallback paths use the same ``_divider`` helper -- no
      copy-paste divider strings.

    Returns a possibly-multi-line string suitable for injection above a
    YAML section.  Never mutates its inputs.
    """
    if style == "none":
        return ""
    if style == "single line" or _contains_non_latin(title):
        return _divider(title)
    try:
        return add_border_to_ascii_art(pyfiglet.figlet_format(title, font=style))
    except pyfiglet.FontNotFound:
        return _divider(title)
