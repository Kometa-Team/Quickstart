"""Safe external YAML editor helpers for Quickstart-managed config files."""

from __future__ import annotations

import json
import hashlib
import urllib.parse
from pathlib import Path

import jsonschema
import requests
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from werkzeug.utils import secure_filename

from modules import helpers, path_validation
from modules.jsonschema_compat import find_non_string_mapping_key_paths, stringify_mapping_keys_for_jsonschema
from modules.validations_shared import _saved_custom_repo_base

EXTERNAL_YAML_KINDS = {
    "collection_files": {
        "label": "Collection file",
        "root": "collections",
        "schema": "collection-schema.json",
        "filename": "collections.yml",
        "template": "collections:\n  Example Collection:\n    summary: Replace this example with your collection.\n",
    },
    "metadata_files": {
        "label": "Metadata file",
        "root": "metadata",
        "schema": "metadata-schema.json",
        "filename": "metadata.yml",
        "template": "metadata:\n  Example Title:\n    summary: Replace this example with your metadata.\n",
    },
    "overlay_files": {
        "label": "Overlay file",
        "root": "overlays",
        "schema": "overlay-schema.json",
        "filename": "overlays.yml",
        "template": "overlays:\n  Example Overlay:\n    overlay:\n      name: Example Overlay\n",
    },
    "playlist_files": {
        "label": "Playlist file",
        "root": "playlists",
        "schema": "playlist-schema.json",
        "filename": "playlists.yml",
        "template": "playlists:\n  Example Playlist:\n    summary: Replace this example with your playlist.\n",
    },
}


def _config_root() -> Path:
    return Path(helpers.CONFIG_DIR).resolve()


def _kind_info(kind):
    info = EXTERNAL_YAML_KINDS.get(str(kind or "").strip())
    if not info:
        raise ValueError("Unsupported YAML file type.")
    return info


def default_external_yaml_location(kind, config_name, library_id="shared"):
    info = _kind_info(kind)
    config_slug = helpers.require_config_name_for_storage(config_name, context="External YAML editor")
    library_slug = str(library_id or "shared").strip() or "shared"
    return Path("config", config_slug, kind, library_slug, info["filename"]).as_posix()


def external_yaml_template(kind):
    return _kind_info(kind)["template"]


def _local_path_parts(raw):
    normalized = str(raw or "").replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts):
        raise ValueError("YAML file path must not contain parent directory segments.")
    if parts and parts[0].lower() == "config":
        parts = parts[1:]
    return parts


def resolve_external_yaml_path(location, *, kind, config_name=None, library_id=None, must_exist=False):
    info = _kind_info(kind)
    raw = str(location or "").strip()
    if not raw:
        if not config_name:
            raise ValueError("YAML file path is required.")
        raw = default_external_yaml_location(kind, config_name, library_id)

    lowered = raw.lower()
    if lowered.startswith(("http://", "https://")):
        raise ValueError("Remote YAML files are read-only in Quickstart.")

    if not lowered.endswith((".yml", ".yaml")):
        raise ValueError(f"{info['label']} path must end with .yml or .yaml.")

    parts = _local_path_parts(raw)

    valid, message = path_validation.validate_path(raw, {"allow_relative": True, "must_exist": False})
    if not valid:
        raise ValueError(f"{info['label']} path: {message}")

    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (_config_root() / Path(*parts)).resolve()

    try:
        resolved.relative_to(_config_root())
    except ValueError as exc:
        raise ValueError("YAML file must live inside the active Quickstart config folder.") from exc

    if must_exist and not resolved.is_file():
        raise ValueError(f"{info['label']} does not exist.")
    if resolved.exists() and resolved.is_dir():
        raise ValueError(f"{info['label']} path points to a folder, not a file.")

    return resolved


def resolve_external_yaml_folder_path(location, *, kind):
    info = _kind_info(kind)
    raw = str(location or "").strip()
    if not raw:
        raise ValueError(f"{info['label']} folder path is required.")
    if raw.lower().startswith(("http://", "https://")):
        raise ValueError(f"{info['label']} folder must be a local folder path.")

    parts = _local_path_parts(raw)
    valid, message = path_validation.validate_path(raw, {"allow_relative": True, "must_exist": False})
    if not valid:
        raise ValueError(f"{info['label']} folder path: {message}")

    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (_config_root() / Path(*parts)).resolve()

    try:
        resolved.relative_to(_config_root())
    except ValueError as exc:
        raise ValueError("YAML folder must live inside the active Quickstart config folder.") from exc

    if not resolved.is_dir():
        raise ValueError(f"{info['label']} folder does not exist.")

    return resolved


def display_external_yaml_location(path):
    resolved = Path(path).resolve()
    try:
        rel = resolved.relative_to(_config_root())
        return Path("config", *rel.parts).as_posix()
    except ValueError:
        return resolved.as_posix()


def _line_column(line, column):
    if line is None:
        return None, None
    return int(line) + 1, int(column or 0) + 1


def _issue(severity, message, *, line=None, column=None, path="", source="yaml"):
    issue = {
        "severity": severity,
        "message": str(message or ""),
        "source": source,
    }
    if path:
        issue["path"] = str(path)
    if line is not None:
        issue["line"] = int(line)
    if column is not None:
        issue["column"] = int(column)
    return issue


def _find_tab_indentation(content):
    for line_number, line in enumerate(str(content or "").splitlines(), start=1):
        leading = line[: len(line) - len(line.lstrip(" \t"))]
        if "\t" in leading:
            return line_number, leading.index("\t") + 1
    return None, None


def lint_external_yaml_text(content):
    text = str(content or "")
    tab_line, tab_column = _find_tab_indentation(text)
    if tab_line is not None:
        return (
            False,
            "YAML indentation must use spaces, not tabs.",
            None,
            _issue(
                "error",
                "YAML indentation must use spaces, not tabs.",
                line=tab_line,
                column=tab_column,
                source="yaml",
            ),
        )
    parser = YAML(typ="safe", pure=True)
    try:
        parsed = parser.load(text)
    except Exception as exc:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        line, column = _line_column(getattr(mark, "line", None), getattr(mark, "column", None))
        return False, str(exc), None, _issue("error", str(exc), line=line, column=column, source="yaml")
    return True, "", parsed, None


def parse_external_yaml_with_lines(content):
    parser = YAML(typ="rt", pure=True)
    try:
        return parser.load(str(content or ""))
    except Exception:
        return None


def _schema_path_label(path):
    return ".".join(str(part) for part in path)


def _node_line_for_path(parsed, path):
    node = parsed
    line = None
    column = None
    for part in path:
        try:
            if isinstance(node, CommentedMap):
                if part in node:
                    key_line, key_column = node.lc.key(part)
                    line, column = _line_column(key_line, key_column)
                    node = node[part]
                else:
                    break
            elif isinstance(node, CommentedSeq) and isinstance(part, int) and 0 <= part < len(node):
                item_line, item_column = node.lc.item(part)
                line, column = _line_column(item_line, item_column)
                node = node[part]
            elif isinstance(node, dict):
                node = node[part]
            elif isinstance(node, list) and isinstance(part, int):
                node = node[part]
            else:
                break
        except Exception:
            break
    return line, column


def _yaml_file_matches_kind(path, info):
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    valid_yaml, _yaml_error, parsed, _issue_payload = lint_external_yaml_text(content)
    if not valid_yaml or not isinstance(parsed, dict):
        return False
    mapping = parsed.get(info["root"])
    return isinstance(mapping, dict) and bool(mapping)


def list_external_yaml_folder_files(kind, location):
    info = _kind_info(kind)
    folder = resolve_external_yaml_folder_path(location, kind=kind)
    files = sorted(
        (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in {".yml", ".yaml"} and _yaml_file_matches_kind(path, info)),
        key=lambda path: path.name.lower(),
    )
    return {
        "folder": display_external_yaml_location(folder),
        "files": [
            {
                "name": path.name,
                "location": display_external_yaml_location(path),
            }
            for path in files
        ],
    }


def validate_external_yaml_content(kind, content):
    info = _kind_info(kind)
    valid_yaml, yaml_error, parsed, yaml_issue = lint_external_yaml_text(content)
    if not valid_yaml:
        issues = [yaml_issue] if yaml_issue else [_issue("error", yaml_error, source="yaml")]
        return {
            "can_save": False,
            "yaml_valid": False,
            "schema_valid": False,
            "error": f"Invalid YAML. {yaml_error}",
            "warnings": [],
            "issues": issues,
        }

    warnings = []
    issues = []
    if not isinstance(parsed, dict):
        message = f"Top-level `{info['root']}:` mapping was not found."
        warnings.append(message)
        issues.append(_issue("warning", message, source="schema"))
    elif info["root"] not in parsed:
        message = f"Top-level `{info['root']}:` mapping was not found."
        warnings.append(message)
        issues.append(_issue("warning", message, source="schema"))
    elif not isinstance(parsed.get(info["root"]), dict) or not parsed.get(info["root"]):
        message = f"Top-level `{info['root']}:` should be a non-empty mapping."
        warnings.append(message)
        parsed_with_lines = parse_external_yaml_with_lines(content)
        line, column = _node_line_for_path(parsed_with_lines, [info["root"]]) if parsed_with_lines is not None else (None, None)
        issues.append(_issue("warning", message, line=line, column=column, path=info["root"], source="schema"))

    schema_valid = True
    try:
        helpers.ensure_json_schema()
        schema_path = Path(helpers.JSON_SCHEMA_DIR) / info["schema"]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        parsed_with_lines = parse_external_yaml_with_lines(content)
        non_string_key_paths = find_non_string_mapping_key_paths(parsed)
        if non_string_key_paths:
            schema_valid = False
            for key_path in non_string_key_paths[:10]:
                path = _schema_path_label(key_path)
                key = key_path[-1]
                message = f"{path}: YAML parsed mapping key `{key}` as {type(key).__name__}; " "quote it if it should be treated as text."
                warnings.append(message)
                line, column = _node_line_for_path(parsed_with_lines, list(key_path)) if parsed_with_lines is not None else (None, None)
                issues.append(_issue("warning", message, line=line, column=column, path=path, source="schema"))
            if len(non_string_key_paths) > 10:
                message = f"{len(non_string_key_paths) - 10} additional non-string YAML keys not shown."
                warnings.append(message)
                issues.append(_issue("warning", message, source="schema"))
        validation_input = stringify_mapping_keys_for_jsonschema(parsed)
        schema_errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(validation_input), key=lambda err: list(err.path))
        if schema_errors:
            schema_valid = False
            for err in schema_errors[:10]:
                path = _schema_path_label(err.path)
                prefix = f"{path}: " if path else ""
                message = f"{prefix}{err.message}"
                warnings.append(message)
                line, column = _node_line_for_path(parsed_with_lines, list(err.path)) if parsed_with_lines is not None else (None, None)
                issues.append(_issue("warning", err.message, line=line, column=column, path=path, source="schema"))
            if len(schema_errors) > 10:
                message = f"{len(schema_errors) - 10} additional schema warnings not shown."
                warnings.append(message)
                issues.append(_issue("warning", message, source="schema"))
    except Exception as exc:
        schema_valid = False
        message = f"Schema validation unavailable: {exc}"
        warnings.append(message)
        issues.append(_issue("warning", message, source="schema"))

    return {
        "can_save": True,
        "yaml_valid": True,
        "schema_valid": schema_valid and not warnings,
        "warnings": warnings,
        "issues": issues,
    }


def _safe_remote_filename(source_type, location, fallback):
    raw = str(location or "").strip()
    parsed = urllib.parse.urlparse(raw)
    candidate = Path(parsed.path or raw).name
    if not candidate or "." not in candidate:
        candidate = fallback
    stem = secure_filename(Path(candidate).stem) or secure_filename(source_type) or "external"
    suffix = Path(candidate).suffix.lower()
    if suffix not in {".yml", ".yaml"}:
        suffix = ".yml"
    digest = hashlib.sha1(f"{source_type}:{raw}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"{stem}_{digest}{suffix}"


def default_remote_copy_location(kind, source_type, source_location, config_name, library_id="shared"):
    info = _kind_info(kind)
    config_slug = helpers.require_config_name_for_storage(config_name, context="External YAML editor")
    library_slug = str(library_id or "shared").strip() or "shared"
    filename = _safe_remote_filename(source_type, source_location, info["filename"])
    return Path("config", config_slug, kind, library_slug, "remote_copies", filename).as_posix()


def remote_external_yaml_url(source_type, location):
    source = str(source_type or "").strip().lower()
    raw = str(location or "").strip()
    if source == "url":
        if not raw.lower().startswith(("http://", "https://")):
            raise ValueError("Remote YAML URL must start with http:// or https://.")
        return raw
    if raw.lower().startswith(("http://", "https://")):
        raise ValueError(f"{source or 'Remote'} YAML source must not be a full URL.")
    if source == "git":
        return f"https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/{raw}"
    if source == "repo":
        custom_repo_base = _saved_custom_repo_base()
        if not custom_repo_base:
            raise ValueError("Repo entries require Custom Repo to be configured and saved first within the Settings page.")
        return f"{custom_repo_base}{raw}"
    raise ValueError("Only url, git, and repo entries can be copied to a local editable file.")


def read_remote_external_yaml_source(kind, source_type, source_location, *, config_name, library_id=None):
    url = remote_external_yaml_url(source_type, source_location)
    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as exc:
        raise ValueError(f"Unable to fetch remote YAML source. {exc}") from exc
    if response.status_code >= 400:
        raise ValueError(f"Unable to fetch remote YAML source ({response.status_code} {response.reason}).")
    location = default_remote_copy_location(kind, source_type, source_location, config_name, library_id)
    content = response.text
    return {
        "source_url": url,
        "location": location,
        "content": content,
        "validation": validate_external_yaml_content(kind, content),
    }


def read_external_yaml_file(kind, location, *, config_name=None, library_id=None):
    path = resolve_external_yaml_path(location, kind=kind, config_name=config_name, library_id=library_id, must_exist=False)
    if path.exists():
        content = path.read_text(encoding="utf-8")
        created = False
    else:
        content = external_yaml_template(kind)
        created = True
    return {
        "path": path,
        "location": display_external_yaml_location(path),
        "content": content,
        "created": created,
        "validation": validate_external_yaml_content(kind, content),
    }


def save_external_yaml_file(kind, location, content, *, config_name=None, library_id=None):
    path = resolve_external_yaml_path(location, kind=kind, config_name=config_name, library_id=library_id, must_exist=False)
    validation = validate_external_yaml_content(kind, content)
    if not validation["can_save"]:
        return False, path, validation
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content or ""), encoding="utf-8")
    return True, path, validation
