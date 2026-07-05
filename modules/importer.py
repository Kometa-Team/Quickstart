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
    "apprise",
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

LIBRARY_RADARR_IMPORT_FIELDS = {
    "url": "string",
    "token": "string",
    "root_folder_path": "string",
    "quality_profile": "string",
    "availability": "string",
    "tag": "string",
    "monitor": "bool",
    "search": "bool",
    "add_missing": "bool",
    "add_existing": "bool",
    "upgrade_existing": "bool",
    "monitor_existing": "bool",
    "ignore_cache": "bool",
    "radarr_path": "string",
    "plex_path": "string",
}
LIBRARY_SONARR_IMPORT_FIELDS = {
    "url": "string",
    "token": "string",
    "root_folder_path": "string",
    "quality_profile": "string",
    "language_profile": "string",
    "series_type": "string",
    "season_folder": "bool",
    "monitor": "string",
    "tag": "string",
    "search": "bool",
    "cutoff_search": "bool",
    "add_missing": "bool",
    "add_existing": "bool",
    "upgrade_existing": "bool",
    "monitor_existing": "bool",
    "ignore_cache": "bool",
    "sonarr_path": "string",
    "plex_path": "string",
}
# Language codes recognized as `weight_<code>` overlay-source ordering keys.
# Hoisted out of prepare_import_payload's ~95-line nested comprehension --
# this is data, not logic, and belongs at module scope where it's easy to
# review and doesn't rebuild on every import call.
LANGUAGE_WEIGHT_TEMPLATE_KEYS: frozenset[str] = frozenset(
    f"weight_{key}"
    for key in (
        "en",
        "de",
        "fr",
        "es",
        "pt",
        "ja",
        "ko",
        "zh",
        "da",
        "ru",
        "it",
        "hi",
        "te",
        "fa",
        "th",
        "nl",
        "no",
        "is",
        "sv",
        "tr",
        "pl",
        "cs",
        "uk",
        "hu",
        "ar",
        "bg",
        "bn",
        "bs",
        "ca",
        "cy",
        "el",
        "et",
        "eu",
        "fi",
        "tl",
        "fil",
        "gl",
        "he",
        "hr",
        "id",
        "ka",
        "kk",
        "kn",
        "la",
        "lt",
        "lv",
        "mk",
        "ml",
        "mr",
        "ms",
        "nb",
        "nn",
        "pa",
        "ro",
        "sk",
        "sl",
        "sq",
        "sr",
        "so",
        "sw",
        "ta",
        "ur",
        "ay",
        "ga",
        "li",
        "kh",
        "vi",
        "mn",
        "af",
        "bm",
        "ln",
        "wo",
        "lo",
        "myn",
        "iu",
        "rom",
        "am",
        "su",
        "zu",
        "lb",
        "mos",
    )
)


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
        suffix = f" :: {reason}" if reason else ""
        self.lines.append(f"{status}: {path}{suffix}")
        self.counts[status] += 1

    def summary(self) -> dict[str, int]:
        return dict(self.counts)


# YAML report-annotation helpers moved to modules/importer_yaml_annotation.py.
# Re-exported here because external callers (import_config_routes,
# tests/test_importer_edge_cases) reach them through `importer.X`, and
# tests/test_template_gap_analyzer monkeypatches `importer._parse_report_details`.
from modules.importer_yaml_annotation import (  # noqa: E402
    _append_status_annotation,  # noqa: F401 (kept for test monkeypatch surface)
    _build_prefix_flags,  # noqa: F401 (kept for test monkeypatch surface)
    _format_report_status,  # noqa: F401 (kept for test monkeypatch surface)
    _lookup_report_reason,  # noqa: F401 (kept for test monkeypatch surface)
    _parse_mapping_key,  # noqa: F401 (kept for test monkeypatch surface)
    _parse_report_details,  # noqa: F401 (monkeypatched by tests/test_template_gap_analyzer)
    _parse_report_statuses,  # noqa: F401 (kept for test monkeypatch surface)
    _split_inline_comment,  # noqa: F401 (kept for test monkeypatch surface)
    _status_from_flags,  # noqa: F401 (kept for test monkeypatch surface)
    annotate_yaml_with_report,  # noqa: F401 (public API, called as importer.annotate_yaml_with_report)
)

# Library-type inference + collection/overlay index builders moved to
# modules/importer_library_types.py.  Re-exported here because
# blueprints/import_config_routes.py calls `importer.build_library_type_plan`
# and the mega prepare_import_payload (which stayed in this module)
# still calls `_build_collection_index` / `_build_overlay_index`.
from modules.importer_library_types import (  # noqa: E402
    _build_collection_index,  # noqa: F401 (used below by prepare_import_payload)
    _build_overlay_index,  # noqa: F401 (used below by prepare_import_payload)
    _normalize_library_type,  # noqa: F401 (kept accessible via importer._normalize_library_type)
    _resolve_collection_id,  # noqa: F401 (kept accessible via importer._resolve_collection_id)
    _resolve_overlay_id,  # noqa: F401 (kept accessible via importer._resolve_overlay_id)
    build_library_type_plan,  # noqa: F401 (public API, called as importer.build_library_type_plan)
    infer_library_types,  # noqa: F401 (public API, called as importer.infer_library_types)
    normalize_library_type,  # noqa: F401 (public API, called as importer.normalize_library_type)
)

# Value-coercion and serialization helpers moved to
# modules/importer_value_coercion.py.  Re-exported here because
# prepare_import_payload (which stayed in this module) calls all of them,
# and tests/test_importer_edge_cases monkeypatches importer._coerce_import_bool.
from modules.importer_value_coercion import (  # noqa: E402
    _coerce_import_bool,  # noqa: F401 (regression-guarded by tests/test_importer_edge_cases)
    _coerce_import_bool_text,  # noqa: F401 (kept accessible via importer._coerce_import_bool_text)
    _coerce_import_int,  # noqa: F401 (kept accessible via importer._coerce_import_int)
    _coerce_import_string_list,  # noqa: F401 (kept accessible via importer._coerce_import_string_list)
    _collect_dynamic_child_field_specs,  # noqa: F401 (kept accessible via importer._collect_dynamic_child_field_specs)
    _collect_overlay_source_override_keys,  # noqa: F401 (kept accessible via importer._collect_overlay_source_override_keys)
    _collect_template_keys,  # noqa: F401 (kept accessible via importer._collect_template_keys)
    _has_template_string_list_values,  # noqa: F401 (kept accessible via importer._has_template_string_list_values)
    _serialize_dynamic_child_mapping_value,  # noqa: F401 (kept accessible via importer._serialize_dynamic_child_mapping_value)
    _serialize_playlist_import_value,  # noqa: F401 (kept accessible via importer._serialize_playlist_import_value)
)

# Library-operation dispatch handlers moved to modules/importer_operations.py.
# Imported as a module (not name-by-name) because the call sites inside
# prepare_import_payload pass kwargs and the `importer_operations.` prefix
# makes it obvious these are the operation-handler cluster.
from modules import importer_operations  # noqa: E402

# Playlist section parser moved to modules/importer_playlists.py.
# Both PLAYLIST_*_IMPORT_FIELDS constants are re-exported here because:
#   * scripts/analyze_uploaded_template_gaps.py reads them as
#     importer.PLAYLIST_SHARED_IMPORT_FIELDS / importer.PLAYLIST_KEYED_IMPORT_FIELDS
#     (guarded by tests/test_template_gap_analyzer)
#   * The libraries block downstream still uses PLAYLIST_SHARED_IMPORT_FIELDS
#     for one type-check on playlist template values.
from modules import importer_playlists  # noqa: E402
from modules.importer_playlists import (  # noqa: E402
    PLAYLIST_KEYED_IMPORT_FIELDS,  # noqa: F401 (scripts/analyze_uploaded_template_gaps.py)
    PLAYLIST_SHARED_IMPORT_FIELDS,  # noqa: F401 (used by libraries block below + scripts)
)


def _build_attribute_sets(
    attribute_config: dict,
) -> tuple[set[str], set[str], dict[str, str], set[str], dict[str, dict], dict[str, dict]]:
    template_var_keys = set()
    simple_attribute_keys = set()
    top_level_map: dict[str, str] = {}
    special_template_vars = {
        "placeholder_imdb_id",
        "placeholder_tmdb_movie",
        "placeholder_tvdb_show",
        "sep_style",
        "collection_mode",
        "use_separator",
    }
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
    overlay_config = helpers.load_quickstart_overlay_config() or []
    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json") or {}
    inferred_types, _ = infer_library_types(config_data)

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

    _playlist_state = importer_playlists.parse_playlist_config(config_data, report)
    playlist_libraries = _playlist_state.libraries
    playlist_file_entries = _playlist_state.file_entries
    playlist_template_field_values = _playlist_state.template_field_values
    playlist_keyed_template_field_values = _playlist_state.keyed_template_field_values

    for section in SIMPLE_SECTIONS:
        if section not in config_data:
            continue
        section_payload = config_data.get(section)
        if section == "playlist_files":
            continue

        if section == "apprise":
            apprise_location = None
            if isinstance(section_payload, dict):
                if "config" in section_payload:
                    apprise_location = section_payload.get("config")
                elif "location" in section_payload:
                    apprise_location = section_payload.get("location")
                elif "apprise" in section_payload:
                    nested_apprise = section_payload.get("apprise")
                    if isinstance(nested_apprise, dict):
                        apprise_location = nested_apprise.get("config") or nested_apprise.get("location")
                    else:
                        apprise_location = nested_apprise
            elif isinstance(section_payload, str):
                apprise_location = section_payload

            apprise_location = str(apprise_location).strip() if apprise_location is not None else ""
            if apprise_location:
                normalized_apprise = {"location": apprise_location}
                payload[section] = {section: normalized_apprise}
                _flatten_dict(section, normalized_apprise, report)
            else:
                report.add("unmapped", section, "Unsupported section format.")
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
        matched_playlist_libraries: set[str] = set()

        for lib_name, lib_cfg in libraries_payload.items():
            if not isinstance(lib_cfg, dict):
                report.add("unmapped", f"libraries.{lib_name}", "Unsupported library entry.")
                continue

            override = None
            if library_type_overrides and str(lib_name) in library_type_overrides:
                override = library_type_overrides.get(str(lib_name))
            override_prefix, override_default = _normalize_library_type(override)

            name = str(lib_name)
            resolved_name = name
            if name in plex_movie_names:
                lib_type = "mov"
                builder_default = "movie"
            elif name in plex_show_names:
                lib_type = "sho"
                builder_default = "show"
            elif override_prefix and override_default:
                lib_type = override_prefix
                builder_default = override_default
            else:
                inferred = inferred_types.get(name)
                if inferred == "movie":
                    lib_type = "mov"
                    builder_default = "movie"
                elif inferred == "show":
                    lib_type = "sho"
                    builder_default = "show"
                else:
                    report.add("unmapped", f"libraries.{lib_name}", "Library type could not be determined.")
                    continue

            lib_id = f"{lib_type}-library_{helpers.normalize_id(name, existing_ids)}"
            libraries_data[f"{lib_id}-library"] = resolved_name
            report.add("imported", f"libraries.{lib_name}.library")
            playlist_names_for_library = {name, resolved_name}
            matched_names = playlist_libraries.intersection(playlist_names_for_library)
            if matched_names:
                libraries_data[f"{lib_id}-playlist"] = "true"
                matched_playlist_libraries.update(matched_names)
                report.add("imported", f"libraries.{lib_name}.playlist_files")

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
                        if key in {"placeholder_imdb_id", "placeholder_tmdb_movie", "placeholder_tvdb_show"}:
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
                imported_collection_files = []
                for idx, entry in enumerate(collection_files):
                    default_value = None
                    template_values = None
                    raw_entry_type = None
                    raw_entry_location = None
                    if isinstance(entry, dict):
                        default_value = entry.get("default")
                        template_values = entry.get("template_variables")
                        for candidate in ("file", "folder", "url", "git", "repo"):
                            location = entry.get(candidate)
                            if location:
                                raw_entry_type = candidate
                                raw_entry_location = str(location)
                                break
                    elif isinstance(entry, str):
                        default_value = entry
                    if raw_entry_type and raw_entry_location:
                        imported_collection_files.append({"type": raw_entry_type, "location": raw_entry_location})
                        report.add("imported", f"libraries.{lib_name}.collection_files[{idx}].{raw_entry_type}")
                        continue
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
                        dynamic_child_fields = _collect_dynamic_child_field_specs(collection_by_id[collection_id].get("template_variables"))
                        clean_id = collection_id.replace("collection_", "", 1)
                        expanded_template_values = dict(template_values)
                        data_block = expanded_template_values.get("data")
                        data_reported = set()
                        pending_dynamic_child_maps: dict[str, dict[str, str]] = {}
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
                        if _has_template_string_list_values(expanded_template_values.get("include")) and _has_template_string_list_values(expanded_template_values.get("exclude")):
                            report.add(
                                "skipped",
                                f"libraries.{lib_name}.collection_files[{idx}].template_variables.include_exclude_warning",
                                "Warning - include and exclude were both imported. Kometa code allows this, but the wiki says not to combine them.",
                            )
                        for key, value in expanded_template_values.items():
                            if key in allowed:
                                child_name = f"{lib_id}-template_collection_{clean_id}_{key}"
                                if isinstance(value, list):
                                    libraries_data[child_name] = json.dumps(value, ensure_ascii=True)
                                else:
                                    libraries_data[child_name] = value
                                report.add(
                                    "imported",
                                    f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                                )
                            else:
                                matched_dynamic_child = next(
                                    (spec for spec in dynamic_child_fields if key.startswith(spec["child_prefix"]) and key != spec["child_prefix"]),
                                    None,
                                )
                                if matched_dynamic_child:
                                    suffix = key[len(matched_dynamic_child["child_prefix"]) :].strip()
                                    serialized_value = _serialize_dynamic_child_mapping_value(
                                        value,
                                        matched_dynamic_child["value_kind"],
                                    )
                                    if suffix and serialized_value:
                                        pending_dynamic_child_maps.setdefault(
                                            matched_dynamic_child["field_key"],
                                            {},
                                        )[suffix] = serialized_value
                                        report.add(
                                            "imported",
                                            f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                                        )
                                        continue
                                report.add(
                                    "unmapped",
                                    f"libraries.{lib_name}.collection_files[{idx}].template_variables.{key}",
                                    "Template variable not available in Quickstart.",
                                )

                        for field_key, field_map in pending_dynamic_child_maps.items():
                            if not field_map:
                                continue
                            libraries_data[f"{lib_id}-template_collection_{clean_id}_{field_key}"] = json.dumps(field_map, ensure_ascii=True)

                if imported_collection_files:
                    libraries_data[f"{lib_id}-collection_files"] = json.dumps(imported_collection_files, ensure_ascii=True)
                    report.add("imported", f"libraries.{lib_name}.collection_files")

            elif collection_files is not None:
                report.add("unmapped", f"libraries.{lib_name}.collection_files", "Unsupported collection_files format.")

            # Overlays
            overlay_files = lib_cfg.get("overlay_files")
            if isinstance(overlay_files, list):
                imported_overlay_files = []
                for idx, entry in enumerate(overlay_files):
                    default_value = None
                    template_values = None
                    builder_level = builder_default
                    raw_entry_type = None
                    raw_entry_location = None
                    if isinstance(entry, dict):
                        default_value = entry.get("default")
                        template_values = entry.get("template_variables")
                        for candidate in ("file", "folder", "url", "git", "repo"):
                            location = entry.get(candidate)
                            if location:
                                raw_entry_type = candidate
                                raw_entry_location = str(location)
                                break
                        if isinstance(template_values, dict) and "builder_level" in template_values:
                            level = template_values.get("builder_level")
                            if level in {"show", "season", "episode"}:
                                builder_level = level
                    elif isinstance(entry, str):
                        default_value = entry

                    if raw_entry_type and raw_entry_location:
                        imported_overlay_files.append({"type": raw_entry_type, "location": raw_entry_location})
                        report.add("imported", f"libraries.{lib_name}.overlay_files[{idx}].{raw_entry_type}")
                        continue

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
                        allowed.update(_collect_overlay_source_override_keys(overlay_meta))
                        if overlay_id in {"overlay_languages", "overlay_languages_subtitles"}:
                            allowed = set(allowed)
                            allowed.update(LANGUAGE_WEIGHT_TEMPLATE_KEYS)
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

                if imported_overlay_files:
                    libraries_data[f"{lib_id}-overlay_files"] = json.dumps(imported_overlay_files, ensure_ascii=True)
                    report.add("imported", f"libraries.{lib_name}.overlay_files")

            elif overlay_files is not None:
                report.add("unmapped", f"libraries.{lib_name}.overlay_files", "Unsupported overlay_files format.")

            metadata_files = lib_cfg.get("metadata_files")
            if isinstance(metadata_files, list):
                imported_metadata_files = []
                for idx, entry in enumerate(metadata_files):
                    entry_type = None
                    location = None
                    if isinstance(entry, dict):
                        if "file" in entry:
                            entry_type = "file"
                            location = entry.get("file")
                        elif "folder" in entry:
                            entry_type = "folder"
                            location = entry.get("folder")
                        elif "git" in entry:
                            entry_type = "git"
                            location = entry.get("git")
                        elif "repo" in entry:
                            entry_type = "repo"
                            location = entry.get("repo")
                        elif "url" in entry:
                            entry_type = "url"
                            location = entry.get("url")
                    if entry_type not in {"file", "folder", "url", "git", "repo"}:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.metadata_files[{idx}]",
                            "Only file, folder, url, git, and repo metadata files are supported.",
                        )
                        continue
                    location = str(location or "").strip()
                    if not location:
                        report.add(
                            "unmapped",
                            f"libraries.{lib_name}.metadata_files[{idx}]",
                            "Metadata file location is required.",
                        )
                        continue
                    imported_metadata_files.append({"type": entry_type, "location": location})
                    report.add("imported", f"libraries.{lib_name}.metadata_files[{idx}].{entry_type}")

                if imported_metadata_files:
                    libraries_data[f"{lib_id}-metadata_files"] = json.dumps(imported_metadata_files, ensure_ascii=True)
                    report.add("imported", f"libraries.{lib_name}.metadata_files")
            elif metadata_files is not None:
                report.add("unmapped", f"libraries.{lib_name}.metadata_files", "Unsupported metadata_files format.")

            # Library settings
            settings_section = lib_cfg.get("settings")
            if isinstance(settings_section, dict):
                imported_settings = False
                for key, value in settings_section.items():
                    if key == "asset_directory":
                        if isinstance(value, list):
                            normalized = [str(item).strip() for item in value if str(item).strip()]
                        elif isinstance(value, str):
                            normalized = [line.strip() for line in value.splitlines() if line.strip()]
                        else:
                            normalized = []

                        if normalized:
                            libraries_data[f"{lib_id}-attribute_{key}"] = normalized
                            report.add("imported", f"libraries.{lib_name}.settings.{key}")
                            imported_settings = True
                        else:
                            report.add(
                                "unmapped",
                                f"libraries.{lib_name}.settings.{key}",
                                "No importable asset directory entries found.",
                            )
                        continue

                    if key == "prioritize_assets" and not isinstance(value, (dict, list)):
                        bool_value = None
                        if isinstance(value, bool):
                            bool_value = value
                        elif isinstance(value, str):
                            lowered = value.strip().lower()
                            if lowered in {"true", "yes", "1"}:
                                bool_value = True
                            elif lowered in {"false", "no", "0"}:
                                bool_value = False

                        if bool_value is None:
                            report.add(
                                "unmapped",
                                f"libraries.{lib_name}.settings.{key}",
                                "Invalid boolean value.",
                            )
                        else:
                            libraries_data[f"{lib_id}-attribute_{key}"] = bool_value
                            report.add("imported", f"libraries.{lib_name}.settings.{key}")
                            imported_settings = True
                        continue

                    report.add(
                        "unmapped",
                        f"libraries.{lib_name}.settings.{key}",
                        "Library setting not supported for import.",
                    )

                if imported_settings:
                    report.add("imported", f"libraries.{lib_name}.settings")
            elif settings_section is not None:
                report.add("unmapped", f"libraries.{lib_name}.settings", "Unsupported settings format.")

            for service_name, field_map in (
                ("radarr", LIBRARY_RADARR_IMPORT_FIELDS),
                ("sonarr", LIBRARY_SONARR_IMPORT_FIELDS),
            ):
                service_section = lib_cfg.get(service_name)
                if not isinstance(service_section, dict):
                    if service_section is not None:
                        report.add("unmapped", f"libraries.{lib_name}.{service_name}", "Unsupported service override format.")
                    continue

                imported_service = False
                if service_name == "radarr" and not str(lib_id).startswith("mov-library_"):
                    report.add("unmapped", f"libraries.{lib_name}.radarr", "Radarr overrides are only supported on movie libraries.")
                    continue
                if service_name == "sonarr" and not str(lib_id).startswith("sho-library_"):
                    report.add("unmapped", f"libraries.{lib_name}.sonarr", "Sonarr overrides are only supported on show libraries.")
                    continue

                for key, value in service_section.items():
                    field_type = field_map.get(str(key))
                    if not field_type:
                        report.add("unmapped", f"libraries.{lib_name}.{service_name}.{key}", "Library service override not supported for import.")
                        continue

                    target_key = f"{lib_id}-attribute_{service_name}_{key}"
                    if field_type == "bool":
                        bool_value = _coerce_import_bool(value)
                        if bool_value is None:
                            report.add("unmapped", f"libraries.{lib_name}.{service_name}.{key}", "Invalid boolean value.")
                            continue
                        libraries_data[target_key] = "true" if bool_value else "false"
                    else:
                        if isinstance(value, (dict, list)):
                            report.add("unmapped", f"libraries.{lib_name}.{service_name}.{key}", "Unsupported override value format.")
                            continue
                        text_value = str(value).strip()
                        if not text_value:
                            report.add("unmapped", f"libraries.{lib_name}.{service_name}.{key}", "Override value is empty.")
                            continue
                        libraries_data[target_key] = text_value

                    report.add("imported", f"libraries.{lib_name}.{service_name}.{key}")
                    imported_service = True

                if imported_service:
                    report.add("imported", f"libraries.{lib_name}.{service_name}")

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

                    handled, imported = importer_operations.handle_delete_collections_operation(
                        lib_id,
                        str(lib_name),
                        key,
                        value,
                        libraries_data=libraries_data,
                        report=report,
                    )
                    if handled:
                        imported_ops = imported_ops or imported
                        continue

                    handled, imported = importer_operations.handle_mass_update_operation(
                        lib_id,
                        str(lib_name),
                        key,
                        value,
                        mass_update_defs=mass_update_defs,
                        libraries_data=libraries_data,
                        report=report,
                    )
                    if handled:
                        imported_ops = imported_ops or imported
                        continue

                    handled, imported = importer_operations.handle_toggle_select_operation(
                        lib_id,
                        str(lib_name),
                        key,
                        value,
                        toggle_select_defs=toggle_select_defs,
                        libraries_data=libraries_data,
                        report=report,
                    )
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

            handled_keys = {"collection_files", "overlay_files", "metadata_files", "template_variables", "settings", "operations", "radarr", "sonarr"}
            handled_keys.update(top_level_map.keys())
            for key in lib_cfg.keys():
                if key in handled_keys:
                    continue
                report.add(
                    "unmapped",
                    f"libraries.{lib_name}.{key}",
                    "Field not supported for import.",
                )

        for key, value in playlist_template_field_values.items():
            hidden_name = f"playlist-template_variables[{key}]"
            if key in {"sync_to_users", "exclude_users"}:
                libraries_data[hidden_name] = ", ".join(str(item).strip() for item in value if str(item).strip())
            elif PLAYLIST_SHARED_IMPORT_FIELDS.get(key) == "string_list":
                libraries_data[hidden_name] = json.dumps(value, ensure_ascii=True)
            else:
                libraries_data[hidden_name] = value
        for prefix, mapping in playlist_keyed_template_field_values.items():
            canonical_prefix = "exclude_users_" if prefix == "exclude_user_" else prefix
            if mapping:
                libraries_data[f"playlist-template_variables[{canonical_prefix}]"] = json.dumps(mapping, ensure_ascii=True)
        if playlist_file_entries:
            libraries_data["playlist_files_entries"] = json.dumps(playlist_file_entries, ensure_ascii=True)

        if libraries_data:
            payload["libraries"] = {"libraries": libraries_data}
            for playlist_library in sorted(playlist_libraries - matched_playlist_libraries):
                report.add(
                    "unmapped",
                    f"playlist_files.libraries.{playlist_library}",
                    "No matching imported library found.",
                )
        else:
            report.add("unmapped", "libraries", "No importable libraries found.")

    elif libraries_payload is not None:
        report.add("unmapped", "libraries", "Unsupported libraries format.")
    elif playlist_libraries:
        report.add("unmapped", "playlist_files", "Playlist selections are imported through Libraries; no importable libraries were found.")

    for key in config_data.keys():
        if key in SIMPLE_SECTIONS or key == "libraries":
            continue
        report.add("unmapped", str(key), "Section not supported in Quickstart.")

    return payload, report
