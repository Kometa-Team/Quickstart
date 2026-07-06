"""Overlay-processing helpers for Kometa config generation.

These functions were previously inlined inside
``modules.output.build_libraries_section.add_entry``.  Each is a pure
function of its arguments -- no closure state -- so they extract
cleanly and can be tested in isolation.

The big rating-slot compaction pipeline
(``prune_rating_template_vars`` and its 12 helpers) plus the
per-overlay-type cleanup pass live in sibling modules now:

* ``modules.output_overlays_rating_slots`` -- rating-slot pipeline:
  drops empty slots, distributes shared offsets, clamps edge anchors,
  rewrites legacy vertical offsets.  Main entry:
  ``prune_rating_template_vars``.
* ``modules.output_overlays_type_cleanups`` -- per-overlay-type
  cleanup pass: normalizes booleans, strips default language weights,
  elides matching-default values.  Main entry:
  ``apply_per_overlay_type_cleanup``.

This module keeps the shared-ish helpers that don't belong to either
cluster:

* ``overlay_lookup_name`` -- canonicalize the three legacy names for
  the commonsense content-rating overlay.  Uses
  ``_COMMONSENSE_ALIASES`` re-imported from
  ``output_overlays_type_cleanups`` (which owns that constant since
  both ``_cleanup_commonsense_overlay`` and this function need it).
* ``reorder_rating_template_vars`` -- reorders rating overlay
  ``template_variables`` so ruamel.yaml emits them in a stable order.
* ``sort_overlay_entries`` -- sort overlay entries by
  (name-order, level-order, subtitles).

All names moved to the two sibling modules are re-exported from here
so external callers keep working unchanged.
"""

from __future__ import annotations

# _COMMONSENSE_ALIASES is defined in output_overlays_type_cleanups
# (see docstring above for the rationale).  overlay_lookup_name below
# depends on it.
from modules.output_overlays_type_cleanups import _COMMONSENSE_ALIASES

# Re-export the rating-slot pipeline for backward compatibility.
from modules.output_overlays_rating_slots import (  # noqa: F401
    _EXPLICIT_SLOT_OFFSET_KEYS,
    _RATINGS_DEFAULT_NAMES,
    _clamp_edge_anchor_offsets,
    _clean_template_variables,
    _collapse_uniform_horizontal_offsets,
    _distribute_shared_offsets,
    _drop_incomplete_rating_slots,
    _extract_slot_payloads,
    _flatten_slot_payloads,
    _is_empty_rating_value,
    _is_ratings_overlay,
    _offset_number,
    _reexpand_uniform_vertical_offsets,
    _rewrite_legacy_vertical_offsets,
    prune_rating_template_vars,
)

# Re-export the per-overlay-type cleanup pass for backward compatibility.
from modules.output_overlays_type_cleanups import (  # noqa: F401
    DEFAULT_LANGUAGE_FLAG_CODES,
    DEFAULT_LANGUAGE_FLAG_WEIGHTS,
    _ASPECT_VIDEO_FORMAT_DEFAULTS,
    _COMMONSENSE_DEFAULTS,
    _EPISODE_INFO_DEFAULTS,
    _LANGUAGES_DEFAULTS,
    _OVERLAY_TYPE_CLEANUPS,
    _RESOLUTION_DEFAULTS,
    _RESOLUTION_EDITION_KEEP_KEYS,
    _RESOLUTION_EDITION_STATIC_KEEP_KEYS,
    _RESOLUTION_LEVELS,
    _RESOLUTION_VARIANTS,
    _cleanup_aspect_video_format_overlay,
    _cleanup_commonsense_overlay,
    _cleanup_episode_info_overlay,
    _cleanup_languages_overlay,
    _cleanup_resolution_overlay,
    _coerce_string_bool,
    _drop_none_values,
    _elide_default_builder_level,
    apply_per_overlay_type_cleanup,
)


def overlay_lookup_name(name):
    """Canonicalize legacy commonsense overlay aliases.

    The Quickstart UI, Kometa defaults, and Kometa overlay filenames
    have disagreed at various times about what to call the
    commonsense content-rating overlay.  This function collapses the
    three known aliases into the single canonical
    ``content_rating_commonsense`` value that Kometa currently
    expects.  Non-string inputs pass through untouched so callers
    can hand it any value from the config dict without pre-checks.
    """
    if not isinstance(name, str):
        return name
    if name in _COMMONSENSE_ALIASES:
        return "content_rating_commonsense"
    return name


# Preferred YAML emission order for rating-overlay template variables.
# Keeping this at module scope avoids the ~50-item list rebuild on
# every call.  Keys not in this list get emitted after in
# insertion order.
_RATING_TEMPLATE_VAR_ORDER = (
    "builder_level",
    "rating1",
    "rating1_image",
    "rating1_font",
    "rating1_font_size",
    "rating1_font_color",
    "rating1_stroke_width",
    "rating1_stroke_color",
    "rating1_horizontal_offset",
    "rating1_vertical_offset",
    "rating2",
    "rating2_image",
    "rating2_font",
    "rating2_font_size",
    "rating2_font_color",
    "rating2_stroke_width",
    "rating2_stroke_color",
    "rating2_horizontal_offset",
    "rating2_vertical_offset",
    "rating3",
    "rating3_image",
    "rating3_font",
    "rating3_font_size",
    "rating3_font_color",
    "rating3_stroke_width",
    "rating3_stroke_color",
    "rating3_horizontal_offset",
    "rating3_vertical_offset",
    "horizontal_position",
    "horizontal_offset",
    "vertical_offset",
    "flag_alignment",
    "back_align",
    "back_color",
    "back_height",
    "back_width",
    "back_line_color",
    "back_line_width",
    "back_padding",
    "back_radius",
    "use_subtitles",
)


def reorder_rating_template_vars(overlay_entry):
    """Reorder a rating overlay's ``template_variables`` for stable YAML.

    Mutates ``overlay_entry`` in place.  No-op for non-rating overlays
    and for entries whose ``template_variables`` is missing, non-dict,
    or empty.  Keys not in the preferred order are appended in their
    original insertion order.

    The stable order matters because ruamel.yaml preserves dict
    insertion order in emitted YAML, and users diff generated configs
    against previous runs.  Without this reorder, an unpredictable
    UI-driven insertion order would produce noisy diffs.
    """
    if not isinstance(overlay_entry, dict):
        return
    default_name = overlay_entry.get("default", "")
    if not (isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))):
        return
    tv = overlay_entry.get("template_variables")
    if not isinstance(tv, dict) or not tv:
        return
    ordered = {}
    for key in _RATING_TEMPLATE_VAR_ORDER:
        if key in tv:
            ordered[key] = tv[key]
    for key in tv:
        if key not in ordered:
            ordered[key] = tv[key]
    overlay_entry["template_variables"] = ordered


def sort_overlay_entries(overlay_entries, overlay_name_order):
    """Sort *overlay_entries* in place by (name-order, level-order, subtitles).

    * name-order comes from *overlay_name_order* (a list of display
      names in canonical order).  ``languages_subtitles`` is folded
      onto ``languages``.
    * level-order is show < season < episode.
    * subtitles-sorted entries come after non-subtitles siblings at
      the same (name, level).

    No-op when *overlay_name_order* is falsy.
    """
    if not overlay_name_order:
        return
    order_map = {name: idx for idx, name in enumerate(overlay_name_order)}
    level_order = {"show": 0, "season": 1, "episode": 2}

    def _key(overlay_entry):
        name = overlay_entry.get("default", "")
        sort_name = "languages" if name == "languages_subtitles" else name
        name_index = order_map.get(sort_name, len(order_map))
        tv = overlay_entry.get("template_variables") or {}
        if not isinstance(tv, dict):
            tv = {}
        level = tv.get("builder_level", "show")
        level_index = level_order.get(level, 0)
        subtitles_index = 1 if tv.get("use_subtitles") else 0
        return (name_index, level_index, subtitles_index)

    overlay_entries.sort(key=_key)
