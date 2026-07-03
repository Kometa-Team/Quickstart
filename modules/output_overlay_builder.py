"""Overlay-entry assembly for Kometa config generation.

Extracted from ``modules.output.build_libraries_section.add_entry``.

This module handles turning the raw per-key overlay selection map (in
``session['data']`` / persistence) into a list of ``overlay_entries``
dicts ready to emit into YAML.

Two entry points:

* ``build_overlay_entries(library_type, overlay_key, raw_overlay_entries)``
  is the public dispatcher.  Returns
  ``(overlay_entries, overlay_name_order)`` for the given library.
* ``_build_movie_overlay_entries`` and ``_build_show_overlay_entries``
  are the per-library-type implementations.

Post-processing of the returned list (per-type cleanup, rating pair
elision, reorder, sort) lives in ``modules.output_overlays`` and is
applied by the caller after this module returns.  Splitting builder
from cleanup keeps each module cohesive and under ~600 lines.
"""

from __future__ import annotations

from modules import helpers
from modules.output_file_entries import _parse_overlay_file_block_entries
from modules.output_overlays import (
    apply_per_overlay_type_cleanup,
    overlay_lookup_name,
    prune_rating_template_vars,
    reorder_rating_template_vars,
    sort_overlay_entries,
)
from modules.output_values import _parse_string_list

# Show library uses these three builder levels in order.  Movie
# libraries have a single implicit level (labeled 'movie' in the key
# schema) and never set ``builder_level`` explicitly.
_SHOW_BUILDER_LEVELS = ("show", "season", "episode")


def _classify_overlay_name(raw_name, value):
    """Compute ``(is_subtitles, overlay_name)`` from a raw overlay key/value.

    * ``languages_subtitles`` is a special marker: entries with this
      raw_name emit as a distinct group but get renamed to ``languages``
      before final YAML emission.
    * When ``value == "commonsense"`` the overlay is the commonsense
      content-rating variant regardless of the raw_name.
    * When ``"content_rating"`` appears in raw_name AND value is a
      string, the value is a select-option variant suffix and gets
      composed into ``content_rating_<variant>``.
    * Otherwise the raw_name passes through unchanged.
    """
    is_subtitles = raw_name == "languages_subtitles"
    if is_subtitles:
        overlay_name = "languages_subtitles"
    elif value == "commonsense":
        overlay_name = "commonsense"
    elif "content_rating" in raw_name and isinstance(value, str):
        overlay_name = f"content_rating_{value}"
    else:
        overlay_name = raw_name
    return is_subtitles, overlay_name


def _coerce_template_var_value(var_name, raw_value):
    """Type-coerce a raw overlay template-variable value.

    * ``languages`` -> normalized list via ``_parse_string_list``.
    * ``weight_*`` -> int (best-effort; leaves as-is on ValueError).
    * String ``"true"`` / ``"false"`` -> bool.
    * Everything else passes through.
    """
    if var_name == "languages":
        return _parse_string_list(raw_value)
    if isinstance(var_name, str) and var_name.startswith("weight_"):
        try:
            return int(str(raw_value).strip())
        except (TypeError, ValueError):
            return raw_value
    if isinstance(raw_value, str):
        lowered = raw_value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return raw_value


def _populate_template_vars_from_raw(overlay_entry, raw_overlay_entries, full_key_prefix):
    """Fill ``overlay_entry['template_variables']`` from raw entries.

    Matches raw keys of the form ``<full_key_prefix>[<var_name>]`` and
    applies ``_coerce_template_var_value`` to each.  Mutates
    ``overlay_entry`` in place.
    """
    for raw_key, raw_value in raw_overlay_entries.items():
        if not raw_key.startswith(full_key_prefix + "["):
            continue
        var_name = raw_key[len(full_key_prefix) + 1 : -1]
        coerced = _coerce_template_var_value(var_name, raw_value)
        overlay_entry.setdefault("template_variables", {})[var_name] = coerced


def _apply_content_rating_color(overlay_entry, overlay_name, full_key_prefix_base, raw_overlay_entries):
    """For content_rating_<variant> overlays, read the ``[color]`` key.

    The color key lives on the un-variant-suffixed template overlay
    key (``..._template_overlay_content_rating_<variant>[color]``).
    Mutates ``overlay_entry`` in place, setting
    ``template_variables['color']`` to a bool.  Default: False.
    """
    if not overlay_name.startswith("content_rating_"):
        return
    variant = overlay_name[len("content_rating_") :]
    color_key = f"{full_key_prefix_base}_content_rating_{variant}[color]"
    color_value = raw_overlay_entries.get(color_key, False)
    if isinstance(color_value, str):
        color_value = color_value.lower() == "true"
    overlay_entry.setdefault("template_variables", {})["color"] = color_value


def _strip_languages_subtitles_suffix(overlay_entries):
    """Rename any ``languages_subtitles`` entry back to ``languages``.

    Kometa expects the canonical key ``languages`` in the emitted YAML;
    Quickstart uses ``languages_subtitles`` internally to distinguish
    the subtitles variant during entry grouping.
    """
    for overlay_entry in overlay_entries:
        if overlay_entry.get("default") == "languages_subtitles":
            overlay_entry["default"] = "languages"


def _build_movie_overlay_entries(overlay_key, raw_overlay_entries, library_type):
    """Assemble the overlay_entries list for a movie library.

    Movie libraries have a single implicit level ('movie' in the key
    schema) and never set ``builder_level`` on entries.  Returns the
    list; caller applies post-processing.
    """
    overlay_groups = {}
    overlay_prefix = f"{library_type}-library_{overlay_key}-movie-overlay_"

    for key, value in raw_overlay_entries.items():
        if not key.startswith(overlay_prefix) or not value:
            continue
        raw_name = key.split("-overlay_")[-1]
        is_subtitles, overlay_name = _classify_overlay_name(raw_name, value)
        overlay_groups.setdefault((overlay_name, is_subtitles), {})

    overlay_entries = []
    for overlay_name, is_subtitles in overlay_groups:
        entry_obj = {"default": overlay_name}
        if is_subtitles:
            entry_obj["template_variables"] = {"use_subtitles": True}
        overlay_entries.append(entry_obj)

    template_prefix_base = f"{library_type}-library_{overlay_key}-movie-template_overlay"
    for overlay_entry in overlay_entries:
        overlay_name = overlay_entry["default"]
        lookup_name = overlay_lookup_name(overlay_name)
        full_key_prefix = f"{template_prefix_base}_{lookup_name}"

        _apply_content_rating_color(overlay_entry, overlay_name, template_prefix_base, raw_overlay_entries)
        _populate_template_vars_from_raw(overlay_entry, raw_overlay_entries, full_key_prefix)
        prune_rating_template_vars(overlay_entry)

    _strip_languages_subtitles_suffix(overlay_entries)
    return overlay_entries


def _build_show_overlay_entries(overlay_key, raw_overlay_entries, library_type):
    """Assemble overlay_entries + overlay_name_order for a show library.

    Show libraries iterate through three builder levels (show, season,
    episode).  ``overlay_name_order`` captures the order in which
    canonical names first appeared, used later by
    ``sort_overlay_entries`` to preserve UI order in the emitted YAML.

    Returns ``(overlay_entries, overlay_name_order)``.
    """
    overlay_groups = {}
    overlay_name_order = []

    for level in _SHOW_BUILDER_LEVELS:
        prefix = f"{library_type}-library_{overlay_key}-{level}-overlay_"
        for key, value in raw_overlay_entries.items():
            if not key.startswith(prefix) or not value:
                continue
            raw_name = key.split("-overlay_")[-1]
            is_subtitles, overlay_name = _classify_overlay_name(raw_name, value)

            sort_name = "languages" if is_subtitles else overlay_name
            if sort_name not in overlay_name_order:
                overlay_name_order.append(sort_name)

            overlay_groups.setdefault((overlay_name, is_subtitles, level), True)

    overlay_entries = []
    for overlay_name, is_subtitles, level in overlay_groups:
        entry_obj = {"default": overlay_name}
        tv = {}
        if level != "show":
            tv["builder_level"] = level
        if is_subtitles:
            tv["use_subtitles"] = True
        if tv:
            entry_obj["template_variables"] = tv
        overlay_entries.append(entry_obj)

    for overlay_entry in overlay_entries:
        overlay_name = overlay_entry["default"]
        level = overlay_entry.get("template_variables", {}).get("builder_level", "show")
        lookup_name = overlay_lookup_name(overlay_name)
        template_prefix_base = f"{library_type}-library_{overlay_key}-{level}-template_overlay"
        full_key_prefix = f"{template_prefix_base}_{lookup_name}"

        _apply_content_rating_color(overlay_entry, overlay_name, template_prefix_base, raw_overlay_entries)
        _populate_template_vars_from_raw(overlay_entry, raw_overlay_entries, full_key_prefix)
        prune_rating_template_vars(overlay_entry)

    _strip_languages_subtitles_suffix(overlay_entries)
    return overlay_entries, overlay_name_order


def build_overlay_entries(library_type, overlay_key, raw_overlay_entries):
    """Assemble the overlay_entries list for a single library.

    Returns ``(overlay_entries, overlay_name_order)``:

    * ``overlay_entries`` is a list of dicts each shaped like
      ``{"default": <name>, "template_variables": {...}}`` (template_variables
      omitted when empty).
    * ``overlay_name_order`` is a list of canonical overlay names in the
      order they first appeared (only populated for show libraries;
      movie libraries return an empty list).

    Post-processing (per-type cleanup, rating pair elision, reorder,
    sort, overlay_files raw-block append) is applied by the caller
    after this returns.
    """
    if library_type == "mov":
        entries = _build_movie_overlay_entries(overlay_key, raw_overlay_entries, library_type)
        return entries, []
    if library_type == "sho":
        return _build_show_overlay_entries(overlay_key, raw_overlay_entries, library_type)
    # Unknown library type -- return empty result rather than crash.
    return [], []


def build_overlay_files_for_library(library_key, library_type, overlays):
    """Assemble the final ``overlay_files`` list for a single library.

    Wraps the four-stage overlay pipeline into one call:

    1. ``build_overlay_entries`` -- classify + populate template vars.
    2. ``apply_per_overlay_type_cleanup`` -- per-type field normalization.
    3. Per-entry ``reorder_rating_template_vars`` + list-level
       ``sort_overlay_entries`` -- final field / entry ordering.
    4. ``_parse_overlay_file_block_entries`` on the raw
       ``<library_prefix>-overlay_files`` value -- appended verbatim.

    Returns the final list.  When the library has no overlay data
    (no matching key in *overlays* and no raw overlay_files block)
    returns an empty list.  Caller is responsible for whether to
    assign to ``entry['overlay_files']``.
    """
    overlay_key = helpers.extract_library_name(library_key)
    if not overlay_key:
        return []

    library_overlay_group = overlays.get(overlay_key, {}) if overlay_key in overlays else None
    if library_overlay_group is None:
        return []

    overlay_entries, overlay_name_order = build_overlay_entries(library_type, overlay_key, library_overlay_group)
    apply_per_overlay_type_cleanup(overlay_entries)
    if overlay_entries:
        for ov in overlay_entries:
            reorder_rating_template_vars(ov)
        sort_overlay_entries(overlay_entries, overlay_name_order)

    overlay_library_prefix = helpers.strip_library_suffix(library_key)
    raw_overlay_file_entries = _parse_overlay_file_block_entries(library_overlay_group.get(f"{overlay_library_prefix}-overlay_files"))
    if raw_overlay_file_entries:
        overlay_entries.extend(raw_overlay_file_entries)

    return overlay_entries
