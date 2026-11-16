"""Seerr configuration, validation and runtime capability checks.

Connection checks only read /auth/me. They never submit media requests.
Keep unrecognized imported values so newer Kometa settings survive editing;
the selected runtime's schema remains authoritative at export time.
"""

from __future__ import annotations

import copy
import json
from urllib.parse import urlsplit

import requests

from modules import helpers, url_validation

SEERR_OPTIONS = ("seerr_add_missing", "seerr_add_existing", "seerr_instance", "seerr_overrides")


def is_seerr_option(key):
    return any(str(key) == option or str(key).startswith(option + "_") for option in SEERR_OPTIONS)


def parse_overrides(value):
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            raise ValueError("Seerr overrides must be a JSON object.") from None
    return copy.deepcopy(value) if value not in (None, "") else {}


def normalize_option(key, value):
    if "seerr_overrides" in key:
        try:
            return parse_overrides(value)
        except ValueError:
            return value
    if "seerr_add_missing" in key or "seerr_add_existing" in key:
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
    return value


def display_overrides(value):
    try:
        parsed = parse_overrides(value)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def redact_seerr_secrets(value, *, in_seerr=False):
    if isinstance(value, dict):
        return {
            key: "(redacted)" if (str(key) == "apikey" and in_seerr) or str(key).endswith("seerr_apikey") else redact_seerr_secrets(child, in_seerr=in_seerr or str(key) == "seerr")
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_seerr_secrets(child, in_seerr=in_seerr) for child in value]
    return value


def enrich_collection_config(groups):
    """Add one shared control group to defaults that accept request options."""
    for group in groups:
        for collection in group.get("collections", []):
            fields = collection.get("template_variables")
            if not isinstance(fields, list) or any(field.get("type") == "seerr_options" for field in fields):
                continue
            if not any(str(field.get("key", "")).startswith(("radarr_add_missing", "sonarr_add_missing")) for field in fields):
                continue
            fields.extend(
                {"key": key, "type": "seerr_options" if index == 0 else "seerr_option_marker", "label": key, "section": "seerr"} for index, key in enumerate(SEERR_OPTIONS)
            )
            if collection.get("template_variable_sections"):
                collection["template_variable_sections"].append({"id": "seerr", "label": "Seerr requests", "default_open": False})
    return groups


def option_errors(options):
    errors = []
    for key, raw in options.items():
        if raw is None or raw == "" or not is_seerr_option(key):
            continue
        if key.startswith(("seerr_add_missing", "seerr_add_existing")):
            if not isinstance(normalize_option(key, raw), bool):
                errors.append("Seerr request switches must be true or false.")
        elif key.startswith("seerr_instance"):
            if not isinstance(raw, str) or raw not in {"standard", "4k", "both"}:
                errors.append("Seerr instance must be standard, 4k, or both.")
        elif key.startswith("seerr_overrides"):
            try:
                overrides = parse_overrides(raw)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if not isinstance(overrides, dict):
                errors.append("Seerr overrides must be an object with standard and/or 4k tiers.")
                continue
            for tier, fields in overrides.items():
                # Preserve future fields; their support is checked by the schema.
                if tier not in {"standard", "4k"}:
                    continue
                if not isinstance(fields, dict):
                    errors.append("Each Seerr override tier must be an object.")
                    continue
                server = fields.get("server_id")
                if server is not None and (type(server) is not int or server < 1):
                    errors.append("Seerr server_id must be a positive integer.")
                profile = fields.get("quality_profile")
                if profile is not None and not ((type(profile) is int and profile > 0) or (isinstance(profile, str) and profile.strip())):
                    errors.append("Seerr quality_profile must be a positive ID or a nonblank profile name.")
                folder = fields.get("root_folder")
                if folder is not None and (not isinstance(folder, str) or not folder.strip()):
                    errors.append("Seerr root_folder must be a nonblank path.")
    return list(dict.fromkeys(errors))


def connection_errors(connection, *, require_complete=True):
    if not isinstance(connection, dict):
        return ["Seerr connection settings must be an object."]
    errors = []
    url = connection.get("url")
    if url:
        if not isinstance(url, str):
            errors.append("Seerr URL must be an HTTP or HTTPS URL.")
        else:
            valid, _message = url_validation.validate_url(url, allow_local=True)
            try:
                parsed = urlsplit(url)
                unsafe = bool(parsed.username or parsed.password or parsed.query or parsed.fragment)
            except ValueError:
                unsafe = True
            if not valid or unsafe:
                errors.append("Seerr URL must be an HTTP or HTTPS URL without credentials, a query, or a fragment.")
    elif require_complete:
        errors.append("Enter a Seerr URL, or inherit one from the global Seerr configuration.")
    key = connection.get("apikey")
    if key is not None and (not isinstance(key, str) or not key.strip()):
        errors.append("Enter a nonblank Seerr API key.")
    elif not key and require_complete:
        errors.append("Enter a Seerr API key, or inherit one from the global Seerr configuration.")
    return errors


def validate_connection(connection):
    errors = connection_errors(connection)
    if errors:
        return {"valid": False, "error": " ".join(errors)}, 400
    try:
        response = requests.get(
            f"{connection['url'].strip().rstrip('/')}/api/v1/auth/me",
            headers={"X-Api-Key": connection["apikey"]},
            timeout=10,
            allow_redirects=False,
        )
        if response.status_code in {401, 403}:
            return {"valid": False, "error": "Seerr rejected the API key. Check Settings > General > API Key in Seerr."}, 401
        if response.status_code != 200:
            return {"valid": False, "error": "Seerr did not return an authenticated response. Check the URL, reverse proxy, and API access."}, 400
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("id"):
            return {"valid": False, "error": "Seerr returned an unexpected authentication response. Check the URL and reverse proxy."}, 400
    except requests.exceptions.Timeout:
        return {"valid": False, "error": "Seerr timed out. Check the address, port, and network access from Quickstart."}, 400
    except (requests.exceptions.RequestException, ValueError):
        # Neither exception strings nor remote response bodies are safe to echo.
        return {"valid": False, "error": "Unable to authenticate with Seerr. Check the URL, API key, TLS certificate, and network access."}, 400
    return {"valid": True}, 200


def runtime_support():
    if helpers.get_kometa_install_mode() == "external":
        return {"supported": None, "message": "Quickstart cannot inspect an external Kometa runtime. Confirm that it includes Seerr support (Kometa PR #3738) before exporting."}
    root = helpers.get_kometa_root_path()
    if not (root / "kometa.py").is_file():
        return {"supported": None, "message": "Install or select a Kometa runtime with Seerr support (PR #3738) before exporting Seerr settings."}
    try:
        config = (root / "modules" / "config.py").read_text(encoding="utf-8")
        builder = (root / "modules" / "builder.py").read_text(encoding="utf-8")
        supported = (root / "modules" / "seerr.py").is_file() and "seerr" in config and "seerr_add_missing" in builder
    except OSError:
        supported = False
    return {
        "supported": supported,
        "message": (
            "The selected Kometa runtime supports Seerr."
            if supported
            else "This Kometa runtime does not include Seerr support. Update Kometa to a build containing PR #3738. Imported settings are preserved."
        ),
    }


def defaults_support():
    if helpers.get_kometa_install_mode() == "external":
        return None
    try:
        templates = (helpers.get_kometa_root_path() / "defaults" / "templates.yml").read_text(encoding="utf-8")
        return all(option + ":" in templates for option in SEERR_OPTIONS)
    except OSError:
        return None


def global_settings():
    from modules import persistence

    settings = persistence.retrieve_settings("125-seerr") or {}
    connection = settings.get("seerr", {})
    enabled = helpers.booler(connection.get("tmp_enabled", True)) if isinstance(connection, dict) else True
    return settings, connection if enabled and isinstance(connection, dict) else {}


def library_connection(library_id, libraries_data, global_connection):
    connection = {key: value for key, value in global_connection.items() if not key.startswith("tmp_")}
    for key in ("url", "apikey"):
        value = libraries_data.get(f"{library_id}-attribute_seerr_{key}")
        if value not in (None, ""):
            connection[key] = value
    return connection


def build_library_connection(attr_group, library_type, lib_id):
    prefix = f"{library_type}-library_{lib_id}-attribute_seerr_"
    result = copy.deepcopy(attr_group.get(prefix + "extra") or {})
    if not isinstance(result, dict):
        result = {}
    for key in ("url", "apikey"):
        value = attr_group.get(prefix + key)
        if value not in (None, ""):
            result[key] = value
    return result


def validate_library_settings(libraries_data, library_ids):
    _settings, global_connection = global_settings()
    errors = []
    for library_id in library_ids:
        options = []
        for key, value in libraries_data.items():
            if key.startswith(library_id + "-template_variables[seerr_"):
                options.append((key.split("[", 1)[1].rstrip("]"), value))
            elif key.startswith(library_id + "-template_collection_"):
                tail = key.split("-template_collection_", 1)[1]
                if "_seerr_" not in tail:
                    continue
                collection, option = tail.split("_seerr_", 1)
                if helpers.booler(libraries_data.get(f"{library_id}-collection_{collection}")):
                    options.append(("seerr_" + option, value))
        messages = [error for option, value in options for error in option_errors({option: value})]
        has_override = any(libraries_data.get(f"{library_id}-attribute_seerr_{field}") not in (None, "") for field in ("url", "apikey"))
        requests_enabled = any(helpers.booler(value) for key, value in options if key.startswith(("seerr_add_missing", "seerr_add_existing")))
        if has_override or requests_enabled:
            messages.extend(connection_errors(library_connection(library_id, libraries_data, global_connection)))
        errors.extend({"library_id": library_id, "field": "seerr", "message": message} for message in dict.fromkeys(messages))
    return errors


def configuration_errors(config, *, compatibility_confirmed=False):
    """Validate emitted Seerr data without altering imported settings."""
    errors = []
    global_connection = config.get("seerr", {})
    if isinstance(global_connection, dict) and "seerr" in global_connection:
        global_connection = global_connection["seerr"]
    present = bool(global_connection)
    uses_default_options = False
    if present:
        errors.extend(connection_errors(global_connection))
    libraries = config.get("libraries", {})
    if isinstance(libraries, dict) and "libraries" in libraries:
        libraries = libraries["libraries"]
    for library in libraries.values() if isinstance(libraries, dict) else []:
        if not isinstance(library, dict):
            continue
        override = library.get("seerr", {})
        if override:
            present = True
            errors.extend(connection_errors({**global_connection, **override}))
        option_sets = [library.get("template_variables", {})]
        option_sets.extend(entry.get("template_variables", {}) for entry in library.get("collection_files", []) if isinstance(entry, dict))
        for options in option_sets:
            if not isinstance(options, dict):
                continue
            if any(is_seerr_option(key) and value not in (None, "") for key, value in options.items()):
                present = True
                uses_default_options = True
                errors.extend(option_errors(options))
                errors.extend(connection_errors({**global_connection, **override}))
    if present:
        support = runtime_support()
        if support["supported"] is False or (support["supported"] is None and not (helpers.get_kometa_install_mode() == "external" and compatibility_confirmed)):
            errors.append(support["message"])
    defaults_confirmed = helpers.get_kometa_install_mode() == "external" and compatibility_confirmed
    if uses_default_options and defaults_support() is not True and not defaults_confirmed:
        errors.append(
            "This Kometa installation's shared defaults template does not forward Seerr options. Update to defaults that support Seerr, or use direct seerr_* attributes in a custom collection YAML file. Saved options are preserved."
        )
    return list(dict.fromkeys(errors))
