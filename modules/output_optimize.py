"""Template-variable pruning + rating-slot offset computation.

Extracted from the original ``modules/output.py`` monolith.  This module
owns ``optimize_template_variables``, which runs late in the config
build pipeline to strip any template variable whose value already
matches its schema default -- so the emitted YAML only carries user
overrides.

Rating overlays are the wrinkle.  They have three optional slots and
their horizontal/vertical offsets depend on which slots are enabled,
the ``rating_alignment`` (horizontal vs vertical), and the
``horizontal_position`` / ``vertical_position`` choice.  Kometa's
default offset math for these cases is baked into the six
``_r{slot}{axis}`` functions below.

Structure:

* Small pure helpers hoisted from the original nested closures:
  ``_to_offset_number``, ``_is_ratings_entry``,
  ``_reorder_ratings_template_vars``.
* ``_ensure_explicit_ratings_offsets`` -- the ratings-offset walker.
  Its six ``r{slot}{axis}`` functions remain as nested closures
  because they close over 7 layout-state variables; refactoring them
  into a dataclass-driven form is a follow-up.
* ``optimize_template_variables`` -- the orchestrator that walks
  libraries, prunes library-level / collection-file / overlay-file
  template variables against their respective default dicts, and calls
  the ratings-offset walker for rating overlays.

Public surface: only ``optimize_template_variables`` -- it's called
from ``build_config`` inside ``output.py``.  Zero external test or
blueprint callers today, so no ``# noqa: F401`` gymnastics needed --
just a plain re-import.
"""

from __future__ import annotations

import re

from modules import helpers
from modules.output_defaults import (
    _build_attribute_defaults,
    _build_collection_defaults,
    _build_overlay_defaults,
    _prune_template_variables,
)

# --- small pure helpers ---------------------------------------------------


def _to_offset_number(value, fallback):
    """Coerce to int/float, honouring a fallback for non-numeric input."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return fallback
        try:
            return int(stripped)
        except ValueError:
            try:
                return float(stripped)
            except ValueError:
                return fallback
    return fallback


def _is_ratings_entry(default_name):
    """Match Kometa's ``ratings`` / ``overlay_ratings*`` overlay defaults."""
    return isinstance(default_name, str) and (default_name == "ratings" or default_name.startswith("overlay_ratings"))


# Canonical ordering for rating overlay template variables so the
# emitted YAML stays diff-stable across regenerations.
_RATINGS_PREFERRED_ORDER = (
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
    "vertical_position",
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


def _reorder_ratings_template_vars(entry):
    """Reorder a rating overlay's template_variables into the canonical order."""
    if not isinstance(entry, dict):
        return
    default_name = entry.get("default", "")
    if not _is_ratings_entry(default_name):
        return
    tv = entry.get("template_variables")
    if not isinstance(tv, dict) or not tv:
        return

    ordered = {}
    for key in _RATINGS_PREFERRED_ORDER:
        if key in tv:
            ordered[key] = tv[key]
    for key in tv:
        if key not in ordered:
            ordered[key] = tv[key]
    entry["template_variables"] = ordered


_NATURAL_SORT_RE = re.compile(r"(\d+)")


def _natural_sort_key(value):
    parts = _NATURAL_SORT_RE.split(str(value or ""))
    return tuple((0, int(part)) if part.isdigit() else (1, part.lower()) for part in parts)


def _build_collection_template_orders():
    """Build canonical template-variable key order from quickstart_collections.json."""
    orders = {"movie": {}, "show": {}, "all": {}}
    try:
        data = helpers.load_quickstart_config("quickstart_collections.json")
    except Exception as exc:
        helpers.ts_log(f"Failed to load quickstart_collections.json for template variable ordering: {exc}", level="ERROR")
        return orders

    for group in data or []:
        for collection in group.get("collections", []):
            collection_id = collection.get("id")
            if not collection_id:
                continue
            default_key = collection_id.replace("collection_", "", 1)
            exact_order = {}
            dynamic_prefixes = []
            exact_keys = []

            for index, item in enumerate(collection.get("template_variables") or []):
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                if key:
                    exact_order[key] = index
                    exact_keys.append(str(key))
                dynamic_prefix = item.get("dynamic_child_prefix")
                if dynamic_prefix:
                    dynamic_prefixes.append((str(dynamic_prefix), index))

            child_suffixes = {key.removeprefix("use_") for key in exact_keys if key.startswith("use_") and key not in {"use_all", "use_separator"}}
            sibling_prefixes = {}
            for key in exact_keys:
                for suffix in sorted(child_suffixes, key=len, reverse=True):
                    if not suffix or not key.endswith(f"_{suffix}"):
                        continue
                    prefix = key[: -len(suffix)]
                    if not prefix:
                        continue
                    sibling_prefixes.setdefault(prefix, []).append((key, exact_order[key], suffix))
                    break

            sortable_sibling_prefixes = [(prefix, min(index for _key, index, _suffix in members)) for prefix, members in sibling_prefixes.items() if len(members) > 1]

            order_spec = {
                "exact": exact_order,
                "dynamic": sorted(dynamic_prefixes, key=lambda pair: (-len(pair[0]), pair[1])),
                "siblings": sorted(sortable_sibling_prefixes, key=lambda pair: (-len(pair[0]), pair[1])),
            }
            media_types = [mt for mt in (collection.get("media_types") or []) if mt in ("movie", "show")]
            if not media_types:
                orders["all"][default_key] = order_spec
                continue
            for media_type in media_types:
                orders[media_type][default_key] = order_spec
            if len(media_types) > 1:
                orders["all"][default_key] = order_spec
    return orders


def _pick_collection_template_order(collection_orders, library_type, default_name):
    if not default_name:
        return None
    library_type = library_type if library_type in ("movie", "show") else None
    if library_type:
        order_spec = collection_orders.get(library_type, {}).get(default_name)
        if order_spec:
            return order_spec
    order_spec = collection_orders.get("all", {}).get(default_name)
    if order_spec:
        return order_spec
    for fallback_type in ("movie", "show"):
        order_spec = collection_orders.get(fallback_type, {}).get(default_name)
        if order_spec:
            return order_spec
    return None


def _collection_template_sort_key(key, order_spec):
    key_text = str(key or "")
    exact_order = (order_spec or {}).get("exact") or {}
    for sibling_prefix, index in (order_spec or {}).get("siblings") or []:
        if key_text.startswith(sibling_prefix) and key_text != sibling_prefix:
            return (0, index, _natural_sort_key(key_text[len(sibling_prefix) :]))

    if key_text in exact_order:
        return (0, exact_order[key_text], ())

    for dynamic_prefix, index in (order_spec or {}).get("dynamic") or []:
        if key_text.startswith(dynamic_prefix) and key_text != dynamic_prefix:
            return (0, index, _natural_sort_key(key_text[len(dynamic_prefix) :]))

    return (1, len(exact_order), _natural_sort_key(key_text))


def _reorder_collection_template_vars(entry, collection_orders, library_type):
    """Reorder collection template_variables into Quickstart's canonical order."""
    if not isinstance(entry, dict):
        return
    tv = entry.get("template_variables")
    if not isinstance(tv, dict) or not tv:
        return

    order_spec = _pick_collection_template_order(collection_orders, library_type, entry.get("default"))
    if not order_spec:
        return

    entry["template_variables"] = {key: tv[key] for key in sorted(tv.keys(), key=lambda item: _collection_template_sort_key(item, order_spec))}


# --- ratings offset math --------------------------------------------------
#
# See module docstring for context.  These constants and the six
# _r{slot}{axis} closures inside _ensure_explicit_ratings_offsets are
# a straight lift from the original nested-closure form in output.py;
# refactoring them into a dataclass-driven form is future work.

_RATING_CONSTANTS = {
    "standard": 30,
    "center": 0,
    "v2": 235,
    "v3": 440,
    "cv2": 105,
    "cv3": 205,
    "h2": 345,
    "h3": 660,
    "ch2": 160,
    "ch3": 335,
}


def _normalize_choice(value, fallback):
    """Lowercase-strip a config value, with a fallback for None/missing."""
    return str(value if value is not None else fallback).strip().lower()


def _ensure_explicit_ratings_offsets(tv, defaults):
    """Compute + inject the six rating*_{h,v}_offset defaults into ``tv``.

    Kometa's default overlay math for ratings depends on which of the
    three rating slots are enabled, the alignment (horizontal vs
    vertical), and the on-axis position.  The output has to include
    explicit per-slot offsets so the YAML is self-contained.
    """
    if not isinstance(tv, dict):
        return
    slot_ids = []
    for idx in ("1", "2", "3"):
        rating_key = f"rating{idx}"
        image_key = f"{rating_key}_image"
        if rating_key in tv and image_key in tv:
            slot_ids.append(idx)
    if not slot_ids:
        return
    defaults = defaults or {}

    def _slot_enabled(slot):
        rating_val = _normalize_choice(tv.get(f"rating{slot}"), "")
        image_val = _normalize_choice(tv.get(f"rating{slot}_image"), "")
        if rating_val in ("", "none") or image_val in ("", "none"):
            return False
        return True

    alignment = _normalize_choice(tv.get("rating_alignment", defaults.get("rating_alignment", "vertical")), "vertical")
    if alignment not in ("horizontal", "vertical"):
        alignment = "vertical"
    h_pos = _normalize_choice(tv.get("horizontal_position", defaults.get("horizontal_position", "left")), "left")
    if h_pos not in ("left", "center", "right"):
        h_pos = "left"
    v_pos = _normalize_choice(tv.get("vertical_position", defaults.get("vertical_position", "center")), "center")
    if v_pos not in ("top", "center", "bottom"):
        v_pos = "center"

    if isinstance(defaults, dict):
        defaults["back_width"] = 270 if alignment == "horizontal" else 160
        defaults["back_height"] = 80 if alignment == "horizontal" else 160
        defaults["addon_position"] = "left" if alignment == "horizontal" else "top"
        defaults["horizontal_offset"] = 0 if h_pos == "center" else 15
        defaults["vertical_offset"] = 0 if v_pos == "center" else 15

    none1 = not _slot_enabled("1")
    none2 = not _slot_enabled("2")
    none3 = not _slot_enabled("3")

    def r1h():
        if alignment == "vertical" and h_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "center" and none2 and none3:
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "center" and none2:
            return -_RATING_CONSTANTS["ch2"]
        if alignment == "horizontal" and h_pos == "center" and none3:
            return -_RATING_CONSTANTS["ch2"]
        if alignment == "horizontal" and h_pos == "center":
            return -_RATING_CONSTANTS["ch3"]
        if alignment == "horizontal" and h_pos == "right" and none2 and none3:
            return _RATING_CONSTANTS["standard"]
        if alignment == "horizontal" and h_pos == "right" and none2:
            return _RATING_CONSTANTS["h2"]
        if alignment == "horizontal" and h_pos == "right" and none3:
            return _RATING_CONSTANTS["h2"]
        if alignment == "horizontal" and h_pos == "right":
            return _RATING_CONSTANTS["h3"]
        return _RATING_CONSTANTS["standard"]

    def r1v():
        if alignment == "horizontal" and v_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "center" and none2 and none3:
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "center" and none2:
            return -_RATING_CONSTANTS["cv2"]
        if alignment == "vertical" and v_pos == "center" and none3:
            return -_RATING_CONSTANTS["cv2"]
        if alignment == "vertical" and v_pos == "center":
            return -_RATING_CONSTANTS["cv3"]
        if alignment == "vertical" and v_pos == "bottom" and none2 and none3:
            return _RATING_CONSTANTS["standard"]
        if alignment == "vertical" and v_pos == "bottom" and none2:
            return _RATING_CONSTANTS["v2"]
        if alignment == "vertical" and v_pos == "bottom" and none3:
            return _RATING_CONSTANTS["v2"]
        if alignment == "vertical" and v_pos == "bottom":
            return _RATING_CONSTANTS["v3"]
        return _RATING_CONSTANTS["standard"]

    def r2h():
        if alignment == "vertical" and h_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "center" and none1 and none3:
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "center" and none1:
            return -_RATING_CONSTANTS["ch2"]
        if alignment == "horizontal" and h_pos == "center" and none3:
            return _RATING_CONSTANTS["ch2"]
        if alignment == "horizontal" and h_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "right" and none1 and none3:
            return _RATING_CONSTANTS["standard"]
        if alignment == "horizontal" and h_pos == "right" and none3:
            return _RATING_CONSTANTS["standard"]
        if alignment == "horizontal" and h_pos == "right":
            return _RATING_CONSTANTS["h2"]
        if alignment == "horizontal" and h_pos == "left" and none1:
            return _RATING_CONSTANTS["standard"]
        if alignment == "horizontal" and h_pos == "left":
            return _RATING_CONSTANTS["h2"]
        return _RATING_CONSTANTS["standard"]

    def r2v():
        if alignment == "horizontal" and v_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "center" and none1 and none3:
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "center" and none1:
            return -_RATING_CONSTANTS["cv2"]
        if alignment == "vertical" and v_pos == "center" and none3:
            return _RATING_CONSTANTS["cv2"]
        if alignment == "vertical" and v_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "bottom" and none1 and none3:
            return _RATING_CONSTANTS["standard"]
        if alignment == "vertical" and v_pos == "bottom" and none1:
            return _RATING_CONSTANTS["v2"]
        if alignment == "vertical" and v_pos == "bottom" and none3:
            return _RATING_CONSTANTS["standard"]
        if alignment == "vertical" and v_pos == "bottom":
            return _RATING_CONSTANTS["v2"]
        if alignment == "vertical" and v_pos == "top" and none1:
            return _RATING_CONSTANTS["standard"]
        if alignment == "vertical" and v_pos == "top":
            return _RATING_CONSTANTS["v2"]
        return _RATING_CONSTANTS["standard"]

    def r3h():
        if alignment == "vertical" and h_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "center" and none1 and none2:
            return _RATING_CONSTANTS["center"]
        if alignment == "horizontal" and h_pos == "center" and none1:
            return _RATING_CONSTANTS["ch2"]
        if alignment == "horizontal" and h_pos == "center" and none2:
            return _RATING_CONSTANTS["ch2"]
        if alignment == "horizontal" and h_pos == "center":
            return _RATING_CONSTANTS["ch3"]
        if alignment == "horizontal" and h_pos == "left" and none1 and none2:
            return _RATING_CONSTANTS["standard"]
        if alignment == "horizontal" and h_pos == "left" and none1:
            return _RATING_CONSTANTS["h2"]
        if alignment == "horizontal" and h_pos == "left" and none2:
            return _RATING_CONSTANTS["h2"]
        if alignment == "horizontal" and h_pos == "left":
            return _RATING_CONSTANTS["h3"]
        return _RATING_CONSTANTS["standard"]

    def r3v():
        if alignment == "horizontal" and v_pos == "center":
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "center" and none1 and none2:
            return _RATING_CONSTANTS["center"]
        if alignment == "vertical" and v_pos == "center" and none1:
            return _RATING_CONSTANTS["cv2"]
        if alignment == "vertical" and v_pos == "center" and none2:
            return _RATING_CONSTANTS["cv2"]
        if alignment == "vertical" and v_pos == "center":
            return _RATING_CONSTANTS["cv3"]
        if alignment == "vertical" and v_pos == "top" and none1 and none2:
            return _RATING_CONSTANTS["standard"]
        if alignment == "vertical" and v_pos == "top" and none1:
            return _RATING_CONSTANTS["v2"]
        if alignment == "vertical" and v_pos == "top" and none2:
            return _RATING_CONSTANTS["v2"]
        if alignment == "vertical" and v_pos == "top":
            return _RATING_CONSTANTS["v3"]
        return _RATING_CONSTANTS["standard"]

    computed = {
        "1": {"h": r1h(), "v": r1v()},
        "2": {"h": r2h(), "v": r2v()},
        "3": {"h": r3h(), "v": r3v()},
    }

    for idx in slot_ids:
        h_key = f"rating{idx}_horizontal_offset"
        v_key = f"rating{idx}_vertical_offset"
        if isinstance(defaults, dict):
            defaults[h_key] = int(round(computed[idx]["h"]))
            defaults[v_key] = int(round(computed[idx]["v"]))
        if h_key not in tv:
            tv[h_key] = int(round(computed[idx]["h"]))
        if v_key not in tv:
            tv[v_key] = int(round(computed[idx]["v"]))


# --- helpers used by the orchestrator -------------------------------------


def _resolve_libraries_dict(config_data):
    """Extract the innermost ``libraries`` dict, handling nested and flat shapes.

    Returns the dict or ``None`` if the config doesn't have a walkable
    libraries section.
    """
    libraries_section = config_data.get("libraries", {})
    if isinstance(libraries_section, dict) and isinstance(libraries_section.get("libraries"), dict):
        return libraries_section.get("libraries")
    if isinstance(libraries_section, dict):
        return libraries_section
    return None


def _pick_collection_defaults(collection_defaults, library_type, default_name):
    """Return the schema defaults for a collection file entry.

    Prefers ``movie``/``show``-specific defaults when the library type
    is known; falls back to the ``all`` bucket.
    """
    if not isinstance(collection_defaults, dict):
        return None
    if library_type in ("movie", "show"):
        defaults = collection_defaults.get(library_type, {}).get(default_name)
        if defaults is not None:
            return defaults
    return collection_defaults.get("all", {}).get(default_name)


def _pick_overlay_defaults(defaults_entry, tv, library_type):
    """Return per-level overlay defaults + optional offsets, merged into one dict."""
    defaults = dict(defaults_entry.get("defaults", {}))

    overlay_level = None
    if isinstance(tv.get("builder_level"), str) and tv.get("builder_level"):
        overlay_level = tv.get("builder_level")
    elif library_type:
        overlay_level = "movie" if library_type == "movie" else "show"

    if overlay_level:
        type_defaults = defaults_entry.get("defaults_by_type", {}).get(overlay_level)
        if type_defaults:
            defaults = dict(type_defaults)
        offsets = defaults_entry.get("offsets_by_type", {}).get(overlay_level)
        if offsets:
            defaults.update(offsets)

    return defaults


_RATINGS_ALWAYS_KEEP_KEYS = frozenset(
    {
        "builder_level",
        "rating1",
        "rating1_image",
        "rating2",
        "rating2_image",
        "rating3",
        "rating3_image",
        "horizontal_position",
        "vertical_position",
    }
)


def _apply_always_keep(pruned, tv, default_name):
    """Force certain keys back into ``pruned`` even if they equal defaults.

    Ratings overlays need certain layout keys to survive pruning so the
    YAML is self-documenting.  ``builder_level`` is always kept when
    present because it drives Kometa's rendering path.
    """
    always_keep = set()
    if _is_ratings_entry(default_name):
        always_keep.update(_RATINGS_ALWAYS_KEEP_KEYS)
    if "builder_level" in tv:
        always_keep.add("builder_level")
    for key in always_keep:
        if key in tv:
            pruned[key] = tv[key]


# --- the orchestrator -----------------------------------------------------


def _optimize_library_level(library_data, attribute_defaults):
    """Prune the library-level template_variables dict in place."""
    tv = library_data.get("template_variables")
    if not isinstance(tv, dict):
        return
    pruned = _prune_template_variables(tv, attribute_defaults)
    if pruned:
        library_data["template_variables"] = pruned
    else:
        library_data.pop("template_variables", None)


def _optimize_collection_files(library_data, collection_defaults, collection_orders, library_type):
    """Prune per-collection-file template_variables in place."""
    collection_files = library_data.get("collection_files")
    if not isinstance(collection_files, list):
        return
    for entry in collection_files:
        if not isinstance(entry, dict):
            continue
        tv = entry.get("template_variables")
        if not isinstance(tv, dict):
            continue
        defaults = _pick_collection_defaults(collection_defaults, library_type, entry.get("default"))
        if not defaults:
            continue
        pruned = _prune_template_variables(tv, defaults)
        # Year collection files carry a data_ending sentinel that must
        # survive pruning even when it matches the default.
        if entry.get("default") == "year" and "data_ending" in tv:
            pruned["data_ending"] = tv.get("data_ending")
        if pruned:
            entry["template_variables"] = pruned
            _reorder_collection_template_vars(entry, collection_orders, library_type)
        else:
            entry.pop("template_variables", None)


def _optimize_overlay_files(library_data, overlay_defaults, library_type):
    """Prune per-overlay-file template_variables in place."""
    overlay_files = library_data.get("overlay_files")
    if not isinstance(overlay_files, list):
        return
    for entry in overlay_files:
        if not isinstance(entry, dict):
            continue
        tv = entry.get("template_variables")
        if not isinstance(tv, dict):
            continue
        defaults_entry = overlay_defaults.get(entry.get("default"))
        if not defaults_entry:
            continue

        defaults = _pick_overlay_defaults(defaults_entry, tv, library_type)

        if _is_ratings_entry(entry.get("default")):
            _ensure_explicit_ratings_offsets(tv, defaults)

        pruned = _prune_template_variables(tv, defaults)
        _apply_always_keep(pruned, tv, entry.get("default"))
        if pruned:
            entry["template_variables"] = pruned
            _reorder_ratings_template_vars(entry)
        else:
            entry.pop("template_variables", None)


def optimize_template_variables(config_data, library_types=None):
    """Prune every template_variables dict against its schema defaults.

    Walks the fully-built config dict and, for each library:

    1. Prune library-level template_variables against attribute defaults.
    2. Prune each collection_files entry against the movie/show/all
       collection defaults.
    3. Prune each overlay_files entry against the overlay defaults, with
       special handling for ratings overlays (offset math + always-keep
       layout keys + canonical reorder).

    The pruning drops any key whose value matches the schema default,
    keeping the emitted YAML small and focused on user overrides.
    Modifies ``config_data`` in place and also returns it.
    """
    libraries = _resolve_libraries_dict(config_data)
    if not isinstance(libraries, dict):
        return config_data

    collection_defaults = _build_collection_defaults()
    collection_orders = _build_collection_template_orders()
    overlay_defaults = _build_overlay_defaults()
    attribute_defaults = _build_attribute_defaults()

    for library_name, library_data in libraries.items():
        if not isinstance(library_data, dict):
            continue

        library_type = None
        if isinstance(library_types, dict):
            library_type = library_types.get(library_name)

        _optimize_library_level(library_data, attribute_defaults)
        _optimize_collection_files(library_data, collection_defaults, collection_orders, library_type)
        _optimize_overlay_files(library_data, overlay_defaults, library_type)

    return config_data
