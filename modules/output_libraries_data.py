"""Library data extraction from persisted flat keys.

Extracted from ``modules.output.build_config``.

Between the user's UI selections and the emitted YAML, Kometa's
Quickstart needs to walk the flat persistence map, identify which
libraries are selected (movie vs show), and then re-group all of
their attribute keys per library.  This module owns that walk.

Public entry point:

* :func:`extract_libraries_bundle(nested_libraries_data, *, debug=False)`
  returns a :class:`LibrariesBundle` carrying every derivative the
  downstream orchestrator needs.

Splitting this out shrinks ``build_config`` by ~55 lines (~10% of
its remaining bulk) and gives future callers a single call to
prepare libraries data instead of hand-writing the four extraction
comprehensions + grouping call + 18-line debug logging block.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules import helpers
from modules.output_grouping import group_movie_and_show_libraries

# Placeholder values considered equivalent to "unselected".  Kometa
# treats each of these as a missing library toggle -- the UI stores
# unset checkboxes as ``False`` while some older rows may still be
# ``None`` or the empty string.
_UNSELECTED_LIBRARY_VALUES = (None, "", False)


@dataclass(frozen=True)
class LibrariesBundle:
    """Every derivative ``build_libraries_section`` needs about the selected libraries.

    Attributes are named to match the local variables ``build_config``
    used to compute inline; downstream code can be migrated to the
    bundle in a follow-up refactor without touching this module.

    * ``movie_libraries`` / ``show_libraries``:
      ``{persisted_key: display_name}`` maps of the selected libraries.
    * ``movie_library_names`` / ``show_library_names``:
      Sets of extracted library-id stems (from
      :func:`helpers.extract_library_name`).
    * ``library_types``: ``{display_name: \"movie\"|\"show\"}`` -- the
      inverse map used by ``optimize_template_variables`` to decide
      per-library default sets.
    * ``movie_groups`` / ``show_groups``:
      Result of :func:`group_movie_and_show_libraries` -- each is
      keyed by grouping stem (\"collections\", \"overlays\",
      \"attributes\", ...) and each value is
      ``{library_id: {flat_key: value}}``.
    """

    movie_libraries: dict = field(default_factory=dict)
    show_libraries: dict = field(default_factory=dict)
    movie_library_names: set = field(default_factory=set)
    show_library_names: set = field(default_factory=set)
    library_types: dict = field(default_factory=dict)
    movie_groups: dict = field(default_factory=dict)
    show_groups: dict = field(default_factory=dict)

    def to_section_kwargs(self):
        """Unpack the bundle into the 16-kwarg form ``build_libraries_section`` wants.

        Each keyword falls back to an empty dict when the corresponding
        grouping stem isn't present -- matches
        ``build_libraries_section``'s own default-coercion so callers
        get identical behavior whether they use the bundle or hand-pass
        args.

        Returns a plain dict suitable for ``**kwargs`` unpacking, e.g.::

            libraries_section = build_libraries_section(**bundle.to_section_kwargs())
        """
        return {
            "movie_libraries": self.movie_libraries,
            "show_libraries": self.show_libraries,
            "movie_collections": self.movie_groups.get("collections", {}),
            "show_collections": self.show_groups.get("collections", {}),
            "movie_collection_files": self.movie_groups.get("collection_files", {}),
            "show_collection_files": self.show_groups.get("collection_files", {}),
            "movie_overlays": self.movie_groups.get("overlays", {}),
            "show_overlays": self.show_groups.get("overlays", {}),
            "movie_attributes": self.movie_groups.get("attributes", {}),
            "show_attributes": self.show_groups.get("attributes", {}),
            "movie_metadata_files": self.movie_groups.get("metadata_files", {}),
            "show_metadata_files": self.show_groups.get("metadata_files", {}),
            "movie_templates": self.movie_groups.get("templates", {}),
            "show_templates": self.show_groups.get("templates", {}),
            "movie_top_level": self.movie_groups.get("top_level", {}),
            "show_top_level": self.show_groups.get("top_level", {}),
        }


def _is_selected_library_key(key, prefix):
    """Return True when *key* is a selected top-level library toggle.

    Recognized shape: ``<prefix>library_<id>-library`` with a truthy
    value.  Anything else (attribute keys, unset toggles) is skipped.
    """
    return isinstance(key, str) and key.startswith(prefix) and key.endswith("-library")


def _select_libraries(nested_libraries_data, prefix):
    """Return ``{key: value}`` for all selected libraries under *prefix*.

    Filters ``nested_libraries_data`` to entries whose key starts
    with *prefix* (``\"mov-library_\"`` or ``\"sho-library_\"``), ends
    with ``-library``, and has a non-placeholder value.
    """
    return {key: value for key, value in nested_libraries_data.items() if _is_selected_library_key(key, prefix) and value not in _UNSELECTED_LIBRARY_VALUES}


def _debug_log_extracted(bundle, debug):
    """Emit the 18-line 'Extracted X:' debug dump when *debug* is truthy."""
    if not debug:
        return

    helpers.ts_log("Movie Library Names:", bundle.movie_library_names, level="DEBUG")
    helpers.ts_log("Show Library Names:", bundle.show_library_names, level="DEBUG")
    helpers.ts_log(f"Extracted Movie Libraries: {bundle.movie_libraries}", level="DEBUG")
    helpers.ts_log(f"Extracted Show Libraries: {bundle.show_libraries}", level="DEBUG")

    # Enumerate every grouping stem so adding a new one in
    # output_grouping._GROUPING_SPECS automatically shows up here
    # without another surgery in this module.
    for stem, group_dict in bundle.movie_groups.items():
        label = stem.replace("_", " ").title()
        helpers.ts_log(f"Extracted Movie {label}: {group_dict}", level="DEBUG")
    for stem, group_dict in bundle.show_groups.items():
        label = stem.replace("_", " ").title()
        helpers.ts_log(f"Extracted Show {label}: {group_dict}", level="DEBUG")


def extract_libraries_bundle(nested_libraries_data, *, debug=False):
    """Build the :class:`LibrariesBundle` from persisted flat data.

    * Filters the flat ``nested_libraries_data`` into selected movie
      and show library toggles.
    * Computes the library-id name sets via
      :func:`helpers.extract_library_name`.
    * Builds the ``library_types`` inverse map (display_name ->
      \"movie\" | \"show\") used by defaults optimization.
    * Runs :func:`group_movie_and_show_libraries` to produce the
      per-kind per-library grouped dicts.
    * When *debug* is truthy, emits the same 18-line ``ts_log``
      trace ``build_config`` used to emit inline.

    Returns a frozen :class:`LibrariesBundle`.  When
    ``nested_libraries_data`` doesn't contain any recognized
    library toggles, returns a bundle with empty defaults for every
    field -- safe to unpack into the downstream orchestrator.
    """
    movie_libraries = _select_libraries(nested_libraries_data, "mov-library_")
    show_libraries = _select_libraries(nested_libraries_data, "sho-library_")

    # Authoritative display names from Plex (id_str → name with spaces preserved).
    # Stored `-library` values may have been stripped; prefer the name map when the
    # key contains a numeric section ID (i.e. after the ID-based migration has run).
    from modules import persistence  # local import to avoid load-order cycle

    plex_name_map = persistence.get_library_names()
    if plex_name_map:
        movie_libraries = {k: plex_name_map.get(helpers.extract_library_name(k), v) for k, v in movie_libraries.items()}
        show_libraries = {k: plex_name_map.get(helpers.extract_library_name(k), v) for k, v in show_libraries.items()}

    movie_library_names = {helpers.extract_library_name(k) for k in movie_libraries}
    show_library_names = {helpers.extract_library_name(k) for k in show_libraries}

    library_types = {name: "movie" for name in movie_libraries.values()}
    library_types.update({name: "show" for name in show_libraries.values()})

    movie_groups, show_groups = group_movie_and_show_libraries(
        nested_libraries_data,
        movie_library_names,
        show_library_names,
    )

    bundle = LibrariesBundle(
        movie_libraries=movie_libraries,
        show_libraries=show_libraries,
        movie_library_names=movie_library_names,
        show_library_names=show_library_names,
        library_types=library_types,
        movie_groups=movie_groups,
        show_groups=show_groups,
    )
    _debug_log_extracted(bundle, debug)
    return bundle
