"""Per-overlay-type post-processing cleanups.

Split out of ``modules.output_overlays`` -- this cluster owns the
"targeted final pass" logic applied to each overlay type after
rating-slot compaction.  Each cleanup pass:

  * Drops keys that the UI injects but which shouldn't emit in YAML.
  * Normalizes values (booleans-from-strings, language weight ints).
  * Elides default-equal values so the emitted YAML stays minimal.

## What lives here

### Constants
* ``DEFAULT_LANGUAGE_FLAG_CODES`` / ``DEFAULT_LANGUAGE_FLAG_WEIGHTS``
  -- Kometa's default flag ordering + per-language weight.  Only
  weights that DIFFER from these defaults emit into YAML.
* ``_COMMONSENSE_ALIASES`` -- the three legacy names for the
  commonsense content-rating overlay (moved here from the main
  module because it's shared with ``_COMMONSENSE_DEFAULTS`` below,
  and only ``overlay_lookup_name`` in the main module still needs
  it -- that function imports it from here).
* ``_RESOLUTION_DEFAULTS`` / ``_EPISODE_INFO_DEFAULTS`` /
  ``_LANGUAGES_DEFAULTS`` / ``_ASPECT_VIDEO_FORMAT_DEFAULTS`` --
  the set of overlay names each cleaner recognizes.
* ``_RESOLUTION_EDITION_STATIC_KEEP_KEYS`` / ``_RESOLUTION_LEVELS``
  / ``_RESOLUTION_VARIANTS`` / ``_RESOLUTION_EDITION_KEEP_KEYS`` --
  fine-grained key allowlists for the resolution overlay.
* ``_OVERLAY_TYPE_CLEANUPS`` -- dispatch table used by the main
  entry point.

### Shared helpers
* ``_drop_none_values`` -- filter dict to non-empty values.
* ``_elide_default_builder_level`` -- drop the ``builder_level: movie``
  default (movies never emit it).
* ``_coerce_string_bool`` -- convert ``"true"`` / ``"1"`` / etc. to
  a real boolean, keeping non-bool-shaped values untouched.

### Per-type cleaners
* ``_cleanup_resolution_overlay`` (37 lines, most complex)
* ``_cleanup_commonsense_overlay``
* ``_cleanup_episode_info_overlay``
* ``_cleanup_languages_overlay`` (38 lines; strips default weights)
* ``_cleanup_aspect_video_format_overlay``

### Main entry point
* ``apply_per_overlay_type_cleanup(overlay_entries)`` -- iterates
  every overlay entry, dispatches to the matching cleaner via the
  ``_OVERLAY_TYPE_CLEANUPS`` table, and applies the shared
  ``_drop_none_values`` + ``_elide_default_builder_level`` passes.

## Backward compatibility

``modules.output_overlays`` re-exports every public/private name
here so external callers keep working unchanged.
"""

from __future__ import annotations

_COMMONSENSE_ALIASES = frozenset(
    {
        "commonsense",
        "overlay_content_rating_commonsense",
        "content_rating_commonsense",
    }
)


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
_COMMONSENSE_DEFAULTS = frozenset(_COMMONSENSE_ALIASES)
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
