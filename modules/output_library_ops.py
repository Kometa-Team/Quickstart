"""Per-library operation builders for build_libraries_section.

Extracted incrementally from the giant ``add_entry`` closure inside
``modules/output.py``.  Each function here takes the raw
``attr_group`` dict for one library plus a couple of identity keys,
and returns the operation's YAML-ready value (or ``None`` when the
operation is disabled).

The naming convention is ``build_<operation_name>_operation`` so it's
obvious what shape the return type matches.

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
