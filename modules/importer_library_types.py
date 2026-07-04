"""Kometa library-type inference and collection/overlay index builders.

Extracted from :mod:`modules.importer` to isolate the ~283 lines of
"figure out what kind of library each Plex library is and which
collections/overlays it can support" logic.

## Public API

* :func:`infer_library_types` -- Given a user's uploaded
  ``config.yml`` dict, return ``(library_types, inference_list)``
  where ``library_types`` maps library names to types
  (``"movie"``, ``"show"``, ``"music"``, ...) and
  ``inference_list`` describes how each guess was made (from an
  explicit ``library_type`` key, from operations/collections
  present, or as a fallback).
* :func:`build_library_type_plan` -- Combines
  :func:`infer_library_types` with the caller-provided
  movie/show library-name sets from Plex to produce the final
  ``(library_types, library_inference, needs_confirmation)``
  triple used by the import-preview UI.
* :func:`normalize_library_type` -- Public wrapper around the
  internal ``_normalize_library_type`` helper.

## Internal (leading ``_``) helpers

* ``_normalize_library_type`` -- Canonicalize a raw
  ``library_type`` value from user YAML.
* ``_build_collection_index`` /
  ``_build_overlay_index`` -- Load
  ``quickstart_collections.json`` /
  ``quickstart_overlays.json`` and index them by id + alias +
  radio-group for fast lookup.
* ``_resolve_collection_id`` /
  ``_resolve_overlay_id`` -- Match a user-provided default
  string against the id or alias indexes.

The two index-builder helpers are re-exported from
:mod:`modules.importer` because ``prepare_import_payload`` (which
stays in that module) also calls them.

Dependency direction: ``importer -> importer_library_types``
(one way).  This module has zero imports from ``importer``, so
no circular imports possible.
"""

from __future__ import annotations

from typing import Any

from modules import helpers


def _build_collection_index(collection_config: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    by_id: dict[str, dict] = {}
    by_alias: dict[str, str] = {}
    for group in collection_config or []:
        for collection in group.get("collections", []) if isinstance(group, dict) else []:
            cid = collection.get("id")
            if not cid:
                continue
            if cid in by_id:
                existing = by_id[cid]
                if isinstance(existing, dict):
                    existing_media = existing.get("media_types")
                    new_media = collection.get("media_types")
                    if isinstance(existing_media, list) or isinstance(new_media, list):
                        merged_media = []
                        for entry in existing_media or []:
                            if entry not in merged_media:
                                merged_media.append(entry)
                        for entry in new_media or []:
                            if entry not in merged_media:
                                merged_media.append(entry)
                        existing["media_types"] = merged_media

                    existing_templates = existing.get("template_variables")
                    new_templates = collection.get("template_variables")
                    if isinstance(existing_templates, list) and isinstance(new_templates, list):
                        seen_keys = {str(item.get("key")) for item in existing_templates if isinstance(item, dict) and item.get("key")}
                        for item in new_templates:
                            if not isinstance(item, dict):
                                continue
                            key = str(item.get("key") or "").strip()
                            if key and key in seen_keys:
                                continue
                            existing_templates.append(item)
                            if key:
                                seen_keys.add(key)
                    elif existing.get("template_variables") in (None, [], {}):
                        existing["template_variables"] = new_templates
                alias = cid.replace("collection_", "", 1)
                by_alias[alias] = cid
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
                radio_value = overlay.get("value")
                radio_map[oid] = {
                    "group_name": str(radio_group),
                    "value": radio_value,
                }
                if isinstance(radio_value, str):
                    radio_alias = radio_value.strip()
                    if radio_alias:
                        by_alias[radio_alias] = oid
    return by_id, by_alias, radio_map


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
    overlay_config = helpers.load_quickstart_overlay_config() or []
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
