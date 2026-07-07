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


# ---------------------------------------------------------------------------
# Confirm-flow validators.
#
# The /import-config/confirm route re-validates the session-stored Plex
# and TMDb credentials before writing the imported config to the database.
# These functions are the confirm-side analog of validate_plex_credentials
# / validate_tmdb_credentials but simpler: creds always come from the
# session (populated by the preview flow), and there's no bundle-cleanup
# to do because at confirm time the bundle directory has already been
# moved out of the scratch cache dir.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ConfirmPlexOutcome:
    """Outcome of :func:`validate_confirm_plex_credentials`.

    On success ``movie_names`` and ``show_names`` are populated with
    what Plex reported.  On failure ``error_response`` is populated
    and the caller should return it directly.
    """

    error_response: tuple | None = None
    movie_names: set = field(default_factory=set)
    show_names: set = field(default_factory=set)


def validate_confirm_plex_credentials() -> ConfirmPlexOutcome:
    """Validate the session-stored Plex credentials during /confirm.

    Reads ``import_preview_plex_url`` and ``import_preview_plex_token``
    from the Flask session, re-runs the Plex validation call, and
    returns the reported movie/show library names.  Emits distinct
    error messages that direct the user to "Re-run Preview Import"
    (unlike the preview validator which asks the user to enter creds).
    """
    plex_url = session.get("import_preview_plex_url") or ""
    plex_token = session.get("import_preview_plex_token") or ""
    if not plex_url or not plex_token:
        return ConfirmPlexOutcome(
            error_response=(
                jsonify(
                    success=False,
                    message="Plex credentials are required to confirm the import. Re-run Preview Import.",
                ),
                400,
            )
        )
    plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
    plex_result = _coerce_validation_response_payload(plex_response)
    if not plex_result or not plex_result.get("validated"):
        error_message = plex_result.get("error") if isinstance(plex_result, dict) else None
        return ConfirmPlexOutcome(
            error_response=(
                jsonify(
                    success=False,
                    message=error_message or "Plex validation failed. Re-run Preview Import.",
                ),
                400,
            )
        )
    movie_names = _parse_csv_or_list_to_set(plex_result.get("movie_libraries", []))
    show_names = _parse_csv_or_list_to_set(plex_result.get("show_libraries", []))
    if not movie_names and not show_names:
        return ConfirmPlexOutcome(
            error_response=(
                jsonify(
                    success=False,
                    message="No movie or show libraries found in Plex.",
                ),
                400,
            )
        )
    return ConfirmPlexOutcome(movie_names=movie_names, show_names=show_names)


def validate_confirm_tmdb_credentials() -> tuple | None:
    """Validate the session-stored TMDb API key during /confirm.

    Reads ``import_preview_tmdb_apikey`` from the Flask session and
    re-runs the TMDb validation call.  Returns the error response
    tuple on failure or None on success.
    """
    tmdb_apikey = session.get("import_preview_tmdb_apikey") or ""
    if not tmdb_apikey:
        return (
            jsonify(
                success=False,
                message="TMDb API key is required to confirm the import. Re-run Preview Import.",
            ),
            400,
        )
    tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": tmdb_apikey})
    tmdb_result = _coerce_validation_response_payload(tmdb_response)
    if not tmdb_result or not tmdb_result.get("valid"):
        error_message = tmdb_result.get("message") if isinstance(tmdb_result, dict) else None
        return (
            jsonify(
                success=False,
                message=error_message or "TMDb validation failed. Re-run Preview Import.",
            ),
            400,
        )
    return None


# ---------------------------------------------------------------------------
# Library mapping validation (confirm flow only).
# ---------------------------------------------------------------------------


def validate_library_mapping(
    *,
    libraries_payload: dict,
    library_mapping: dict,
    movie_names,
    show_names,
    needs_plex: bool,
) -> tuple[dict | None, tuple | None]:
    """Validate + apply a library-mapping dict to a libraries payload.

    Called from /import-config/confirm after Plex credentials have been
    re-validated.  For each library in ``libraries_payload`` either:

    * The library name matches an existing Plex library -- passes through.
    * The library name has an entry in ``library_mapping`` -- gets
      renamed to the mapping target (or dropped if the target is the
      ``__ignore__`` sentinel).
    * The library name has no mapping -- reported as "missing".
    * The library name maps to something not in Plex -- reported as
      "invalid targets".
    * Two libraries map to the same target -- reported as "duplicates".

    On success, MUTATES ``libraries_payload``'s enclosing dict via
    the caller's ``config_data`` -- but here we just return the
    filtered ``mapped_libraries`` dict (or None on error, with the
    error_response tuple that the caller returns directly).

    :returns: (mapped_libraries_dict, None) on success, or
              (None, error_response_tuple) on failure.
    """
    plex_lookup = {name: name for name in movie_names}
    plex_lookup.update({name: name for name in show_names})
    plex_names = set(plex_lookup.values())

    if needs_plex and not plex_names:
        return None, (
            jsonify(
                success=False,
                message="Plex libraries are unavailable. Validate Plex and preview the import again.",
            ),
            400,
        )

    missing: list = []
    invalid_targets: list = []
    duplicates: list = []
    used_targets: set = set()
    mapped_libraries: dict = {}

    for lib_name, lib_cfg in libraries_payload.items():
        name = str(lib_name)
        if name in plex_lookup:
            target = plex_lookup[name]
        else:
            mapped = library_mapping.get(name)
            if mapped is None:
                missing.append(name)
                continue
            mapped = str(mapped).strip()
            if not mapped:
                missing.append(name)
                continue
            if mapped == "__ignore__":
                continue
            if mapped not in plex_lookup:
                invalid_targets.append(mapped)
                continue
            target = plex_lookup[mapped]

        if target in used_targets:
            duplicates.append(target)
            continue
        used_targets.add(target)
        mapped_libraries[target] = lib_cfg

    if missing:
        return None, (
            jsonify(
                success=False,
                message=f"Library mapping required for: {', '.join(missing)}",
            ),
            400,
        )
    if invalid_targets:
        unique_targets = sorted(set(invalid_targets))
        return None, (
            jsonify(
                success=False,
                message=f"Invalid Plex libraries selected: {', '.join(unique_targets)}",
            ),
            400,
        )
    if duplicates:
        unique_targets = sorted(set(duplicates))
        return None, (
            jsonify(
                success=False,
                message=f"Multiple imports mapped to the same Plex library: {', '.join(unique_targets)}",
            ),
            400,
        )

    return mapped_libraries, None


# ---------------------------------------------------------------------------
# Preview-mapped library mapping (accumulating variant).
#
# import_config_preview_mapped needs to run the same library-mapping logic
# as import_config_confirm, but with different failure semantics: instead
# of erroring on missing / invalid / duplicate entries, it accumulates
# skip reasons + stats so the preview UI can show a "here's what will
# happen" report.  The failure modes and their string messages are
# byte-identical to the develop code they replace.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PreviewMappingResult:
    """Outcome of :func:`apply_library_mapping_for_preview`.

    Unlike :class:`PlexValidationOutcome` there's no ``error_response``
    -- preview-mapped never errors out on library mapping issues, it
    just records them and lets the caller build a report.
    """

    mapped_libraries: dict = field(default_factory=dict)
    alias_map: dict = field(default_factory=dict)
    skip_reasons: dict = field(default_factory=dict)
    stats: dict = field(default_factory=lambda: {"mapped": 0, "ignored": 0, "missing": 0, "invalid": 0, "duplicate": 0})


def apply_library_mapping_for_preview(
    *,
    libraries_payload: dict,
    library_mapping: dict,
    movie_names,
    show_names,
) -> PreviewMappingResult:
    """Apply library mapping to a preview-mapped payload, accumulating stats.

    Same core loop as :func:`validate_library_mapping` (confirm flow)
    but records outcomes rather than returning an error tuple.  Callers
    use the returned ``skip_reasons`` and ``alias_map`` to build the
    preview report shown to the user before they hit "Import".

    :param libraries_payload: dict of imported library name -> config.
    :param library_mapping: dict of imported name -> Plex target name.
    :param movie_names: known Plex movie library names.
    :param show_names: known Plex show library names.
    :returns: :class:`PreviewMappingResult` with mapped_libraries,
              alias_map (source -> target rename), skip_reasons (per
              library name), and stats counters.
    """
    plex_lookup = {name: name for name in movie_names}
    plex_lookup.update({name: name for name in show_names})
    plex_names = set(plex_lookup.values())

    result = PreviewMappingResult()
    used_targets: set = set()

    for lib_name, lib_cfg in libraries_payload.items():
        name = str(lib_name)
        if name in plex_lookup:
            target = plex_lookup[name]
        else:
            mapped = library_mapping.get(name)
            if mapped is None or str(mapped).strip() == "":
                result.skip_reasons[name] = "Library mapping not provided."
                result.stats["missing"] += 1
                continue
            mapped = str(mapped).strip()
            if mapped == "__ignore__":
                result.skip_reasons[name] = "Mapping set to ignore library."
                result.stats["ignored"] += 1
                continue
            if mapped not in plex_lookup:
                result.skip_reasons[name] = "Mapped library not found in Plex."
                result.stats["invalid"] += 1
                continue
            target = plex_lookup[mapped]

        if target != name:
            result.alias_map[name] = target

        if target in used_targets:
            result.skip_reasons[name] = "Mapped library already assigned to another entry."
            if name not in plex_names:
                result.stats["duplicate"] += 1
            continue
        used_targets.add(target)
        result.mapped_libraries[target] = lib_cfg
        if name not in plex_names:
            result.stats["mapped"] += 1

    return result
