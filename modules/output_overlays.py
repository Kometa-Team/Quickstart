"""Overlay-processing helpers for Kometa config generation.

These functions were previously inlined inside
``modules.output.build_libraries_section.add_entry``.  Each is a pure
function of its arguments -- no closure state -- so they extract
cleanly and can be tested in isolation.

Overlay rating-slot compaction is the main protagonist:
``prune_rating_template_vars`` normalizes a rating overlay entry's
``template_variables`` by:

  1. Dropping any variable whose value is empty / "none".
  2. Enforcing the ``ratingN`` <-> ``ratingN_image`` dependency --
     if either half is empty, drop the whole slot.
  3. Compacting the surviving 1-3 slots so the emitted YAML matches
     the contiguous canvas preview even after the user reduces
     the rating count or clears a middle slot.
  4. Distributing the shared ``horizontal_offset`` / ``vertical_offset``
     onto per-slot offsets according to the chosen alignment and
     anchor position, respecting explicit per-slot overrides.
"""

_EXPLICIT_SLOT_OFFSET_KEYS = frozenset(
    {
        "rating1_horizontal_offset",
        "rating1_vertical_offset",
        "rating2_horizontal_offset",
        "rating2_vertical_offset",
        "rating3_horizontal_offset",
        "rating3_vertical_offset",
    }
)

_RATINGS_DEFAULT_NAMES = frozenset({"ratings", "overlay_ratings_episode"})


def _is_empty_rating_value(val):
    """Empty check used by rating-slot dependency enforcement."""
    if val is None or val is False:
        return True
    if isinstance(val, str):
        stripped = val.strip()
        return stripped == "" or stripped.lower() == "none"
    return False


def _offset_number(value, fallback):
    """Coerce *value* to a numeric offset, using *fallback* on failure.

    Booleans are rejected (they'd otherwise sneak through as 0/1).
    Ints and floats pass through unchanged.  Strings are stripped and
    tried as int then float; anything else returns the fallback.
    """
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


def _is_ratings_overlay(overlay_entry):
    """Return True for overlay entries whose ``default`` targets ratings."""
    default_name = overlay_entry.get("default", "")
    if not isinstance(default_name, str):
        return False
    return default_name.startswith("overlay_ratings") or default_name in _RATINGS_DEFAULT_NAMES


def _clean_template_variables(tv):
    """Return a dict copy of *tv* with empty / "none" values dropped.

    Handles three value shapes:
      * ``None`` / ``False`` -- always dropped.
      * ``dict`` (select-option {value, label}) -- unwrap ``value``,
        drop if empty / "none".
      * ``str`` -- strip and drop if empty / "none".
      * Anything else -- kept as-is.
    """
    cleaned = {}
    for k, v in tv.items():
        if v is None or v is False:
            continue
        if isinstance(v, dict):
            raw_val = v.get("value", "")
            if not raw_val or (isinstance(raw_val, str) and raw_val.strip().lower() == "none"):
                continue
            cleaned[k] = raw_val
            continue
        if isinstance(v, str):
            stripped = v.strip()
            if stripped == "" or stripped.lower() == "none":
                continue
        cleaned[k] = v
    return cleaned


def _drop_incomplete_rating_slots(cleaned):
    """Drop rating slots whose ``ratingN`` / ``ratingN_image`` pair is incomplete.

    Mutates *cleaned* in place.  A slot is dropped entirely when
    either half of the pair is empty, along with any lingering
    slot-specific style / offset fields from a previous higher
    rating count.
    """
    for idx in ("1", "2", "3"):
        r_key = f"rating{idx}"
        i_key = f"{r_key}_image"
        if r_key not in cleaned and i_key not in cleaned:
            continue
        if _is_empty_rating_value(cleaned.get(r_key)) or _is_empty_rating_value(cleaned.get(i_key)):
            for key in [k for k in list(cleaned.keys()) if k == r_key or k.startswith(f"{r_key}_")]:
                cleaned.pop(key, None)


def _extract_slot_payloads(cleaned):
    """Pull complete rating slots out of *cleaned* into a list of payloads.

    Mutates *cleaned* by removing the slot keys.  Each payload is a
    dict keyed by suffix (``""`` for the rating name itself, or
    ``"_horizontal_offset"`` / ``"_image"`` etc).
    """
    slot_payloads = []
    for idx in ("1", "2", "3"):
        rating_key = f"rating{idx}"
        image_key = f"{rating_key}_image"
        if rating_key not in cleaned or image_key not in cleaned:
            continue
        slot_payload = {}
        for key in [k for k in list(cleaned.keys()) if k == rating_key or k.startswith(f"{rating_key}_")]:
            suffix = "" if key == rating_key else key[len(rating_key) :]
            slot_payload[suffix] = cleaned.pop(key)
        if slot_payload:
            slot_payloads.append(slot_payload)
    return slot_payloads


def _distribute_shared_offsets(cleaned, slot_payloads, back_height, back_padding):
    """Compute derived per-slot offsets from the shared offset keys.

    Mutates *slot_payloads* in place, inserting ``_horizontal_offset``
    and ``_vertical_offset`` when they're absent.  Removes the shared
    keys from *cleaned* after distributing them.
    """
    vertical_step = back_height + (back_padding * 3)
    center_index = (len(slot_payloads) - 1) / 2 if slot_payloads else 0
    for axis in ("horizontal", "vertical"):
        shared_key = f"{axis}_offset"
        axis_default = 15 if axis == "horizontal" else 0
        shared_val = cleaned.get(shared_key, axis_default)
        shared_number = _offset_number(shared_val, axis_default)
        for slot_position, slot_payload in enumerate(slot_payloads):
            slot_key = f"_{axis}_offset"
            if slot_key in slot_payload:
                continue
            if axis == "horizontal":
                slot_payload[slot_key] = int(round(shared_number + back_padding))
            else:
                relative_index = slot_position - center_index
                slot_payload[slot_key] = int(round(shared_number + (vertical_step * relative_index)))
        cleaned.pop(shared_key, None)
    return vertical_step, center_index


def _reexpand_uniform_vertical_offsets(slot_payloads, vertical_step, center_index):
    """When all explicit vertical offsets are identical, re-expand the stack.

    A shared anchor from Quickstart's composite preview looks like
    uniform per-slot offsets on the way in; here we spread them back
    out to match the canvas.
    """
    vertical_values = [_offset_number(sp.get("_vertical_offset"), None) for sp in slot_payloads]
    if not all(v is not None for v in vertical_values):
        return
    if len(set(vertical_values)) != 1:
        return
    base_vertical = vertical_values[0]
    for slot_position, slot_payload in enumerate(slot_payloads):
        relative_index = slot_position - center_index
        slot_payload["_vertical_offset"] = int(round(base_vertical + (vertical_step * relative_index)))


def _collapse_uniform_horizontal_offsets(slot_payloads, shared_horizontal_base, back_padding):
    """When all horizontal offsets equal the shared base, re-add back_padding."""
    horizontal_values = [_offset_number(sp.get("_horizontal_offset"), None) for sp in slot_payloads]
    if not all(v is not None for v in horizontal_values):
        return
    if len(set(horizontal_values)) != 1:
        return
    if horizontal_values[0] != shared_horizontal_base:
        return
    for slot_payload in slot_payloads:
        slot_payload["_horizontal_offset"] = int(round(horizontal_values[0] + back_padding))


def _rewrite_legacy_vertical_offsets(
    slot_payloads,
    vertical_step,
    center_index,
    back_height,
    back_padding,
    shared_vertical_base,
):
    """Detect legacy per-slot vertical offsets and rewrite to new spacing.

    Older Quickstart versions used ``back_height + back_padding`` as
    the vertical step.  If the current per-slot offsets exactly
    match that legacy stack, rewrite them to the new
    ``back_height + 3 * back_padding`` step.
    """
    vertical_values = [_offset_number(sp.get("_vertical_offset"), None) for sp in slot_payloads]
    if not all(v is not None for v in vertical_values):
        return
    old_vertical_step = back_height + back_padding
    for slot_position, explicit_vertical in enumerate(vertical_values):
        relative_index = slot_position - center_index
        expected_legacy = int(round(shared_vertical_base + (old_vertical_step * relative_index)))
        if explicit_vertical != expected_legacy:
            return
    for slot_position, slot_payload in enumerate(slot_payloads):
        relative_index = slot_position - center_index
        slot_payload["_vertical_offset"] = int(round(shared_vertical_base + (vertical_step * relative_index)))


def _clamp_edge_anchor_offsets(slot_payloads, h_pos, v_pos):
    """Kometa enforces non-negative offsets for right/bottom anchors.

    Left/top anchors can still legitimately be negative (an
    intentional nudge past the edge).
    """
    if h_pos == "right":
        for sp in slot_payloads:
            value = _offset_number(sp.get("_horizontal_offset"), None)
            if value is not None and value < 0:
                sp["_horizontal_offset"] = int(round(abs(value)))
    if v_pos == "bottom":
        for sp in slot_payloads:
            value = _offset_number(sp.get("_vertical_offset"), None)
            if value is not None and value < 0:
                sp["_vertical_offset"] = int(round(abs(value)))


def _flatten_slot_payloads(cleaned, slot_payloads):
    """Re-emit compacted slot payloads back into *cleaned*."""
    for slot_position, slot_payload in enumerate(slot_payloads, start=1):
        rating_key = f"rating{slot_position}"
        for suffix, value in slot_payload.items():
            target_key = rating_key if suffix == "" else f"{rating_key}{suffix}"
            cleaned[target_key] = value


def prune_rating_template_vars(overlay_entry):
    """Normalize a rating overlay entry's ``template_variables`` in place.

    Drops empty / "none" values, enforces the rating/image pair
    dependency, compacts the surviving 1-3 slots contiguously, and
    distributes shared offsets onto per-slot offsets to match the
    Quickstart canvas preview.

    No-op for non-rating overlays and for entries whose
    ``template_variables`` is missing or non-dict.
    """
    if not isinstance(overlay_entry, dict):
        return
    if not _is_ratings_overlay(overlay_entry):
        return
    tv = overlay_entry.get("template_variables")
    if not isinstance(tv, dict):
        return

    cleaned = _clean_template_variables(tv)
    _drop_incomplete_rating_slots(cleaned)

    had_explicit_slot_offsets = any(key in cleaned for key in _EXPLICIT_SLOT_OFFSET_KEYS)
    slot_payloads = _extract_slot_payloads(cleaned)

    back_height = _offset_number(cleaned.get("back_height"), 160)
    back_padding = max(0, _offset_number(cleaned.get("back_padding"), 15))
    alignment_raw = str(cleaned.get("rating_alignment", "vertical")).strip().lower()
    alignment = "horizontal" if alignment_raw == "horizontal" else "vertical"
    h_pos_raw = str(cleaned.get("horizontal_position", "left")).strip().lower()
    h_pos = h_pos_raw if h_pos_raw in {"left", "center", "right"} else "left"
    v_pos_raw = str(cleaned.get("vertical_position", "center")).strip().lower()
    v_pos = v_pos_raw if v_pos_raw in {"top", "center", "bottom"} else "center"
    shared_horizontal_base = _offset_number(cleaned.get("horizontal_offset"), 15)
    shared_vertical_base = _offset_number(cleaned.get("vertical_offset"), 0)

    vertical_step, center_index = _distribute_shared_offsets(cleaned, slot_payloads, back_height, back_padding)

    preserve_explicit = had_explicit_slot_offsets and len(slot_payloads) > 1
    if not preserve_explicit and len(slot_payloads) > 1:
        if alignment == "vertical":
            _reexpand_uniform_vertical_offsets(slot_payloads, vertical_step, center_index)
        _collapse_uniform_horizontal_offsets(slot_payloads, shared_horizontal_base, back_padding)
        if alignment == "vertical":
            _rewrite_legacy_vertical_offsets(
                slot_payloads,
                vertical_step,
                center_index,
                back_height,
                back_padding,
                shared_vertical_base,
            )

    _clamp_edge_anchor_offsets(slot_payloads, h_pos, v_pos)
    _flatten_slot_payloads(cleaned, slot_payloads)

    if cleaned:
        overlay_entry["template_variables"] = cleaned
    else:
        overlay_entry.pop("template_variables", None)


_COMMONSENSE_ALIASES = frozenset(
    {
        "commonsense",
        "overlay_content_rating_commonsense",
        "content_rating_commonsense",
    }
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
