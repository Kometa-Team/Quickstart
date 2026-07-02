"""Canonical key-ordering for library sections.

Extracted from the original ``modules/output.py`` monolith.  Kometa's
generated ``config.yml`` benefits from a consistent library-block key
order -- ``report_path`` first, then schedule bits, then template
variables, then settings/arr/operations, then the file lists.  This
module owns that ordering.

Public surface: ``reorder_library_section`` is called from inside
``output.py`` (during config build) and from ``tests/`` directly as
``output.reorder_library_section``, so it MUST re-export.
"""

from __future__ import annotations

# Top-level library key ordering.  Everything not in this tuple falls
# through to the natural-order tail so we never accidentally drop
# unknown keys.
_LIBRARY_KEY_ORDER = (
    # 1. Reporting output for the run
    "report_path",
    # 2. Scheduling / overlay housekeeping
    "schedule",
    "auto_sort_hubs",
    "remove_overlays",
    "reset_overlays",
    "schedule_overlays",
    # 3. Template variables shared by every entry in the library
    "template_variables",
    # 4. Library-scope settings and per-library Arr overrides
    "settings",
    "radarr",
    "sonarr",
    # 5. Operations -- special-cased below with its own inner ordering
    "operations",
    # 6. File lists (metadata comes before collections comes before overlays)
    "metadata_files",
    "collection_files",
    "overlay_files",
)


# Canonical order for the inner ``operations`` block.  From the Kometa
# Wiki -- any operation not in this list will be appended to the end
# in its natural order.
_OPERATIONS_ORDER = (
    "assets_for_all",
    "assets_for_all_collections",
    "delete_collections",
    "mass_genre_update",
    "mass_content_rating_update",
    "mass_original_title_update",
    "mass_studio_update",
    "mass_originally_available_update",
    "mass_added_at_update",
    "mass_audience_rating_update",
    "mass_critic_rating_update",
    "mass_user_rating_update",
    "mass_episode_audience_rating_update",
    "mass_episode_critic_rating_update",
    "mass_episode_user_rating_update",
    "mass_poster_update",
    "mass_background_update",
    "mass_imdb_parental_labels",
    "mass_collection_mode",
    "update_blank_track_titles",
    "remove_title_parentheses",
    "split_duplicates",
    "radarr_add_all",
    "radarr_remove_by_tag",
    "sonarr_add_all",
    "sonarr_remove_by_tag",
    "genre_mapper",
    "content_rating_mapper",
    "metadata_backup",
)


def _reorder_by_template(data, key_order):
    """Return a new dict with ``key_order`` keys first, unknowns appended.

    Only keys that actually exist in ``data`` are emitted -- there's no
    autovivification.  Preserves the natural insertion order of any
    unknown keys.
    """
    reordered = {key: data[key] for key in key_order if key in data}
    for key, value in data.items():
        if key not in reordered:
            reordered[key] = value
    return reordered


def reorder_library_section(library_data):
    """Reorder a library-section dict into Kometa's canonical key order.

    Ordering rules (see ``_LIBRARY_KEY_ORDER`` for the full tuple):

    * ``report_path`` first
    * ``schedule``, then ``auto_sort_hubs``, then the overlay-schedule keys
    * ``template_variables``
    * ``settings``, ``radarr``/``sonarr``, ``operations`` (with its own
      inner reordering against ``_OPERATIONS_ORDER``)
    * File lists last: ``metadata_files`` -> ``collection_files`` -> ``overlay_files``
    * Any other keys retain their natural insertion order at the tail

    Returns a *new* dict.  The input is not modified.
    """
    reordered = _reorder_by_template(library_data, _LIBRARY_KEY_ORDER)
    if isinstance(reordered.get("operations"), dict):
        reordered["operations"] = _reorder_by_template(reordered["operations"], _OPERATIONS_ORDER)
    return reordered
