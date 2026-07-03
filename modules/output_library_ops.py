"""Per-library builders for build_libraries_section.

Extracted incrementally from the giant ``add_entry`` closure inside
``modules/output.py``.  Each function here takes the raw form-input
dict (``attr_group``, ``top_group``, or ``template_data``) plus a
couple of identity keys, and returns the operation / entry-field
value ready for YAML serialization (or an empty container when the
input is disabled/absent).

Naming conventions:
  * ``build_<operation_name>_operation`` -- goes under ``entry.operations``
  * ``build_<field_group>_fields``       -- merged into ``entry`` directly
  * ``build_template_variables``         -- goes under ``entry.template_variables``

Public surface: none.  These helpers are called from the
``build_libraries_section`` orchestrator; ``output.py`` imports each
name without underscore because they're consumed inside the same
package.
"""

from __future__ import annotations

import json

from ruamel.yaml.comments import CommentedSeq

from modules import helpers
from modules.output_values import _coerce_bool

# Values that we treat as "no override provided" for the numeric-ish
# knobs inside operation blocks.  Users can wipe a field by clearing
# the form input, which arrives as one of these placeholders.
_EMPTY_OVERRIDE_VALUES = frozenset({None, "", "None", "none"})


def _attr_key(library_type, lib_id, suffix):
    """Compose the per-library attribute lookup key.

    Consolidates the ``f"{library_type}-library_{lib_id}-attribute_{...}"``
    string builder that appears literally dozens of times inside
    ``add_entry``.  Not exported for now -- callers stay within this
    module.
    """
    return f"{library_type}-library_{lib_id}-attribute_{suffix}"


def _parse_json_list(raw_value, context_label):
    """Best-effort ``json.loads`` returning a list, or ``None`` on failure.

    ``context_label`` is used purely for the debug/error log message so
    callers can distinguish which input misbehaved.
    """
    if not raw_value:
        return None
    try:
        parsed = json.loads(raw_value)
    except Exception as e:
        helpers.ts_log(f"Skipping invalid JSON in {context_label}: {raw_value} - {e}", level="ERROR")
        return None
    return parsed if isinstance(parsed, list) else None


def build_delete_collections_operation(attr_group, library_type, lib_id):
    """Return the ``delete_collections`` operations dict, or an empty dict.

    Reads four attribute inputs off ``attr_group``:

    * ``delete_collections_configured`` -- bool
    * ``delete_collections_managed`` -- bool
    * ``delete_collections_ignore_empty_smart_collections`` -- bool
    * ``delete_collections_less`` -- int (or empty)

    Returns an empty dict when none of the four are actually set --
    callers should treat that as "don't emit a delete_collections
    block".  When at least one input is set, returns a dict shaped
    like the Kometa ``operations.delete_collections`` schema:

        {
            "configured": bool,
            "managed": bool,
            "less": int,                              # if provided
            "ignore_empty_smart_collections": True,   # if enabled
        }
    """
    configured_value = _coerce_bool(attr_group.get(_attr_key(library_type, lib_id, "delete_collections_configured")))
    managed_value = _coerce_bool(attr_group.get(_attr_key(library_type, lib_id, "delete_collections_managed")))
    ignore_value = _coerce_bool(attr_group.get(_attr_key(library_type, lib_id, "delete_collections_ignore_empty_smart_collections")))

    less_value = None
    raw_less = attr_group.get(_attr_key(library_type, lib_id, "delete_collections_less"))
    if raw_less not in _EMPTY_OVERRIDE_VALUES:
        try:
            less_value = int(raw_less)
        except Exception:
            helpers.ts_log(f"Skipping invalid delete_collections_less value: {raw_less}", level="DEBUG")

    enabled = configured_value is True or managed_value is True or ignore_value is True or less_value is not None
    if not enabled:
        return {}

    result = {
        "configured": configured_value if configured_value is not None else False,
        "managed": managed_value if managed_value is not None else False,
    }
    if less_value is not None:
        result["less"] = less_value
    if ignore_value is True:
        result["ignore_empty_smart_collections"] = True
    return result


def build_mass_genre_update_operation(attr_group, library_type, lib_id):
    """Return the ``mass_genre_update`` operations value, or an empty list.

    Two attribute inputs feed this operation:

    * ``mass_genre_update_order``  -- JSON list of sortable source strings.
      Each string becomes a top-level entry.  Items shaped like
      ``"[foo]"`` are treated as malformed UI leftovers and skipped.
      Nested-list items get flattened.
    * ``mass_genre_update_custom`` -- JSON list of custom genre strings
      (e.g. ``["Thriller", "Action"]``).  The whole list is appended as
      a single nested flow-style sequence so the emitted YAML reads
      ``- [Thriller, Action]``.

    Returns the assembled list (order + optional nested-custom).  An
    empty list means the operation is disabled and shouldn't be emitted.
    """
    result = []

    order_items = _parse_json_list(
        attr_group.get(_attr_key(library_type, lib_id, "mass_genre_update_order")),
        "custom genre",
    )
    if order_items is not None:
        for item in order_items:
            if isinstance(item, str) and item.startswith("[") and item.endswith("]"):
                # Probably malformed nested list -- skip
                continue
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, list):  # rare case: nested list, flatten
                result.extend(item)

    custom_items = _parse_json_list(
        attr_group.get(_attr_key(library_type, lib_id, "mass_genre_update_custom")),
        "custom genre strings",
    )
    if custom_items:  # non-empty list only
        # Wrap in a flow-style CommentedSeq so YAML emits `[a, b]` inline.
        custom_flow_list = CommentedSeq(custom_items)
        custom_flow_list.fa.set_flow_style()
        result.append(custom_flow_list)

    return result


# Keys read from attr_group for each 'mass_<media>_update' operation.
# Poster has one extra key (ignore_overlays) that background lacks;
# otherwise the shape is identical, which is why they share a helper.
_MASS_POSTER_UPDATE_KEYS = ("seasons", "episodes", "ignore_locked", "ignore_overlays", "source")
_MASS_BACKGROUND_UPDATE_KEYS = ("seasons", "episodes", "ignore_locked", "source")

# Values that the mass_poster/background 'empty' check considers
# 'user hasn't set this field' -- distinct from _EMPTY_OVERRIDE_VALUES
# because these two operations skip 'False' (boolean off) rather than
# only string placeholders.
_MASS_MEDIA_EMPTY_VALUES = frozenset({None, False, ""})


def _build_mass_media_update_operation(attr_group, library_type, lib_id, media_kind, keys):
    """Shared builder for the two mass_<media>_update operations.

    ``media_kind`` is ``"poster"`` or ``"background"`` -- used to compose
    the ``mass_<media>_<key>`` attribute lookup keys.  ``keys`` is the
    tuple of subfields to check (see ``_MASS_POSTER_UPDATE_KEYS`` /
    ``_MASS_BACKGROUND_UPDATE_KEYS``).

    Returns a dict of the subfields whose value is non-empty, or an
    empty dict when the whole operation should be skipped.
    """
    result = {}
    for key in keys:
        val = attr_group.get(_attr_key(library_type, lib_id, f"mass_{media_kind}_{key}"))
        if val not in _MASS_MEDIA_EMPTY_VALUES:
            result[key] = val
    return result


def build_mass_poster_update_operation(attr_group, library_type, lib_id):
    """Return the ``mass_poster_update`` operations dict, or empty.

    Reads five per-library attribute inputs:
    ``mass_poster_seasons``, ``mass_poster_episodes``,
    ``mass_poster_ignore_locked``, ``mass_poster_ignore_overlays``,
    ``mass_poster_source``.  Any subfield with a truthy-ish value
    (i.e. not ``None``, ``False``, or the empty string) is included.
    """
    return _build_mass_media_update_operation(attr_group, library_type, lib_id, "poster", _MASS_POSTER_UPDATE_KEYS)


def build_mass_background_update_operation(attr_group, library_type, lib_id):
    """Return the ``mass_background_update`` operations dict, or empty.

    Same shape as :func:`build_mass_poster_update_operation` but reads
    four inputs (no ``ignore_overlays``): ``mass_background_seasons``,
    ``mass_background_episodes``, ``mass_background_ignore_locked``,
    ``mass_background_source``.
    """
    return _build_mass_media_update_operation(attr_group, library_type, lib_id, "background", _MASS_BACKGROUND_UPDATE_KEYS)


def build_mapper_operations(attr_group, library_type, lib_id):
    """Return a dict of the enabled mapper operations.

    Reads ``genre_mapper`` and ``content_rating_mapper`` attribute
    inputs.  Each value is expected to be a JSON-encoded dict; when
    valid and non-empty, it's copied into the returned dict under
    the matching key.

    Returns an empty dict if neither mapper is set (or both are
    invalid/empty).  Callers should merge the result into their
    ``operations`` dict.
    """
    result = {}
    for mapper_key in ("genre_mapper", "content_rating_mapper"):
        raw_value = attr_group.get(_attr_key(library_type, lib_id, mapper_key))
        if not raw_value:
            continue
        try:
            parsed = json.loads(raw_value)
        except Exception as e:
            helpers.ts_log(f"Skipping invalid JSON for {mapper_key}: {raw_value} - {e}", level="ERROR")
            continue
        if isinstance(parsed, dict) and parsed:
            result[mapper_key] = parsed
    return result


def build_metadata_backup_operation(attr_group, library_type, lib_id):
    """Return the ``metadata_backup`` operations dict, or empty.

    Reads four attribute inputs:

    * ``metadata_backup_path`` -- filesystem path (string).
    * ``metadata_backup_exclude`` -- JSON list; only included when it
      parses to a non-empty list.
    * ``sync_tags`` -- included only when literally ``True``.
    * ``add_blank_entries`` -- included only when literally ``True``.

    Returns an empty dict when none of the four are set; callers
    should treat that as 'don't emit a metadata_backup block'.
    """
    result = {}

    path_value = attr_group.get(_attr_key(library_type, lib_id, "metadata_backup_path"))
    if path_value:
        result["path"] = path_value

    exclude_raw = attr_group.get(_attr_key(library_type, lib_id, "metadata_backup_exclude"))
    if exclude_raw:
        try:
            parsed = json.loads(exclude_raw) if isinstance(exclude_raw, str) else exclude_raw
        except Exception as e:
            helpers.ts_log(f"Skipping invalid exclude value: {exclude_raw} - {e}", level="ERROR")
            parsed = None
        if isinstance(parsed, list) and parsed:  # non-empty list only
            result["exclude"] = parsed

    if attr_group.get(_attr_key(library_type, lib_id, "sync_tags")) is True:
        result["sync_tags"] = True
    if attr_group.get(_attr_key(library_type, lib_id, "add_blank_entries")) is True:
        result["add_blank_entries"] = True

    return result


# The five 'top_level' fields whose emptiness rule is 'None or empty
# string means user didn't set it'.  ``remove_overlays`` uses a
# truthy check and ``reset_overlays`` also filters the literal
# string 'None' (UI leftover), so they're handled inline below.
_TOP_LEVEL_SIMPLE_FIELDS = (
    "report_path",
    "schedule",
    "auto_sort_hubs",
    "schedule_overlays",
)


def _top_level_key(library_type, lib_id, suffix):
    """Compose a ``top_level_<suffix>`` lookup key.

    Mirrors :func:`_attr_key` but for the ``top_level`` namespace so
    ``top_group.get(_top_level_key(...))`` reads clean.
    """
    return f"{library_type}-library_{lib_id}-top_level_{suffix}"


def build_top_level_fields(top_group, library_type, lib_id):
    """Return the top-level fields dict to merge into a library's entry.

    Reads six top-level inputs off ``top_group``:

    * ``report_path``, ``schedule``, ``auto_sort_hubs``, ``schedule_overlays``
      -- included when the value isn't ``None`` or empty string.
    * ``remove_overlays`` -- included as literal ``True`` when the raw
      value is truthy.  (The stored value is always emitted as ``True``
      per the Kometa schema; we only care whether it was set.)
    * ``reset_overlays`` -- included when the value isn't ``None``,
      empty string, or the literal string ``"None"`` (a UI leftover).

    Returns an empty dict when none of the six are set.  Callers merge
    the result into their per-library entry dict via ``entry.update(...)``.
    """
    result = {}

    for field in _TOP_LEVEL_SIMPLE_FIELDS:
        value = top_group.get(_top_level_key(library_type, lib_id, field))
        if value not in (None, ""):
            result[field] = value

    if top_group.get(_top_level_key(library_type, lib_id, "remove_overlays")):
        result["remove_overlays"] = True

    reset_overlays = top_group.get(_top_level_key(library_type, lib_id, "reset_overlays"))
    if reset_overlays not in (None, "None", ""):
        result["reset_overlays"] = reset_overlays

    return result


# Suffix -> template_variables output key.  We iterate template_data
# looking for keys ending in one of these six suffixes with the
# matching library prefix, and stash the value under the mapped key.
# The prefix is checked so a movie library doesn't accidentally pick
# up template variables meant for a show library with the same lib_id.
_TEMPLATE_VAR_SUFFIXES = {
    "-template_variables[use_separator]": "use_separator",
    "-attribute_template_variables[placeholder_imdb_id]": "placeholder_imdb_id",
    "-attribute_template_variables[placeholder_tmdb_movie]": "placeholder_tmdb_movie",
    "-attribute_template_variables[placeholder_tvdb_show]": "placeholder_tvdb_show",
    "-template_variables[language]": "language",
    "-template_variables[collection_mode]": "collection_mode",
}


def _discover_template_variables(template_data, library_type, template_key):
    """Walk ``template_data`` and pull out the six known template-variable inputs.

    Returns a dict keyed by the output name (``use_separator``,
    ``placeholder_imdb_id``, ...).  Missing inputs are simply absent
    from the returned dict.
    """
    prefix = f"{library_type}-library_{template_key}"
    discovered = {}
    for key, value in template_data.items():
        if not key.startswith(prefix):
            continue
        for suffix, output_name in _TEMPLATE_VAR_SUFFIXES.items():
            if key.endswith(suffix):
                discovered[output_name] = value
                break
    return discovered


def build_template_variables(templates, library_type, library_key, has_collectionless):
    """Return the ``template_variables`` dict for a library entry.

    Extracts the template-key from ``library_key`` (via
    :func:`helpers.extract_library_name`), looks up the matching
    template-data dict in ``templates``, and walks it for the six
    known template-variable inputs.  Assembles the result into the
    shape Kometa expects.

    Rules:
      * ``use_separator`` is always emitted (defaults ``False``).
      * ``sep_style`` is emitted only when a separator color is set --
        the raw value from the form doubles as the style.
      * For movie libraries (``library_type == "mov"``), the
        ``placeholder_tmdb_movie`` input wins over ``placeholder_imdb_id``.
        For show libraries, ``placeholder_tvdb_show`` wins.
      * ``language`` and ``collection_mode`` are passed through when set.
      * If the library has a collectionless entry (``has_collectionless``),
        ``collection_mode`` is forced to ``"hide"`` (overriding any
        user-set value).
    """
    template_key = helpers.extract_library_name(library_key)
    template_data = templates.get(template_key, {})
    discovered = _discover_template_variables(template_data, library_type, template_key)

    sep_color = discovered.get("use_separator")
    template_vars = {"use_separator": bool(sep_color)}
    if sep_color:
        template_vars["sep_style"] = sep_color

    # Placeholder selection: media-specific placeholder wins over the
    # generic IMDB fallback.
    imdb_fallback = discovered.get("placeholder_imdb_id")
    if library_type == "mov":
        primary = discovered.get("placeholder_tmdb_movie")
        primary_key = "placeholder_tmdb_movie"
    else:
        primary = discovered.get("placeholder_tvdb_show")
        primary_key = "placeholder_tvdb_show"
    if primary:
        template_vars[primary_key] = primary
    elif imdb_fallback:
        template_vars["placeholder_imdb_id"] = imdb_fallback

    for optional_key in ("language", "collection_mode"):
        value = discovered.get(optional_key)
        if value:
            template_vars[optional_key] = value

    if has_collectionless:
        template_vars["collection_mode"] = "hide"

    return template_vars
