"""Library-scoped data grouping for Kometa config generation.

Extracted from ``modules.output.build_config``.

The Quickstart persistence layer stores every library-scoped setting
as a flat key/value pair, with keys shaped like
``<mov|sho>-library_<id>-<kind>_<name>[option]``.  To emit the YAML
config we need those flattened keys re-nested per library and per
kind (collections, overlays, attributes, templates, etc.).

``group_by_library`` filters the flat map by a ``prefix`` classifier
and re-groups the matching entries by their extracted library id.
Overlays additionally strip the builder-level suffix
(``-movie``/``-show``/``-season``/``-episode``) so that all three
builder levels for one show library land in the same group.

The related dispatcher ``group_movie_and_show_libraries`` runs the
full set of nine kinds twice (once for the movie library set, once
for the show library set) and returns two dicts of dicts.  It also
folds ``overlay_files`` into ``overlays`` -- Kometa treats the raw
block as another overlay source, and the caller was doing this fold
inline for both library types.
"""

from __future__ import annotations

from modules import helpers

# Substring predicates for each prefix classifier.  Keeping these as
# module-level lambdas (rather than an if/elif chain inside the
# grouping function) means each row is one line and the mapping is
# obvious.  Predicates run against a stringified key.
_INFIX_MATCHERS = {
    "collection_": lambda key: "-collection_" in key or "-template_collection_" in key,
    "overlay_": lambda key: "-overlay_" in key or "-template_overlay_" in key,
    "attribute_": lambda key: "-attribute_" in key,
    "template_variables": lambda key: ("-template_variables" in key or "-attribute_template_variables" in key),
    "top_level_": lambda key: "-top_level_" in key,
}

# For these three prefixes the classifier is a strict trailing
# suffix rather than a substring: ``mov-library_<id>-collection_files``
# etc.  Keeping the raw ``*_files`` blocks separate from the
# collection/overlay group entries prevents them from suppressing
# built-in defaults during YAML emission.
_SUFFIX_KINDS = frozenset({"collection_files", "overlay_files", "metadata_files"})

# Builder-level suffixes on overlay keys.  A show library called
# ``TVShows`` produces keys like ``sho-library_TVShows-show-overlay_...``
# for show-level overlays, ``sho-library_TVShows-season-overlay_...``
# for season-level, and so on.  When normalising we strip whichever
# suffix is present so the three builder levels re-merge under the
# base library id.
_OVERLAY_LEVEL_SUFFIXES = ("-movie", "-show", "-season", "-episode")


def _key_matches_prefix(key, prefix):
    """Return True when *key* belongs to the group named *prefix*.

    Not exported -- this is the classifier used by
    :func:`group_by_library`.  Split out for clarity and testability.
    """
    if not isinstance(key, str):
        return False
    matcher = _INFIX_MATCHERS.get(prefix)
    if matcher is not None:
        return matcher(key)
    if prefix in _SUFFIX_KINDS:
        return key.endswith(f"-{prefix}")
    return prefix in key


def _strip_overlay_builder_suffix(lib_name_raw):
    """Trim any ``-movie``/``-show``/``-season``/``-episode`` suffix.

    Returns *lib_name_raw* unchanged when it isn't a string or doesn't
    end with any of the known builder levels.
    """
    if not isinstance(lib_name_raw, str):
        return lib_name_raw
    for suffix in _OVERLAY_LEVEL_SUFFIXES:
        if lib_name_raw.endswith(suffix):
            return lib_name_raw[: -len(suffix)]
    return lib_name_raw


def group_by_library(prefix, names, source, *, normalize_overlays=False):
    """Group *source* entries by base library name.

    Parameters
    ----------
    prefix:
        Kind classifier.  Recognised values include
        ``collection_``, ``overlay_``, ``attribute_``,
        ``template_variables``, ``top_level_``,
        ``collection_files``, ``overlay_files``, ``metadata_files``.
        Any other value falls back to a plain substring match.
    names:
        Set (or any container) of library ids to keep.  Entries whose
        extracted library id is not in *names* are dropped.
    source:
        Flat key/value map -- typically the ``libraries.libraries``
        payload from persistence.
    normalize_overlays:
        When True, strip a trailing builder-level suffix
        (``-movie``/``-show``/``-season``/``-episode``) from each
        extracted library id before grouping.  Only used for
        overlay-kind prefixes.
    """
    grouped = {}
    for key, value in source.items():
        if not _key_matches_prefix(key, prefix):
            continue
        lib_name_raw = helpers.extract_library_name(key)
        lib_name = _strip_overlay_builder_suffix(lib_name_raw) if normalize_overlays else lib_name_raw
        if lib_name in names:
            grouped.setdefault(lib_name, {})[key] = value
    return grouped


# Ordered specification of which grouped dicts ``build_config``
# builds and how.  Each row is (attribute_stem, prefix,
# normalize_overlays).  ``attribute_stem`` becomes both the
# ``movie_<stem>`` and ``show_<stem>`` variable names on the returned
# dispatcher result.
_GROUPING_SPECS = (
    ("collections", "collection_", False),
    ("collection_files", "collection_files", False),
    ("overlay_file_blocks", "overlay_files", False),
    ("overlays", "overlay_", True),
    ("attributes", "attribute_", False),
    ("metadata_files", "metadata_files", False),
    ("templates", "template_variables", False),
    ("top_level", "top_level_", False),
)


def group_movie_and_show_libraries(source, movie_library_names, show_library_names):
    """Group *source* for both library sets across all grouping kinds.

    Returns two dicts (``movie_groups``, ``show_groups``) keyed by
    the attribute stem from :data:`_GROUPING_SPECS`.  Overlay-files
    payloads are folded into the corresponding ``overlays`` group --
    Kometa treats the raw ``<prefix>-overlay_files`` block as an
    additional overlay source and the caller was doing this fold
    inline for both library types.

    So::

        movie_groups["overlays"] == group_by_library("overlay_", ..., normalize_overlays=True)
                                        merged-with(overlay_files payloads)
        movie_groups["collections"] == group_by_library("collection_", ...)
        ...

    Access via ``movie_groups["<stem>"]``.  The two overlay-file
    payloads (``movie_overlay_file_blocks`` and
    ``show_overlay_file_blocks``) remain visible so the caller can
    still log them separately when needed.
    """

    def _make(names):
        return {stem: group_by_library(prefix, names, source, normalize_overlays=norm) for stem, prefix, norm in _GROUPING_SPECS}

    movie_groups = _make(movie_library_names)
    show_groups = _make(show_library_names)

    # Fold each overlay_files payload into the matching overlays
    # group so callers see a unified overlay source per library.
    for groups in (movie_groups, show_groups):
        for lib_name, payload in groups["overlay_file_blocks"].items():
            groups["overlays"].setdefault(lib_name, {}).update(payload)

    return movie_groups, show_groups
