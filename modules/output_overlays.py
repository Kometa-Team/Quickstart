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


# ---------------------------------------------------------------------------
# Per-overlay-type post-processing cleanup.
#
# After the overlay entries are built and rating-slot compaction has been
# applied, each overlay type gets a targeted cleanup pass that:
#   * Drops keys that were injected by the UI but shouldn't emit in YAML.
#   * Normalizes values (booleans-from-strings, language weight ints).
#   * Elides default-equal values so the emitted YAML stays minimal.
# ---------------------------------------------------------------------------

# Language weights used by the "languages" overlay.  These are the Kometa
# defaults, in priority order (higher weight = higher priority).  Only weights
# that DIFFER from these defaults emit into YAML; matching ones are dropped.
DEFAULT_LANGUAGE_FLAG_CODES = ("en", "de", "fr", "es", "pt", "ja")
DEFAULT_LANGUAGE_FLAG_WEIGHTS = {
    "en": 610,
    "de": 600,
    "fr": 590,
    "es": 580,
    "pt": 570,
    "ja": 560,
    "ko": 550,
    "zh": 540,
    "da": 530,
    "ru": 520,
    "it": 510,
    "hi": 500,
    "te": 490,
    "fa": 480,
    "th": 470,
    "nl": 460,
    "no": 450,
    "is": 440,
    "sv": 430,
    "tr": 420,
    "pl": 410,
    "cs": 400,
    "uk": 390,
    "hu": 380,
    "ar": 370,
    "bg": 360,
    "bn": 350,
    "bs": 340,
    "ca": 330,
    "cy": 320,
    "el": 310,
    "et": 300,
    "eu": 290,
    "fi": 280,
    "tl": 270,
    "fil": 265,
    "gl": 260,
    "he": 250,
    "hr": 240,
    "id": 230,
    "ka": 220,
    "kk": 210,
    "kn": 200,
    "la": 190,
    "lt": 180,
    "lv": 170,
    "mk": 160,
    "ml": 150,
    "mr": 140,
    "ms": 130,
    "nb": 120,
    "nn": 110,
    "pa": 100,
    "ro": 90,
    "sk": 80,
    "sl": 70,
    "sq": 60,
    "sr": 50,
    "so": 45,
    "sw": 40,
    "ta": 30,
    "ur": 20,
    "ay": 19,
    "ga": 18,
    "li": 17,
    "kh": 16,
    "vi": 15,
    "mn": 14,
    "af": 13,
    "bm": 12,
    "ln": 11,
    "wo": 10,
    "lo": 9,
    "myn": 8,
    "iu": 7,
    "rom": 6,
    "am": 5,
    "su": 4,
    "zu": 3,
    "lb": 2,
    "mos": 1,
}

# Recognized "resolution" overlay defaults.
_RESOLUTION_DEFAULTS = frozenset({"resolution", "overlay_resolution"})
_COMMONSENSE_DEFAULTS = frozenset(_COMMONSENSE_ALIASES)  # reuse from earlier
_EPISODE_INFO_DEFAULTS = frozenset({"episode_info", "overlay_episode_info"})
_LANGUAGES_DEFAULTS = frozenset({"languages", "overlay_languages"})
_ASPECT_VIDEO_FORMAT_DEFAULTS = frozenset({"aspect", "video_format", "overlay_aspect", "overlay_video_format"})

# Keys kept when a resolution overlay has use_edition=True; anything else
# is stripped.  The dynamic per-(level,variant) combinations get generated
# once at module load.
_RESOLUTION_EDITION_STATIC_KEEP_KEYS = frozenset(
    {
        "builder_level",
        "use_edition",
        "use_resolution",
        "use_4k",
        "use_1080p",
        "use_720p",
        "use_576p",
        "use_480p",
        "use_dv",
        "use_hlg",
        "use_hdr",
        "use_plus",
        "use_dvhdr",
        "use_dvhdrplus",
        "use_extended",
        "use_uncut",
        "use_unrated",
        "use_special",
        "use_anniversary",
        "use_collector",
        "use_diamond",
        "use_platinum",
        "use_directors",
        "use_final",
        "use_international",
        "use_theatrical",
        "use_ultimate",
        "use_alternate",
        "use_coda",
        "use_enhanced",
        "use_imax",
        "use_remastered",
        "use_criterion",
        "use_richarddonner",
        "use_blackchrome",
        "use_definitive",
        "use_openmatte",
        "use_ulysses",
        "use_producers",
        "horizontal_offset",
        "vertical_offset",
    }
)
_RESOLUTION_LEVELS = ("4k", "1080p", "720p", "576p", "480p")
_RESOLUTION_VARIANTS = ("dvhdrplus", "dvhdr", "plus", "dv", "hlg", "hdr")
_RESOLUTION_EDITION_KEEP_KEYS = frozenset(_RESOLUTION_EDITION_STATIC_KEEP_KEYS | {f"use_{lvl}_{var}" for lvl in _RESOLUTION_LEVELS for var in _RESOLUTION_VARIANTS})


def _drop_none_values(tv):
    """Drop keys whose value is exactly ``None``.  Mutates *tv*."""
    for key, value in list(tv.items()):
        if value is None:
            tv.pop(key, None)


def _elide_default_builder_level(tv):
    """Drop ``builder_level`` if it equals the default ``"show"``.

    Returns True if the caller should short-circuit (tv became empty).
    """
    if tv.get("builder_level") == "show":
        tv.pop("builder_level", None)
        return not tv
    return False


def _coerce_string_bool(val):
    """Coerce a string boolean ("true"/"false") to Python bool.

    Preserves non-string inputs (including the sentinel ``None``).
    """
    if isinstance(val, str):
        return val.lower() == "true"
    return val


def _cleanup_resolution_overlay(tv):
    """Post-process a resolution overlay's template_variables in place.

    Normalizes ``use_edition`` / ``use_resolution``:
      * Missing (None) -> written as bool True.
      * String "true"  -> left as string (historical quirk of the inline code).
      * String "false" -> rewritten to bool False.
      * Bool True/False -> left as-is.

    When ``use_edition`` is truthy, strips any key not in the resolution
    edition allow-list.

    Returns True if *tv* became empty (caller should pop it).
    """
    use_edition_val = _coerce_string_bool(tv.get("use_edition"))
    use_resolution_val = _coerce_string_bool(tv.get("use_resolution"))
    if use_edition_val is None:
        tv["use_edition"] = True
        use_edition_val = True
    elif use_edition_val is False:
        # This overwrites both native False and the string "false".
        # (String "true" is not touched -- neither branch fires.)
        tv["use_edition"] = False

    if use_resolution_val is None:
        tv["use_resolution"] = True
    elif use_resolution_val is False:
        tv["use_resolution"] = False

    if use_edition_val is not True:
        return False
    for key in list(tv.keys()):
        if key not in _RESOLUTION_EDITION_KEEP_KEYS:
            tv.pop(key, None)
    return not tv


def _cleanup_commonsense_overlay(tv):
    """Drop text/font styling from a commonsense overlay -- it uses images.

    Returns True if *tv* became empty.
    """
    for key in ("text", "font", "font_size", "font_color"):
        tv.pop(key, None)
    return not tv


def _cleanup_episode_info_overlay(tv):
    """Drop the ``text`` key from an episode_info overlay -- Kometa injects
    the episode text itself; a stale text key would override.

    Returns True if *tv* became empty.
    """
    tv.pop("text", None)
    return not tv


def _cleanup_languages_overlay(tv):
    """Normalize a languages overlay in place.

    * ``languages`` list: normalized via _parse_string_list and dropped
      if it equals the default set.
    * ``weight_XX`` keys: coerced to int; dropped if they match the
      default weight for that language.

    Returns True if *tv* became empty.
    """
    # Delay-import to avoid a circular reference during module load
    # (output_values -> output_overlays would create a cycle if this ever grew).
    from modules.output_values import _parse_string_list

    languages_value = tv.get("languages")
    if languages_value is not None:
        normalized_languages = _parse_string_list(languages_value)
        if normalized_languages == list(DEFAULT_LANGUAGE_FLAG_CODES) or not normalized_languages:
            tv.pop("languages", None)
        else:
            tv["languages"] = normalized_languages

    for key in list(tv.keys()):
        if not (isinstance(key, str) and key.startswith("weight_")):
            continue
        language_key = key[len("weight_") :]
        default_weight = DEFAULT_LANGUAGE_FLAG_WEIGHTS.get(language_key)
        try:
            numeric_value = int(str(tv.get(key)).strip())
        except (TypeError, ValueError):
            continue
        tv[key] = numeric_value
        if default_weight is not None and numeric_value == default_weight:
            tv.pop(key, None)

    return not tv


def _cleanup_aspect_video_format_overlay(tv):
    """Drop the ``text`` key from aspect / video_format overlays -- they
    use image glyphs, so a stale text key from the UI must not emit.

    Returns True if *tv* became empty.
    """
    tv.pop("text", None)
    return not tv


# Dispatch table: default-name -> (allowed default names, cleanup function).
# Ordered by the sequence the original inline code applied them.
_OVERLAY_TYPE_CLEANUPS = (
    (_RESOLUTION_DEFAULTS, _cleanup_resolution_overlay),
    (_COMMONSENSE_DEFAULTS, _cleanup_commonsense_overlay),
    (_EPISODE_INFO_DEFAULTS, _cleanup_episode_info_overlay),
    (_LANGUAGES_DEFAULTS, _cleanup_languages_overlay),
    (_ASPECT_VIDEO_FORMAT_DEFAULTS, _cleanup_aspect_video_format_overlay),
)


def apply_per_overlay_type_cleanup(overlay_entries):
    """Post-process every overlay in *overlay_entries* by type.

    For each entry:
      1. Skip if template_variables is missing or non-dict.
      2. Drop any key whose value is None.
      3. Elide default ``builder_level: show``.
      4. Dispatch to the type-specific cleanup based on ``default``.

    If an overlay's template_variables becomes empty at any point,
    remove the key entirely from the entry.

    Mutates *overlay_entries* (list of dicts) in place.
    """
    for ov in overlay_entries:
        default_name = ov.get("default", "")
        tv = ov.get("template_variables")
        if not isinstance(tv, dict):
            continue

        _drop_none_values(tv)

        if _elide_default_builder_level(tv):
            ov.pop("template_variables", None)
            continue

        # Type dispatch: the recognized default-name sets are pairwise
        # disjoint, so at most one branch can match.  If it empties tv,
        # pop template_variables from the entry.
        if not isinstance(default_name, str):
            continue
        for names, cleanup in _OVERLAY_TYPE_CLEANUPS:
            if default_name not in names:
                continue
            if cleanup(tv):
                ov.pop("template_variables", None)
            break


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
