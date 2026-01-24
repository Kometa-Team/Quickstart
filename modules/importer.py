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
            by_id[oid] = overlay
            alias = oid.replace("overlay_", "", 1)
            by_alias[alias] = oid
            if input_type == "radio" and radio_group and "value" in overlay:
                radio_map[oid] = {
                    "group_name": str(radio_group),
                    "value": overlay.get("value"),
                }
    return by_id, by_alias, radio_map


def _build_attribute_sets(attribute_config: dict) -> tuple[set[str], set[str], dict[str, str], set[str]]:
    template_var_keys = set()
    simple_attribute_keys = set()
    top_level_map: dict[str, str] = {}
    special_template_vars = {"placeholder_imdb_id"}
    simple_types = {"boolean_toggle", "select", "text_input", "number"}

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
            if section.get("type") in simple_types:
                simple_attribute_keys.add(str(prefix))
    return template_var_keys, simple_attribute_keys, top_level_map, special_template_vars


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
) -> tuple[dict[str, dict], ImportReport]:
    report = ImportReport()
    payload: dict[str, dict] = {}

    collection_config = helpers.load_quickstart_config("quickstart_collections.json") or []
    overlay_config = helpers.load_quickstart_config("quickstart_overlays.json") or []
    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json") or {}

    collection_by_id, collection_by_alias = _build_collection_index(collection_config)
    overlay_by_id, overlay_by_alias, overlay_radio = _build_overlay_index(overlay_config)
    template_vars, simple_attrs, top_level_map, special_template_vars = _build_attribute_sets(attribute_config)

    for section in SIMPLE_SECTIONS:
        if section not in config_data:
            continue
        section_payload = config_data.get(section)
        if section == "playlist_files":
            libraries = []
            if isinstance(section_payload, list):
                for entry in section_payload:
                    if isinstance(entry, dict):
                        tv = entry.get("template_variables", {})
                        if isinstance(tv, dict):
                            libs = tv.get("libraries")
                            if isinstance(libs, list):
                                libraries.extend([str(lib) for lib in libs if str(lib).strip()])
            if libraries:
                payload[section] = {"playlist_files": {"libraries": ",".join(libraries)}}
                report.add("imported", f"{section}.libraries")
            else:
                report.add("unmapped", section, "Missing playlist library entries.")
            continue

        if isinstance(section_payload, dict):
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

            if lib_name in plex_movie_names:
                lib_type = "mov"
                builder_default = "movie"
            elif lib_name in plex_show_names:
                lib_type = "sho"
                builder_default = "show"
            else:
                report.add("unmapped", f"libraries.{lib_name}", "Library type not found in Plex lists.")
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
                    if raw_default.startswith("collection_"):
                        collection_id = raw_default
                    else:
                        collection_id = collection_by_alias.get(raw_default)
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
                        for key, value in template_values.items():
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
                    if raw_default.startswith("overlay_"):
                        overlay_id = raw_default
                    elif raw_default.startswith("content_rating_"):
                        overlay_id = f"overlay_{raw_default}"
                    else:
                        overlay_id = overlay_by_alias.get(raw_default)

                    if overlay_id not in overlay_by_id:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.overlay_files[{idx}].default",
                            "Overlay not found in Quickstart.",
                        )
                        continue

                    overlay_meta = overlay_by_id.get(overlay_id, {})
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

            # Operations (simple values only)
            operations = lib_cfg.get("operations")
            if isinstance(operations, dict):
                for key, value in operations.items():
                    if key in simple_attrs and not isinstance(value, (dict, list)):
                        libraries_data[f"{lib_id}-attribute_{key}"] = value
                        report.add("imported", f"libraries.{lib_name}.operations.{key}")
                    else:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.operations.{key}",
                            "Complex operation not supported for import.",
                        )
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
