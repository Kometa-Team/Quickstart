"""Library file-entry primitives: parsing, validation, normalization, managed-store copy/clone.

This module owns the logic for the three library file kinds (metadata_files,
collection_files, overlay_files) plus the auto_sort_hubs validator. It moved
out of quickstart.py during the PR-D refactor. Pure Python -- no Flask, no DB,
no session; just helpers + filesystem + the validations module.

Public surface (used by callers in quickstart.py + blueprints.library_routes):
* LIBRARY_FILE_KINDS, LOCAL_LIBRARY_FILE_TYPES, LIBRARY_FILE_VALIDATORS,
  LIBRARY_FILE_PARSE_FUNCTIONS, SETTINGS_AUTO_SORT_HUBS_VALUES
* _parse_metadata_file_entries / _parse_collection_file_entries / _parse_overlay_file_entries
  (kind-specific wrappers around the shared _parse_library_file_entries)
* _format_library_file_validation_error, _validate_library_file_entry
* _safe_external_artifact_slug, _remove_managed_path
* _managed_library_folder_slug, _managed_library_config_root, _managed_library_file_root
* _parse_managed_library_relative_path, _normalized_managed_library_relative_path
* _is_bundled_library_archive_member, _resolve_local_library_source
* _display_library_managed_location
* _copy_library_artifact_to_managed_store, _normalize_library_external_entry
* _clone_library_file_entries_for_target, _normalize_library_file_entries_payload
* _normalize_imported_libraries_payload
* _validate_library_metadata_files / _validate_library_collection_files
  / _validate_library_overlay_files / _validate_library_auto_sort_hubs
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from werkzeug.utils import secure_filename

from modules import helpers, validations

# --- constants -------------------------------------------------------------

LIBRARY_FILE_KINDS = ("metadata_files", "collection_files", "overlay_files")
LOCAL_LIBRARY_FILE_TYPES = {"file", "folder"}

LIBRARY_FILE_VALIDATORS = {
    "metadata_files": (
        "metadata_file_type",
        "metadata_file_location",
        validations.validate_metadata_file_payload,
    ),
    "collection_files": (
        "collection_file_type",
        "collection_file_location",
        validations.validate_collection_file_payload,
    ),
    "overlay_files": (
        "overlay_file_type",
        "overlay_file_location",
        validations.validate_overlay_file_payload,
    ),
}

SETTINGS_AUTO_SORT_HUBS_VALUES = {
    "sort_title",
    "sort_title.desc",
    "alpha",
    "alpha.desc",
    "configured",
    "configured.desc",
    "random",
}


# --- entry parsing ---------------------------------------------------------


def _parse_library_file_entries(value):
    """Shared parser for the three library-file-entry kinds.

    The three kinds (metadata/collection/overlay) historically had three
    byte-for-byte identical implementations.  They now share this one body
    and the kind-specific names are thin wrappers below for back-compat.

    Returns:
        * list[dict] of entries on success (possibly empty)
        * None on malformed JSON / non-list
    """
    if isinstance(value, list):
        raw_entries = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            raw_entries = json.loads(text)
        except (TypeError, ValueError):
            return None
    else:
        return []

    if not isinstance(raw_entries, list):
        return None

    entries = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        validated = helpers.booler(entry.get("validated"))
        if not entry_type and not location:
            continue
        parsed_entry = {"type": entry_type, "location": location}
        if validated:
            parsed_entry["validated"] = True
        entries.append(parsed_entry)
    return entries


# Kind-specific wrappers so existing call sites keep working unchanged.
def _parse_metadata_file_entries(value):
    return _parse_library_file_entries(value)


def _parse_collection_file_entries(value):
    return _parse_library_file_entries(value)


def _parse_overlay_file_entries(value):
    return _parse_library_file_entries(value)


LIBRARY_FILE_PARSE_FUNCTIONS = {
    "metadata_files": _parse_metadata_file_entries,
    "collection_files": _parse_collection_file_entries,
    "overlay_files": _parse_overlay_file_entries,
}


# --- error formatting ------------------------------------------------------


def _format_library_file_validation_error(lib_id, kind, idx, message, entry, details=None):
    location = str((entry or {}).get("location") or "").strip()
    detail_text = ""
    if isinstance(details, dict):
        detail_text = str(details.get("message") or "").strip()
    if location:
        path_label = "Path"
        if detail_text and detail_text not in message:
            return f"{lib_id} {kind}[{idx}]: {message} {detail_text} {path_label}: {location}"
        return f"{lib_id} {kind}[{idx}]: {message} {path_label}: {location}"
    if detail_text and detail_text not in message:
        return f"{lib_id} {kind}[{idx}]: {message} {detail_text}"
    return f"{lib_id} {kind}[{idx}]: {message}"


# --- slug / path utilities -------------------------------------------------


def _safe_external_artifact_slug(value, fallback="artifact"):
    safe = secure_filename(str(value or "").strip())
    return safe or fallback


def _managed_library_folder_slug(source_path, kind):
    raw_name = str(getattr(source_path, "name", "") or "").strip().lower()
    folder_name = _safe_external_artifact_slug(getattr(source_path, "name", ""), "folder")
    if raw_name in set(LIBRARY_FILE_KINDS):
        parent_name = _safe_external_artifact_slug(getattr(source_path.parent, "name", ""), "")
        if parent_name:
            return f"{parent_name}_{folder_name}"
    return folder_name


def _managed_library_config_root(config_name):
    config_slug = helpers.require_config_name_for_storage(config_name, context="Managed library artifact paths")
    return (Path(helpers.CONFIG_DIR) / config_slug).resolve()


def _managed_library_file_root(kind, config_name):
    return (_managed_library_config_root(config_name) / kind).resolve()


def _parse_managed_library_relative_path(path_value):
    raw = str(path_value or "").strip().replace("\\", "/")
    if not raw:
        return None
    parts = [part for part in raw.split("/") if part]
    if not parts:
        return None
    has_config_prefix = parts[0] == "config"
    if has_config_prefix:
        parts = parts[1:]
    if len(parts) >= 3 and parts[1] in LIBRARY_FILE_KINDS:
        return {
            "layout": "config_first",
            "config_name": parts[0],
            "kind": parts[1],
            "remainder": parts[2:],
            "has_config_prefix": has_config_prefix,
            "parts": parts,
        }
    if len(parts) >= 3 and parts[0] in LIBRARY_FILE_KINDS:
        return {
            "layout": "type_first",
            "config_name": parts[1],
            "kind": parts[0],
            "remainder": parts[2:],
            "has_config_prefix": has_config_prefix,
            "parts": parts,
        }
    return None


def _normalized_managed_library_relative_path(path_value):
    info = _parse_managed_library_relative_path(path_value)
    if not info:
        return None
    return Path(info["config_name"], info["kind"], *info["remainder"]).as_posix()


def _is_bundled_library_archive_member(path_value):
    return _normalized_managed_library_relative_path(str(path_value or "").replace("\\", "/").lstrip("/")) is not None


def _resolve_local_library_source(location):
    raw = str(location or "").strip()
    if not raw:
        return None
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        try:
            return expanded.resolve()
        except OSError:
            return expanded
    managed_info = _parse_managed_library_relative_path(expanded)
    if managed_info:
        if managed_info["layout"] == "config_first":
            managed_relative = Path(managed_info["config_name"], managed_info["kind"], *managed_info["remainder"])
        else:
            managed_relative = Path(*managed_info["parts"])
        try:
            return (Path(helpers.CONFIG_DIR) / managed_relative).resolve()
        except OSError:
            return Path(helpers.CONFIG_DIR) / managed_relative
    normalized_parts = [part for part in str(expanded).replace("\\", "/").split("/") if part]
    if normalized_parts and normalized_parts[0] in LIBRARY_FILE_KINDS:
        try:
            return (Path(helpers.CONFIG_DIR) / expanded).resolve()
        except OSError:
            return Path(helpers.CONFIG_DIR) / expanded
    try:
        return (Path.cwd() / expanded).resolve()
    except OSError:
        return Path.cwd() / expanded


def _display_library_managed_location(location):
    raw = str(location or "").strip().replace("\\", "/")
    if not raw:
        return raw
    normalized_relative = _normalized_managed_library_relative_path(raw)
    if normalized_relative:
        return Path("config", *normalized_relative.split("/")).as_posix()
    return raw


# --- single-entry validation -----------------------------------------------


def _validate_library_file_entry(kind, entry):
    validator_info = LIBRARY_FILE_VALIDATORS.get(kind)
    if not validator_info:
        return False, f"Unsupported library file kind: {kind}", {}
    type_key, location_key, validator = validator_info
    payload = {
        type_key: str((entry or {}).get("type") or "").strip().lower(),
        location_key: str((entry or {}).get("location") or "").strip(),
    }
    return validations._normalize_metadata_validation_result(validator(payload))


# --- managed-store copy/clone ---------------------------------------------


def _remove_managed_path(path, root):
    resolved_root = Path(root).resolve()
    resolved_path = Path(path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except Exception as exc:
        raise RuntimeError(f"Refusing to remove unmanaged path: {resolved_path}") from exc
    if resolved_path.is_dir():
        shutil.rmtree(resolved_path, ignore_errors=False)
    elif resolved_path.exists():
        resolved_path.unlink()


def _copy_library_artifact_to_managed_store(kind, entry_type, location, config_name, library_scope, force_clone_managed=False):
    # _managed_bundle_location_for_path still lives in quickstart.py until PR G; lazy-import
    # to avoid a load-order cycle.
    import quickstart as _qs

    source_path = _resolve_local_library_source(location)
    if source_path is None:
        raise RuntimeError("Path is required.")

    managed_location = _qs._managed_bundle_location_for_path(source_path)
    if managed_location and not force_clone_managed:
        return managed_location

    managed_root = _managed_library_file_root(kind, config_name)
    library_slug = _safe_external_artifact_slug(library_scope, "library")
    source_token = str(source_path).replace("\\", "/").lower()
    digest = hashlib.sha1(source_token.encode("utf-8", errors="ignore")).hexdigest()[:10]
    target_dir = managed_root / library_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    if entry_type == "file":
        stem = _safe_external_artifact_slug(source_path.stem, "file")
        suffix = source_path.suffix or ".yml"
        target_path = (target_dir / f"{stem}_{digest}{suffix}").resolve()
        if source_path != target_path:
            shutil.copy2(source_path, target_path)
    else:
        folder_name = _managed_library_folder_slug(source_path, kind)
        target_path = (target_dir / f"{folder_name}_{digest}").resolve()
        if source_path != target_path:
            if target_path.exists():
                _remove_managed_path(target_path, managed_root)
            shutil.copytree(source_path, target_path)

    try:
        relative = target_path.relative_to(Path(helpers.CONFIG_DIR).resolve())
    except Exception as exc:
        raise RuntimeError(f"Managed artifact path escaped config directory: {target_path}") from exc
    return Path(*relative.parts).as_posix()


def _normalize_library_external_entry(kind, entry, config_name, library_scope, validate_local=True, force_clone_managed=False, require_managed_context=False):
    parsed_entry = dict(entry) if isinstance(entry, dict) else {}
    entry_type = str(parsed_entry.get("type") or "").strip().lower()
    location = str(parsed_entry.get("location") or "").strip()
    is_validated = helpers.booler(parsed_entry.get("validated"))
    if entry_type not in {"file", "folder", "url", "git", "repo"} or not location:
        return parsed_entry, False, None
    if entry_type in LOCAL_LIBRARY_FILE_TYPES and require_managed_context:
        if not str(config_name or "").strip():
            return None, False, "Managed library files require an explicit config name."
        if not str(library_scope or "").strip():
            return None, False, "Managed library files require a library scope."
    if entry_type not in LOCAL_LIBRARY_FILE_TYPES or not config_name or not library_scope:
        normalized_entry = {"type": entry_type, "location": location}
        if is_validated:
            normalized_entry["validated"] = True
        return normalized_entry, False, None

    if validate_local:
        valid, message, _details = _validate_library_file_entry(kind, {"type": entry_type, "location": location})
        if not valid:
            return None, False, message

    try:
        normalized_location = _copy_library_artifact_to_managed_store(
            kind,
            entry_type,
            location,
            config_name,
            library_scope,
            force_clone_managed=force_clone_managed,
        )
    except Exception as exc:
        return None, False, f"Unable to organize {kind}: {exc}"

    display_location = _display_library_managed_location(normalized_location)
    changed = display_location != location
    normalized_entry = {"type": entry_type, "location": display_location}
    if is_validated:
        normalized_entry["validated"] = True
    return normalized_entry, changed, None


def _clone_library_file_entries_for_target(kind, raw_value, config_name, target_library_id):
    parser = LIBRARY_FILE_PARSE_FUNCTIONS.get(kind)
    if not parser:
        return raw_value
    entries = parser(raw_value)
    if entries is None:
        return raw_value
    cloned_entries = []
    for idx, entry in enumerate(entries, start=1):
        normalized_entry, _changed, entry_error = _normalize_library_external_entry(
            kind,
            entry,
            config_name,
            target_library_id,
            validate_local=False,
            force_clone_managed=True,
            require_managed_context=True,
        )
        if entry_error:
            raise RuntimeError(_format_library_file_validation_error(target_library_id, kind, idx, entry_error, entry))
        cloned_entries.append(normalized_entry if normalized_entry is not None else entry)
    return json.dumps(cloned_entries, ensure_ascii=True)


def _normalize_library_file_entries_payload(libraries_data, config_name, validate_local=True):
    if not isinstance(libraries_data, dict):
        return {}, [], False

    normalized = dict(libraries_data)
    errors = []
    changed = False
    for kind in LIBRARY_FILE_KINDS:
        parser = LIBRARY_FILE_PARSE_FUNCTIONS[kind]
        suffix = f"-{kind}"
        for key, raw_value in list(normalized.items()):
            if not isinstance(key, str) or not key.endswith(suffix):
                continue
            library_scope = key[: -len(suffix)]
            entries = parser(raw_value)
            if entries is None:
                errors.append(f"{library_scope}: {kind} must be a valid list.")
                continue
            new_entries = []
            for idx, entry in enumerate(entries, start=1):
                normalized_entry, entry_changed, entry_error = _normalize_library_external_entry(
                    kind,
                    entry,
                    config_name,
                    library_scope,
                    validate_local=validate_local,
                    require_managed_context=True,
                )
                if entry_error:
                    errors.append(_format_library_file_validation_error(library_scope, kind, idx, entry_error, entry))
                    continue
                if normalized_entry:
                    new_entries.append(normalized_entry)
                changed = changed or bool(entry_changed)
            normalized[key] = json.dumps(new_entries, ensure_ascii=True)
    return normalized, errors, changed


def _normalize_imported_libraries_payload(payload_section, config_name):
    # _normalize_overlay_source_override_entries_payload stays in quickstart.py
    # until PR G (overlay-image bundle cluster); lazy-import.
    import quickstart as _qs

    if not isinstance(payload_section, dict):
        return payload_section, []
    libraries_data = payload_section.get("libraries") if isinstance(payload_section.get("libraries"), dict) else payload_section
    if not isinstance(libraries_data, dict):
        return payload_section, []
    normalized, errors, _changed = _normalize_library_file_entries_payload(libraries_data, config_name, validate_local=True)
    normalized, overlay_errors, _overlay_changed = _qs._normalize_overlay_source_override_entries_payload(normalized, config_name)
    errors.extend(overlay_errors)
    if errors:
        return None, errors
    updated = dict(payload_section)
    if "libraries" in updated and isinstance(updated.get("libraries"), dict):
        updated["libraries"] = normalized
    else:
        updated = normalized
    return updated, []


# --- list-level validators (per-kind + auto_sort_hubs) --------------------


def _validate_library_files(libraries_data, selected_library_ids, kind):
    """Shared validator body for the three library-file-entry kinds.

    Pre-refactor the three (metadata/collection/overlay) had near-identical
    bodies differing only in the kind string, the parser, and the validator
    info.  All three data sources are already keyed by ``kind`` via the
    LIBRARY_FILE_VALIDATORS / LIBRARY_FILE_PARSE_FUNCTIONS tables, so the
    refactor collapses them into this one function with thin kind-specific
    wrappers below for back-compat.

    Note: the validator function is resolved via ``getattr(validations, ...)``
    on each call rather than the cached reference in LIBRARY_FILE_VALIDATORS.
    This preserves the pre-refactor behavior where tests can monkeypatch
    ``validations.validate_metadata_file_payload`` etc. and have the patch
    propagate to this code path.
    """
    if not isinstance(libraries_data, dict):
        return []

    validator_info = LIBRARY_FILE_VALIDATORS.get(kind)
    parser = LIBRARY_FILE_PARSE_FUNCTIONS.get(kind)
    if not validator_info or not parser:
        return []

    type_key, location_key, _cached_validator = validator_info
    validator_attr = f"validate_{kind[:-1]}_payload"  # e.g. metadata_files -> validate_metadata_file_payload
    errors = []
    for lib_id in selected_library_ids or []:
        raw_value = libraries_data.get(f"{lib_id}-{kind}")
        if raw_value in [None, "", "[]"]:
            continue

        entries = parser(raw_value)
        if entries is None:
            errors.append(f"{lib_id}: {kind} must be a valid list.")
            continue

        for idx, entry in enumerate(entries, start=1):
            # Re-resolve the validator on every call so test monkeypatches on
            # the ``validations`` module take effect.
            validator = getattr(validations, validator_attr)
            valid, message, details = validations._normalize_metadata_validation_result(
                validator(
                    {
                        type_key: entry.get("type"),
                        location_key: entry.get("location"),
                    }
                )
            )
            if not valid:
                errors.append(_format_library_file_validation_error(lib_id, kind, idx, message, entry, details))

    return errors


def _validate_library_metadata_files(libraries_data, selected_library_ids):
    return _validate_library_files(libraries_data, selected_library_ids, "metadata_files")


def _validate_library_collection_files(libraries_data, selected_library_ids):
    return _validate_library_files(libraries_data, selected_library_ids, "collection_files")


def _validate_library_overlay_files(libraries_data, selected_library_ids):
    return _validate_library_files(libraries_data, selected_library_ids, "overlay_files")


def _validate_library_auto_sort_hubs(libraries_data, selected_library_ids):
    # _is_valid_auto_sort_hubs_value stays in quickstart.py (used by 2 unrelated
    # settings-save callers there); lazy-import.
    import quickstart as _qs

    if not isinstance(libraries_data, dict):
        return []

    errors = []
    allowed_values = ", ".join(sorted(SETTINGS_AUTO_SORT_HUBS_VALUES))
    for lib_id in selected_library_ids or []:
        value = libraries_data.get(f"{lib_id}-top_level_auto_sort_hubs")
        if _qs._is_valid_auto_sort_hubs_value(value):
            continue
        library_name = libraries_data.get(f"{lib_id}-library") or lib_id
        errors.append(f"{library_name}: auto_sort_hubs must be one of: {allowed_values}")

    return errors
