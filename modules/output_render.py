"""Orchestration helpers for ``build_config``.

Extracted from ``modules.output.build_config``.

This module owns the wrap-around orchestration that sits at both ends
of ``build_config``: pulling per-section data out of persistence at the
start, and running the fixed transformation chain before YAML dump
at the end.  The library-processing phase in the middle lives in
:mod:`modules.output_libraries_data` /
:mod:`modules.output_libraries_section`.

Public entry points:

* :func:`retrieve_config_sections` -- walk the template list and pull
  every validated section out of persistence.  Returns
  ``(config_data, header_art)`` where the latter is the pre-rendered
  header-art dict keyed by section name.

* :data:`ORDERED_CONFIG_SECTIONS` -- the compile-time section order
  used when writing YAML.  Loaded once at import time.

* :func:`apply_final_transformations` -- the six-step chain that
  scrubs, optimizes, and reshapes ``config_data`` before dump.
  Preserves the exact call order because several later steps assume
  earlier ones have already run.

Private helpers:

* :func:`_strip_mal_code_verifier` -- one-line PKCE half-secret scrub.
"""

from __future__ import annotations

import copy

from modules import helpers, persistence
from modules.output_collections import (
    _collapse_collection_data_template_vars,
    _normalize_legacy_collection_template_vars,
)
from modules.output_headers import render_section_header
from modules.output_optimize import optimize_template_variables
from modules.output_postprocess import _rewrite_custom_font_paths, clean_section_data


def retrieve_config_sections(header_style):
    """Walk the template list and pull every validated section into memory.

    Returns ``(config_data, header_art)``:

    * ``config_data`` -- ``{config_attribute: cleaned_section_data}``
      for every section whose persistence row has ``validated=True``.
      Deep-copied at read time so any downstream normalization can
      mutate freely without corrupting the persistence-layer cache
      for the rest of the request lifecycle.
    * ``header_art`` -- ``{config_attribute: rendered_header_string}``
      pre-rendered once per section using *header_style*.  The dump
      loop later re-uses these instead of re-rendering per section.

    Reads section data via :mod:`modules.persistence`, so must be
    called within a Flask app context (persistence depends on
    ``current_app`` for its DB handle).

    A section that isn't validated is skipped for ``config_data`` but
    still gets its header art rendered -- ``build_config``'s dump loop
    won't emit it (guarded by ``section_key in config_data``) but the
    header would be available if a future caller wanted to render
    an empty-but-present section.
    """
    sections = helpers.get_template_list()
    config_data = {}
    header_art = {}

    for name in sections:
        item = sections[name]
        persistence_key = item["stem"]
        config_attribute = item["raw_name"]

        header_art[config_attribute] = render_section_header(item["name"], header_style)

        # Deep-copy here so YAML normalization can't mutate the
        # in-memory persistence cache for this request lifecycle.
        section_data = copy.deepcopy(persistence.retrieve_settings(persistence_key))

        if "validated" in section_data and section_data["validated"]:
            config_data[config_attribute] = clean_section_data(section_data, config_attribute)

    return config_data, header_art


# The order Kometa's YAML file uses for top-level sections.  Anchored
# alongside the render logic so both live in the same module.  Second
# element is the persistence stem (used only when a section is present).
#
# Kometa doesn't care about section order but this ordering keeps
# generated files stable and diff-friendly across regenerations.
ORDERED_CONFIG_SECTIONS = (
    ("libraries", "025-libraries"),
    ("playlist_files", "027-playlist_files"),
    ("settings", "150-settings"),
    ("webhooks", "140-webhooks"),
    ("plex", "010-plex"),
    ("tmdb", "020-tmdb"),
    ("tautulli", "030-tautulli"),
    ("github", "040-github"),
    ("omdb", "050-omdb"),
    ("mdblist", "060-mdblist"),
    ("notifiarr", "070-notifiarr"),
    ("gotify", "080-gotify"),
    ("ntfy", "085-ntfy"),
    ("apprise", "087-apprise"),
    ("anidb", "090-anidb"),
    ("radarr", "100-radarr"),
    ("sonarr", "110-sonarr"),
    ("trakt", "120-trakt"),
    ("mal", "130-mal"),
)


def _strip_mal_code_verifier(config_data):
    """Remove ``code_verifier`` from ``config_data['mal']['mal']['authorization']``.

    The ``code_verifier`` is the client-side half of a PKCE flow and
    should never be persisted to the emitted config -- it's a short-
    lived request-time secret.  Best-effort: silently no-ops when
    the surrounding structure isn't present.
    """
    if "mal" not in config_data or "mal" not in config_data["mal"]:
        return
    authorization_data = config_data["mal"]["mal"].get("authorization", {})
    authorization_data.pop("code_verifier", None)


def apply_final_transformations(config_data, library_types, *, optimize_defaults=True):
    """Run the fixed pre-dump transformation chain.

    Order matters -- each step assumes its predecessor's shape.

    1. Strip ``code_verifier`` from any ``mal.authorization`` block.
    2. Normalize legacy collection template variables.  Turns older
       persistence shapes into the canonical shape expected by
       ``optimize_template_variables``.
    3. (Optional) Optimize template variables against defaults so
       explicit values matching the default set are dropped.  Skipped
       when *optimize_defaults* is falsy (used by tests that need to
       inspect the un-optimized values).
    4. Collapse ``collection_data`` template variables into their
       canonical single-line shape.
    5. Enforce string typing for every field in
       :data:`helpers.STRING_FIELDS`.
    6. Rewrite user-supplied custom font paths to their config-relative
       equivalents.

    Returns the transformed ``config_data``.  Steps 2-6 return new
    dicts (some are functional; others mutate and return).  Step 1
    mutates the input.  Callers should not rely on ``id(config_data)``
    staying stable.
    """
    _strip_mal_code_verifier(config_data)
    config_data = _normalize_legacy_collection_template_vars(config_data)
    if optimize_defaults:
        config_data = optimize_template_variables(config_data, library_types)
    config_data = _collapse_collection_data_template_vars(config_data)
    config_data = helpers.enforce_string_fields(config_data, helpers.STRING_FIELDS)
    config_data = _rewrite_custom_font_paths(config_data)
    return config_data
