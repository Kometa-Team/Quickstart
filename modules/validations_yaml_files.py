"""YAML file/folder location validators for Metadata / Collection / Overlay / Playlist.

Split out of ``modules.validations`` -- this is the second thematic
cluster in that file (~700 lines) that handles the whole "user gave us
a YAML location, does it point at valid Kometa YAML?" pipeline for
each of the four YAML types Kometa consumes:

* **Metadata** (``metadata:`` top-level key)
* **Collection** (``collections:`` top-level key)
* **Overlay** (``overlays:`` top-level key)
* **Playlist** (``playlists:`` top-level key)

## The layered API

The cluster is organised in three tiers, each one calling the tier below:

1. **Text validators** (``_validate_yaml_text``, ``_validate_metadata_yaml_text``,
   etc.) -- given raw YAML *text*, verify it's parseable and has the
   right top-level mapping.
2. **Location validators** (``_validate_yaml_location`` and its four
   typed variants) -- given a *location* (URL or filesystem path),
   fetch the text and delegate to the text validators.
3. **Payload / server validators** (``validate_metadata_file_payload``,
   ``validate_metadata_file_server``, and the collection/overlay/playlist
   variants) -- the public API that dispatches on ``file`` / ``folder`` /
   ``url`` / ``git`` / ``repo`` source-type strings.

There are also **folder validators** (``_validate_yaml_folder``,
``_validate_collection_yaml_folder``, ``_validate_overlay_yaml_folder``)
that iterate every top-level ``.yml`` / ``.yaml`` file in a directory.

## Public API used by external callers

* ``validate_metadata_file_payload(data)`` -- used by
  ``modules.library_file_entries`` and ``quickstart.py``.
* ``validate_collection_file_payload(data)`` -- same.
* ``validate_overlay_file_payload(data)`` -- same.
* ``validate_playlist_file_payload(data)`` -- used by ``quickstart.py``.
* ``_normalize_metadata_validation_result(result)`` -- used by
  ``modules.library_file_entries`` and ``quickstart.py`` (leading
  underscore is historical; treat as public API).
* The four ``*_server`` wrappers are called from
  ``blueprints/validation_routes.py`` (via ``validations.<name>``
  re-exports).
"""

from __future__ import annotations

import os
import urllib.parse

import requests
from ruamel.yaml import YAML
from flask import jsonify

from modules import path_validation, url_validation
from modules.validations_shared import (
    _resolve_managed_library_path,
    _saved_custom_repo_base,
)

# ---------------------------------------------------------------------------
# Tier 1: text validators (raw YAML string in, (valid, message[, parsed]) out)
# ---------------------------------------------------------------------------


def _validate_yaml_text(raw_text, label):
    if not isinstance(raw_text, str) or not raw_text.strip():
        return False, f"{label} must not be empty."
    parser = YAML(typ="safe", pure=True)
    try:
        parsed = parser.load(raw_text)
    except Exception as exc:
        return False, f"{label} must contain valid YAML. {exc}"
    return True, None, parsed


def _display_yaml_source_name(source_name, label):
    source = str(source_name or "").strip()
    if source:
        return f"`{source}`"
    return label


def _validate_required_top_level_mapping(raw_text, label, source_name, mapping_name):
    subject = _display_yaml_source_name(source_name, label)
    if not isinstance(raw_text, str) or not raw_text.strip():
        return False, f"{subject} must not be empty."

    parser = YAML(typ="safe", pure=True)
    try:
        parsed = parser.load(raw_text)
    except Exception as exc:
        return False, f"Invalid YAML in {subject}. {exc}"

    if not isinstance(parsed, dict):
        return False, f"Top-level `{mapping_name}:` was not found in {subject}."

    if mapping_name not in parsed:
        return False, f"Top-level `{mapping_name}:` was not found in {subject}."

    mapping = parsed.get(mapping_name)
    if not isinstance(mapping, dict) or not mapping:
        return False, f"Top-level `{mapping_name}:` in {subject} must be a non-empty mapping."

    return True, None


def _validate_metadata_yaml_text(raw_text, label, source_name=None):
    return _validate_required_top_level_mapping(raw_text, label, source_name, "metadata")


def _validate_collection_yaml_text(raw_text, label, source_name=None):
    return _validate_required_top_level_mapping(raw_text, label, source_name, "collections")


def _validate_overlay_yaml_text(raw_text, label, source_name=None):
    return _validate_required_top_level_mapping(raw_text, label, source_name, "overlays")


def _validate_playlist_yaml_text(raw_text, label, source_name=None):
    return _validate_required_top_level_mapping(raw_text, label, source_name, "playlists")


# ---------------------------------------------------------------------------
# Tier 2: location validators (URL or filesystem path in, (valid, message) out)
# ---------------------------------------------------------------------------


def _validate_yaml_location_suffix(location, label):
    lowered = str(location or "").strip().lower()
    if not lowered.endswith((".yml", ".yaml")):
        return False, f"{label} must end with .yml or .yaml."
    return True, None


def _validate_yaml_location(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = _validate_yaml_location_suffix(location, label)
    if not valid:
        return False, message

    if str(location).strip().lower().startswith(("http://", "https://")):
        valid, message = url_validation.validate_url(location, allow_local=True)
        if not valid:
            return False, f"{label}: {message}"

        try:
            response = requests.get(location, timeout=10)
        except requests.RequestException as exc:
            return False, f"Connection error: {str(exc)}"

        if response.status_code >= 400:
            return False, f"Failed to fetch {label} ({response.status_code} [{response.reason}])."

        result = _validate_yaml_text(response.text, label)
        if len(result) == 2:
            return result
        valid, message, _parsed = result
        return valid, message

    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_file"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        with open(resolved_location, "r", encoding="utf-8") as handle:
            yaml_text = handle.read()
    except OSError as exc:
        return False, f"{label}: Unable to read file. {exc}"

    result = _validate_yaml_text(yaml_text, label)
    if len(result) == 2:
        return result
    valid, message, _parsed = result
    return valid, message


def _validate_metadata_yaml_location(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = _validate_yaml_location_suffix(location, label)
    if not valid:
        return False, message

    source_name = os.path.basename(urllib.parse.urlparse(str(location)).path) or os.path.basename(str(location)) or label

    if str(location).strip().lower().startswith(("http://", "https://")):
        valid, message = url_validation.validate_url(location, allow_local=True)
        if not valid:
            return False, f"{label}: {message}"

        try:
            response = requests.get(location, timeout=10)
        except requests.RequestException as exc:
            return False, f"Connection error: {str(exc)}"

        if response.status_code >= 400:
            return False, f"Failed to fetch {label} ({response.status_code} [{response.reason}])."

        return _validate_metadata_yaml_text(response.text, label, source_name)

    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_file"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        with open(resolved_location, "r", encoding="utf-8") as handle:
            yaml_text = handle.read()
    except OSError as exc:
        return False, f"{label}: Unable to read file. {exc}"

    return _validate_metadata_yaml_text(yaml_text, label, source_name)


def _validate_collection_yaml_location(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = _validate_yaml_location_suffix(location, label)
    if not valid:
        return False, message

    source_name = os.path.basename(urllib.parse.urlparse(str(location)).path) or os.path.basename(str(location)) or label

    if str(location).strip().lower().startswith(("http://", "https://")):
        valid, message = url_validation.validate_url(location, allow_local=True)
        if not valid:
            return False, f"{label}: {message}"

        try:
            response = requests.get(location, timeout=10)
        except requests.RequestException as exc:
            return False, f"Connection error: {str(exc)}"

        if response.status_code >= 400:
            return False, f"Failed to fetch {label} ({response.status_code} [{response.reason}])."

        return _validate_collection_yaml_text(response.text, label, source_name)

    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_file"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        with open(resolved_location, "r", encoding="utf-8") as handle:
            yaml_text = handle.read()
    except OSError as exc:
        return False, f"{label}: Unable to read file. {exc}"

    return _validate_collection_yaml_text(yaml_text, label, source_name)


def _validate_overlay_yaml_location(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = _validate_yaml_location_suffix(location, label)
    if not valid:
        return False, message

    source_name = os.path.basename(urllib.parse.urlparse(str(location)).path) or os.path.basename(str(location)) or label

    if str(location).strip().lower().startswith(("http://", "https://")):
        valid, message = url_validation.validate_url(location, allow_local=True)
        if not valid:
            return False, f"{label}: {message}"

        try:
            response = requests.get(location, timeout=15)
        except requests.RequestException as exc:
            return False, f"{label}: Unable to fetch URL. {exc}"
        if response.status_code >= 400:
            return False, f"{label}: URL returned HTTP {response.status_code} {response.reason}."
        yaml_text = response.text
    else:
        valid, message = path_validation.validate_path(
            resolved_location,
            {"allow_relative": True, "must_exist": True, "mode": "input_file"},
        )
        if not valid:
            return False, f"{label}: {message}"

        try:
            with open(resolved_location, "r", encoding="utf-8") as handle:
                yaml_text = handle.read()
        except OSError as exc:
            return False, f"{label}: Unable to read file. {exc}"

    return _validate_overlay_yaml_text(yaml_text, label, source_name)


def _validate_playlist_yaml_location(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = _validate_yaml_location_suffix(location, label)
    if not valid:
        return False, message

    source_name = os.path.basename(urllib.parse.urlparse(str(location)).path) or os.path.basename(str(location)) or label

    if str(location).strip().lower().startswith(("http://", "https://")):
        valid, message = url_validation.validate_url(location, allow_local=True)
        if not valid:
            return False, f"{label}: {message}"

        try:
            response = requests.get(location, timeout=10)
        except requests.RequestException as exc:
            return False, f"Connection error: {str(exc)}"

        if response.status_code >= 400:
            return False, f"Failed to fetch {label} ({response.status_code} [{response.reason}])."

        return _validate_playlist_yaml_text(response.text, label, source_name)

    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_file"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        with open(resolved_location, "r", encoding="utf-8") as handle:
            yaml_text = handle.read()
    except OSError as exc:
        return False, f"{label}: Unable to read file. {exc}"

    return _validate_playlist_yaml_text(yaml_text, label, source_name)


# ---------------------------------------------------------------------------
# Folder validators: iterate every top-level .yml/.yaml file in a directory
# ---------------------------------------------------------------------------


def _summarize_folder_validation_failures(label, yaml_files, failures):
    scanned_files = len(yaml_files)
    invalid_files = len(failures)
    suffix = "" if scanned_files == 1 else "s"
    invalid_suffix = "" if invalid_files == 1 else "s"
    summary = f"{label}: Scanned {scanned_files} top-level YAML file{suffix} and found {invalid_files} invalid file{invalid_suffix}."
    return False, summary, {"message": summary, "files": failures}


def _validate_yaml_folder(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_dir"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        entries = sorted(os.listdir(resolved_location), key=str.casefold)
    except OSError as exc:
        return False, f"{label}: Unable to read folder. {exc}"

    yaml_files = [
        os.path.join(resolved_location, entry) for entry in entries if os.path.isfile(os.path.join(resolved_location, entry)) and entry.lower().endswith((".yml", ".yaml"))
    ]
    if not yaml_files:
        return False, f"{label}: Folder must contain at least one top-level .yml or .yaml file."

    failures = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, "r", encoding="utf-8") as handle:
                yaml_text = handle.read()
        except OSError as exc:
            failures.append(f"Unable to read `{os.path.basename(yaml_file)}`. {exc}")
            continue

        valid, message = _validate_metadata_yaml_text(yaml_text, label, os.path.basename(yaml_file))
        if not valid:
            failures.append(message)

    if failures:
        return _summarize_folder_validation_failures(label, yaml_files, failures)

    validated_files = len(yaml_files)
    file_names = [os.path.basename(yaml_file) for yaml_file in yaml_files]
    suffix = "" if validated_files == 1 else "s"
    return True, None, {"validated_files": validated_files, "files": file_names, "message": f"Validated {validated_files} YAML file{suffix} in folder."}


def _validate_collection_yaml_folder(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_dir"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        entries = sorted(os.listdir(resolved_location), key=str.casefold)
    except OSError as exc:
        return False, f"{label}: Unable to read folder. {exc}"

    yaml_files = [
        os.path.join(resolved_location, entry) for entry in entries if os.path.isfile(os.path.join(resolved_location, entry)) and entry.lower().endswith((".yml", ".yaml"))
    ]
    if not yaml_files:
        return False, f"{label}: Folder must contain at least one top-level .yml or .yaml file."

    failures = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, "r", encoding="utf-8") as handle:
                yaml_text = handle.read()
        except OSError as exc:
            failures.append(f"Unable to read `{os.path.basename(yaml_file)}`. {exc}")
            continue

        valid, message = _validate_collection_yaml_text(yaml_text, label, os.path.basename(yaml_file))
        if not valid:
            failures.append(message)

    if failures:
        return _summarize_folder_validation_failures(label, yaml_files, failures)

    validated_files = len(yaml_files)
    file_names = [os.path.basename(yaml_file) for yaml_file in yaml_files]
    suffix = "" if validated_files == 1 else "s"
    return True, None, {"validated_files": validated_files, "files": file_names, "message": f"Validated {validated_files} YAML file{suffix} in folder."}


def _validate_overlay_yaml_folder(location, label):
    resolved_location = _resolve_managed_library_path(location)
    valid, message = path_validation.validate_path(
        resolved_location,
        {"allow_relative": True, "must_exist": True, "mode": "input_dir"},
    )
    if not valid:
        return False, f"{label}: {message}"

    try:
        entries = sorted(os.listdir(resolved_location), key=str.casefold)
    except OSError as exc:
        return False, f"{label}: Unable to read folder. {exc}"

    yaml_files = [
        os.path.join(resolved_location, entry) for entry in entries if os.path.isfile(os.path.join(resolved_location, entry)) and entry.lower().endswith((".yml", ".yaml"))
    ]
    if not yaml_files:
        return False, f"{label}: Folder must contain at least one top-level .yml or .yaml file."

    failures = []
    for yaml_file in yaml_files:
        try:
            with open(yaml_file, "r", encoding="utf-8") as handle:
                yaml_text = handle.read()
        except OSError as exc:
            failures.append(f"Unable to read `{os.path.basename(yaml_file)}`. {exc}")
            continue

        valid, message = _validate_overlay_yaml_text(yaml_text, label, os.path.basename(yaml_file))
        if not valid:
            failures.append(message)

    if failures:
        return _summarize_folder_validation_failures(label, yaml_files, failures)

    validated_files = len(yaml_files)
    file_names = [os.path.basename(yaml_file) for yaml_file in yaml_files]
    suffix = "" if validated_files == 1 else "s"
    return True, None, {"validated_files": validated_files, "files": file_names, "message": f"Validated {validated_files} YAML file{suffix} in folder."}


# ---------------------------------------------------------------------------
# Result normalization helper (used by external callers too)
# ---------------------------------------------------------------------------


def _normalize_metadata_validation_result(result):
    if isinstance(result, tuple):
        if len(result) == 3:
            valid, message, details = result
            return bool(valid), message, details or {}
        if len(result) == 2:
            valid, message = result
            return bool(valid), message, {}
    return False, "Validation failed.", {}


# ---------------------------------------------------------------------------
# Tier 3: payload validators (public API -- dispatch on file/folder/url/git/repo)
# ---------------------------------------------------------------------------


def validate_metadata_file_payload(data):
    metadata_file_type = str(data.get("metadata_file_type") or "").strip().lower()
    metadata_file_location = str(data.get("metadata_file_location") or "").strip()

    if metadata_file_type not in {"file", "folder", "url", "git", "repo"}:
        return False, "Metadata file type must be file, folder, url, git, or repo.", {}

    if not metadata_file_location:
        return False, "Metadata file location is required.", {}

    if metadata_file_type == "url":
        if not metadata_file_location.lower().startswith(("http://", "https://")):
            return False, "Metadata file URL must start with http:// or https://.", {}
        label = "Metadata file URL"
        return _normalize_metadata_validation_result(_validate_metadata_yaml_location(metadata_file_location, label))

    if metadata_file_type == "folder":
        if metadata_file_location.lower().startswith(("http://", "https://")):
            return False, "Metadata folder path must be a local folder path.", {}
        label = "Metadata folder path"
        return _normalize_metadata_validation_result(_validate_yaml_folder(metadata_file_location, label))

    if metadata_file_type == "file":
        if metadata_file_location.lower().startswith(("http://", "https://")):
            return False, "Metadata file path must be a local file path.", {}
        label = "Metadata file path"
        return _normalize_metadata_validation_result(_validate_metadata_yaml_location(metadata_file_location, label))

    if metadata_file_location.lower().startswith(("http://", "https://")):
        return False, f"Metadata file {metadata_file_type} value must not be a full URL.", {}

    if metadata_file_type == "git":
        valid, message = _validate_yaml_location_suffix(metadata_file_location, "Metadata file git path")
        if not valid:
            return False, message, {}
        return _normalize_metadata_validation_result(
            _validate_metadata_yaml_location(
                f"https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/{metadata_file_location}",
                "Metadata file git path",
            )
        )

    custom_repo_base = _saved_custom_repo_base()
    if not custom_repo_base:
        return False, "Metadata file repo entries require Custom Repo to be configured and saved first within the Settings page.", {}
    valid, message = _validate_yaml_location_suffix(metadata_file_location, "Metadata file repo path")
    if not valid:
        return False, message, {}
    resolved_repo_location = f"{custom_repo_base}{metadata_file_location}"
    return _normalize_metadata_validation_result(_validate_metadata_yaml_location(resolved_repo_location, "Metadata file repo path"))


def validate_collection_file_payload(data):
    collection_file_type = str(data.get("collection_file_type") or "").strip().lower()
    collection_file_location = str(data.get("collection_file_location") or "").strip()

    if collection_file_type not in {"file", "folder", "url", "git", "repo"}:
        return False, "Collection file type must be file, folder, url, git, or repo.", {}

    if not collection_file_location:
        return False, "Collection file location is required.", {}

    if collection_file_type == "url":
        if not collection_file_location.lower().startswith(("http://", "https://")):
            return False, "Collection file URL must start with http:// or https://.", {}
        label = "Collection file URL"
        return _normalize_metadata_validation_result(_validate_collection_yaml_location(collection_file_location, label))

    if collection_file_type == "folder":
        if collection_file_location.lower().startswith(("http://", "https://")):
            return False, "Collection folder path must be a local folder path.", {}
        label = "Collection folder path"
        return _normalize_metadata_validation_result(_validate_collection_yaml_folder(collection_file_location, label))

    if collection_file_type == "file":
        if collection_file_location.lower().startswith(("http://", "https://")):
            return False, "Collection file path must be a local file path.", {}
        label = "Collection file path"
        return _normalize_metadata_validation_result(_validate_collection_yaml_location(collection_file_location, label))

    if collection_file_location.lower().startswith(("http://", "https://")):
        return False, f"Collection file {collection_file_type} value must not be a full URL.", {}

    if collection_file_type == "git":
        valid, message = _validate_yaml_location_suffix(collection_file_location, "Collection file git path")
        if not valid:
            return False, message, {}
        return _normalize_metadata_validation_result(
            _validate_collection_yaml_location(
                f"https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/{collection_file_location}",
                "Collection file git path",
            )
        )

    custom_repo_base = _saved_custom_repo_base()
    if not custom_repo_base:
        return False, "Collection file repo entries require Custom Repo to be configured and saved first within the Settings page.", {}
    valid, message = _validate_yaml_location_suffix(collection_file_location, "Collection file repo path")
    if not valid:
        return False, message, {}
    resolved_repo_location = f"{custom_repo_base}{collection_file_location}"
    return _normalize_metadata_validation_result(_validate_collection_yaml_location(resolved_repo_location, "Collection file repo path"))


def validate_overlay_file_payload(data):
    overlay_file_type = str(data.get("overlay_file_type") or "").strip().lower()
    overlay_file_location = str(data.get("overlay_file_location") or "").strip()

    if overlay_file_type not in {"file", "folder", "url", "git", "repo"}:
        return False, "Overlay file type must be file, folder, url, git, or repo.", {}

    if not overlay_file_location:
        return False, "Overlay file location is required.", {}

    if overlay_file_type == "url":
        if not overlay_file_location.lower().startswith(("http://", "https://")):
            return False, "Overlay file URL must start with http:// or https://.", {}
        label = "Overlay file URL"
        return _normalize_metadata_validation_result(_validate_overlay_yaml_location(overlay_file_location, label))

    if overlay_file_type == "folder":
        if overlay_file_location.lower().startswith(("http://", "https://")):
            return False, "Overlay folder path must be a local folder path.", {}
        label = "Overlay folder path"
        return _normalize_metadata_validation_result(_validate_overlay_yaml_folder(overlay_file_location, label))

    if overlay_file_type == "file":
        if overlay_file_location.lower().startswith(("http://", "https://")):
            return False, "Overlay file path must be a local file path.", {}
        label = "Overlay file path"
        return _normalize_metadata_validation_result(_validate_overlay_yaml_location(overlay_file_location, label))

    if overlay_file_location.lower().startswith(("http://", "https://")):
        return False, f"Overlay file {overlay_file_type} value must not be a full URL.", {}

    if overlay_file_type == "git":
        valid, message = _validate_yaml_location_suffix(overlay_file_location, "Overlay file git path")
        if not valid:
            return False, message, {}
        return _normalize_metadata_validation_result(
            _validate_overlay_yaml_location(
                f"https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/{overlay_file_location}",
                "Overlay file git path",
            )
        )

    custom_repo_base = _saved_custom_repo_base()
    if not custom_repo_base:
        return False, "Overlay file repo entries require Custom Repo to be configured and saved first within the Settings page.", {}
    valid, message = _validate_yaml_location_suffix(overlay_file_location, "Overlay file repo path")
    if not valid:
        return False, message, {}
    resolved_repo_location = f"{custom_repo_base}{overlay_file_location}"
    return _normalize_metadata_validation_result(_validate_overlay_yaml_location(resolved_repo_location, "Overlay file repo path"))


def validate_playlist_file_payload(data):
    playlist_file_type = str(data.get("playlist_file_type") or "").strip().lower()
    playlist_file_location = str(data.get("playlist_file_location") or "").strip()

    if playlist_file_type not in {"file", "url", "git", "repo"}:
        return False, "Playlist file type must be file, url, git, or repo.", {}

    if not playlist_file_location:
        return False, "Playlist file location is required.", {}

    if playlist_file_type == "url":
        if not playlist_file_location.lower().startswith(("http://", "https://")):
            return False, "Playlist file URL must start with http:// or https://.", {}
        return _normalize_metadata_validation_result(_validate_playlist_yaml_location(playlist_file_location, "Playlist file URL"))

    if playlist_file_type == "file":
        if playlist_file_location.lower().startswith(("http://", "https://")):
            return False, "Playlist file path must be a local file path.", {}
        return _normalize_metadata_validation_result(_validate_playlist_yaml_location(playlist_file_location, "Playlist file path"))

    if playlist_file_type == "git":
        valid, message = _validate_yaml_location_suffix(playlist_file_location, "Playlist file git path")
        if not valid:
            return False, message, {}
        return _normalize_metadata_validation_result(
            _validate_playlist_yaml_location(
                f"https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/{playlist_file_location}",
                "Playlist file git path",
            )
        )

    custom_repo_base = _saved_custom_repo_base()
    if not custom_repo_base:
        return False, "Playlist file repo entries require Custom Repo to be configured and saved first within the Settings page.", {}
    valid, message = _validate_yaml_location_suffix(playlist_file_location, "Playlist file repo path")
    if not valid:
        return False, message, {}
    resolved_repo_location = f"{custom_repo_base}{playlist_file_location}"
    return _normalize_metadata_validation_result(_validate_playlist_yaml_location(resolved_repo_location, "Playlist file repo path"))


# ---------------------------------------------------------------------------
# Flask endpoint wrappers
# ---------------------------------------------------------------------------


def validate_metadata_file_server(data):
    valid, message, details = validate_metadata_file_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message") or isinstance(details.get("files"), list):
            payload["error_details"] = {"text": details.get("message") or message, "files": details.get("files") if isinstance(details.get("files"), list) else []}
        if isinstance(details.get("files"), list):
            payload["files"] = details["files"]
        return jsonify(payload), 400
    payload = {"valid": True}
    if details.get("message"):
        payload["message"] = details["message"]
    if "validated_files" in details:
        payload["validated_files"] = details["validated_files"]
    if isinstance(details.get("files"), list):
        payload["files"] = details["files"]
    return jsonify(payload)


def validate_collection_file_server(data):
    valid, message, details = validate_collection_file_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message") or isinstance(details.get("files"), list):
            payload["error_details"] = {"text": details.get("message") or message, "files": details.get("files") if isinstance(details.get("files"), list) else []}
        if isinstance(details.get("files"), list):
            payload["files"] = details["files"]
        return jsonify(payload), 400
    payload = {"valid": True}
    if details.get("message"):
        payload["message"] = details["message"]
    if "validated_files" in details:
        payload["validated_files"] = details["validated_files"]
    if isinstance(details.get("files"), list):
        payload["files"] = details["files"]
    return jsonify(payload)


def validate_overlay_file_server(data):
    valid, message, details = validate_overlay_file_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message") or isinstance(details.get("files"), list):
            payload["error_details"] = {"text": details.get("message") or message, "files": details.get("files") if isinstance(details.get("files"), list) else []}
        if isinstance(details.get("files"), list):
            payload["files"] = details["files"]
        return jsonify(payload), 400
    payload = {"valid": True}
    if details.get("message"):
        payload["message"] = details["message"]
    if "validated_files" in details:
        payload["validated_files"] = details["validated_files"]
    if isinstance(details.get("files"), list):
        payload["files"] = details["files"]
    return jsonify(payload)


def validate_playlist_file_server(data):
    valid, message, details = validate_playlist_file_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message") or isinstance(details.get("files"), list):
            payload["error_details"] = {"text": details.get("message") or message, "files": details.get("files") if isinstance(details.get("files"), list) else []}
        if isinstance(details.get("files"), list):
            payload["files"] = details["files"]
        return jsonify(payload), 400
    payload = {"valid": True}
    if details.get("message"):
        payload["message"] = details["message"]
    if "validated_files" in details:
        payload["validated_files"] = details["validated_files"]
    if isinstance(details.get("files"), list):
        payload["files"] = details["files"]
    return jsonify(payload)
