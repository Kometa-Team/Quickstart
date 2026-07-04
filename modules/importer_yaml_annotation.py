"""YAML import-report annotation helpers.

Extracted from :mod:`modules.importer` to isolate the ~256 lines of
"take a raw YAML string plus an import-report and annotate every
line with an `# imported / not imported / etc.` comment" logic.

The Kometa Quickstart config-import flow runs a user-uploaded
``config.yml`` through :func:`modules.importer.prepare_import_payload`,
which produces both a normalized payload dict AND a plain-text
report ("libraries.movies.radarr: imported", "libraries.movies.overlay_files.0: not imported (unknown default)", ...).

This module's :func:`annotate_yaml_with_report` takes the ORIGINAL
yaml text plus that report and emits an annotated copy that
Quickstart shows the user in a diff-style preview so they can see
exactly which of their config keys got picked up and which
silently dropped.

The nine leading ``_`` helpers are internal to the annotation
walk but are re-exported from :mod:`modules.importer` because
``tests/test_template_gap_analyzer.py`` monkeypatches
``importer._parse_report_details`` to inject fake reports.  Do NOT
rename them without updating those tests.
"""

from __future__ import annotations

import re


def _parse_report_details(report_lines: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    status_map: dict[str, str] = {}
    reason_map: dict[str, str] = {}
    if not report_lines:
        return status_map, reason_map
    for line in report_lines:
        if not isinstance(line, str) or ":" not in line:
            continue
        status, rest = line.split(":", 1)
        status = status.strip().lower()
        if status not in {"imported", "unmapped", "skipped"}:
            continue
        path = rest.strip()
        reason = ""
        if " :: " in path:
            path, reason = path.rsplit(" :: ", 1)
            path = path.strip()
            reason = reason.strip()
        elif " - " in path and status != "imported":
            candidate_path, candidate_reason = path.rsplit(" - ", 1)
            if " - " not in candidate_path:
                path = candidate_path.strip()
                reason = candidate_reason.strip()
        if not path:
            continue
        mapped = "mapped" if status == "imported" else status
        status_map[path] = mapped
        if reason:
            reason_map[path] = reason
    return status_map, reason_map


def _parse_report_statuses(report_lines: list[str]) -> dict[str, str]:
    status_map, _ = _parse_report_details(report_lines)
    return status_map


def _lookup_report_reason(reason_map: dict[str, str], status_path: str | None) -> str | None:
    if not status_path:
        return None
    if status_path in reason_map:
        return reason_map[status_path]
    if "[" in status_path:
        normalized = re.sub(r"\[\d+\]", "", status_path)
        if normalized in reason_map:
            return reason_map[normalized]
    if status_path.endswith(".default"):
        alt = status_path[: -len(".default")]
        if alt in reason_map:
            return reason_map[alt]
    parts = status_path.split(".")
    for idx in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:idx])
        if prefix in reason_map:
            return reason_map[prefix]
    return None


def _format_report_status(status: str | None, reason: str | None) -> str | None:
    if not status:
        return None
    if reason:
        return f"{status} - {reason}"
    return status


def _build_prefix_flags(status_map: dict[str, str]) -> dict[str, dict[str, bool]]:
    prefix_map: dict[str, dict[str, bool]] = {}
    for path, status in status_map.items():
        parts = path.split(".")
        for idx in range(1, len(parts) + 1):
            prefix = ".".join(parts[:idx])
            flags = prefix_map.setdefault(prefix, {"mapped": False, "unmapped": False, "skipped": False})
            if status in flags:
                flags[status] = True
            if "[" in prefix:
                normalized = re.sub(r"\[\d+\]", "", prefix)
                if normalized and normalized != prefix:
                    norm_flags = prefix_map.setdefault(normalized, {"mapped": False, "unmapped": False, "skipped": False})
                    if status in norm_flags:
                        norm_flags[status] = True
    return prefix_map


def _status_from_flags(flags: dict[str, bool] | None) -> str | None:
    if not flags:
        return None
    mapped = flags.get("mapped")
    unmapped = flags.get("unmapped")
    skipped = flags.get("skipped")
    if mapped and (unmapped or skipped):
        return "partial"
    if mapped:
        return "mapped"
    if unmapped:
        return "unmapped"
    if skipped:
        return "skipped"
    return None


def _split_inline_comment(text: str) -> tuple[str, str]:
    in_single = False
    in_double = False
    for idx, char in enumerate(text):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return text[:idx], text[idx:]
    return text, ""


def _parse_mapping_key(text: str) -> tuple[str | None, str | None]:
    if ":" not in text:
        return None, None
    key, rest = text.split(":", 1)
    # Treat as mapping only when ":" is followed by space or end-of-line.
    # This avoids misclassifying plain strings like "C:\Path" or "http://".
    if rest and not rest.startswith(" "):
        return None, None
    key = key.strip()
    if not key:
        return None, None
    if key[0] in {"'", '"'} and key[-1:] == key[:1]:
        key = key[1:-1]
    return key, rest


def _append_status_annotation(line: str, status: str | None) -> str:
    if not status:
        return line
    if "#" in line:
        return f"{line} | {status}"
    return f"{line}  # {status}"


def annotate_yaml_with_report(raw_text: str, report_lines: list[str], binary: bool = False) -> str:
    if not raw_text:
        return ""
    status_map, reason_map = _parse_report_details(report_lines)
    if binary:
        imported_only = {path: status for path, status in status_map.items() if status == "mapped"}
        prefix_map = _build_prefix_flags(imported_only)
    else:
        prefix_map = _build_prefix_flags(status_map)
    if not prefix_map and not binary:
        return raw_text

    lines = raw_text.splitlines()
    annotated: list[str] = []
    stack: list[dict[str, str | int]] = []
    list_counters: dict[tuple[str, int], int] = {}
    prev_indent = 0
    block_scalar_indent: int | None = None

    for line in lines:
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)

        if block_scalar_indent is not None:
            if not stripped or indent > block_scalar_indent:
                annotated.append(line)
                continue
            block_scalar_indent = None

        if not stripped or stripped.startswith("#"):
            annotated.append(line)
            continue

        if indent < prev_indent:
            list_counters = {k: v for k, v in list_counters.items() if k[1] < indent}
        prev_indent = indent

        content, _ = _split_inline_comment(stripped)
        content = content.rstrip()
        if not content:
            annotated.append(line)
            continue

        is_list_line = content.startswith("-")
        while stack:
            top = stack[-1]
            top_indent = top["indent"]
            top_path = str(top.get("path", ""))
            if indent < top_indent:
                stack.pop()
                continue
            if is_list_line and indent == top_indent and "[" in top_path:
                stack.pop()
                continue
            if not is_list_line and indent <= top_indent:
                stack.pop()
                continue
            break

        line_path = None

        if content.startswith("-"):
            item_content = content[1:].lstrip()
            parent_path = stack[-1]["path"] if stack else ""
            list_id = (str(parent_path), indent)
            index = list_counters.get(list_id, -1) + 1
            list_counters[list_id] = index
            list_path = f"{parent_path}[{index}]" if parent_path else f"[{index}]"
            stack.append({"indent": indent, "path": list_path})

            if item_content:
                item_content, _ = _split_inline_comment(item_content)
                key, rest = _parse_mapping_key(item_content)
                if key:
                    line_path = f"{list_path}.{key}" if list_path else key
                    rest = rest or ""
                    rest_text = rest.strip()
                    if rest_text == "":
                        stack.append({"indent": indent, "path": line_path})
                    elif rest_text.startswith(("|", ">")):
                        block_scalar_indent = indent
                else:
                    line_path = list_path
            else:
                line_path = list_path
        else:
            key, rest = _parse_mapping_key(content)
            if key:
                parent_path = stack[-1]["path"] if stack else ""
                line_path = f"{parent_path}.{key}" if parent_path else key
                rest_text = (rest or "").strip()
                if rest_text == "":
                    stack.append({"indent": indent, "path": line_path})
                elif rest_text.startswith(("|", ">")):
                    block_scalar_indent = indent

        status_path = line_path
        if status_path and status_path not in prefix_map and f"{status_path}.default" in prefix_map:
            status_path = f"{status_path}.default"
        flags = prefix_map.get(status_path) if status_path else None
        if not flags and status_path and "[" in status_path:
            normalized_path = re.sub(r"\[\d+\]", "", status_path)
            flags = prefix_map.get(normalized_path)
        if binary and status_path:
            status = "imported" if flags and flags.get("mapped") else "not imported"
            reason = _lookup_report_reason(reason_map, status_path) if status == "not imported" else None
            if status == "not imported" and not reason:
                reason = "No matching Quickstart mapping"
            status_text = _format_report_status(status, reason)
        else:
            status = _status_from_flags(flags)
            reason = _lookup_report_reason(reason_map, status_path) if status and status != "imported" else None
            status_text = _format_report_status(status, reason)
        annotated.append(_append_status_annotation(line, status_text))

    return "\n".join(annotated)
