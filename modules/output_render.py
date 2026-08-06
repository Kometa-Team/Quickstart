"""Orchestration helpers for ``build_config``.

Extracted from ``modules.output.build_config``.

This module owns the full orchestration pipeline for ``build_config``:
pulling per-section data out of persistence at the start, building
the libraries subtree in the middle, and running the fixed
transformation chain plus YAML emission at the end.  Individual
builders (``build_libraries_section``, ``build_collection_files``,
etc.) live in their own modules; this module composes them.

Public entry points:

* :func:`retrieve_config_sections` -- walk the template list and pull
  every validated section out of persistence.  Returns
  ``(config_data, header_art)`` where the latter is the pre-rendered
  header-art dict keyed by section name.

* :func:`process_libraries_block` -- build the libraries subtree in
  place and return the per-library metadata (movie/show library
  toggles and library_types) needed for the emit phase.

* :data:`ORDERED_CONFIG_SECTIONS` -- the compile-time section order
  used when writing YAML.  Loaded once at import time.

* :func:`apply_final_transformations` -- the six-step chain that
  scrubs, optimizes, and reshapes ``config_data`` before dump.
  Preserves the exact call order because several later steps assume
  earlier ones have already run.

* :func:`emit_and_validate_config` -- final phase.  Combines
  ``apply_final_transformations``, YAML dump per section, and
  jsonschema validation into one call that returns the 5-tuple
  ``build_config`` needs to return to its caller.

Private helpers:

* :func:`_strip_mal_code_verifier` -- one-line PKCE half-secret scrub.
* :func:`_load_config_schema` -- open the config JSON schema once,
  return a shared YAML parser + parsed schema dict.
* :func:`_dump_config_sections` -- iterate
  :data:`ORDERED_CONFIG_SECTIONS` and append each section's YAML to
  the running text.
* :func:`_validate_yaml_content` -- run the parsed YAML through
  Draft7 jsonschema.
"""

from __future__ import annotations

import copy
import os

import jsonschema
from flask import current_app as app
from ruamel.yaml import YAML

from modules import helpers, persistence
from modules.output_collections import (
    _collapse_collection_data_template_vars,
    _normalize_legacy_collection_template_vars,
)
from modules.output_dump import dump_section
from modules.output_headers import render_section_header
from modules.output_libraries_data import extract_libraries_bundle
from modules.output_libraries_section import build_libraries_section
from modules.output_optimize import optimize_template_variables
from modules.output_playlists import apply_playlist_libraries_toggle
from modules.output_postprocess import _rewrite_custom_font_paths, clean_section_data
from modules.output_yaml_header import render_yaml_header
from modules.jsonschema_compat import stringify_mapping_keys_for_jsonschema


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


def process_libraries_block(config_data, *, debug=False):
    """Build the libraries subtree in place; return per-library metadata.

    Returns ``(movie_libraries, show_libraries, library_types)``.
    Mutates *config_data* in place: replaces its ``"libraries"`` entry
    with the nested libraries-section structure produced by
    :func:`build_libraries_section`, and applies the playlist-libraries
    toggle.

    When the source ``config_data`` doesn't contain a nested
    ``libraries.libraries`` block (e.g. no libraries were selected),
    returns three empty dicts and leaves *config_data* untouched --
    the emit phase later dumps an empty libraries section.

    The ``debug`` flag controls two ts_log dumps (raw input dict and
    final libraries-section dict) that are extremely noisy in
    production but useful when diagnosing library-config bugs.
    """
    if "libraries" not in config_data or "libraries" not in config_data["libraries"]:
        return {}, {}, {}

    nested_libraries_data = config_data["libraries"]["libraries"]
    if debug:
        helpers.ts_log("Raw nested libraries data:", nested_libraries_data, level="DEBUG")

    bundle = extract_libraries_bundle(nested_libraries_data, debug=debug)
    libraries_section = build_libraries_section(**bundle.to_section_kwargs())

    config_data["libraries"] = libraries_section.get("libraries", {}) if isinstance(libraries_section, dict) else {}
    apply_playlist_libraries_toggle(config_data, nested_libraries_data, libraries_section)

    if debug:
        helpers.ts_log(f"Final Libraries Section: {libraries_section}", level="DEBUG")

    return bundle.movie_libraries, bundle.show_libraries, bundle.library_types


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
    ("tracearr", "035-tracearr"),
    ("github", "040-github"),
    ("omdb", "050-omdb"),
    ("mdblist", "060-mdblist"),
    ("serializd", "065-serializd"),
    ("floppy", "067-floppy"),
    ("notifiarr", "070-notifiarr"),
    ("gotify", "080-gotify"),
    ("ntfy", "085-ntfy"),
    ("apprise", "087-apprise"),
    ("yamtrack", "088-yamtrack"),
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


def _load_config_schema():
    """Return ``(yaml_parser, schema_dict)`` for validation.

    Uses a pure/safe ``YAML`` instance since we only need JSON-like
    parsing of a schema file we control.  ``helpers.ensure_json_schema()``
    is a no-op after the first successful call, so calling it here on
    every request is cheap.
    """
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.sort_keys = False

    helpers.ensure_json_schema()
    schema_path = os.path.join(helpers.JSON_SCHEMA_DIR, "config-schema.json")
    with open(schema_path, "r") as file:
        schema = yaml.load(file)

    return yaml, schema


def _dump_config_sections(config_data, header_art, header_style, config_name):
    """Iterate :data:`ORDERED_CONFIG_SECTIONS` and dump each present section.

    Returns the accumulated YAML string (no leading header).  Sections
    with no entry in *config_data* are skipped.  The pre-rendered header
    art from :func:`retrieve_config_sections` is preferred over a fresh
    render so identical section names stay byte-identical between the
    initial retrieval pass and the emission pass.
    """
    yaml_body = ""
    for section_key, _section_stem in ORDERED_CONFIG_SECTIONS:
        if section_key not in config_data:
            continue
        section_data = config_data[section_key]
        # Prefer the pre-rendered header art; fall back to re-rendering
        # for sections that didn't come from the template list.
        if section_key in header_art:
            section_art = header_art[section_key]
        else:
            section_art = render_section_header(helpers.user_visible_name(section_key), header_style)
        yaml_body += dump_section(section_art, section_key, section_data, header_style, config_name)
    return yaml_body


def _validate_yaml_content(yaml_content, yaml_parser, schema):
    """Validate *yaml_content* against *schema*.

    Returns ``(validated, first_error, sorted_errors)`` where:

    * ``validated`` -- bool, True when no errors
    * ``first_error`` -- the earliest error by path (stable ordering)
      or ``None`` when valid
    * ``sorted_errors`` -- the full sorted-by-path list; may be empty
    """
    parsed_yaml = yaml_parser.load(yaml_content)
    validator = jsonschema.Draft7Validator(schema)
    validation_input = stringify_mapping_keys_for_jsonschema(parsed_yaml)
    sorted_errors = sorted(validator.iter_errors(validation_input), key=lambda err: list(err.path))
    if sorted_errors:
        return False, sorted_errors[0], sorted_errors
    return True, None, []


def emit_and_validate_config(
    config_data,
    header_art,
    header_style,
    config_name,
    library_types,
    movie_libraries,
    show_libraries,
):
    """Final phase of ``build_config``: header + transforms + dump + validate.

    Composes the six-step transformation chain
    (:func:`apply_final_transformations`, gated by
    ``QS_OPTIMIZE_DEFAULTS``), YAML dump per ordered section
    (:func:`_dump_config_sections`), and jsonschema validation
    (:func:`_validate_yaml_content`) into one call.

    Reuses the update snapshot cached at ``app.config['VERSION_CHECK']``
    when available -- avoids a network call on every final-page render.

    Returns the 5-tuple ``build_config`` returns to its caller:
    ``(validated, first_error, transformed_config_data, yaml_content, sorted_errors)``.
    """
    yaml_parser, schema = _load_config_schema()

    version_info = app.config.get("VERSION_CHECK") or helpers.check_for_update()
    yaml_content = render_yaml_header(header_style, config_name, movie_libraries, show_libraries, version_info)

    optimize_defaults = helpers.booler(app.config.get("QS_OPTIMIZE_DEFAULTS", True))
    config_data = apply_final_transformations(config_data, library_types, optimize_defaults=optimize_defaults)

    yaml_content += _dump_config_sections(config_data, header_art, header_style, config_name)

    validated, first_error, sorted_errors = _validate_yaml_content(yaml_content, yaml_parser, schema)
    return validated, first_error, config_data, yaml_content, sorted_errors
