"""ASCII art / section header helpers for output.py.

Extracted from the original ``modules/output.py`` monolith.  Kometa
config files carry decorative section headers between YAML sections --
either single-line comments or pyfiglet-generated ASCII art wrapped in
a hash-mark border.  These two helpers own that rendering.

Public surface: ``section_heading`` is called from ``quickstart.py`` as
``output.section_heading(...)``.  ``add_border_to_ascii_art`` is used
in several build_config / build_libraries_section contexts to wrap a
pre-generated pyfiglet block.  Both are re-exported from ``output.py``
so historical call sites keep working.
"""

from __future__ import annotations

import pyfiglet


def add_border_to_ascii_art(art):
    lines = art.split("\n")
    lines = lines[:-1]
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    return "\n".join(bordered_art)


def section_heading(title, font="standard"):
    if font == "none":
        return ""
    if font == "single line":
        return f"#==================== {title} ====================#"
    try:
        return add_border_to_ascii_art(pyfiglet.figlet_format(title, font=font))
    except pyfiglet.FontNotFound:
        return f"#==================== {title} ====================#"
