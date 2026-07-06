"""Credential-validation blocks for the config-import preview flow.

Split out of :mod:`blueprints.import_config_routes` -- the
``import_config_preview`` route used to inline ~200 lines of
credential validation logic that ran once for Plex and once for
TMDb.  Both blocks are now separate functions here.

## What lives here

Two public entry points:

* :func:`validate_plex_credentials` -- runs the Plex validation
  state machine.  On success, mutates ``parsed`` with the plex
  block, sets two session keys, and returns the movie/show
  libraries that Plex reported.  On failure returns an error
  response the caller should return directly.

* :func:`validate_tmdb_credentials` -- same shape for TMDb API
  key validation.

Both functions follow the same three-source credential resolution
pattern: try the form fields first, then any base-config being
merged into, then the imported config's own values.  The
:mod:`blueprints.import_config_helpers` module owns the six
per-source parser primitives (``_parse_*_credentials_from_*``).

## The result dataclass pattern

Both return a small dataclass so the caller can:

.. code-block:: python

    outcome = validate_plex_credentials(...)
    if outcome.error_response:
        return outcome.error_response
    movie_names = outcome.movie_names
    show_names = outcome.show_names
    plex_libraries = outcome.plex_libraries

matching the same shape used by :func:`extract_bundle_upload`
in :mod:`blueprints.import_config_bundle`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from flask import jsonify, session

from blueprints.import_config_bundle import cleanup_bundle_dir
from blueprints.import_config_helpers import (
    _coerce_validation_response_payload,
    _parse_base_plex_libraries,
    _parse_csv_or_list_to_set,
    _parse_plex_credentials_from_base,
    _parse_plex_credentials_from_config,
    _parse_plex_credentials_from_form,
    _parse_tmdb_credentials_from_base,
    _parse_tmdb_credentials_from_config,
    _parse_tmdb_credentials_from_form,
)
from modules import validations


@dataclass(slots=True)
class PlexValidationOutcome:
    """Outcome of :func:`validate_plex_credentials`.

    Success and failure are mutually exclusive: if ``error_response``
    is set the caller must return it, and the ``movie_names`` /
    ``show_names`` / ``plex_libraries`` fields hold their default
    values.  Otherwise the caller adopts those three fields as its
    new working set.
    """

    error_response: tuple | None = None
    movie_names: set = field(default_factory=set)
    show_names: set = field(default_factory=set)
    plex_libraries: dict = field(default_factory=lambda: {"movie": [], "show": []})


def validate_plex_credentials(
    *,
    parsed: dict,
    form_data,
    merge_mode: bool,
    base_config: str,
    extracted_dir: Path | None,
    default_movie_names: set,
    default_show_names: set,
    default_plex_libraries: dict,
) -> PlexValidationOutcome:
    """Validate Plex credentials for the /import-config/preview flow.

    On success mutates ``parsed`` (setting ``parsed["plex"]["url"]``
    / ``parsed["plex"]["token"]``) and writes two session keys.
    On failure the caller should return the error response tuple
    directly.

    :param parsed: the loaded YAML config; will be mutated on success.
    :param form_data: ``request.form`` (or empty dict for tests).
    :param merge_mode: whether the caller is merging into an
        existing base config.
    :param base_config: name of the base config being merged into.
        Only consulted when ``merge_mode`` is True.
    :param extracted_dir: the scratch dir from
        :func:`extract_bundle_upload`, or None.  Cleaned up on
        error paths.
    :param default_movie_names: fallback movie library names if
        validation is skipped or the outcome is unchanged.
    :param default_show_names: fallback show library names.
    :param default_plex_libraries: fallback plex_libraries dict.
    :returns: :class:`PlexValidationOutcome`.
    """
    movie_names = default_movie_names
    show_names = default_show_names
    plex_libraries = default_plex_libraries
    skip_plex_validation = False
    if merge_mode and base_config:
        base_movie_names, base_show_names = _parse_base_plex_libraries(base_config)
        if base_movie_names or base_show_names:
            movie_names = base_movie_names
            show_names = base_show_names
            plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
            skip_plex_validation = True

    form_plex_url, form_plex_token = _parse_plex_credentials_from_form(form_data or {})
    imported_plex_url, imported_plex_token = _parse_plex_credentials_from_config(parsed)
    base_plex_url, base_plex_token = _parse_plex_credentials_from_base(base_config) if merge_mode else ("", "")
    has_form = bool(form_plex_url and form_plex_token)
    has_imported = bool(imported_plex_url and imported_plex_token)
    has_base = bool(base_plex_url and base_plex_token)
    used_plex_url = ""
    used_plex_token = ""

    if not skip_plex_validation and not has_form and not has_imported and not has_base:
        cleanup_bundle_dir(extracted_dir)
        return PlexValidationOutcome(
            error_response=(
                jsonify(
                    success=False,
                    needs_plex_credentials=True,
                    message=("Plex credentials are required to import library settings. " "Enter a Plex URL and token to continue."),
                    plex_url="",
                    plex_token="",
                ),
                400,
            )
        )

    plex_result = None
    if not skip_plex_validation:
        last_error = None
        if has_form:
            used_plex_url = form_plex_url
            used_plex_token = form_plex_token
            plex_response = validations.validate_plex_server({"plex_url": form_plex_url, "plex_token": form_plex_token})
            plex_result = _coerce_validation_response_payload(plex_response)
            if not plex_result or not plex_result.get("validated"):
                if isinstance(plex_result, dict):
                    last_error = plex_result.get("error")
                cleanup_bundle_dir(extracted_dir)
                return PlexValidationOutcome(
                    error_response=(
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or "Plex validation failed. Please enter valid credentials.",
                            plex_url=form_plex_url or "",
                            plex_token=form_plex_token or "",
                        ),
                        400,
                    )
                )
        else:
            candidates = []
            if merge_mode and has_base:
                candidates.append((base_plex_url, base_plex_token))
            if has_imported:
                candidates.append((imported_plex_url, imported_plex_token))
            if not candidates:
                candidates.append((imported_plex_url or base_plex_url, imported_plex_token or base_plex_token))
            for candidate_url, candidate_token in candidates:
                used_plex_url = candidate_url
                used_plex_token = candidate_token
                plex_response = validations.validate_plex_server({"plex_url": used_plex_url, "plex_token": used_plex_token})
                plex_result = _coerce_validation_response_payload(plex_response)
                if plex_result and plex_result.get("validated"):
                    last_error = None
                    break
                if isinstance(plex_result, dict):
                    last_error = plex_result.get("error")
            if not plex_result or not plex_result.get("validated"):
                cleanup_bundle_dir(extracted_dir)
                return PlexValidationOutcome(
                    error_response=(
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or ("Plex credentials from the import/base config could not be validated. " "Please enter a valid Plex URL and token."),
                            plex_url=imported_plex_url or base_plex_url or "",
                            plex_token=imported_plex_token or base_plex_token or "",
                        ),
                        400,
                    )
                )
    if not skip_plex_validation:
        session["import_preview_plex_url"] = used_plex_url
        session["import_preview_plex_token"] = used_plex_token
    if used_plex_url and used_plex_token:
        plex_block = parsed.get("plex")
        if not isinstance(plex_block, dict):
            plex_block = {}
            parsed["plex"] = plex_block
        plex_block["url"] = used_plex_url
        plex_block["token"] = used_plex_token
    if not skip_plex_validation:
        movie_names = _parse_csv_or_list_to_set(plex_result.get("movie_libraries", []))
        show_names = _parse_csv_or_list_to_set(plex_result.get("show_libraries", []))
        plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
        if not movie_names and not show_names:
            cleanup_bundle_dir(extracted_dir)
            return PlexValidationOutcome(
                error_response=(
                    jsonify(
                        success=False,
                        message="No movie or show libraries found in Plex.",
                    ),
                    400,
                )
            )

    return PlexValidationOutcome(
        movie_names=movie_names,
        show_names=show_names,
        plex_libraries=plex_libraries,
    )


def validate_tmdb_credentials(
    *,
    parsed: dict,
    form_data,
    merge_mode: bool,
    base_config: str,
    extracted_dir: Path | None,
) -> tuple | None:
    """Validate TMDb API key for the /import-config/preview flow.

    On success mutates ``parsed`` (setting ``parsed["tmdb"]["apikey"]``)
    and writes one session key.  On failure returns the error
    response tuple the caller should return directly; otherwise
    returns None.

    :param parsed: the loaded YAML config; will be mutated on success.
    :param form_data: ``request.form`` (or empty dict for tests).
    :param merge_mode: whether the caller is merging into an
        existing base config.
    :param base_config: name of the base config being merged into.
    :param extracted_dir: the scratch dir from
        :func:`extract_bundle_upload`, or None.
    :returns: an error-response tuple, or None on success.
    """
    form_tmdb_key = _parse_tmdb_credentials_from_form(form_data or {})
    imported_tmdb_key = _parse_tmdb_credentials_from_config(parsed)
    base_tmdb_key = _parse_tmdb_credentials_from_base(base_config) if merge_mode else ""
    has_form = bool(form_tmdb_key)
    has_imported = bool(imported_tmdb_key)
    has_base = bool(base_tmdb_key)
    used_tmdb_key = ""

    if not has_form and not has_imported and not has_base:
        cleanup_bundle_dir(extracted_dir)
        return (
            jsonify(
                success=False,
                needs_tmdb_credentials=True,
                message="TMDb API key is required to import metadata settings. Enter a valid TMDb API key to continue.",
                tmdb_apikey="",
            ),
            400,
        )

    tmdb_result = None
    last_error = None
    if has_form:
        used_tmdb_key = form_tmdb_key
        tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": form_tmdb_key})
        tmdb_result = _coerce_validation_response_payload(tmdb_response)
        if not tmdb_result or not tmdb_result.get("valid"):
            if isinstance(tmdb_result, dict):
                last_error = tmdb_result.get("message")
            cleanup_bundle_dir(extracted_dir)
            return (
                jsonify(
                    success=False,
                    needs_tmdb_credentials=True,
                    message=last_error or "TMDb validation failed. Please enter a valid API key.",
                    tmdb_apikey=form_tmdb_key or "",
                ),
                400,
            )
    else:
        candidates = []
        if merge_mode and has_base:
            candidates.append(base_tmdb_key)
        if has_imported:
            candidates.append(imported_tmdb_key)
        if not candidates:
            candidates.append(imported_tmdb_key or base_tmdb_key)
        for candidate_key in candidates:
            used_tmdb_key = candidate_key
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": used_tmdb_key})
            tmdb_result = _coerce_validation_response_payload(tmdb_response)
            if tmdb_result and tmdb_result.get("valid"):
                last_error = None
                break
            if isinstance(tmdb_result, dict):
                last_error = tmdb_result.get("message")
        if not tmdb_result or not tmdb_result.get("valid"):
            cleanup_bundle_dir(extracted_dir)
            return (
                jsonify(
                    success=False,
                    needs_tmdb_credentials=True,
                    message=last_error or "TMDb API key from the import/base config could not be validated. Please enter a valid key.",
                    tmdb_apikey=imported_tmdb_key or base_tmdb_key or "",
                ),
                400,
            )
    session["import_preview_tmdb_apikey"] = used_tmdb_key
    if used_tmdb_key:
        tmdb_block = parsed.get("tmdb")
        if not isinstance(tmdb_block, dict):
            tmdb_block = {}
            parsed["tmdb"] = tmdb_block
        tmdb_block["apikey"] = used_tmdb_key
    return None
