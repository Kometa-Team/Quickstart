"""Preview-mapped report line builders.

The ``/import-config/preview-mapped`` route produces a text report
showing which parts of the imported config will land in the DB and
which will be skipped.  Two chunks of report-building logic used to
live inline in that route:

1. :func:`build_alias_report_lines` -- for libraries that were
   renamed via a mapping (e.g. imported "Anime Movies" mapped to
   Plex "Movies"), generate additional report lines showing the
   original name so the user can see "your Anime Movies config
   will go to Movies".

2. :func:`compute_line_counts` -- count imported / not_imported /
   comment / blank / diff lines from the raw + annotated YAML.
"""

from __future__ import annotations

from blueprints.import_config_helpers import count_annotated_lines


def build_alias_report_lines(
    *,
    report_lines: list,
    alias_map: dict,
    libraries_payload,
) -> list:
    """Generate aliased duplicate report lines for renamed libraries.

    For each entry in ``alias_map`` (imported-name -> plex-target-name),
    find every report line under ``libraries.<target>`` and emit an
    aliased copy under ``libraries.<original>`` so the user can see
    exactly what will happen to the config they uploaded.

    :param report_lines: existing report lines (not mutated).
    :param alias_map: dict of imported library name -> Plex target.
    :param libraries_payload: the ``config_data.get("libraries")``
        value; the alias lines are only generated if this is a dict.
    :returns: a list of NEW alias lines to append (never modifies
              the input); empty if there's nothing to alias.
    """
    if not alias_map or not isinstance(libraries_payload, dict):
        return []

    alias_lines: list = []
    seen = set(report_lines)
    for original_name, mapped_name in alias_map.items():
        if not original_name:
            continue
        mapped_name = str(mapped_name).strip()
        if not mapped_name or mapped_name == "__ignore__":
            continue
        if mapped_name == original_name:
            continue
        prefix = f"libraries.{mapped_name}"
        for line in report_lines:
            if not isinstance(line, str) or ":" not in line:
                continue
            status, rest = line.split(":", 1)
            status = status.strip()
            path = rest.strip()
            suffix = ""
            if " :: " in path:
                path, reason = path.split(" :: ", 1)
                path = path.strip()
                suffix = f" :: {reason}"
            elif status != "imported" and " - " in path:
                path, reason = path.split(" - ", 1)
                path = path.strip()
                suffix = f" - {reason}"
            if path == prefix or path.startswith(prefix + "."):
                alias_path = f"libraries.{original_name}{path[len(prefix) :]}"
                alias_line = f"{status}: {alias_path}{suffix}"
                if alias_line not in seen:
                    alias_lines.append(alias_line)
                    seen.add(alias_line)
    return alias_lines


def compute_line_counts(*, config_text: str, annotated_report: str, comments_count: int) -> dict:
    """Compute imported / not_imported / comment / blank / total / diff counts.

    :param config_text: the raw YAML text of the imported config.
    :param annotated_report: the annotated version with report markers.
    :param comments_count: pre-computed comment line count (from cache).
    :returns: dict with keys imported_lines, not_imported_lines,
              comments, blank, total, diff.
    """
    text_str = str(config_text)
    blank_count = sum(1 for line in text_str.splitlines() if not line.strip())
    total_lines = len(text_str.splitlines())
    annotated_counts = count_annotated_lines(str(annotated_report))
    imported_lines = annotated_counts.get("imported", 0)
    not_imported_lines = annotated_counts.get("not_imported", 0)
    diff_count = total_lines - (imported_lines + not_imported_lines + blank_count + comments_count)
    return {
        "imported_lines": imported_lines,
        "not_imported_lines": not_imported_lines,
        "comments": comments_count,
        "blank": blank_count,
        "total": total_lines,
        "diff": diff_count,
    }
