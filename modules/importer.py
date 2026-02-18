import json
import re
from typing import Any

from ruamel.yaml import YAML

from modules import helpers

SIMPLE_SECTIONS = {
    "plex",
    "tmdb",
    "omdb",
    "mdblist",
    "tautulli",
    "notifiarr",
    "gotify",
    "ntfy",
    "github",
    "radarr",
    "sonarr",
    "trakt",
    "mal",
    "anidb",
    "webhooks",
    "settings",
    "playlist_files",
}


def sanitize_config_name(raw_name: str | None) -> str:
    if not isinstance(raw_name, str):
        return ""
    return re.sub(r"[^a-z0-9_]", "", raw_name.strip().lower())


def load_yaml_config(raw_text: str) -> dict:
    yaml = YAML(typ="safe", pure=True)
    loaded = yaml.load(raw_text)
    return loaded if isinstance(loaded, dict) else {}


class ImportReport:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.counts = {"imported": 0, "unmapped": 0, "skipped": 0}

    def add(self, status: str, path: str, reason: str | None = None) -> None:
        if status not in self.counts:
            status = "skipped"
        suffix = f" - {reason}" if reason else ""
        self.lines.append(f"{status}: {path}{suffix}")
        self.counts[status] += 1

    def summary(self) -> dict[str, int]:
        return dict(self.counts)


def _parse_report_statuses(report_lines: list[str]) -> dict[str, str]:
    status_map: dict[str, str] = {}
    if not report_lines:
        return status_map
    for line in report_lines:
        if not isinstance(line, str) or ":" not in line:
            continue
        status, rest = line.split(":", 1)
        status = status.strip().lower()
        if status not in {"imported", "unmapped", "skipped"}:
            continue
        path = rest.strip()
        if " - " in path:
            path = path.split(" - ", 1)[0].strip()
        if not path:
            continue
        mapped = "mapped" if status == "imported" else status
        status_map[path] = mapped
    return status_map


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
    status_map = _parse_report_statuses(report_lines)
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
        else:
            status = _status_from_flags(flags)
        annotated.append(_append_status_annotation(line, status))

    return "\n".join(annotated)


def _collect_template_keys(template_vars: Any) -> set[str]:
    keys = set()
    if isinstance(template_vars, dict):
        keys.update(str(k) for k in template_vars.keys())
    elif isinstance(template_vars, list):
        for item in template_vars:
            if isinstance(item, dict):
                key = item.get("key")
                if key:
                    keys.add(str(key))
    return keys


def _build_collection_index(collection_config: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    by_id: dict[str, dict] = {}
    by_alias: dict[str, str] = {}
    for group in collection_config or []:
        for collection in group.get("collections", []) if isinstance(group, dict) else []:
            cid = collection.get("id")
            if not cid:
                continue
            by_id[cid] = collection
            alias = cid.replace("collection_", "", 1)
            by_alias[alias] = cid
    return by_id, by_alias


def _build_overlay_index(overlay_config: list[dict]) -> tuple[dict[str, dict], dict[str, str], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_alias: dict[str, str] = {}
    radio_map: dict[str, dict] = {}
    for group in overlay_config or []:
        if not isinstance(group, dict):
            continue
        input_type = group.get("input_type")
        radio_group = group.get("radio_group_name")
        for overlay in group.get("overlays", []):
            if not isinstance(overlay, dict):
                continue
            oid = overlay.get("id")
            if not oid:
                continue
            if oid in by_id:
                existing = by_id[oid]
                if isinstance(existing, dict):
                    existing_media = existing.get("media_types")
                    new_media = overlay.get("media_types")
                    if isinstance(existing_media, list) or isinstance(new_media, list):
                        merged = []
                        for entry in existing_media or []:
                            if entry not in merged:
                                merged.append(entry)
                        for entry in new_media or []:
                            if entry not in merged:
                                merged.append(entry)
                        existing["media_types"] = merged
                    existing_templates = existing.get("template_variables")
                    new_templates = overlay.get("template_variables")
                    if isinstance(existing_templates, dict) and isinstance(new_templates, dict):
                        for key, value in new_templates.items():
                            if key not in existing_templates:
                                existing_templates[key] = value
                    elif isinstance(new_templates, dict) and not isinstance(existing_templates, dict):
                        existing["template_variables"] = new_templates
            else:
                by_id[oid] = overlay
            alias = oid.replace("overlay_", "", 1)
            by_alias[alias] = oid
            if input_type == "radio" and radio_group and "value" in overlay:
                radio_map[oid] = {
                    "group_name": str(radio_group),
                    "value": overlay.get("value"),
                }
    return by_id, by_alias, radio_map


def _build_attribute_sets(
    attribute_config: dict,
) -> tuple[set[str], set[str], dict[str, str], set[str], dict[str, dict], dict[str, dict]]:
    template_var_keys = set()
    simple_attribute_keys = set()
    top_level_map: dict[str, str] = {}
    special_template_vars = {"placeholder_imdb_id", "sep_style", "collection_mode", "use_separator"}
    simple_types = {"boolean_toggle", "select", "text_input", "number"}
    mass_update_defs: dict[str, dict] = {}
    toggle_select_defs: dict[str, dict] = {}

    for section in attribute_config.get("sections", []) if isinstance(attribute_config, dict) else []:
        if not isinstance(section, dict):
            continue
        prefix = section.get("prefix")
        if not prefix:
            continue
        yml_location = section.get("yml_location")
        if yml_location == "template_variables":
            template_var_keys.add(str(prefix))
        elif yml_location == "top_level":
            alias = str(prefix).replace("top_level_", "", 1)
            top_level_map[alias] = str(prefix)
        elif yml_location == "attribute":
            section_type = section.get("type")
            if section_type in simple_types:
                simple_attribute_keys.add(str(prefix))
            elif section_type == "mass_update":
                sources = set()
                raw_sources = section.get("sources")
                if isinstance(raw_sources, list):
                    for source in raw_sources:
                        if isinstance(source, list) and source:
                            sources.add(str(source[0]))
                existing = mass_update_defs.setdefault(
                    str(prefix),
                    {
                        "sources": set(),
                        "has_custom_string": bool(section.get("has_custom_string")),
                        "custom_string_behavior": section.get("custom_string_behavior") or "string",
                    },
                )
                existing["sources"].update(sources)
            elif section_type == "toggle_with_select":
                select_input = section.get("select_input") or {}
                select_key = select_input.get("key")
                select_options = set()
                raw_options = select_input.get("options")
                if isinstance(raw_options, list):
                    for option in raw_options:
                        if isinstance(option, list) and option:
                            value = str(option[0]).strip()
                            if value:
                                select_options.add(value)
                toggle_keys = {str(toggle.get("key")) for toggle in section.get("toggles", []) if isinstance(toggle, dict) and toggle.get("key")}
                existing = toggle_select_defs.setdefault(
                    str(prefix),
                    {"select_key": select_key, "toggle_keys": set(), "select_options": set()},
                )
                if select_key:
                    existing["select_key"] = select_key
                existing["toggle_keys"].update(toggle_keys)
                existing["select_options"].update(select_options)
    return (
        template_var_keys,
        simple_attribute_keys,
        top_level_map,
        special_template_vars,
        mass_update_defs,
        toggle_select_defs,
    )


def _normalize_library_type(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    text = str(value).strip().lower()
    if text in {"movie", "mov"}:
        return "mov", "movie"
    if text in {"show", "sho", "series"}:
        return "sho", "show"
    return None, None


def normalize_library_type(value: Any) -> str | None:
    _, label = _normalize_library_type(value)
    return label


def _resolve_collection_id(raw_default: str, collection_by_id: dict, collection_by_alias: dict) -> str | None:
    if raw_default.startswith("collection_") and raw_default in collection_by_id:
        return raw_default
    return collection_by_alias.get(raw_default)


def _resolve_overlay_id(raw_default: str, overlay_by_id: dict, overlay_by_alias: dict) -> str | None:
    if raw_default.startswith("overlay_") and raw_default in overlay_by_id:
        return raw_default
    if raw_default.startswith("content_rating_"):
        candidate = f"overlay_{raw_default}"
        return candidate if candidate in overlay_by_id else None
    return overlay_by_alias.get(raw_default)


def infer_library_types(config_data: dict) -> tuple[dict[str, str], list[dict]]:
    collection_config = helpers.load_quickstart_config("quickstart_collections.json") or []
    overlay_config = helpers.load_quickstart_config("quickstart_overlays.json") or []
    collection_by_id, collection_by_alias = _build_collection_index(collection_config)
    overlay_by_id, overlay_by_alias, _ = _build_overlay_index(overlay_config)

    inferred_types: dict[str, str] = {}
    details: list[dict] = []

    libraries_payload = config_data.get("libraries")
    if not isinstance(libraries_payload, dict):
        return inferred_types, details

    for lib_name, lib_cfg in libraries_payload.items():
        if not isinstance(lib_cfg, dict):
            continue
        movie_score = 0
        show_score = 0

        collection_files = lib_cfg.get("collection_files")
        if isinstance(collection_files, list):
            for entry in collection_files:
                default_value = None
                if isinstance(entry, dict):
                    default_value = entry.get("default")
                elif isinstance(entry, str):
                    default_value = entry
                if not default_value:
                    continue
                raw_default = str(default_value)
                collection_id = _resolve_collection_id(raw_default, collection_by_id, collection_by_alias)
                if not collection_id:
                    continue
                media_types = collection_by_id.get(collection_id, {}).get("media_types") or []
                is_movie = "movie" in media_types
                is_show = "show" in media_types
                if is_movie and not is_show:
                    movie_score += 2
                elif is_show and not is_movie:
                    show_score += 2
                elif is_movie and is_show:
                    movie_score += 1
                    show_score += 1

        overlay_files = lib_cfg.get("overlay_files")
        if isinstance(overlay_files, list):
            for entry in overlay_files:
                default_value = None
                template_values = None
                if isinstance(entry, dict):
                    default_value = entry.get("default")
                    template_values = entry.get("template_variables")
                elif isinstance(entry, str):
                    default_value = entry
                if not default_value:
                    continue
                if isinstance(template_values, dict):
                    builder_level = template_values.get("builder_level")
                    if builder_level in {"show", "season", "episode"}:
                        show_score += 2
                    elif builder_level == "movie":
                        movie_score += 2

                raw_default = str(default_value)
                overlay_id = _resolve_overlay_id(raw_default, overlay_by_id, overlay_by_alias)
                if not overlay_id:
                    continue
                media_types = overlay_by_id.get(overlay_id, {}).get("media_types") or []
                movie_types = "movie" in media_types
                show_types = any(t in {"show", "season", "episode"} for t in media_types)
                if movie_types and not show_types:
                    movie_score += 1
                elif show_types and not movie_types:
                    show_score += 1
                elif movie_types and show_types:
                    movie_score += 1
                    show_score += 1

        inferred = None
        if show_score > movie_score:
            inferred = "show"
        elif movie_score > show_score:
            inferred = "movie"

        if movie_score == 0 and show_score == 0:
            confidence = "unknown"
        else:
            confidence = "high" if abs(movie_score - show_score) >= 2 else "low"

        if inferred:
            inferred_types[str(lib_name)] = inferred

        details.append(
            {
                "name": str(lib_name),
                "inferred_type": inferred,
                "movie_score": movie_score,
                "show_score": show_score,
                "confidence": confidence,
            }
        )

    return inferred_types, details


def build_library_type_plan(
    config_data: dict,
    plex_movie_names: set[str],
    plex_show_names: set[str],
) -> tuple[dict[str, str], list[dict], bool]:
    inferred_types, details = infer_library_types(config_data)
    detail_map = {d.get("name"): d for d in details}
    library_types: dict[str, str] = {}
    inference_list: list[dict] = []

    libraries_payload = config_data.get("libraries")
    if not isinstance(libraries_payload, dict):
        return library_types, inference_list, False

    for lib_name in libraries_payload.keys():
        name = str(lib_name)
        if name in plex_movie_names:
            inferred_type = "movie"
            source = "plex"
            confidence = "confirmed"
        elif name in plex_show_names:
            inferred_type = "show"
            source = "plex"
            confidence = "confirmed"
        else:
            inferred_type = inferred_types.get(name)
            source = "inferred" if inferred_type else "unknown"
            confidence = detail_map.get(name, {}).get("confidence", "unknown")
        if inferred_type:
            library_types[name] = inferred_type
        detail = detail_map.get(name, {})
        inference_list.append(
            {
                "name": name,
                "source": source,
                "type": inferred_type,
                "confidence": confidence,
                "movie_score": detail.get("movie_score", 0),
                "show_score": detail.get("show_score", 0),
            }
        )

    needs_confirmation = any(item.get("source") != "plex" for item in inference_list)
    return library_types, inference_list, needs_confirmation


def _flatten_dict(base: str, payload: Any, report: ImportReport, max_depth: int = 3) -> None:
    if max_depth <= 0:
        report.add("imported", base)
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{base}.{key}"
            _flatten_dict(child, value, report, max_depth - 1)
        if not payload:
            report.add("imported", base)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            child = f"{base}[{idx}]"
            _flatten_dict(child, value, report, max_depth - 1)
        if not payload:
            report.add("imported", base)
    else:
        report.add("imported", base)


def prepare_import_payload(
    config_data: dict,
    plex_movie_names: set[str],
    plex_show_names: set[str],
    library_type_overrides: dict | None = None,
) -> tuple[dict[str, dict], ImportReport]:
    report = ImportReport()
    payload: dict[str, dict] = {}

    collection_config = helpers.load_quickstart_config("quickstart_collections.json") or []
    overlay_config = helpers.load_quickstart_config("quickstart_overlays.json") or []
    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json") or {}

    collection_by_id, collection_by_alias = _build_collection_index(collection_config)
    overlay_by_id, overlay_by_alias, overlay_radio = _build_overlay_index(overlay_config)
    (
        template_vars,
        simple_attrs,
        top_level_map,
        special_template_vars,
        mass_update_defs,
        toggle_select_defs,
    ) = _build_attribute_sets(attribute_config)

    def _encode_json(values: list) -> str:
        return json.dumps(values, ensure_ascii=True)

    def _clean_custom_value(value: Any) -> Any | None:
        if value is None or value is False:
            return None
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        return text if text else None

    def _normalize_op_items(value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _handle_mass_update_operation(
        lib_id: str,
        lib_name: str,
        op_key: str,
        op_value: Any,
    ) -> tuple[bool, bool]:
        definition = mass_update_defs.get(op_key)
        if not definition:
            return False, False

        sources = definition.get("sources", set())
        has_custom = definition.get("has_custom_string")
        custom_behavior = definition.get("custom_string_behavior") or "string"
        order: list[str] = []
        custom_values: list[Any] = []
        items = _normalize_op_items(op_value)

        for idx, item in enumerate(items):
            item_path = f"libraries.{lib_name}.operations.{op_key}[{idx}]" if isinstance(op_value, list) else f"libraries.{lib_name}.operations.{op_key}"
            if isinstance(item, list):
                for entry in item:
                    custom_value = _clean_custom_value(entry)
                    if custom_value is not None:
                        custom_values.append(custom_value)
                if has_custom and item:
                    report.add("imported", item_path)
                else:
                    report.add("unmapped", item_path, "Unsupported mass update list entry.")
                continue
            if isinstance(item, dict):
                report.add("unmapped", item_path, "Unsupported mass update format.")
                continue

            if isinstance(item, (int, float)):
                if has_custom:
                    custom_values.append(item)
                    report.add("imported", item_path)
                else:
                    report.add("unmapped", item_path, "Custom values are not supported.")
                continue

            text = str(item).strip()
            if not text:
                continue
            if text in sources:
                if text not in order:
                    order.append(text)
                libraries_data[f"{lib_id}-attribute_{op_key}_{text}"] = True
                report.add("imported", item_path)
            elif has_custom:
                custom_values.append(text)
                report.add("imported", item_path)
            else:
                report.add("unmapped", item_path, "Custom values are not supported.")

        if order:
            libraries_data[f"{lib_id}-attribute_{op_key}_order"] = _encode_json(order)

        if custom_values:
            if custom_behavior == "list":
                libraries_data[f"{lib_id}-attribute_{op_key}_custom"] = _encode_json(custom_values)
            else:
                libraries_data[f"{lib_id}-attribute_{op_key}_custom_string"] = _clean_custom_value(custom_values[0])
                if len(custom_values) > 1:
                    libraries_data[f"{lib_id}-attribute_{op_key}_custom"] = _encode_json(custom_values[1:])

        if order or custom_values:
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
            return True, True

        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "No importable values found.")
        return True, False

    def _handle_toggle_select_operation(
        lib_id: str,
        lib_name: str,
        op_key: str,
        op_value: Any,
    ) -> tuple[bool, bool]:
        definition = toggle_select_defs.get(op_key)
        if not definition:
            return False, False

        select_key = definition.get("select_key")
        select_options = set(definition.get("select_options") or [])
        toggle_keys = set(definition.get("toggle_keys") or [])
        toggle_aliases = {}
        for key in toggle_keys:
            toggle_aliases[key] = key
            if key.startswith(f"{op_key}_"):
                toggle_aliases[key.replace(f"{op_key}_", "", 1)] = key

        def resolve_toggle_key(raw_key: str) -> str | None:
            return toggle_aliases.get(raw_key)

        source = None
        imported_any = False

        if isinstance(op_value, dict):
            for raw_key, raw_value in op_value.items():
                key = str(raw_key)
                if key == "source":
                    candidate = str(raw_value).strip()
                    if candidate in select_options:
                        source = candidate
                        report.add("imported", f"libraries.{lib_name}.operations.{op_key}.source")
                        imported_any = True
                    else:
                        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.source")
                    continue
                resolved = resolve_toggle_key(key)
                if resolved:
                    if helpers.booler(raw_value):
                        libraries_data[f"{lib_id}-attribute_{resolved}"] = True
                    report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")
                    imported_any = True
                else:
                    report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{key}")
            if source and select_key:
                libraries_data[f"{lib_id}-attribute_{select_key}"] = source
            return True, imported_any

        if isinstance(op_value, list):
            for idx, item in enumerate(op_value):
                item_path = f"libraries.{lib_name}.operations.{op_key}[{idx}]"
                if isinstance(item, str):
                    text = item.strip()
                    if text in select_options:
                        source = text
                        report.add("imported", item_path)
                        imported_any = True
                        continue
                    resolved = resolve_toggle_key(text)
                    if resolved:
                        libraries_data[f"{lib_id}-attribute_{resolved}"] = True
                        report.add("imported", item_path)
                        imported_any = True
                        continue
                report.add("unmapped", item_path, "Unsupported option.")
            if source and select_key:
                libraries_data[f"{lib_id}-attribute_{select_key}"] = source
            if imported_any:
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
            return True, imported_any

        if isinstance(op_value, str):
            candidate = op_value.strip()
            if candidate in select_options and select_key:
                libraries_data[f"{lib_id}-attribute_{select_key}"] = candidate
                report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
                return True, True
            else:
                report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported option.")
                return True, False

        report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "Unsupported operation format.")
        return True, False

    def _handle_delete_collections_operation(
        lib_id: str,
        lib_name: str,
        op_key: str,
        op_value: Any,
    ) -> tuple[bool, bool]:
        if op_key != "delete_collections":
            return False, False
        if not isinstance(op_value, dict):
            report.add(
                "unmapped",
                f"libraries.{lib_name}.operations.{op_key}",
                "Unsupported delete_collections format.",
            )
            return True, False

        mapping = {
            "configured": "delete_collections_configured",
            "managed": "delete_collections_managed",
            "ignore_empty_smart_collections": "delete_collections_ignore_empty_smart_collections",
            "less": "delete_collections_less",
        }
        imported_any = False

        for raw_key, raw_value in op_value.items():
            key = str(raw_key)
            target = mapping.get(key)
            if not target:
                report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}.{key}")
                continue
            if key == "less":
                try:
                    if raw_value is None or raw_value == "":
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.operations.{op_key}.{key}",
                            "Missing numeric value.",
                        )
                        continue
                    libraries_data[f"{lib_id}-attribute_{target}"] = int(raw_value)
                    report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")
                    imported_any = True
                except Exception:
                    report.add(
                        "unmapped",
                        f"libraries.{lib_name}.operations.{op_key}.{key}",
                        "Invalid numeric value.",
                    )
                continue
            bool_value = None
            if isinstance(raw_value, bool):
                bool_value = raw_value
            elif isinstance(raw_value, str):
                lowered = raw_value.strip().lower()
                if lowered in {"true", "yes", "1"}:
                    bool_value = True
                elif lowered in {"false", "no", "0"}:
                    bool_value = False
            if bool_value is None:
                report.add(
                    "unmapped",
                    f"libraries.{lib_name}.operations.{op_key}.{key}",
                    "Invalid boolean value.",
                )
                continue
            libraries_data[f"{lib_id}-attribute_{target}"] = bool_value
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}.{key}")
            imported_any = True

        if imported_any:
            report.add("imported", f"libraries.{lib_name}.operations.{op_key}")
        else:
            report.add("unmapped", f"libraries.{lib_name}.operations.{op_key}", "No importable values found.")
        return True, imported_any

    for section in SIMPLE_SECTIONS:
        if section not in config_data:
            continue
        section_payload = config_data.get(section)
        if section == "playlist_files":
            libraries = []
            if isinstance(section_payload, list):
                for idx, entry in enumerate(section_payload):
                    if isinstance(entry, dict):
                        tv = entry.get("template_variables", {})
                        if isinstance(tv, dict):
                            libs = tv.get("libraries")
                            if isinstance(libs, list):
                                entry_libs = [str(lib) for lib in libs if str(lib).strip()]
                                libraries.extend(entry_libs)
                                report.add("imported", f"{section}[{idx}]")
                                default_value = entry.get("default")
                                if default_value == "playlist":
                                    report.add("imported", f"{section}[{idx}].default")
                                elif default_value is not None:
                                    report.add("unmapped", f"{section}[{idx}].default", "Unsupported playlist default.")
                                report.add("imported", f"{section}[{idx}].template_variables")
                                report.add("imported", f"{section}[{idx}].template_variables.libraries")
                                for lib_idx in range(len(entry_libs)):
                                    report.add("imported", f"{section}[{idx}].template_variables.libraries[{lib_idx}]")
            if libraries:
                payload[section] = {"playlist_files": {"libraries": ",".join(libraries)}}
                report.add("imported", section)
                report.add("imported", f"{section}.libraries")
            else:
                report.add("unmapped", section, "Missing playlist library entries.")
            continue

        if isinstance(section_payload, dict):
            if section == "settings":
                asset_directory = section_payload.get("asset_directory")
                if isinstance(asset_directory, (str, list)):
                    normalized = (
                        [line.strip() for line in str(asset_directory).splitlines()] if isinstance(asset_directory, str) else [str(item).strip() for item in asset_directory]
                    )
                    normalized = [entry for entry in normalized if entry]
                    section_payload = dict(section_payload)
                    section_payload["asset_directory"] = normalized
            if section == "anidb":
                if "enable" not in section_payload:
                    has_values = any(value not in [None, "", [], {}] for value in section_payload.values())
                    if has_values:
                        section_payload = dict(section_payload)
                        section_payload["enable"] = True
            payload[section] = {section: section_payload}
            _flatten_dict(section, section_payload, report)
        else:
            report.add("unmapped", section, "Unsupported section format.")

    libraries_payload = config_data.get("libraries")
    if isinstance(libraries_payload, dict):
        libraries_data: dict[str, Any] = {}
        existing_ids: set[str] = set()

        for lib_name, lib_cfg in libraries_payload.items():
            if not isinstance(lib_cfg, dict):
                report.add("unmapped", f"libraries.{lib_name}", "Unsupported library entry.")
                continue

            override = None
            if library_type_overrides and str(lib_name) in library_type_overrides:
                override = library_type_overrides.get(str(lib_name))
            override_prefix, override_default = _normalize_library_type(override)

            if lib_name in plex_movie_names:
                lib_type = "mov"
                builder_default = "movie"
            elif lib_name in plex_show_names:
                lib_type = "sho"
                builder_default = "show"
            elif override_prefix and override_default:
                lib_type = override_prefix
                builder_default = override_default
            else:
                report.add("unmapped", f"libraries.{lib_name}", "Library type could not be determined.")
                continue

            lib_id = f"{lib_type}-library_{helpers.normalize_id(str(lib_name), existing_ids)}"
            libraries_data[f"{lib_id}-library"] = lib_name
            report.add("imported", f"libraries.{lib_name}.library")

            # Top-level values
            for yaml_key, field_prefix in top_level_map.items():
                if yaml_key in lib_cfg:
                    libraries_data[f"{lib_id}-{field_prefix}"] = lib_cfg.get(yaml_key)
                    report.add("imported", f"libraries.{lib_name}.{yaml_key}")

            # Library template variables
            lib_template_vars = lib_cfg.get("template_variables")
            if isinstance(lib_template_vars, dict):
                for key, value in lib_template_vars.items():
                    if key in template_vars or key in special_template_vars:
                        if key == "placeholder_imdb_id":
                            name = f"{lib_id}-attribute_template_variables[{key}]"
                            libraries_data[name] = value
                        elif key == "sep_style":
                            name = f"{lib_id}-template_variables[{key}]"
                            libraries_data[name] = value
                            libraries_data[f"{lib_id}-template_variables[use_separator]"] = value
                        else:
                            name = f"{lib_id}-template_variables[{key}]"
                            libraries_data[name] = value
                        report.add("imported", f"libraries.{lib_name}.template_variables.{key}")
                    else:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.template_variables.{key}",
                            "Template variable not available in Quickstart.",
                        )
            elif lib_template_vars is not None:
                report.add("unmapped", f"libraries.{lib_name}.template_variables", "Unsupported template_variables format.")

            # Collections
            collection_files = lib_cfg.get("collection_files")
            if isinstance(collection_files, list):
                for idx, entry in enumerate(collection_files):
                    default_value = None
                    template_values = None
                    if isinstance(entry, dict):
                        default_value = entry.get("default")
                        template_values = entry.get("template_variables")
                    elif isinstance(entry, str):
                        default_value = entry
                    if not default_value:
                        report.add("unmapped", f"libraries.{lib_name}.collection_files[{idx}]", "Missing default.")
                        continue

                    raw_default = str(default_value)
                    collection_id = _resolve_collection_id(raw_default, collection_by_id, collection_by_alias)
                    if not collection_id or collection_id not in collection_by_id:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.collection_files[{idx}].default",
                            "Collection not found in Quickstart.",
                        )
                        continue

                    libraries_data[f"{lib_id}-{collection_id}"] = True
                    report.add("imported", f"libraries.{lib_name}.collection_files[{idx}].default")

                    if isinstance(template_values, dict):
                        allowed = _collect_template_keys(collection_by_id[collection_id].get("template_variables"))
                        clean_id = collection_id.replace("collection_", "", 1)
                        expanded_template_values = dict(template_values)
                        data_block = expanded_template_values.get("data")
                        data_reported = set()
                        if isinstance(data_block, dict):
                            for subkey, subval in data_block.items():
                                flat_key = f"data_{subkey}"
                                if flat_key in allowed and flat_key not in expanded_template_values:
                                    expanded_template_values[flat_key] = subval
                                if flat_key in allowed:
                                    report.add(
                                        "imported",
                                        f"libraries.{lib_name}.collection_files[{idx}].template_variables.data.{subkey}",
                                    )
                                    data_reported.add(subkey)
                            if "data" in expanded_template_values and "data" not in allowed:
                                expanded_template_values.pop("data", None)
                            if data_reported:
                                report.add(
                                    "imported",
                                    f"libraries.{lib_name}.collection_files[{idx}].template_variables.data",
                                )
                        for key, value in expanded_template_values.items():
                            if key in allowed:
                                child_name = f"{lib_id}-template_collection_{clean_id}_{key}"
                                libraries_data[child_name] = value
                                report.add(
                                    "imported",
                                    f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                                )
                            else:
                                report.add(
                                    "unmapped",
                                    f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                                    "Template variable not available in Quickstart.",
                                )

            elif collection_files is not None:
                report.add("unmapped", f"libraries.{lib_name}.collection_files", "Unsupported collection_files format.")

            # Overlays
            overlay_files = lib_cfg.get("overlay_files")
            if isinstance(overlay_files, list):
                for idx, entry in enumerate(overlay_files):
                    default_value = None
                    template_values = None
                    builder_level = builder_default
                    if isinstance(entry, dict):
                        default_value = entry.get("default")
                        template_values = entry.get("template_variables")
                        if isinstance(template_values, dict) and "builder_level" in template_values:
                            level = template_values.get("builder_level")
                            if level in {"show", "season", "episode"}:
                                builder_level = level
                    elif isinstance(entry, str):
                        default_value = entry

                    if not default_value:
                        report.add("unmapped", f"libraries.{lib_name}.overlay_files[{idx}]", "Missing default.")
                        continue

                    raw_default = str(default_value)
                    overlay_id = _resolve_overlay_id(raw_default, overlay_by_id, overlay_by_alias)
                    if overlay_id not in overlay_by_id:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.overlay_files[{idx}].default",
                            "Overlay not found in Quickstart.",
                        )
                        continue

                    overlay_meta = overlay_by_id.get(overlay_id, {})
                    if overlay_id == "overlay_languages" and isinstance(template_values, dict) and str(template_values.get("use_subtitles", "")).strip().lower() == "true":
                        subtitles_id = overlay_by_alias.get("languages_subtitles")
                        if subtitles_id:
                            overlay_id = subtitles_id
                            overlay_meta = overlay_by_id.get(overlay_id, {})
                            template_values = dict(template_values)
                            template_values.pop("use_subtitles", None)
                            report.add(
                                "imported",
                                f"libraries.{lib_name}.overlay_files[{idx}].template_variables.use_subtitles",
                            )
                    media_types = overlay_meta.get("media_types") or []
                    if builder_level == "movie" and media_types and "movie" not in media_types:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.overlay_files[{idx}].default",
                            "Overlay not available for movie libraries.",
                        )
                        continue
                    if builder_level not in media_types and builder_level != "movie":
                        if "show" in media_types:
                            builder_level = "show"
                        elif media_types:
                            builder_level = media_types[0]

                    radio_info = overlay_radio.get(overlay_id)
                    if radio_info:
                        radio_key = f"{lib_id}-{builder_level}-{radio_info['group_name']}"
                        libraries_data[radio_key] = radio_info.get("value")
                    else:
                        libraries_data[f"{lib_id}-{builder_level}-{overlay_id}"] = True
                    report.add("imported", f"libraries.{lib_name}.overlay_files[{idx}].default")

                    if isinstance(template_values, dict):
                        allowed = _collect_template_keys(overlay_meta.get("template_variables"))
                        for key, value in template_values.items():
                            if key not in allowed:
                                if key == "builder_level":
                                    continue
                                report.add(
                                    "unmapped",
                                    f"libraries.{lib_name}.overlay_files[{idx}].template_variables.{key}",
                                    "Template variable not available in Quickstart.",
                                )
                                continue
                            child_name = f"{lib_id}-{builder_level}-template_{overlay_id}[{key}]"
                            libraries_data[child_name] = value
                            report.add(
                                "imported",
                                f"libraries.{lib_name}.overlay_files[{idx}].template_variables.{key}",
                            )

            elif overlay_files is not None:
                report.add("unmapped", f"libraries.{lib_name}.overlay_files", "Unsupported overlay_files format.")

            # Operations
            operations = lib_cfg.get("operations")
            if isinstance(operations, dict):
                imported_ops = False
                for key, value in operations.items():
                    if key in simple_attrs and not isinstance(value, (dict, list)):
                        libraries_data[f"{lib_id}-attribute_{key}"] = value
                        report.add("imported", f"libraries.{lib_name}.operations.{key}")
                        imported_ops = True
                        continue

                    handled, imported = _handle_delete_collections_operation(lib_id, str(lib_name), key, value)
                    if handled:
                        imported_ops = imported_ops or imported
                        continue

                    handled, imported = _handle_mass_update_operation(lib_id, str(lib_name), key, value)
                    if handled:
                        imported_ops = imported_ops or imported
                        continue

                    handled, imported = _handle_toggle_select_operation(lib_id, str(lib_name), key, value)
                    if handled:
                        imported_ops = imported_ops or imported
                        continue
                    report.add(
                        "unmapped",
                        f"libraries.{lib_name}.operations.{key}",
                        "Complex operation not supported for import.",
                    )
                if imported_ops:
                    report.add("imported", f"libraries.{lib_name}.operations")
            elif operations is not None:
                report.add("unmapped", f"libraries.{lib_name}.operations", "Unsupported operations format.")

            handled_keys = {"collection_files", "overlay_files", "template_variables", "operations"}
            handled_keys.update(top_level_map.keys())
            for key in lib_cfg.keys():
                if key in handled_keys:
                    continue
                report.add(
                    "unmapped",
                    f"libraries.{lib_name}.{key}",
                    "Field not supported for import.",
                )

        if libraries_data:
            payload["libraries"] = {"libraries": libraries_data}
        else:
            report.add("unmapped", "libraries", "No importable libraries found.")

    elif libraries_payload is not None:
        report.add("unmapped", "libraries", "Unsupported libraries format.")

    for key in config_data.keys():
        if key in SIMPLE_SECTIONS or key == "libraries":
            continue
        report.add("unmapped", str(key), "Section not supported in Quickstart.")

    return payload, report
