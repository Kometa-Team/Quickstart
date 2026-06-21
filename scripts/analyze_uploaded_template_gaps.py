import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import warnings
import zipfile
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.composer import ReusedAnchorWarning

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import importer

try:
    import py7zr
except ImportError:
    py7zr = None

CACHE_VERSION = 4
CACHE_SAVE_EVERY_ITEMS = 1000
CACHE_SAVE_EVERY_SECS = 60.0
VERIFY_CHECKPOINT_VERSION = 2
VERIFY_CHECKPOINT_EVERY_ITEMS = 1000
VERIFY_CHECKPOINT_EVERY_SECS = 30.0
VERIFY_CHECKPOINT_DIRNAME = "template_gap_verify_checkpoint"
ARCHIVE_CACHE_VERSION = 1
ARCHIVE_CACHE_DIRNAME = "template_gap_archive_cache"
QS_SPECIAL_LIBRARY_TEMPLATE_KEYS = {
    "placeholder_imdb_id",
    "sep_style",
}
QS_SPECIAL_GLOBAL_SUPPORTED_KEYS = {
    "minimum_items",
    "playlist_exclude_users",
    "playlist_sync_to_users",
}
QS_SPECIAL_PLAYLIST_SUPPORTED_KEYS = {
    "exclude_users",
    "libraries",
    "playlist_exclude_users",
    "playlist_sync_to_users",
    "sync_to_users",
}

DEFAULT_EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "assets",
    "bin",
    "build",
    "cache",
    "cache_data",
    "dist",
    "images",
    "img",
    "log",
    "logs",
    "node_modules",
    "obj",
    "output",
    "packages",
    "photos",
    "pictures",
    "site-packages",
    ARCHIVE_CACHE_DIRNAME,
    VERIFY_CHECKPOINT_DIRNAME,
    "vendor",
    "videos",
    "venv",
}

READ_TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
KOMETA_TOP_LEVEL_MARKERS = (
    "libraries",
    "playlist_files",
    "plex",
    "tmdb",
    "omdb",
    "mdblist",
    "tautulli",
    "notifiarr",
    "gotify",
    "ntfy",
    "apprise",
    "github",
    "radarr",
    "sonarr",
    "trakt",
    "mal",
    "anidb",
    "webhooks",
    "settings",
)
EXTERNAL_TOP_LEVEL_MARKERS = (
    "collections",
    "dynamic_collections",
    "overlays",
    "metadata",
    "playlists",
)
PROBABLE_ARTIFACT_NAME_PATTERNS = (
    re.compile(r"^parsed_.*(?:\.log|\.txt)_config_.*\.ya?ml$", re.IGNORECASE),
    re.compile(r"^parsed_.*\.ya?ml$", re.IGNORECASE),
)
PROBABLE_ARTIFACT_PATH_PARTS = {
    "fromdownloads",
}
YAML_SUFFIXES = {".yml", ".yaml"}


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        handle.write(text)
        temp_name = handle.name
    Path(temp_name).replace(path)


DEFAULT_EXCLUDED_TOP_LEVEL_DIR_NAMES = {
    "$recycle.bin",
    "program files",
    "program files (x86)",
    "programdata",
    "windows",
}
DEFAULT_EXCLUDED_PATH_SEQUENCES = {
    ("defaults-image-creation", "create_people_posters", "config", "chrome-profile"),
    ("onedrive",),
    ("users", "default"),
    ("users", "public"),
}

yaml = YAML(typ="safe", pure=True)


def read_text_with_fallbacks(path: Path) -> tuple[str, str]:
    last_exc: Exception | None = None
    for encoding in READ_TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise UnicodeDecodeError("utf-8", b"", 0, 1, f"unable to decode {path}")


def load_yaml(path: Path) -> tuple[Any, str]:
    raw_text, encoding = read_text_with_fallbacks(path)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ReusedAnchorWarning)
        return yaml.load(raw_text), encoding


def looks_like_kometa_config_text(raw_text: str) -> bool:
    if not isinstance(raw_text, str) or not raw_text.strip():
        return False
    pattern = rf"(?m)^\s*(?:{'|'.join(re.escape(marker) for marker in KOMETA_TOP_LEVEL_MARKERS)})\s*:"
    return re.search(pattern, raw_text) is not None


def classify_yaml_document_type(data: Any) -> str:
    if not isinstance(data, dict):
        return "unknown"

    keys = {str(key) for key in data.keys()}

    if keys.intersection(KOMETA_TOP_LEVEL_MARKERS):
        return "config"
    if "collections" in keys or "dynamic_collections" in keys:
        return "external_collection"
    if "overlays" in keys:
        return "external_overlay"
    if "metadata" in keys:
        return "external_metadata"
    if "playlists" in keys:
        return "external_playlist"
    if "templates" in keys or "external_templates" in keys:
        return "external_template_bundle"
    return "unknown"


def yaml_type_matches_focus(document_type: str, focus: str) -> bool:
    if focus == "all":
        return True
    if focus == "config":
        return document_type == "config"
    return document_type == focus


def is_probable_non_config_artifact(path: Path) -> bool:
    filename = path.name
    if any(pattern.match(filename) for pattern in PROBABLE_ARTIFACT_NAME_PATTERNS):
        return True
    lower_parts = {part.lower() for part in path.parts}
    if lower_parts.intersection(PROBABLE_ARTIFACT_PATH_PARTS) and filename.lower().startswith("parsed_"):
        return True
    return False


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def empty_cache(context: dict[str, Any] | None = None) -> dict[str, Any]:
    cache: dict[str, Any] = {"version": CACHE_VERSION, "files": {}}
    if context is not None:
        cache["context"] = context
    return cache


def load_cache(path: Path, expected_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return empty_cache(expected_context)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty_cache(expected_context)
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION or not isinstance(data.get("files"), dict):
        return empty_cache(expected_context)
    if expected_context is not None and data.get("context") != expected_context:
        return empty_cache(expected_context)
    return data


def save_cache(path: Path, cache_data: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(cache_data, indent=2, default=json_default))


def get_cache_path(root: Path, requested_path: str | None) -> Path:
    if requested_path:
        return Path(requested_path).resolve()
    return root / "artifacts" / "template_gap_cache.json"


def get_verification_checkpoint_dir(root: Path) -> Path:
    return root / "artifacts" / VERIFY_CHECKPOINT_DIRNAME


def get_archive_cache_dir(root: Path) -> Path:
    return root / "artifacts" / ARCHIVE_CACHE_DIRNAME


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
        return
    for child in path.iterdir():
        if child.is_dir():
            remove_tree(child)
        else:
            child.unlink()
    path.rmdir()


def compute_uploaded_signature(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(rows)).encode("utf-8"))
    for row in rows:
        digest.update(
            json.dumps(
                [
                    row.get("file"),
                    row.get("kind"),
                    row.get("default"),
                    row.get("library"),
                    row.get("key"),
                    row.get("value"),
                ],
                ensure_ascii=False,
                separators=(",", ":"),
                default=json_default,
            ).encode("utf-8")
        )
    return digest.hexdigest()


def append_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=json_default))
            handle.write("\n")


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"unexpected non-object JSONL entry at {path}:{line_number}")
            rows.append(item)
    return rows


def load_matching_report_rows(
    report_dir: Path,
    *,
    quickstart_root: Path,
    inputs: list[Path],
    cache_context: dict[str, Any],
    uploaded_signature: str,
    uploaded_count: int,
) -> tuple[list[dict[str, Any]] | None, Path | None]:
    if not report_dir.exists():
        return None, None
    candidates = sorted(report_dir.glob("template_gap_report_*.json"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for candidate in candidates:
        try:
            data = load_json(candidate)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("quickstart_root") != str(quickstart_root):
            continue
        if data.get("inputs") != [str(p) for p in inputs]:
            continue
        if data.get("cache_context") != cache_context:
            continue
        rows = data.get("all_rows")
        if not isinstance(rows, list) or len(rows) != uploaded_count:
            continue
        if not all(isinstance(row, dict) for row in rows):
            continue
        if compute_uploaded_signature(rows) != uploaded_signature:
            continue
        return rows, candidate
    return None, None


def file_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def safe_file_signature(path: Path) -> dict[str, int] | None:
    try:
        return file_signature(path)
    except FileNotFoundError:
        return None


def normalized_parts(path: Path) -> list[str]:
    parts: list[str] = []
    for part in path.parts:
        cleaned = part.rstrip("\\/").lower()
        if cleaned:
            parts.append(cleaned)
    return parts


def is_virtualenv_dir_name(name: str) -> bool:
    lowered = name.lower()
    return lowered == "venv" or lowered.endswith("-venv") or lowered.endswith("_venv") or lowered.startswith("py_env-python")


def has_part_sequence(parts: list[str], sequence: tuple[str, ...]) -> bool:
    if len(parts) < len(sequence):
        return False
    for idx in range(len(parts) - len(sequence) + 1):
        if tuple(parts[idx : idx + len(sequence)]) == sequence:
            return True
    return False


def should_exclude_directory(path: Path, root: Path, enabled: bool = True) -> bool:
    if not enabled:
        return False
    try:
        relative = path.relative_to(root)
        parts = normalized_parts(relative)
    except ValueError:
        parts = normalized_parts(path)
    if not parts:
        return False
    if parts[0] in DEFAULT_EXCLUDED_TOP_LEVEL_DIR_NAMES:
        return True
    if any(part.startswith(".") for part in parts):
        return True
    if "appdata" in parts:
        return True
    if any(is_virtualenv_dir_name(part) for part in parts):
        return True
    if any(part in DEFAULT_EXCLUDED_DIR_NAMES for part in parts):
        return True
    return any(has_part_sequence(parts, sequence) for sequence in DEFAULT_EXCLUDED_PATH_SEQUENCES)


def describe_default_excludes(enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "top_level_dir_names": [],
            "dir_names_anywhere": [],
            "path_sequences": [],
            "logic_rules": [],
        }
    return {
        "enabled": True,
        "top_level_dir_names": sorted(DEFAULT_EXCLUDED_TOP_LEVEL_DIR_NAMES),
        "dir_names_anywhere": sorted(DEFAULT_EXCLUDED_DIR_NAMES),
        "path_sequences": ["\\".join(sequence) for sequence in sorted(DEFAULT_EXCLUDED_PATH_SEQUENCES)],
        "logic_rules": [
            "dot-prefixed folders",
            "any path containing AppData",
            "virtualenv-style folders: venv, *-venv, *_venv, py_env-python*",
        ],
    }


def relative_label(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path.resolve())


def fingerprint_paths(paths: list[Path], base: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: relative_label(p, base)):
        signature = file_signature(path)
        digest.update(relative_label(path, base).encode("utf-8"))
        digest.update(str(signature["size"]).encode("utf-8"))
        digest.update(str(signature["mtime_ns"]).encode("utf-8"))
    return digest.hexdigest()


def build_cache_context(
    root: Path,
    qs_collections_path: Path,
    qs_overlays_path: Path,
    qs_attributes_path: Path,
    kometa_defaults: Path,
    yaml_type_focus: str,
) -> dict[str, Any]:
    quickstart_support_files = [qs_collections_path, qs_overlays_path, qs_attributes_path]
    kometa_default_files = [path for path in kometa_defaults.rglob("*.yml") if path.is_file()]
    analyzer_file = Path(__file__).resolve()
    return {
        "quickstart_root": str(root),
        "analyzer_signature": file_signature(analyzer_file),
        "quickstart_support_fingerprint": fingerprint_paths(quickstart_support_files, root),
        "kometa_defaults_fingerprint": fingerprint_paths(kometa_default_files, root),
        "kometa_default_file_count": len(kometa_default_files),
        "yaml_type_focus": yaml_type_focus,
    }


def collect_qs_keys(raw: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(raw, dict):
        keys.update(str(k) for k in raw.keys())
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("key"):
                keys.add(str(item["key"]))
    return keys


def collect_declared_yaml_patterns(raw: Any, *, parent_key: str | None = None) -> set[str]:
    patterns: set[str] = set()
    if isinstance(raw, dict):
        for raw_key, raw_value in raw.items():
            key = str(raw_key)
            if key not in RESERVED:
                patterns.add(key)
                if key.endswith(".exists"):
                    patterns.add(key[: -len(".exists")])
                if parent_key == "data":
                    patterns.add(f"data_{key}")
            patterns.update(collect_declared_yaml_patterns(raw_value, parent_key=key))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                if parent_key == "template":
                    continue
                token = item.strip()
                if token and re.fullmatch(r"[A-Za-z0-9_<>-]+(?:\.[A-Za-z0-9_<>-]+)?", token) and token not in RESERVED:
                    patterns.add(token)
                    if token.endswith(".exists"):
                        patterns.add(token[: -len(".exists")])
            else:
                patterns.update(collect_declared_yaml_patterns(item, parent_key=parent_key))
    return patterns


def build_qs_collection_map(qs_collections_path: Path) -> dict[str, set[str]]:
    data = load_json(qs_collections_path)
    mapping: dict[str, set[str]] = {}
    for group in data:
        if not isinstance(group, dict):
            continue
        for collection in group.get("collections", []):
            if not isinstance(collection, dict):
                continue
            cid = collection.get("id")
            if not cid:
                continue
            alias = str(cid).replace("collection_", "", 1)
            mapping.setdefault(alias, set()).update(collect_qs_keys(collection.get("template_variables")))
    return mapping


def build_qs_overlay_map(qs_overlays_path: Path, *, enrich_runtime_support: bool = True) -> dict[str, set[str]]:
    data = load_json(qs_overlays_path)
    mapping: dict[str, set[str]] = {}
    for group in data:
        if not isinstance(group, dict):
            continue
        for overlay in group.get("overlays", []):
            if not isinstance(overlay, dict):
                continue
            oid = overlay.get("id")
            if not oid:
                continue
            alias = str(oid).replace("overlay_", "", 1)
            keys = collect_qs_keys(overlay.get("template_variables"))

            if enrich_runtime_support:
                # Quickstart injects horizontal/vertical offset controls at render time
                # for overlays that declare default offsets or initial offset aliases.
                default_offsets = overlay.get("default_offsets")
                default_offsets_by_type = overlay.get("default_offsets_by_type")
                supports_runtime_offsets = False
                supports_origin_alignment = False

                if {"horizontal_offset", "vertical_offset", "initial_horizontal_offset", "initial_vertical_offset"} & keys:
                    supports_runtime_offsets = True

                if isinstance(default_offsets, dict):
                    if any(axis in default_offsets for axis in ("horizontal", "vertical")):
                        supports_runtime_offsets = True
                    if default_offsets.get("origin") is not None:
                        supports_origin_alignment = True

                if isinstance(default_offsets_by_type, dict):
                    for values in default_offsets_by_type.values():
                        if not isinstance(values, dict):
                            continue
                        if any(axis in values for axis in ("horizontal", "vertical")):
                            supports_runtime_offsets = True
                        if values.get("origin") is not None:
                            supports_origin_alignment = True

                if supports_runtime_offsets:
                    keys.update({"horizontal_offset", "vertical_offset"})
                if supports_origin_alignment:
                    keys.update({"horizontal_align", "vertical_align"})

            # Some Quickstart defaults intentionally reuse the same alias for
            # different media types. Merge their declared keys so later entries
            # do not erase earlier support and create false-positive gaps.
            mapping.setdefault(alias, set()).update(keys)
    return mapping


def overlay_key_supported_in_quickstart(alias: str | None, key: str, qs_overlays: dict[str, set[str]]) -> bool:
    alias_text = str(alias or "")
    if key in qs_overlays.get(alias_text, set()):
        return True

    # Quickstart models subtitle language flags as a dedicated overlay alias,
    # while user configs legitimately express that selection as
    # default: languages + template_variables.use_subtitles: true.
    if alias_text == "languages" and key == "use_subtitles":
        return key in qs_overlays.get("languages_subtitles", set())

    return False


def build_qs_library_template_keys(qs_attributes_path: Path) -> set[str]:
    data = load_json(qs_attributes_path)
    keys: set[str] = set(QS_SPECIAL_LIBRARY_TEMPLATE_KEYS)
    for section in data.get("sections", []):
        if not isinstance(section, dict):
            continue
        prefix = section.get("prefix")
        key = section.get("key")
        yml_location = section.get("yml_location")
        if yml_location == "template_variables":
            if prefix:
                keys.add(str(prefix))
            if key:
                keys.add(str(key))
        elif yml_location == "top_level":
            if prefix:
                prefix_text = str(prefix)
                keys.add(prefix_text)
                if prefix_text.startswith("top_level_"):
                    keys.add(prefix_text[len("top_level_") :])
            if key:
                keys.add(str(key))
    return keys


def build_qs_global_supported_keys(qs_attributes_path: Path) -> set[str]:
    return build_qs_library_template_keys(qs_attributes_path) | set(QS_SPECIAL_GLOBAL_SUPPORTED_KEYS) | set(QS_SPECIAL_PLAYLIST_SUPPORTED_KEYS)


def build_qs_playlist_supported_keys(qs_attributes_path: Path) -> set[str]:
    keys = set(QS_SPECIAL_PLAYLIST_SUPPORTED_KEYS)
    keys.update(build_qs_global_supported_keys(qs_attributes_path))
    return keys


def build_schema_key_set(schema_path: Path) -> set[str]:
    data = load_json(schema_path)
    keys: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for key, value in properties.items():
                    keys.add(str(key))
                    walk(value)
            pattern_properties = node.get("patternProperties")
            if isinstance(pattern_properties, dict):
                for key, value in pattern_properties.items():
                    keys.add(str(key))
                    walk(value)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return keys


def resolve_default_paths(alias: str, kind: str, kometa_defaults: Path) -> list[Path]:
    support_files: list[Path] = []
    if kind == "overlay":
        path = kometa_defaults / "overlays" / f"{alias}.yml"
        if path.exists():
            support_files.append(path)
        return support_files
    if kind == "playlist":
        path = kometa_defaults / "playlist.yml"
        if path.exists():
            support_files.append(path)
        return support_files
    matches = sorted(kometa_defaults.rglob(f"{alias}.yml"))
    support_files.extend([p for p in matches if p.is_file()])
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in support_files:
        if path in seen:
            continue
        deduped.append(path)
        seen.add(path)
    return deduped


KEY_RE = re.compile(r"^\s*([A-Za-z0-9_<>-]+(?:\.[A-Za-z0-9_<>-]+)?)\s*:\s*(?:.*)?$")
LIST_RE = re.compile(r"^\s*-\s+([A-Za-z0-9_<>-]+(?:\.[A-Za-z0-9_<>-]+)?)\s*$")
PLACEHOLDER_RE = re.compile(r"<<[^>]+>>")

RESERVED = {
    "external_templates",
    "templates",
    "collections",
    "overlays",
    "playlists",
    "default",
    "optional",
    "conditionals",
    "conditions",
    "variables",
    "template",
    "value",
    "key",
    "type",
    "group",
    "run_definition",
    "allowed_libraries",
    "mapping_name",
    "mapping_name_encoded",
    "search",
    "filters",
    "plex_search",
    "plex_all",
    "ignore_blank_results",
    "validate",
    "all",
    "any",
    "name",
    "summary",
}


def kometa_defaults_root_for(path: Path) -> Path:
    for candidate in [path.parent, *path.parents]:
        if candidate.name == "defaults":
            return candidate
    return path.parent


def extract_template_names(raw: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(raw, str):
        token = raw.strip()
        if token:
            names.add(token)
    elif isinstance(raw, dict):
        name = raw.get("name")
        if name:
            names.add(str(name))
    elif isinstance(raw, list):
        for item in raw:
            names.update(extract_template_names(item))
    return names


@lru_cache(maxsize=None)
def load_template_sections(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    parsed = load_yaml(path) or {}
    local_templates = parsed.get("templates") if isinstance(parsed, dict) else {}
    if not isinstance(local_templates, dict):
        local_templates = {}

    shared_templates: dict[str, dict[str, Any]] = {}
    if not isinstance(parsed, dict):
        return parsed, shared_templates

    defaults_root = kometa_defaults_root_for(path)
    external_templates = parsed.get("external_templates")
    template_defaults: list[str] = []
    if isinstance(external_templates, dict):
        external_default = external_templates.get("default")
        if isinstance(external_default, str):
            template_defaults.append(external_default)
        elif isinstance(external_default, list):
            template_defaults.extend(str(item) for item in external_default if item)

    for template_default in template_defaults:
        template_path = defaults_root / f"{template_default}.yml"
        if not template_path.exists():
            continue
        shared_parsed = load_yaml(template_path) or {}
        shared_section = shared_parsed.get("templates") if isinstance(shared_parsed, dict) else {}
        if isinstance(shared_section, dict):
            for template_name, template_cfg in shared_section.items():
                shared_templates[str(template_name)] = template_cfg

    return parsed, shared_templates


def _collect_template_patterns(
    template_name: str,
    local_templates: dict[str, Any],
    shared_templates: dict[str, dict[str, Any]],
    seen: set[str] | None = None,
) -> set[str]:
    if seen is None:
        seen = set()
    if template_name in seen:
        return set()
    seen.add(template_name)

    template_cfg = local_templates.get(template_name)
    if template_cfg is None:
        template_cfg = shared_templates.get(template_name)
    if not isinstance(template_cfg, dict):
        return set()

    patterns = collect_declared_yaml_patterns(template_cfg)
    for nested_template in extract_template_names(template_cfg.get("template")):
        patterns.update(_collect_template_patterns(nested_template, local_templates, shared_templates, seen))
    return patterns


@lru_cache(maxsize=None)
def patterns_from_default_file(path: Path) -> set[str]:
    try:
        parsed, shared_templates = load_template_sections(path)
    except Exception:
        parsed = None
        shared_templates = {}
    if isinstance(parsed, dict):
        patterns: set[str] = set()
        external_templates = parsed.get("external_templates")
        if isinstance(external_templates, dict):
            template_variables = external_templates.get("template_variables")
            patterns.update(collect_declared_yaml_patterns(template_variables))

        local_templates = parsed.get("templates")
        if not isinstance(local_templates, dict):
            local_templates = {}

        for section_name in ("collections", "dynamic_collections", "overlays", "playlists"):
            section = parsed.get(section_name)
            if not isinstance(section, dict):
                continue
            for entry_cfg in section.values():
                if not isinstance(entry_cfg, dict):
                    continue
                patterns.update(collect_declared_yaml_patterns(entry_cfg))
                for template_name in extract_template_names(entry_cfg.get("template")):
                    patterns.update(_collect_template_patterns(template_name, local_templates, shared_templates))
        return patterns

    patterns = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        km = KEY_RE.match(line)
        lm = LIST_RE.match(line)
        token = None
        if km:
            token = km.group(1)
        elif lm:
            token = lm.group(1)
        if not token or token in RESERVED:
            continue
        patterns.add(token)
        if token.endswith(".exists"):
            patterns.add(token[: -len(".exists")])
    return patterns


def key_matches_pattern(key: str, pattern: str) -> bool:
    if key == pattern:
        return True
    literal_pattern = PLACEHOLDER_RE.sub("", pattern)
    if not re.search(r"[A-Za-z0-9_.-]", literal_pattern):
        return False
    regex = "^" + PLACEHOLDER_RE.sub(lambda _: r"[^:\s]+", re.escape(pattern)) + "$"
    return re.match(regex, key) is not None


def key_is_valid_for_default(key: str, default_files: list[Path]) -> tuple[bool, list[Path]]:
    matched: list[Path] = []
    for path in default_files:
        for pattern in patterns_from_default_file(path):
            if key_matches_pattern(key, pattern):
                matched.append(path)
                break
    return bool(matched), matched


def classify_validation_level(
    quickstart_supported: bool,
    schema_declared: bool,
    kometa_declared: bool,
) -> str:
    if quickstart_supported:
        return "supported_in_quickstart"
    if kometa_declared and schema_declared:
        return "works_in_kometa_missing_from_quickstart"
    if kometa_declared and not schema_declared:
        return "works_in_kometa_missing_from_quickstart_and_schema"
    if schema_declared and not kometa_declared:
        return "schema_declared_not_confirmed_in_kometa_defaults"
    return "unverified"


BOOL_PREFIXES = (
    "use_",
    "build_",
    "remove_",
    "delete_",
    "create_",
    "save_",
    "show_",
)
BOOL_EXACT = {
    "custom_keys",
    "sync",
    "test",
}
NUMERIC_HINTS = {
    "horizontal_offset",
    "vertical_offset",
    "back_width",
    "back_height",
    "back_padding",
    "back_radius",
    "back_line_width",
    "font_size",
    "stroke_width",
    "weight",
    "overlay_limit",
    "minimum_items",
    "data_increment",
}
LIST_HINTS = {
    "libraries",
    "languages",
    "exclude",
    "include",
    "append_exclude",
    "append_include",
    "remove_exclude",
    "remove_include",
}
STRING_HINTS = {
    "file",
    "text",
    "final_name",
    "horizontal_align",
    "vertical_align",
    "horizontal_position",
    "vertical_position",
    "style",
    "collection_mode",
    "sync_mode",
    "back_align",
    "back_color",
    "back_line_color",
    "font",
    "font_color",
    "stroke_color",
    "language",
}
URLISH_PREFIXES = (
    "trakt_list_",
    "imdb_list_",
    "mdblist_list_",
    "url_",
    "git_",
    "repo_",
    "file_",
)


def infer_value_shape(value: Any, key: str) -> tuple[bool | None, str]:
    if key in BOOL_EXACT or key.startswith(BOOL_PREFIXES):
        return isinstance(value, bool), "bool"
    if key in NUMERIC_HINTS:
        return isinstance(value, (int, float)) and not isinstance(value, bool), "number"
    if key in LIST_HINTS:
        if isinstance(value, list):
            return True, "list"
        if isinstance(value, str):
            return True, "string_or_list"
        return False, "string_or_list"
    if key in STRING_HINTS or key.startswith(URLISH_PREFIXES):
        return isinstance(value, str), "string"
    if key.startswith(("data_", "summary_", "name_")):
        return isinstance(value, (str, int, float, bool, list, dict)), "dynamic"
    return None, "unknown"


def normalize_nested_template_key(key: str, value: Any) -> list[tuple[str, Any]]:
    if key == "data" and isinstance(value, dict):
        return [(f"data_{subkey}", subvalue) for subkey, subvalue in value.items()]
    return [(key, value)]


def extract_findings_from_data(data: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    libraries = data.get("libraries")
    if isinstance(libraries, dict):
        for library_name, lib_cfg in libraries.items():
            if not isinstance(lib_cfg, dict):
                continue
            tv = lib_cfg.get("template_variables")
            if isinstance(tv, dict):
                for raw_key, raw_value in tv.items():
                    for key, value in normalize_nested_template_key(str(raw_key), raw_value):
                        findings.append(
                            {
                                "file": str(path),
                                "library": str(library_name),
                                "section": "library_template_variables",
                                "default": None,
                                "kind": "library",
                                "key": key,
                                "value": value,
                            }
                        )
            for section_name, kind in (("collection_files", "collection"), ("overlay_files", "overlay")):
                entries = lib_cfg.get(section_name)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    alias = entry.get("default")
                    tv = entry.get("template_variables")
                    if not alias or not isinstance(tv, dict):
                        continue
                    for raw_key, raw_value in tv.items():
                        for key, value in normalize_nested_template_key(str(raw_key), raw_value):
                            findings.append(
                                {
                                    "file": str(path),
                                    "library": str(library_name),
                                    "section": section_name,
                                    "default": str(alias),
                                    "kind": kind,
                                    "key": key,
                                    "value": value,
                                }
                            )
    playlist_files = data.get("playlist_files")
    if isinstance(playlist_files, list):
        for entry in playlist_files:
            if not isinstance(entry, dict):
                continue
            alias = entry.get("default")
            tv = entry.get("template_variables")
            if not alias or not isinstance(tv, dict):
                continue
            for raw_key, raw_value in tv.items():
                for key, value in normalize_nested_template_key(str(raw_key), raw_value):
                    findings.append(
                        {
                            "file": str(path),
                            "library": None,
                            "section": "playlist_files",
                            "default": str(alias),
                            "kind": "playlist",
                            "key": key,
                            "value": raw_value,
                        }
                    )
    return findings


def classify_importer_reason(reason: str | None) -> str:
    if not reason:
        return "unknown"
    lowered = reason.strip().lower()
    if "template variable not available in quickstart" in lowered:
        return "missing_template_variable_support"
    if "section not supported in quickstart" in lowered:
        return "unsupported_section"
    if "library type could not be determined" in lowered:
        return "library_type_unknown"
    if "unsupported" in lowered and "format" in lowered:
        return "unsupported_format"
    if "missing default" in lowered:
        return "missing_default"
    if "unsupported playlist default" in lowered:
        return "unsupported_default"
    if "missing playlist library entries" in lowered:
        return "missing_playlist_libraries"
    if "service override not supported for import" in lowered:
        return "unsupported_service_override"
    if "invalid boolean value" in lowered:
        return "invalid_boolean"
    if "override value is empty" in lowered:
        return "empty_override_value"
    if "unsupported override value format" in lowered:
        return "unsupported_override_value_format"
    if "no importable values found" in lowered:
        return "no_importable_values"
    if "radarr overrides are only supported on movie libraries" in lowered:
        return "radarr_wrong_library_type"
    if "sonarr overrides are only supported on show libraries" in lowered:
        return "sonarr_wrong_library_type"
    if "warning - include and exclude were both imported" in lowered:
        return "include_exclude_warning"
    if "unsupported option" in lowered:
        return "unsupported_option"
    if "unsupported library entry" in lowered:
        return "unsupported_library_entry"
    if "unsupported mass update" in lowered:
        return "unsupported_mass_update"
    if "custom values are not supported" in lowered:
        return "custom_values_unsupported"
    return "other"


def _split_library_status_path(status_path: str, libraries_payload: dict[str, Any]) -> tuple[str | None, str]:
    if not status_path.startswith("libraries."):
        return None, status_path
    remainder = status_path[len("libraries.") :]
    for lib_name in sorted((str(name) for name in libraries_payload.keys()), key=len, reverse=True):
        if remainder == lib_name:
            return lib_name, ""
        prefix = f"{lib_name}."
        if remainder.startswith(prefix):
            return lib_name, remainder[len(prefix) :]
    return None, remainder


def _lookup_indexed_entry(lib_cfg: dict[str, Any], section_name: str, index_text: str) -> dict[str, Any] | None:
    entries = lib_cfg.get(section_name)
    if not isinstance(entries, list):
        return None
    try:
        index = int(index_text)
    except (TypeError, ValueError):
        return None
    if index < 0 or index >= len(entries):
        return None
    entry = entries[index]
    return entry if isinstance(entry, dict) else None


def _normalize_importer_template_key(path_tail: str) -> str:
    if path_tail.startswith("template_variables."):
        key = path_tail[len("template_variables.") :]
        if key.startswith("data."):
            return f"data_{key[len('data.') :]}"
        return key
    return path_tail or "entry"


def infer_analyzer_library_type_overrides(config_data: dict[str, Any]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    libraries_payload = config_data.get("libraries")
    if not isinstance(libraries_payload, dict):
        return overrides
    for raw_name in libraries_payload.keys():
        name = str(raw_name).strip().lower()
        if any(token in name for token in ("movie", "movies", "film", "films", "cinema")):
            overrides[str(raw_name)] = "movie"
        elif any(token in name for token in ("show", "shows", "series", "tv", "anime", "season", "episode")):
            overrides[str(raw_name)] = "show"
    return overrides


def _importer_row(
    *,
    file: Path,
    kind: str,
    key: str,
    status: str,
    reason: str | None,
    raw_path: str,
    default: str | None = None,
    library: str | None = None,
    section: str | None = None,
    detail_key: str | None = None,
) -> dict[str, Any]:
    return {
        "file": str(file),
        "library": library,
        "section": section,
        "default": default,
        "kind": kind,
        "key": key,
        "detail_key": detail_key or key,
        "import_status": status,
        "import_reason": reason,
        "reason_class": classify_importer_reason(reason),
        "raw_path": raw_path,
        "source": "importer",
    }


def extract_importer_findings_from_data(data: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return findings

    analyzer_overrides = infer_analyzer_library_type_overrides(data)
    payload, report = importer.prepare_import_payload(data, set(), set(), library_type_overrides=analyzer_overrides or None)
    _ = payload
    status_map, reason_map = importer._parse_report_details(report.lines)
    libraries_payload = data.get("libraries") if isinstance(data.get("libraries"), dict) else {}

    for status_path, mapped_status in status_map.items():
        if mapped_status == "mapped":
            continue
        reason = reason_map.get(status_path)

        if status_path.startswith("playlist_files["):
            match = re.match(r"playlist_files\[(\d+)\](?:\.(.*))?$", status_path)
            if match:
                index_text, tail = match.groups()
                playlist_files = data.get("playlist_files")
                entry = None
                if isinstance(playlist_files, list):
                    try:
                        idx = int(index_text)
                    except (TypeError, ValueError):
                        idx = -1
                    if 0 <= idx < len(playlist_files) and isinstance(playlist_files[idx], dict):
                        entry = playlist_files[idx]
                alias = str(entry.get("default")) if isinstance(entry, dict) and entry.get("default") else None
                key = _normalize_importer_template_key(tail or "")
                findings.append(
                    _importer_row(
                        file=path,
                        kind="playlist",
                        default=alias,
                        key=key,
                        detail_key=tail or key,
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section="playlist_files",
                    )
                )
                continue

        if status_path == "playlist_files":
            findings.append(
                _importer_row(
                    file=path,
                    kind="playlist",
                    key="playlist_files",
                    status=mapped_status,
                    reason=reason,
                    raw_path=status_path,
                    section="playlist_files",
                )
            )
            continue

        if status_path.startswith("libraries."):
            lib_name, remainder = _split_library_status_path(status_path, libraries_payload if isinstance(libraries_payload, dict) else {})
            lib_cfg = libraries_payload.get(lib_name) if lib_name and isinstance(libraries_payload, dict) else None
            if not remainder:
                findings.append(
                    _importer_row(
                        file=path,
                        kind="library",
                        library=lib_name,
                        key="library_type",
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section="libraries",
                    )
                )
                continue

            section_match = re.match(r"(collection_files|overlay_files)\[(\d+)\](?:\.(.*))?$", remainder)
            if section_match and isinstance(lib_cfg, dict):
                section_name, index_text, tail = section_match.groups()
                entry = _lookup_indexed_entry(lib_cfg, section_name, index_text)
                alias = str(entry.get("default")) if isinstance(entry, dict) and entry.get("default") else None
                kind = "collection" if section_name == "collection_files" else "overlay"
                key = _normalize_importer_template_key(tail or "")
                findings.append(
                    _importer_row(
                        file=path,
                        kind=kind,
                        library=lib_name,
                        default=alias,
                        key=key,
                        detail_key=tail or key,
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section=section_name,
                    )
                )
                continue

            if remainder in {"collection_files", "overlay_files", "metadata_files", "settings", "operations", "radarr", "sonarr"}:
                findings.append(
                    _importer_row(
                        file=path,
                        kind="library",
                        library=lib_name,
                        key=remainder,
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section=remainder,
                    )
                )
                continue

            if remainder.startswith("template_variables."):
                key = _normalize_importer_template_key(remainder)
                findings.append(
                    _importer_row(
                        file=path,
                        kind="library",
                        library=lib_name,
                        key=key,
                        detail_key=remainder,
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section="library_template_variables",
                    )
                )
                continue

            if remainder.startswith(("settings.", "radarr.", "sonarr.")):
                key = remainder.split(".", 1)[1] if "." in remainder else remainder
                findings.append(
                    _importer_row(
                        file=path,
                        kind="library",
                        library=lib_name,
                        key=key,
                        detail_key=remainder,
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section=remainder.split(".", 1)[0],
                    )
                )
                continue

            if remainder.startswith("operations."):
                op_tail = remainder[len("operations.") :]
                op_parts = op_tail.split(".") if op_tail else []
                if len(op_parts) >= 2:
                    key = f"operations.{op_parts[-1]}"
                elif op_parts:
                    key = f"operations.{op_parts[0]}"
                else:
                    key = "operations"
                findings.append(
                    _importer_row(
                        file=path,
                        kind="library",
                        library=lib_name,
                        key=key,
                        detail_key=remainder,
                        status=mapped_status,
                        reason=reason,
                        raw_path=status_path,
                        section="operations",
                    )
                )
                continue

            findings.append(
                _importer_row(
                    file=path,
                    kind="library",
                    library=lib_name,
                    key=remainder,
                    detail_key=remainder,
                    status=mapped_status,
                    reason=reason,
                    raw_path=status_path,
                    section="libraries",
                )
            )
            continue

        findings.append(
            _importer_row(
                file=path,
                kind="section",
                key=status_path,
                status=mapped_status,
                reason=reason,
                raw_path=status_path,
                section="top_level",
            )
        )

    return findings


def is_yaml_path(path: Path) -> bool:
    return path.suffix.lower() in YAML_SUFFIXES


def classify_archive_type(path: Path) -> str | None:
    lower_name = path.name.lower()
    if lower_name.endswith(".tar.gz") or lower_name.endswith(".tgz"):
        return "targz"
    if lower_name.endswith(".tar"):
        return "tar"
    if lower_name.endswith(".zip"):
        return "zip"
    if lower_name.endswith(".7z"):
        return "7z"
    if lower_name.endswith(".gz"):
        return "gz"
    return None


def archive_type_is_supported(archive_type: str) -> bool:
    if archive_type == "7z" and py7zr is None:
        return False
    return archive_type in {"zip", "tar", "targz", "gz", "7z"}


def build_archive_cache_key(path: Path, archive_type: str) -> str:
    signature = file_signature(path)
    digest = hashlib.sha256()
    digest.update(str(path.resolve()).encode("utf-8"))
    digest.update(archive_type.encode("utf-8"))
    digest.update(str(signature["size"]).encode("utf-8"))
    digest.update(str(signature["mtime_ns"]).encode("utf-8"))
    return digest.hexdigest()


def load_archive_cache_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = load_json(path)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def build_archive_manifest(archive_type: str, extracted_path: Path, base_dir: Path) -> dict[str, Any]:
    return {
        "version": ARCHIVE_CACHE_VERSION,
        "archive_type": archive_type,
        "relative_output": str(extracted_path.relative_to(base_dir)),
        "is_dir": extracted_path.is_dir(),
    }


def resolve_cached_archive_output(entry_dir: Path) -> Path | None:
    manifest = load_archive_cache_manifest(entry_dir / "_archive_manifest.json")
    if not manifest:
        return None
    if manifest.get("version") != ARCHIVE_CACHE_VERSION:
        return None
    relative_output = manifest.get("relative_output")
    if not isinstance(relative_output, str) or not relative_output:
        return None
    output_path = entry_dir / relative_output
    if not output_path.exists():
        return None
    return output_path


def prepare_archive_extraction_target(
    path: Path,
    archive_type: str,
    temp_dirs: list[tempfile.TemporaryDirectory],
    archive_cache_dir: Path | None,
) -> tuple[Path, Path | None, Path | None]:
    if archive_cache_dir is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="qs_template_gap_")
        temp_dirs.append(temp_dir)
        extract_root = Path(temp_dir.name)
        return extract_root, None, None

    archive_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = build_archive_cache_key(path, archive_type)
    entry_dir = archive_cache_dir / cache_key
    cached_output = resolve_cached_archive_output(entry_dir)
    if cached_output is not None:
        return cached_output, entry_dir, None

    staging_dir = archive_cache_dir / f".{cache_key}.tmp-{os.getpid()}-{time.time_ns()}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    extract_root = staging_dir / "payload"
    extract_root.mkdir(parents=True, exist_ok=True)
    return extract_root, entry_dir, staging_dir


def finalize_archive_extraction(
    extracted_path: Path,
    archive_type: str,
    archive_cache_entry_dir: Path | None,
    staging_root: Path | None,
) -> Path:
    if archive_cache_entry_dir is None:
        return extracted_path

    if staging_root is None:
        raise RuntimeError(f"missing staging root for archive cache entry {archive_cache_entry_dir}")

    if archive_cache_entry_dir.exists():
        cached_output = resolve_cached_archive_output(archive_cache_entry_dir)
        if cached_output is not None:
            remove_tree(staging_root)
            return cached_output
        remove_tree(archive_cache_entry_dir)

    manifest = build_archive_manifest(archive_type, extracted_path, staging_root)
    write_text_atomic(staging_root / "_archive_manifest.json", json.dumps(manifest, indent=2, default=json_default))
    try:
        shutil.move(str(staging_root), str(archive_cache_entry_dir))
    except (PermissionError, OSError):
        if archive_cache_entry_dir.exists():
            remove_tree(archive_cache_entry_dir)
        archive_cache_entry_dir.mkdir(parents=True, exist_ok=True)
        for child in staging_root.iterdir():
            target = archive_cache_entry_dir / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
            else:
                shutil.copy2(child, target)
        remove_tree(staging_root)
    cached_output = resolve_cached_archive_output(archive_cache_entry_dir)
    if cached_output is None:
        raise RuntimeError(f"archive cache finalize failed for {archive_cache_entry_dir}")
    return cached_output


def extract_archive(
    path: Path,
    archive_type: str,
    temp_dirs: list[tempfile.TemporaryDirectory],
    archive_cache_dir: Path | None = None,
) -> Path:
    prepared_path, archive_cache_entry_dir, staging_root = prepare_archive_extraction_target(path, archive_type, temp_dirs, archive_cache_dir)
    if archive_cache_entry_dir is not None and prepared_path.exists():
        maybe_cached = resolve_cached_archive_output(archive_cache_entry_dir)
        if maybe_cached is not None:
            return maybe_cached
    extract_root = prepared_path

    if archive_type == "zip":
        with zipfile.ZipFile(path) as zf:
            zf.extractall(extract_root)
        return finalize_archive_extraction(extract_root, archive_type, archive_cache_entry_dir, staging_root)

    if archive_type in {"tar", "targz"}:
        with tarfile.open(path, mode="r:*") as tf:
            extract_kwargs: dict[str, Any] = {}
            if "filter" in tarfile.TarFile.extractall.__code__.co_varnames:
                extract_kwargs["filter"] = "data"
            tf.extractall(extract_root, **extract_kwargs)
        return finalize_archive_extraction(extract_root, archive_type, archive_cache_entry_dir, staging_root)

    if archive_type == "7z":
        if py7zr is None:
            raise RuntimeError("7z archive support requires the optional py7zr dependency")
        with py7zr.SevenZipFile(path, mode="r") as zf:
            zf.extractall(path=extract_root)
        return finalize_archive_extraction(extract_root, archive_type, archive_cache_entry_dir, staging_root)

    if archive_type == "gz":
        output_name = path.name[:-3] if path.name.lower().endswith(".gz") else path.stem
        output_path = extract_root / output_name
        with gzip.open(path, "rb") as source_handle, output_path.open("wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
        return finalize_archive_extraction(output_path, archive_type, archive_cache_entry_dir, staging_root)

    raise ValueError(f"Unsupported archive type {archive_type} for {path}")


def append_yaml_path(yaml_files: list[Path], seen_yaml_paths: set[str], path: Path) -> None:
    key = str(path)
    if key in seen_yaml_paths:
        return
    seen_yaml_paths.add(key)
    yaml_files.append(path)


def walk_for_yaml_and_archives(
    root_path: Path,
    walk_base: Path,
    yaml_files: list[Path],
    temp_dirs: list[tempfile.TemporaryDirectory],
    include_archives: bool,
    archive_cache_dir: Path | None,
    seen_yaml_paths: set[str],
    seen_archive_paths: set[str],
    discovery_callback=None,
    exclude_defaults: bool = True,
) -> None:
    for current_root, dirnames, filenames in os.walk(root_path, topdown=True):
        current_path = Path(current_root)
        if should_exclude_directory(current_path, walk_base, enabled=exclude_defaults):
            dirnames[:] = []
            continue
        dirnames[:] = [dirname for dirname in dirnames if not should_exclude_directory(current_path / dirname, walk_base, enabled=exclude_defaults)]
        if discovery_callback:
            discovery_callback("dir", current_path, len(yaml_files))
        for filename in filenames:
            candidate_path = current_path / filename
            if is_yaml_path(candidate_path):
                append_yaml_path(yaml_files, seen_yaml_paths, candidate_path)
                continue
            archive_type = classify_archive_type(candidate_path)
            if archive_type:
                collect_supported_file(
                    candidate_path,
                    yaml_files,
                    temp_dirs,
                    include_archives,
                    archive_cache_dir,
                    seen_yaml_paths,
                    seen_archive_paths,
                    discovery_callback=discovery_callback,
                    exclude_defaults=exclude_defaults,
                )


def collect_supported_file(
    input_path: Path,
    yaml_files: list[Path],
    temp_dirs: list[tempfile.TemporaryDirectory],
    include_archives: bool,
    archive_cache_dir: Path | None,
    seen_yaml_paths: set[str],
    seen_archive_paths: set[str],
    discovery_callback=None,
    exclude_defaults: bool = True,
    allow_unsupported_file: bool = False,
) -> None:
    if input_path.is_dir():
        if discovery_callback:
            discovery_callback("root", input_path, len(yaml_files))
        walk_for_yaml_and_archives(
            input_path,
            input_path,
            yaml_files,
            temp_dirs,
            include_archives,
            archive_cache_dir,
            seen_yaml_paths,
            seen_archive_paths,
            discovery_callback=discovery_callback,
            exclude_defaults=exclude_defaults,
        )
        if discovery_callback:
            discovery_callback("root_done", input_path, len(yaml_files))
        return

    if input_path.is_file() and is_yaml_path(input_path):
        append_yaml_path(yaml_files, seen_yaml_paths, input_path)
        return

    if input_path.is_file():
        archive_type = classify_archive_type(input_path)
        if archive_type is None:
            if allow_unsupported_file:
                return
            raise FileNotFoundError(f"Unsupported input path: {input_path}")
        if not include_archives:
            if discovery_callback:
                discovery_callback("archive_skipped", input_path, len(yaml_files))
            return
        if not archive_type_is_supported(archive_type):
            if discovery_callback:
                discovery_callback("archive_unsupported", input_path, len(yaml_files))
            return
        archive_key = str(input_path.resolve())
        if archive_key in seen_archive_paths:
            return
        seen_archive_paths.add(archive_key)
        if discovery_callback:
            discovery_callback("archive", input_path, len(yaml_files))
        extracted_path = extract_archive(input_path, archive_type, temp_dirs, archive_cache_dir=archive_cache_dir)
        if extracted_path.is_dir():
            walk_for_yaml_and_archives(
                extracted_path,
                extracted_path,
                yaml_files,
                temp_dirs,
                include_archives,
                archive_cache_dir,
                seen_yaml_paths,
                seen_archive_paths,
                discovery_callback=discovery_callback,
                exclude_defaults=exclude_defaults,
            )
        else:
            collect_supported_file(
                extracted_path,
                yaml_files,
                temp_dirs,
                include_archives,
                archive_cache_dir,
                seen_yaml_paths,
                seen_archive_paths,
                discovery_callback=discovery_callback,
                exclude_defaults=exclude_defaults,
                allow_unsupported_file=True,
            )
        return

    raise FileNotFoundError(f"Unsupported input path: {input_path}")


def collect_yaml_files(
    inputs: list[Path],
    discovery_callback=None,
    exclude_defaults: bool = True,
    include_archives: bool = False,
    archive_cache_dir: Path | None = None,
) -> tuple[list[Path], list[tempfile.TemporaryDirectory]]:
    yaml_files: list[Path] = []
    temp_dirs: list[tempfile.TemporaryDirectory] = []
    seen_yaml_paths: set[str] = set()
    seen_archive_paths: set[str] = set()
    for input_path in inputs:
        collect_supported_file(
            input_path,
            yaml_files,
            temp_dirs,
            include_archives,
            archive_cache_dir,
            seen_yaml_paths,
            seen_archive_paths,
            discovery_callback=discovery_callback,
            exclude_defaults=exclude_defaults,
        )
    return sorted(yaml_files), temp_dirs


def prefilter_yaml_files(
    input_files: list[Path],
    yaml_type_focus: str = "config",
    cache_data: dict[str, Any] | None = None,
    progress_callback=None,
    checkpoint_callback=None,
) -> tuple[list[Path], list[dict[str, str]], dict[str, int]]:
    candidate_files: list[Path] = []
    skipped_files: list[dict[str, str]] = []
    stats = {"cache_hits": 0, "cache_misses": 0, "decode_fallbacks": 0, "artifact_skips": 0, "non_kometa_skips": 0}
    files_cache = cache_data.get("files", {}) if isinstance(cache_data, dict) else {}
    total_files = len(input_files)
    for idx, path in enumerate(input_files, start=1):
        cache_key = str(path)
        signature = safe_file_signature(path)
        if signature is None:
            skip_record = {
                "file": str(path),
                "error_type": "FileNotFoundError",
                "reason": "file disappeared before prefilter could inspect it",
                "detail": f"FileNotFoundError: {path}",
                "stage": "prefilter",
            }
            skipped_files.append(skip_record)
            if isinstance(files_cache, dict):
                files_cache.pop(cache_key, None)
            if progress_callback:
                progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        cached = files_cache.get(cache_key) if isinstance(files_cache, dict) else None
        if isinstance(cached, dict) and cached.get("signature") == signature and "contains_relevant_yaml" in cached:
            stats["cache_hits"] += 1
            if cached.get("prefilter_skip"):
                skipped_files.append(dict(cached["prefilter_skip"]))
                if progress_callback:
                    progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
                if checkpoint_callback:
                    checkpoint_callback(idx, total_files)
                continue
            if cached.get("contains_relevant_yaml"):
                candidate_files.append(path)
            if progress_callback:
                progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        stats["cache_misses"] += 1
        try:
            raw_text, encoding_used = read_text_with_fallbacks(path)
        except Exception as exc:
            skip_record = {
                "file": str(path),
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "detail": f"{type(exc).__name__}: {exc}",
                "stage": "prefilter",
            }
            skipped_files.append(skip_record)
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {"signature": signature, "prefilter_skip": skip_record, "contains_relevant_yaml": False}
            if progress_callback:
                progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        if encoding_used not in {"utf-8", "utf-8-sig"}:
            stats["decode_fallbacks"] += 1
        contains_relevant_yaml = (
            "template_variables" in raw_text or looks_like_kometa_config_text(raw_text) or any(f"{marker}:" in raw_text for marker in EXTERNAL_TOP_LEVEL_MARKERS)
        )
        if not contains_relevant_yaml:
            if is_probable_non_config_artifact(path):
                skip_record = {
                    "file": str(path),
                    "error_type": "IgnoredArtifact",
                    "reason": "probable extracted log or message artifact",
                    "detail": f"IgnoredArtifact: {path.name}",
                    "stage": "prefilter",
                    "noise": True,
                    "noise_reason": "artifact_filename_heuristic",
                }
                skipped_files.append(skip_record)
                stats["artifact_skips"] += 1
                if isinstance(files_cache, dict):
                    files_cache[cache_key] = {"signature": signature, "prefilter_skip": skip_record, "contains_relevant_yaml": False}
                if progress_callback:
                    progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
                if checkpoint_callback:
                    checkpoint_callback(idx, total_files)
                continue
            skip_record = {
                "file": str(path),
                "error_type": "NotKometaConfig",
                "reason": "did not look like a Kometa config and had no template_variables",
                "detail": f"NotKometaConfig: {path.name}",
                "stage": "prefilter",
                "noise": True,
                "noise_reason": "non_kometa_content",
            }
            skipped_files.append(skip_record)
            stats["non_kometa_skips"] += 1
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {"signature": signature, "prefilter_skip": skip_record, "contains_relevant_yaml": False}
            if progress_callback:
                progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        if isinstance(files_cache, dict):
            files_cache[cache_key] = {"signature": signature, "contains_relevant_yaml": contains_relevant_yaml}
        if contains_relevant_yaml:
            candidate_files.append(path)
        if progress_callback:
            progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
        if checkpoint_callback:
            checkpoint_callback(idx, total_files)
    return candidate_files, skipped_files, stats


def scan_uploaded_configs(
    input_files: list[Path],
    yaml_type_focus: str = "config",
    progress_callback=None,
    cache_data: dict[str, Any] | None = None,
    checkpoint_callback=None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], list[str], dict[str, int]]:
    findings: list[dict[str, Any]] = []
    importer_findings: list[dict[str, Any]] = []
    skipped_files: list[dict[str, str]] = []
    parsed_file_paths: list[str] = []
    parsed_count = 0
    total_files = len(input_files)
    stats = {"cache_hits": 0, "cache_misses": 0, "decode_fallbacks": 0, "type_excluded": 0}
    files_cache = cache_data.get("files", {}) if isinstance(cache_data, dict) else {}
    for idx, path in enumerate(input_files, start=1):
        cache_key = str(path)
        signature = safe_file_signature(path)
        if signature is None:
            skip_record = {
                "file": str(path),
                "error_type": "FileNotFoundError",
                "reason": "file disappeared before parse could inspect it",
                "detail": f"FileNotFoundError: {path}",
                "stage": "parse",
            }
            skipped_files.append(skip_record)
            if isinstance(files_cache, dict):
                files_cache.pop(cache_key, None)
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        cached = files_cache.get(cache_key) if isinstance(files_cache, dict) else None
        if isinstance(cached, dict) and cached.get("signature") == signature and cached.get("yaml_type_focus") == yaml_type_focus and "scan_result" in cached:
            stats["cache_hits"] += 1
            scan_result = cached["scan_result"]
            if scan_result.get("status") == "skip":
                skipped_files.append(dict(scan_result["skip_record"]))
                if progress_callback:
                    progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
                continue
            parsed_file_paths.append(str(path))
            parsed_count += 1
            findings.extend(scan_result.get("findings", []))
            importer_findings.extend(scan_result.get("importer_findings", []))
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        stats["cache_misses"] += 1
        try:
            data, encoding_used = load_yaml(path)
        except ReusedAnchorWarning as exc:
            skip_record = {
                "file": str(path),
                "error_type": "DuplicateYamlAnchor",
                "reason": "duplicate YAML anchor",
                "detail": str(exc),
                "stage": "parse",
                "malformed": True,
                "malformed_reason": "duplicate_yaml_anchor",
            }
            skipped_files.append(skip_record)
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {
                    "signature": signature,
                    "contains_relevant_yaml": True,
                    "yaml_type_focus": yaml_type_focus,
                    "scan_result": {"status": "skip", "skip_record": skip_record},
                }
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        except Exception as exc:
            skip_record = {
                "file": str(path),
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "detail": f"{type(exc).__name__}: {exc}",
                "stage": "parse",
            }
            skipped_files.append(skip_record)
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {
                    "signature": signature,
                    "contains_relevant_yaml": True,
                    "yaml_type_focus": yaml_type_focus,
                    "scan_result": {"status": "skip", "skip_record": skip_record},
                }
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        if encoding_used not in {"utf-8", "utf-8-sig"}:
            stats["decode_fallbacks"] += 1
        document_type = classify_yaml_document_type(data)
        if not yaml_type_matches_focus(document_type, yaml_type_focus):
            skip_record = {
                "file": str(path),
                "error_type": "YamlTypeExcluded",
                "reason": f"document type {document_type} excluded by yaml_type focus {yaml_type_focus}",
                "detail": f"YamlTypeExcluded: {document_type}",
                "stage": "parse",
                "yaml_document_type": document_type,
                "noise": True,
                "noise_reason": "yaml_type_excluded",
            }
            skipped_files.append(skip_record)
            stats["type_excluded"] += 1
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {
                    "signature": signature,
                    "contains_relevant_yaml": True,
                    "yaml_type_focus": yaml_type_focus,
                    "scan_result": {"status": "skip", "skip_record": skip_record},
                }
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        parsed_file_paths.append(str(path))
        if not isinstance(data, dict):
            parsed_count += 1
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {
                    "signature": signature,
                    "contains_relevant_yaml": True,
                    "yaml_type_focus": yaml_type_focus,
                    "scan_result": {"status": "ok", "findings": [], "importer_findings": []},
                }
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        file_findings = extract_findings_from_data(data, path)
        file_importer_findings = extract_importer_findings_from_data(data, path)
        findings.extend(file_findings)
        importer_findings.extend(file_importer_findings)
        parsed_count += 1
        if isinstance(files_cache, dict):
            files_cache[cache_key] = {
                "signature": signature,
                "contains_relevant_yaml": True,
                "yaml_type_focus": yaml_type_focus,
                "scan_result": {"status": "ok", "findings": file_findings, "importer_findings": file_importer_findings},
            }
        if progress_callback:
            progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
        if checkpoint_callback:
            checkpoint_callback(idx, total_files)
    return findings, importer_findings, skipped_files, parsed_file_paths, stats


def make_periodic_persistor(callback, every_items: int, every_seconds: float):
    state = {"last_index": 0, "last_time": time.monotonic()}

    def persist(index: int, total: int | None = None, force: bool = False) -> bool:
        now = time.monotonic()
        should_save = force
        if not should_save and total is not None and index >= total:
            should_save = True
        if not should_save and index - state["last_index"] >= every_items:
            should_save = True
        if not should_save and now - state["last_time"] >= every_seconds:
            should_save = True
        if not should_save:
            return False
        callback()
        state["last_index"] = index
        state["last_time"] = now
        return True

    return persist


def accumulate_gap_summary(summary: dict[tuple[str, str | None, str], dict[str, Any]], row: dict[str, Any]) -> None:
    if not row.get("name_verified") or row.get("supported_in_quickstart"):
        return
    accumulate_ranked_summary(summary, row)


def accumulate_ranked_summary(summary: dict[tuple[str, str | None, str], dict[str, Any]], row: dict[str, Any]) -> None:
    bucket = summary.setdefault(
        (str(row.get("kind")), row.get("default"), str(row.get("key"))),
        {
            "kind": row.get("kind"),
            "default": row.get("default"),
            "key": row.get("key"),
            "occurrences": 0,
            "files": set(),
            "libraries": set(),
            "matched_default_files": set(),
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": False,
            "validation_level": "",
            "value_shape_verified_occurrences": 0,
            "value_shape_unknown_occurrences": 0,
            "value_shape_rules": set(),
        },
    )
    bucket["occurrences"] += 1
    if row.get("file"):
        bucket["files"].add(row["file"])
    if row.get("library"):
        bucket["libraries"].add(row["library"])
    for item in row.get("matched_default_files", []):
        bucket["matched_default_files"].add(item)
    bucket["supported_in_quickstart"] = bucket["supported_in_quickstart"] or bool(row.get("supported_in_quickstart"))
    bucket["quickstart_declared"] = bucket["quickstart_declared"] or bool(row.get("quickstart_declared"))
    bucket["schema_declared"] = bucket["schema_declared"] or bool(row.get("schema_declared"))
    bucket["kometa_declared"] = bucket["kometa_declared"] or bool(row.get("kometa_declared"))
    bucket["validation_level"] = str(row.get("validation_level") or bucket["validation_level"])
    if row.get("value_shape_verified") is True:
        bucket["value_shape_verified_occurrences"] += 1
    elif row.get("value_shape_verified") is None:
        bucket["value_shape_unknown_occurrences"] += 1
    bucket["value_shape_rules"].add(row.get("value_shape_rule"))


def build_gap_summary(rows: list[dict[str, Any]]) -> dict[tuple[str, str | None, str], dict[str, Any]]:
    summary: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for row in rows:
        accumulate_gap_summary(summary, row)
    return summary


def accumulate_importer_summary(summary: dict[tuple[str, str | None, str, str, str], dict[str, Any]], row: dict[str, Any]) -> None:
    bucket = summary.setdefault(
        (
            str(row.get("kind")),
            row.get("default"),
            str(row.get("key")),
            str(row.get("import_status")),
            str(row.get("reason_class")),
        ),
        {
            "kind": row.get("kind"),
            "default": row.get("default"),
            "key": row.get("key"),
            "import_status": row.get("import_status"),
            "reason_class": row.get("reason_class"),
            "occurrences": 0,
            "files": set(),
            "libraries": set(),
            "sections": set(),
            "detail_keys": set(),
            "reasons": set(),
        },
    )
    bucket["occurrences"] += 1
    if row.get("file"):
        bucket["files"].add(row["file"])
    if row.get("library"):
        bucket["libraries"].add(row["library"])
    if row.get("section"):
        bucket["sections"].add(row["section"])
    if row.get("detail_key"):
        bucket["detail_keys"].add(row["detail_key"])
    if row.get("import_reason"):
        bucket["reasons"].add(row["import_reason"])


def build_importer_summary(rows: list[dict[str, Any]]) -> dict[tuple[str, str | None, str, str, str], dict[str, Any]]:
    summary: dict[tuple[str, str | None, str, str, str], dict[str, Any]] = {}
    for row in rows:
        accumulate_importer_summary(summary, row)
    return summary


QUICKSTART_RECOMMENDATION_EXCLUSIONS: dict[tuple[str, str], str] = {
    ("library", "metadata_path"): "legacy_library_path_key_not_recommended",
    ("library", "overlay_path"): "legacy_library_path_key_not_recommended",
    ("library", "reapply_overlays"): "valid_but_not_recommended_for_quickstart",
}


def get_quickstart_recommendation_exclusion(row: dict[str, Any]) -> str | None:
    kind = str(row.get("kind") or "")
    key = str(row.get("key") or "")
    return QUICKSTART_RECOMMENDATION_EXCLUSIONS.get((kind, key))


def accumulate_quickstart_recommendation_summary(summary: dict[tuple[str, str | None, str], dict[str, Any]], row: dict[str, Any]) -> None:
    if not row.get("name_verified") or row.get("quickstart_declared"):
        return
    if get_quickstart_recommendation_exclusion(row):
        return
    accumulate_ranked_summary(summary, row)


def build_quickstart_recommendation_summary(rows: list[dict[str, Any]]) -> dict[tuple[str, str | None, str], dict[str, Any]]:
    summary: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for row in rows:
        accumulate_quickstart_recommendation_summary(summary, row)
    return summary


def build_quickstart_recommendation_exclusion_summary(rows: list[dict[str, Any]]) -> dict[tuple[str, str | None, str], dict[str, Any]]:
    summary: dict[tuple[str, str | None, str], dict[str, Any]] = {}
    for row in rows:
        if not row.get("name_verified") or row.get("quickstart_declared"):
            continue
        exclusion_reason = get_quickstart_recommendation_exclusion(row)
        if not exclusion_reason:
            continue
        bucket = summary.setdefault(
            (str(row.get("kind") or ""), str(row.get("default") or ""), str(row.get("key") or "")),
            {
                "kind": str(row.get("kind") or ""),
                "default": row.get("default"),
                "key": str(row.get("key") or ""),
                "occurrences": 0,
                "file_count": 0,
                "files": set(),
                "libraries": set(),
                "reason": exclusion_reason,
            },
        )
        bucket["occurrences"] += 1
        if row.get("file"):
            bucket["files"].add(str(row["file"]))
        if row.get("library"):
            bucket["libraries"].add(str(row["library"]))
    for bucket in summary.values():
        bucket["file_count"] = len(bucket["files"])
        bucket["files"] = sorted(bucket["files"])
        bucket["libraries"] = sorted(bucket["libraries"])
    return summary


def serialize_ranked_summary(summary: dict[tuple[str, str | None, str], dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        summary.values(),
        key=lambda item: (-item["occurrences"], -len(item["files"]), str(item["default"]), str(item["key"])),
    )
    serializable_ranked: list[dict[str, Any]] = []
    for item in ranked:
        serializable_ranked.append(
            {
                "kind": item["kind"],
                "default": item["default"],
                "key": item["key"],
                "occurrences": item["occurrences"],
                "file_count": len(item["files"]),
                "files": sorted(item["files"]),
                "libraries": sorted(item["libraries"]),
                "matched_default_files": sorted(item["matched_default_files"]),
                "supported_in_quickstart": item["supported_in_quickstart"],
                "quickstart_declared": item["quickstart_declared"],
                "schema_declared": item["schema_declared"],
                "kometa_declared": item["kometa_declared"],
                "validation_level": item["validation_level"],
                "name_verified": True,
                "value_shape_verified_occurrences": item["value_shape_verified_occurrences"],
                "value_shape_unknown_occurrences": item["value_shape_unknown_occurrences"],
                "value_shape_rules": sorted(item["value_shape_rules"]),
                "runtime_guaranteed": False,
            }
        )
    return serializable_ranked


def serialize_importer_ranked_summary(summary: dict[tuple[str, str | None, str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        summary.values(),
        key=lambda item: (
            item["import_status"] != "unmapped",
            -item["occurrences"],
            -len(item["files"]),
            str(item["default"]),
            str(item["key"]),
        ),
    )
    serializable_ranked: list[dict[str, Any]] = []
    for item in ranked:
        serializable_ranked.append(
            {
                "kind": item["kind"],
                "default": item["default"],
                "key": item["key"],
                "import_status": item["import_status"],
                "reason_class": item["reason_class"],
                "occurrences": item["occurrences"],
                "file_count": len(item["files"]),
                "files": sorted(item["files"]),
                "libraries": sorted(item["libraries"]),
                "sections": sorted(item["sections"]),
                "detail_keys": sorted(item["detail_keys"]),
                "reasons": sorted(item["reasons"]),
            }
        )
    return serializable_ranked


def build_merged_fix_queue(
    verified_rows: list[dict[str, Any]],
    importer_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    queue: dict[tuple[str, str | None, str], dict[str, Any]] = {}

    def ensure_bucket(kind: str, default: str | None, key: str) -> dict[str, Any]:
        return queue.setdefault(
            (kind, default, key),
            {
                "kind": kind,
                "default": default,
                "key": key,
                "verified_occurrences": 0,
                "importer_occurrences": 0,
                "verified_files": set(),
                "importer_files": set(),
                "libraries": set(),
                "matched_default_files": set(),
                "validation_levels": set(),
                "importer_statuses": set(),
                "importer_reason_classes": set(),
                "importer_reasons": set(),
                "needs_schema_support": False,
                "needs_quickstart_support": False,
                "needs_importer_support": False,
                "quickstart_exclusion_reason": QUICKSTART_RECOMMENDATION_EXCLUSIONS.get((kind, key)),
            },
        )

    for item in verified_rows:
        kind = str(item.get("kind") or "")
        default = item.get("default")
        key = str(item.get("key") or "")
        bucket = ensure_bucket(kind, default, key)
        bucket["verified_occurrences"] += int(item.get("occurrences", 0) or 0)
        bucket["verified_files"].update(str(path) for path in item.get("files", []) if path)
        bucket["libraries"].update(str(lib) for lib in item.get("libraries", []) if lib)
        bucket["matched_default_files"].update(str(path) for path in item.get("matched_default_files", []) if path)
        if item.get("validation_level"):
            bucket["validation_levels"].add(str(item.get("validation_level")))
        if item.get("kometa_declared") and not item.get("schema_declared"):
            bucket["needs_schema_support"] = True
        if item.get("kometa_declared") and not item.get("quickstart_declared") and not bucket["quickstart_exclusion_reason"]:
            bucket["needs_quickstart_support"] = True

    for item in importer_rows:
        kind = str(item.get("kind") or "")
        default = item.get("default")
        key = str(item.get("key") or "")
        bucket = ensure_bucket(kind, default, key)
        bucket["importer_occurrences"] += int(item.get("occurrences", 0) or 0)
        bucket["importer_files"].update(str(path) for path in item.get("files", []) if path)
        bucket["libraries"].update(str(lib) for lib in item.get("libraries", []) if lib)
        if item.get("import_status"):
            bucket["importer_statuses"].add(str(item.get("import_status")))
        if item.get("reason_class"):
            bucket["importer_reason_classes"].add(str(item.get("reason_class")))
        for reason in item.get("reasons", []):
            if reason:
                bucket["importer_reasons"].add(str(reason))
        if item.get("import_status") != "mapped" and not bucket["quickstart_exclusion_reason"]:
            bucket["needs_importer_support"] = True

    ranked: list[dict[str, Any]] = []
    for bucket in queue.values():
        action_targets: list[str] = []
        if bucket["needs_schema_support"]:
            action_targets.append("schema")
        if bucket["needs_quickstart_support"]:
            action_targets.append("quickstart")
        if bucket["needs_importer_support"]:
            action_targets.append("importer")
        if not action_targets:
            continue
        importer_priority = 2
        if "unmapped" in bucket["importer_statuses"]:
            importer_priority = 0
        elif bucket["importer_statuses"]:
            importer_priority = 1
        ranked.append(
            {
                "kind": bucket["kind"],
                "default": bucket["default"],
                "key": bucket["key"],
                "action_targets": action_targets,
                "action_target_count": len(action_targets),
                "verified_occurrences": bucket["verified_occurrences"],
                "importer_occurrences": bucket["importer_occurrences"],
                "total_occurrences": bucket["verified_occurrences"] + bucket["importer_occurrences"],
                "verified_file_count": len(bucket["verified_files"]),
                "importer_file_count": len(bucket["importer_files"]),
                "libraries": sorted(bucket["libraries"]),
                "matched_default_files": sorted(bucket["matched_default_files"]),
                "validation_levels": sorted(bucket["validation_levels"]),
                "importer_statuses": sorted(bucket["importer_statuses"]),
                "importer_reason_classes": sorted(bucket["importer_reason_classes"]),
                "importer_reasons": sorted(bucket["importer_reasons"]),
                "quickstart_exclusion_reason": bucket["quickstart_exclusion_reason"],
                "_importer_priority": importer_priority,
            }
        )
    ranked.sort(
        key=lambda item: (
            -item["action_target_count"],
            item["_importer_priority"],
            -item["total_occurrences"],
            -len(item["libraries"]),
            str(item["default"]),
            str(item["key"]),
        )
    )
    for item in ranked:
        item.pop("_importer_priority", None)
    return ranked


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find template variables used in uploaded configs that are valid in Kometa but not exposed in Quickstart.")
    parser.add_argument(
        "--input",
        nargs="+",
        help="YAML file, folder, or ZIP to scan. Can be passed multiple times or with multiple values.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output file path. If omitted, writes to artifacts/template_gap_reports/<timestamp>.json.",
    )
    parser.add_argument(
        "--quickstart-root",
        default=str(ROOT),
        help="Path to the Quickstart repo root. Defaults to the repo containing this script.",
    )
    parser.add_argument(
        "--cache-path",
        help="Optional cache JSON path. Defaults to artifacts/template_gap_cache.json.",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable incremental file-result caching for this run. Default is off.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable periodic progress output during long scans.",
    )
    parser.add_argument(
        "--include-archives",
        action="store_true",
        help="Enable entering archive files during discovery. Default is off.",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in excludes such as Windows, Program Files, ProgramData, $Recycle.Bin, dot-prefixed folders, .git, node_modules, common virtualenv folders, all AppData trees, OneDrive, common media/output/cache/build directories, and VS Code history folders.",
    )
    parser.add_argument(
        "--yaml-type",
        choices=[
            "config",
            "all",
            "external_collection",
            "external_overlay",
            "external_metadata",
            "external_playlist",
            "external_template_bundle",
            "unknown",
        ],
        default="config",
        help="Which YAML document type to analyze. Default is config so external collection/overlay/metadata/playlist files are excluded.",
    )
    return parser.parse_args()


def build_progress_callbacks(enabled: bool):
    if not enabled:
        return None, None, None, None

    start_time = time.monotonic()
    discovery_state = {
        "last_time": 0.0,
        "last_dirs": 0,
        "dirs": 0,
        "archives": 0,
        "skipped_archives": 0,
        "unsupported_archives": 0,
        "roots_started": 0,
        "roots_done": 0,
    }
    prefilter_state = {"last_time": 0.0, "last_index": 0}
    scan_state = {"last_time": 0.0, "last_index": 0}
    verify_state = {"last_time": 0.0, "last_index": 0, "last_stage": ""}

    def elapsed_label() -> str:
        elapsed = int(time.monotonic() - start_time)
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def short_path(path: Path, max_len: int = 110) -> str:
        text = str(path)
        if len(text) <= max_len:
            return text
        keep = max_len - 3
        head = keep // 2
        tail = keep - head
        return f"{text[:head]}...{text[-tail:]}"

    def stage_rate(count: int) -> str:
        elapsed = max(time.monotonic() - start_time, 0.001)
        return f"{count / elapsed:.1f}/s"

    def percent(index: int, total: int) -> str:
        if total <= 0:
            return "0.0%"
        return f"{(index / total) * 100:.1f}%"

    def emit_discovery(event: str, current_path: Path, yaml_found: int) -> None:
        now = time.monotonic()
        if event == "root":
            discovery_state["roots_started"] += 1
            print(
                f"[progress][{elapsed_label()}] discovery start | root {discovery_state['roots_started']} | {short_path(current_path)}",
                file=sys.stderr,
                flush=True,
            )
            discovery_state["last_time"] = now
            return
        if event == "archive_skipped":
            discovery_state["skipped_archives"] += 1
        elif event == "archive_unsupported":
            discovery_state["unsupported_archives"] += 1
        elif event == "archive":
            discovery_state["archives"] += 1
        elif event == "root_done":
            discovery_state["roots_done"] += 1
            print(
                f"[progress][{elapsed_label()}] discovery root done | {discovery_state['roots_done']}/{discovery_state['roots_started']} roots | "
                f"dirs {discovery_state['dirs']} | archives {discovery_state['archives']} | skipped-archives {discovery_state['skipped_archives']} | "
                f"yaml {yaml_found} | "
                f"{short_path(current_path)}",
                file=sys.stderr,
                flush=True,
            )
            discovery_state["last_time"] = now
            return
        else:
            discovery_state["dirs"] += 1
            discovery_state["last_dirs"] += 1

        should_emit = (
            discovery_state["dirs"] == 1
            or discovery_state["archives"] == 1
            or discovery_state["skipped_archives"] == 1
            or discovery_state["last_dirs"] % 250 == 0
            or (discovery_state["archives"] > 0 and discovery_state["archives"] % 25 == 0)
            or now - discovery_state["last_time"] >= 5.0
            or event in {"archive_skipped", "archive_unsupported"}
        )
        if not should_emit:
            return

        if event == "archive_skipped":
            current_summary = f"skipped archive by default {short_path(current_path)}"
        elif event == "archive_unsupported":
            current_summary = f"skipped unsupported archive {short_path(current_path)}"
        elif event == "archive":
            current_summary = f"current archive {short_path(current_path)}"
        else:
            current_summary = f"current dir {short_path(current_path)}"

        print(
            f"[progress][{elapsed_label()}] discovery | dirs {discovery_state['dirs']} ({stage_rate(discovery_state['dirs'])}) | "
            f"archives {discovery_state['archives']} ({stage_rate(discovery_state['archives'])}) | "
            f"skipped-archives {discovery_state['skipped_archives']} | unsupported {discovery_state['unsupported_archives']} | "
            f"yaml {yaml_found} | {current_summary}",
            file=sys.stderr,
            flush=True,
        )
        discovery_state["last_time"] = now

    def emit(index: int, total: int, parsed: int, skipped: int, current_path: Path) -> None:
        now = time.monotonic()
        should_emit = index == 1 or index == total or index - scan_state["last_index"] >= 100 or now - scan_state["last_time"] >= 5.0
        if not should_emit:
            return
        print(
            f"[progress][{elapsed_label()}] parse {index}/{total} ({percent(index, total)}) | "
            f"parsed {parsed} | skipped {skipped} | rate {stage_rate(index)} | {short_path(current_path)}",
            file=sys.stderr,
            flush=True,
        )
        scan_state["last_time"] = now
        scan_state["last_index"] = index

    def emit_prefilter(index: int, total: int, selected: int, skipped: int, current_path: Path) -> None:
        now = time.monotonic()
        should_emit = index == 1 or index == total or index - prefilter_state["last_index"] >= 250 or now - prefilter_state["last_time"] >= 5.0
        if not should_emit:
            return
        print(
            f"[progress][{elapsed_label()}] prefilter {index}/{total} ({percent(index, total)}) | "
            f"selected {selected} | skipped {skipped} | rate {stage_rate(index)} | {short_path(current_path)}",
            file=sys.stderr,
            flush=True,
        )
        prefilter_state["last_time"] = now
        prefilter_state["last_index"] = index

    def emit_verify(stage: str, index: int | None = None, total: int | None = None) -> None:
        now = time.monotonic()
        if index is None or total is None:
            print(f"[progress][{elapsed_label()}] {stage}", file=sys.stderr, flush=True)
            verify_state["last_time"] = now
            verify_state["last_stage"] = stage
            verify_state["last_index"] = 0
            return
        should_emit = index == 1 or index == total or stage != verify_state["last_stage"] or index - verify_state["last_index"] >= 500 or now - verify_state["last_time"] >= 5.0
        if not should_emit:
            return
        print(f"[progress][{elapsed_label()}] {stage} {index}/{total}", file=sys.stderr, flush=True)
        verify_state["last_time"] = now
        verify_state["last_index"] = index
        verify_state["last_stage"] = stage

    return emit_discovery, emit, emit_verify, emit_prefilter


def ensure_json_output_path(root: Path, requested_output: str | None) -> Path:
    if requested_output:
        return Path(requested_output).resolve()
    report_dir = root / "artifacts" / "template_gap_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return report_dir / f"template_gap_report_{timestamp}.json"


def compact_path_list(paths: list[str], limit: int = 3) -> str:
    if not paths:
        return "-"
    shown = paths[:limit]
    text = ", ".join(shown)
    remaining = len(paths) - len(shown)
    if remaining > 0:
        text += f" +{remaining}"
    return text


def render_table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{title}\n  none\n"
    headers = ["default", "key", "occ", "qs", "schema", "kometa", "status", "files", "libraries", "kometa file"]
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                str(row.get("default") or "-"),
                str(row.get("key") or "-"),
                str(row.get("occurrences", 0)),
                "yes" if row.get("supported_in_quickstart") else "no",
                "yes" if row.get("schema_declared") else "no",
                "yes" if row.get("kometa_declared") else "no",
                str(row.get("validation_level") or "-"),
                str(row.get("file_count", 0)),
                compact_path_list(row.get("libraries", []), limit=2),
                compact_path_list(row.get("matched_default_files", []), limit=2),
            ]
        )
    widths = []
    for col_idx, header in enumerate(headers):
        widths.append(max(len(header), *(len(r[col_idx]) for r in table_rows)))

    def fmt(row: list[str]) -> str:
        return "  " + " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))

    lines = [title, fmt(headers), "  " + "-+-".join("-" * width for width in widths)]
    lines.extend(fmt(row) for row in table_rows)
    return "\n".join(lines) + "\n"


def render_importer_table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{title}\n  none\n"
    headers = ["kind", "default", "key", "status", "reason", "occ", "files", "libraries"]
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                str(row.get("kind") or "-"),
                str(row.get("default") or "-"),
                str(row.get("key") or "-"),
                str(row.get("import_status") or "-"),
                str(row.get("reason_class") or "-"),
                str(row.get("occurrences", 0)),
                str(row.get("file_count", 0)),
                compact_path_list(row.get("libraries", []), limit=2),
            ]
        )
    widths = []
    for col_idx, header in enumerate(headers):
        widths.append(max(len(header), *(len(r[col_idx]) for r in table_rows)))
    lines = [title]
    header_line = "  " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    separator = "  " + "-+-".join("-" * widths[idx] for idx in range(len(headers)))
    lines.append(header_line)
    lines.append(separator)
    for row in table_rows:
        lines.append("  " + " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(headers))))
    return "\n".join(lines) + "\n"


def render_action_queue_table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{title}\n  none\n"
    headers = ["kind", "default", "key", "targets", "occ", "importer", "status", "libraries"]
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                str(row.get("kind") or "-"),
                str(row.get("default") or "-"),
                str(row.get("key") or "-"),
                ",".join(str(target) for target in row.get("action_targets", [])) or "-",
                str(row.get("total_occurrences", 0)),
                compact_path_list(row.get("importer_reason_classes", []), limit=2),
                compact_path_list(row.get("validation_levels", []), limit=2),
                compact_path_list(row.get("libraries", []), limit=2),
            ]
        )
    widths = []
    for col_idx, header in enumerate(headers):
        widths.append(max(len(header), *(len(r[col_idx]) for r in table_rows)))
    lines = [title]
    header_line = "  " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    separator = "  " + "-+-".join("-" * widths[idx] for idx in range(len(headers)))
    lines.append(header_line)
    lines.append(separator)
    for row in table_rows:
        lines.append("  " + " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(headers))))
    return "\n".join(lines) + "\n"


def render_grouped_default_table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{title}\n  none\n"
    headers = ["kind", "default", "gaps", "occ", "keys"]
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                str(row.get("kind") or "-"),
                str(row.get("default") or "-"),
                str(row.get("gap_count", 0)),
                str(row.get("occurrences", 0)),
                compact_path_list(row.get("keys", []), limit=4),
            ]
        )
    widths = []
    for col_idx, header in enumerate(headers):
        widths.append(max(len(header), *(len(r[col_idx]) for r in table_rows)))

    def fmt(row: list[str]) -> str:
        return "  " + " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))

    lines = [title, fmt(headers), "  " + "-+-".join("-" * width for width in widths)]
    lines.extend(fmt(row) for row in table_rows)
    return "\n".join(lines) + "\n"


def render_summary(report: dict[str, Any], json_output_path: Path) -> str:
    overlays = report.get("verified_gaps_by_kind", {}).get("overlay", [])
    collections = report.get("verified_gaps_by_kind", {}).get("collection", [])
    playlists = report.get("verified_gaps_by_kind", {}).get("playlist", [])
    libraries = report.get("verified_gaps_by_kind", {}).get("library", [])
    importer_section = report.get("importer_findings_by_kind", {}).get("section", [])
    importer_library = report.get("importer_findings_by_kind", {}).get("library", [])
    importer_collection = report.get("importer_findings_by_kind", {}).get("collection", [])
    importer_overlay = report.get("importer_findings_by_kind", {}).get("overlay", [])
    importer_playlist = report.get("importer_findings_by_kind", {}).get("playlist", [])
    schema_backlog = report.get("schema_backlog_by_default", [])
    quickstart_backlog = report.get("quickstart_backlog_by_default", [])
    merged_fix_queue = report.get("merged_fix_queue_ranked", [])
    quickstart_excluded = report.get("quickstart_recommendation_exclusions", [])

    lines = [
        "Template Variable Gap Summary",
        f"  yaml type focus: {report.get('yaml_type_focus', 'config')}",
        f"  include archives: {report.get('include_archives', False)}",
        f"  files discovered: {report.get('discovered_file_count', 0)}",
        f"  candidate YAML after prefilter: {report.get('candidate_yaml_file_count', report.get('prefiltered_file_count', 0))}",
        f"  files parsed under yaml type focus: {report.get('parsed_file_count', 0)}",
        f"  files skipped: {report.get('skipped_file_count', 0)}",
        f"  files matching yaml type focus: {report.get('yaml_type_matched_file_count', report.get('files_with_relevant_yaml_count', 0))}",
        f"  cache enabled: {report.get('cache_enabled', False)}",
        f"  default excludes: {report.get('default_excludes_enabled', True)}",
        f"  cache hits: {report.get('cache_hit_count', 0)}",
        f"  cache misses: {report.get('cache_miss_count', 0)}",
        "  cache invalidates on: analyzer, Quickstart support JSON, Kometa defaults, or source file changes",
        f"  template variable occurrences scanned: {report.get('template_variable_occurrences_scanned', 0)}",
        f"  importer candidate files scanned: {report.get('importer_candidate_file_count', 0)}",
        f"  decode fallbacks used: {report.get('decode_fallback_count', 0)}",
        f"  probable artifact skips: {report.get('artifact_skipped_file_count', 0)}",
        f"  non-Kometa YAML skips: {report.get('non_kometa_skipped_file_count', 0)}",
        f"  YAML type excluded skips: {report.get('yaml_type_excluded_file_count', 0)}",
        "  note: prefilter is intentionally broad; yaml-type focus is enforced after parsing",
        f"  importer issues: {report.get('importer_issue_count', 0)}",
        f"  importer unmapped: {report.get('importer_unmapped_count', 0)}",
        f"  importer skipped: {report.get('importer_skipped_count', 0)}",
        f"  importer files with issues: {report.get('importer_files_with_issues_count', 0)}",
        f"  verified gaps: {report.get('verified_gap_count', 0)}",
        f"  schema-declared verified gaps: {report.get('schema_declared_gap_count', 0)}",
        f"  kometa-declared verified gaps: {report.get('kometa_declared_gap_count', 0)}",
        f"  verified gaps missing from schema but supported by Kometa: {report.get('kometa_missing_schema_gap_count', 0)}",
        f"  value-shape verified gaps: {report.get('value_shape_verified_gap_count', 0)}",
        f"  quickstart recommendations: {report.get('quickstart_recommendation_count', 0)}",
        f"  excluded quickstart recommendation candidates: {report.get('quickstart_recommendation_exclusion_count', 0)}",
        f"  runtime-supported quickstart recommendations: {report.get('quickstart_runtime_supported_recommendation_count', 0)}",
        f"  merged fix queue items: {report.get('merged_fix_queue_count', 0)}",
        f"  overlay gaps: {len(overlays)}",
        f"  collection gaps: {len(collections)}",
        f"  playlist gaps: {len(playlists)}",
        f"  library gaps: {len(libraries)}",
        f"  importer section issues: {len(importer_section)}",
        f"  importer library issues: {len(importer_library)}",
        f"  importer collection issues: {len(importer_collection)}",
        f"  importer overlay issues: {len(importer_overlay)}",
        f"  importer playlist issues: {len(importer_playlist)}",
        "  runtime guaranteed: false",
        "",
    ]
    exclude_details = report.get("default_excludes")
    if isinstance(exclude_details, dict):
        lines.append("Default Excludes Active")
        if exclude_details.get("enabled"):
            lines.append(f"  top-level dir names: {', '.join(exclude_details.get('top_level_dir_names', [])) or 'none'}")
            lines.append(f"  dir names anywhere: {', '.join(exclude_details.get('dir_names_anywhere', [])) or 'none'}")
            lines.append(f"  path sequences: {', '.join(exclude_details.get('path_sequences', [])) or 'none'}")
            lines.append(f"  logic rules: {', '.join(exclude_details.get('logic_rules', [])) or 'none'}")
        else:
            lines.append("  none")
        lines.append("")
    lines.extend(
        [
            render_action_queue_table("Merged Fix Queue", merged_fix_queue[:25]),
            render_importer_table("Top Importer Misses", report.get("importer_findings_ranked", [])[:20]),
            render_table("Overlay Gaps", overlays),
            render_table("Collection Gaps", collections),
        ]
    )
    if quickstart_backlog:
        lines.append(render_grouped_default_table("Quickstart Backlog By Default", quickstart_backlog))
    if schema_backlog:
        lines.append(render_grouped_default_table("Schema Backlog By Default", schema_backlog))
    if playlists:
        lines.append(render_table("Playlist Gaps", playlists))
    if libraries:
        lines.append(render_table("Library Gaps", libraries))
    if quickstart_excluded:
        lines.append("Excluded Quickstart Recommendation Candidates")
        for item in quickstart_excluded[:10]:
            lines.append(
                f"  {item.get('kind')} {item.get('default') or '-'} {item.get('key')}: "
                f"{item.get('reason')} (occ={item.get('occurrences', 0)}, files={item.get('file_count', 0)})"
            )
        remaining = len(quickstart_excluded) - min(len(quickstart_excluded), 10)
        if remaining > 0:
            lines.append(f"  ... plus {remaining} more excluded recommendation candidates")
    skipped_files = report.get("skipped_files", [])
    if skipped_files:
        lines.append("Skipped Files")
        for item in skipped_files[:10]:
            suffix_parts = []
            if item.get("stage"):
                suffix_parts.append(str(item.get("stage")))
            if item.get("noise_reason"):
                suffix_parts.append(str(item.get("noise_reason")))
            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
            lines.append(f"  {item.get('file')}: {item.get('error_type')}{suffix}")
        remaining = len(skipped_files) - min(len(skipped_files), 10)
        if remaining > 0:
            lines.append(f"  ... plus {remaining} more skipped files")
    if report.get("cache_enabled", False):
        lines.append(f"Cache file: {report.get('cache_path')}")
        lines.append(f"Archive cache: {report.get('archive_cache_path')}")
    lines.append(f"Full JSON report: {json_output_path}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    root = Path(args.quickstart_root).resolve()
    kometa_defaults = root / "config" / "kometa" / "defaults"
    kometa_schema_path = root / "config" / "kometa" / "json-schema" / "config-schema.json"
    qs_collections_path = root / "static" / "json" / "quickstart_collections.json"
    qs_overlays_path = root / "static" / "json" / "quickstart_overlays.json"
    qs_attributes_path = root / "static" / "json" / "quickstart_attributes.json"
    cache_context = build_cache_context(
        root,
        qs_collections_path,
        qs_overlays_path,
        qs_attributes_path,
        kometa_defaults,
        args.yaml_type,
    )
    cache_path = get_cache_path(root, args.cache_path)
    archive_cache_dir = get_archive_cache_dir(root)
    verification_checkpoint_dir = get_verification_checkpoint_dir(root)
    verification_meta_path = verification_checkpoint_dir / "metadata.json"
    verification_rows_path = verification_checkpoint_dir / "all_rows.ndjson"
    cache_enabled = args.use_cache
    cache_data = load_cache(cache_path, expected_context=cache_context) if cache_enabled else empty_cache(cache_context)
    cache_persist = make_periodic_persistor(lambda: save_cache(cache_path, cache_data), CACHE_SAVE_EVERY_ITEMS, CACHE_SAVE_EVERY_SECS) if cache_enabled else None
    default_excludes_enabled = not args.no_default_excludes
    default_excludes = describe_default_excludes(default_excludes_enabled)

    inputs = [Path(p).resolve() for p in args.input] if args.input else [root / "artifacts" / "config_zip_scan"]
    discovery_callback, progress_callback, verify_callback, prefilter_progress_callback = build_progress_callbacks(not args.no_progress)
    input_files, temp_dirs = collect_yaml_files(
        inputs,
        discovery_callback=discovery_callback,
        exclude_defaults=default_excludes_enabled,
        include_archives=args.include_archives,
        archive_cache_dir=archive_cache_dir if (cache_enabled and args.include_archives) else None,
    )
    candidate_files, prefilter_skipped_files, prefilter_cache_stats = prefilter_yaml_files(
        input_files,
        yaml_type_focus=args.yaml_type,
        cache_data=cache_data if cache_enabled else None,
        progress_callback=prefilter_progress_callback,
        checkpoint_callback=cache_persist,
    )

    try:
        qs_collections = build_qs_collection_map(qs_collections_path)
        qs_overlays = build_qs_overlay_map(qs_overlays_path)
        qs_overlays_declared = build_qs_overlay_map(qs_overlays_path, enrich_runtime_support=False)
        qs_library_keys = build_qs_library_template_keys(qs_attributes_path)
        qs_global_keys = build_qs_global_supported_keys(qs_attributes_path)
        qs_playlist_keys = build_qs_playlist_supported_keys(qs_attributes_path)
        schema_keys = build_schema_key_set(kometa_schema_path)
        if progress_callback:
            print(
                f"[progress][discovery] discovered {len(input_files)} YAML files across {len(inputs)} input root(s)",
                file=sys.stderr,
                flush=True,
            )
            print(
                f"[progress][prefilter] selected {len(candidate_files)} candidate YAML files for later yaml-type classification " f"(focus: {args.yaml_type})",
                file=sys.stderr,
                flush=True,
            )
        uploaded, importer_rows, parse_skipped_files, parsed_file_paths, parse_cache_stats = scan_uploaded_configs(
            candidate_files,
            yaml_type_focus=args.yaml_type,
            progress_callback=progress_callback,
            cache_data=cache_data if cache_enabled else None,
            checkpoint_callback=cache_persist,
        )
        if cache_persist:
            cache_persist(len(candidate_files), len(candidate_files), force=True)
        skipped_files = prefilter_skipped_files + parse_skipped_files

        uploaded_signature = compute_uploaded_signature(uploaded)
        all_rows: list[dict[str, Any]] = []
        summary: dict[tuple[str, str | None, str], dict[str, Any]] = {}
        resumed_from_index = 0
        resume_used = False

        def reset_verification_checkpoint() -> None:
            remove_tree(verification_checkpoint_dir)
            verification_checkpoint_dir.mkdir(parents=True, exist_ok=True)

        def save_verification_metadata(processed_count: int) -> None:
            metadata = {
                "version": VERIFY_CHECKPOINT_VERSION,
                "quickstart_root": str(root),
                "inputs": [str(p) for p in inputs],
                "cache_context": cache_context,
                "uploaded_signature": uploaded_signature,
                "uploaded_count": len(uploaded),
                "processed_count": processed_count,
                "rows_path": str(verification_rows_path),
            }
            write_text_atomic(verification_meta_path, json.dumps(metadata, indent=2, default=json_default))

        checkpoint_valid = False
        if verification_meta_path.exists() and verification_rows_path.exists():
            try:
                checkpoint_meta = load_json(verification_meta_path)
                if (
                    isinstance(checkpoint_meta, dict)
                    and checkpoint_meta.get("version") == VERIFY_CHECKPOINT_VERSION
                    and checkpoint_meta.get("quickstart_root") == str(root)
                    and checkpoint_meta.get("inputs") == [str(p) for p in inputs]
                    and checkpoint_meta.get("cache_context") == cache_context
                    and checkpoint_meta.get("uploaded_signature") == uploaded_signature
                    and checkpoint_meta.get("uploaded_count") == len(uploaded)
                ):
                    all_rows = load_jsonl_rows(verification_rows_path)
                    if len(all_rows) <= len(uploaded):
                        summary = build_gap_summary(all_rows)
                        resumed_from_index = len(all_rows)
                        resume_used = resumed_from_index > 0
                        checkpoint_valid = True
            except Exception as exc:
                if verify_callback:
                    verify_callback(f"ignoring invalid verification checkpoint: {exc}")
        if not checkpoint_valid:
            seeded_rows, seeded_report_path = load_matching_report_rows(
                root / "artifacts" / "template_gap_reports",
                quickstart_root=root,
                inputs=inputs,
                cache_context=cache_context,
                uploaded_signature=uploaded_signature,
                uploaded_count=len(uploaded),
            )
            if seeded_rows is not None:
                all_rows = seeded_rows
                summary = build_gap_summary(all_rows)
                resumed_from_index = len(all_rows)
                resume_used = resumed_from_index > 0
                checkpoint_valid = True
                reset_verification_checkpoint()
                append_jsonl_rows(verification_rows_path, all_rows)
                save_verification_metadata(len(all_rows))
                if verify_callback and seeded_report_path is not None:
                    verify_callback(f"reusing completed verification from {seeded_report_path}")
            else:
                reset_verification_checkpoint()
                save_verification_metadata(0)
                all_rows = []
                summary = {}

        verify_buffer: list[dict[str, Any]] = []
        verify_save_state = {"last_index": len(all_rows), "last_time": time.monotonic()}

        def flush_verification_checkpoint(processed_count: int, force: bool = False) -> None:
            now = time.monotonic()
            should_save = force
            if not should_save and processed_count >= len(uploaded):
                should_save = True
            if not should_save and processed_count - verify_save_state["last_index"] >= VERIFY_CHECKPOINT_EVERY_ITEMS:
                should_save = True
            if not should_save and now - verify_save_state["last_time"] >= VERIFY_CHECKPOINT_EVERY_SECS:
                should_save = True
            if not should_save:
                return
            append_jsonl_rows(verification_rows_path, verify_buffer)
            verify_buffer.clear()
            save_verification_metadata(processed_count)
            verify_save_state["last_index"] = processed_count
            verify_save_state["last_time"] = now

        if verify_callback:
            verify_callback(f"verifying {len(uploaded)} findings against Quickstart and Kometa defaults")
            if resume_used:
                verify_callback(f"resuming verification from {resumed_from_index}/{len(uploaded)} using {verification_rows_path}")
        for idx, row in enumerate(uploaded[resumed_from_index:], start=resumed_from_index + 1):
            if verify_callback:
                verify_callback("verifying findings", idx, len(uploaded))
            key = row["key"]
            kind = row["kind"]
            alias = row["default"]
            if kind == "collection":
                supported = key in qs_collections.get(alias or "", set()) or key in qs_global_keys
                quickstart_declared = supported
                default_files = resolve_default_paths(alias or "", kind, kometa_defaults)
                name_verified, matched_files = key_is_valid_for_default(key, default_files)
            elif kind == "overlay":
                supported = overlay_key_supported_in_quickstart(alias, key, qs_overlays)
                quickstart_declared = overlay_key_supported_in_quickstart(alias, key, qs_overlays_declared)
                default_files = resolve_default_paths(alias or "", kind, kometa_defaults)
                name_verified, matched_files = key_is_valid_for_default(key, default_files)
            elif kind == "playlist":
                supported = key in qs_playlist_keys
                quickstart_declared = supported
                default_files = resolve_default_paths(alias or "", kind, kometa_defaults)
                name_verified, matched_files = key_is_valid_for_default(key, default_files)
            else:
                supported = key in qs_library_keys or key in qs_global_keys
                quickstart_declared = supported
                name_verified = True
                matched_files = []

            value_shape_verified, value_shape_rule = infer_value_shape(row["value"], key)
            schema_declared = key in schema_keys
            validation_level = classify_validation_level(supported, schema_declared, name_verified)
            out = dict(row)
            out["supported_in_quickstart"] = supported
            out["quickstart_declared"] = quickstart_declared
            out["schema_declared"] = schema_declared
            out["kometa_declared"] = name_verified
            out["validation_level"] = validation_level
            out["name_verified"] = name_verified
            out["value_shape_verified"] = value_shape_verified
            out["value_shape_rule"] = value_shape_rule
            out["runtime_guaranteed"] = False
            out["valid_for_kometa"] = name_verified
            out["matched_default_files"] = [str(p.relative_to(kometa_defaults)) for p in matched_files]
            all_rows.append(out)
            verify_buffer.append(out)
            accumulate_gap_summary(summary, out)
            flush_verification_checkpoint(len(all_rows))

        if verify_callback:
            verify_callback("aggregating ranked gaps")
        flush_verification_checkpoint(len(all_rows), force=True)
        serializable_ranked = serialize_ranked_summary(summary)
        quickstart_recommendation_ranked = serialize_ranked_summary(build_quickstart_recommendation_summary(all_rows))
        quickstart_recommendation_excluded = sorted(
            build_quickstart_recommendation_exclusion_summary(all_rows).values(),
            key=lambda item: (-item["occurrences"], -item["file_count"], str(item["default"]), str(item["key"])),
        )
        importer_ranked = serialize_importer_ranked_summary(build_importer_summary(importer_rows))
        merged_fix_queue_ranked = build_merged_fix_queue(serializable_ranked, importer_ranked)

        by_kind: dict[str, list[dict[str, Any]]] = {"overlay": [], "collection": [], "playlist": [], "library": []}
        for item in serializable_ranked:
            kind_key = item["kind"] if item["kind"] in by_kind else "library"
            by_kind[kind_key].append(item)

        quickstart_recommendations_by_kind: dict[str, list[dict[str, Any]]] = {"overlay": [], "collection": [], "playlist": [], "library": []}
        for item in quickstart_recommendation_ranked:
            kind_key = item["kind"] if item["kind"] in quickstart_recommendations_by_kind else "library"
            quickstart_recommendations_by_kind[kind_key].append(item)

        importer_by_kind: dict[str, list[dict[str, Any]]] = {
            "section": [],
            "library": [],
            "collection": [],
            "overlay": [],
            "playlist": [],
        }
        for item in importer_ranked:
            kind_key = item["kind"] if item["kind"] in importer_by_kind else "library"
            importer_by_kind[kind_key].append(item)

        schema_backlog_summary: dict[tuple[str, str | None], dict[str, Any]] = {}
        for item in serializable_ranked:
            if not item["kometa_declared"] or item["schema_declared"]:
                continue
            bucket = schema_backlog_summary.setdefault(
                (item["kind"], item["default"]),
                {
                    "kind": item["kind"],
                    "default": item["default"],
                    "occurrences": 0,
                    "keys": set(),
                },
            )
            bucket["occurrences"] += item["occurrences"]
            bucket["keys"].add(item["key"])

        schema_backlog_by_default = sorted(
            [
                {
                    "kind": item["kind"],
                    "default": item["default"],
                    "occurrences": item["occurrences"],
                    "gap_count": len(item["keys"]),
                    "keys": sorted(item["keys"]),
                }
                for item in schema_backlog_summary.values()
            ],
            key=lambda item: (-item["occurrences"], -item["gap_count"], str(item["default"]), str(item["kind"])),
        )

        quickstart_backlog_summary: dict[tuple[str, str | None], dict[str, Any]] = {}
        for item in quickstart_recommendation_ranked:
            if not item["kometa_declared"] or item["quickstart_declared"]:
                continue
            bucket = quickstart_backlog_summary.setdefault(
                (item["kind"], item["default"]),
                {
                    "kind": item["kind"],
                    "default": item["default"],
                    "occurrences": 0,
                    "keys": set(),
                },
            )
            bucket["occurrences"] += item["occurrences"]
            bucket["keys"].add(item["key"])

        quickstart_backlog_by_default = sorted(
            [
                {
                    "kind": item["kind"],
                    "default": item["default"],
                    "occurrences": item["occurrences"],
                    "gap_count": len(item["keys"]),
                    "keys": sorted(item["keys"]),
                }
                for item in quickstart_backlog_summary.values()
            ],
            key=lambda item: (-item["occurrences"], -item["gap_count"], str(item["default"]), str(item["kind"])),
        )

        malformed_files = [item for item in skipped_files if item.get("malformed") is True]

        report = {
            "quickstart_root": str(root),
            "inputs": [str(p) for p in inputs],
            "yaml_type_focus": args.yaml_type,
            "cache_enabled": cache_enabled,
            "include_archives": args.include_archives,
            "cache_path": str(cache_path),
            "archive_cache_path": str(archive_cache_dir) if (cache_enabled and args.include_archives) else None,
            "cache_context": cache_context,
            "verification_checkpoint_path": str(verification_rows_path),
            "verification_resume_used": resume_used,
            "verification_resumed_row_count": resumed_from_index,
            "default_excludes_enabled": default_excludes_enabled,
            "default_excludes": default_excludes,
            "cache_hit_count": prefilter_cache_stats["cache_hits"] + parse_cache_stats["cache_hits"],
            "cache_miss_count": prefilter_cache_stats["cache_misses"] + parse_cache_stats["cache_misses"],
            "cache_stats": {
                "prefilter": prefilter_cache_stats,
                "parse": parse_cache_stats,
            },
            "discovered_file_count": len(input_files),
            "prefiltered_file_count": len(candidate_files),
            "candidate_yaml_file_count": len(candidate_files),
            "parsed_files": sorted(parsed_file_paths),
            "uploaded_files_scanned": sorted({row["file"] for row in uploaded}),
            "skipped_files": skipped_files,
            "skipped_file_count": len(skipped_files),
            "malformed_files": malformed_files,
            "malformed_file_count": len(malformed_files),
            "parsed_file_count": len(parsed_file_paths),
            "yaml_type_matched_file_count": len(parsed_file_paths),
            "files_with_template_variables_count": len(sorted({row["file"] for row in uploaded})),
            "files_with_relevant_yaml_count": len(parsed_file_paths),
            "template_variable_occurrences_scanned": len(uploaded),
            "importer_candidate_file_count": len(parsed_file_paths),
            "decode_fallback_count": prefilter_cache_stats.get("decode_fallbacks", 0) + parse_cache_stats.get("decode_fallbacks", 0),
            "artifact_skipped_file_count": sum(1 for item in skipped_files if item.get("noise_reason") == "artifact_filename_heuristic"),
            "non_kometa_skipped_file_count": sum(1 for item in skipped_files if item.get("noise_reason") == "non_kometa_content"),
            "yaml_type_excluded_file_count": sum(1 for item in skipped_files if item.get("noise_reason") == "yaml_type_excluded"),
            "importer_issue_count": len(importer_rows),
            "importer_unmapped_count": sum(1 for item in importer_rows if item.get("import_status") == "unmapped"),
            "importer_skipped_count": sum(1 for item in importer_rows if item.get("import_status") == "skipped"),
            "importer_files_with_issues_count": len(sorted({row["file"] for row in importer_rows})),
            "verified_gap_count": len(serializable_ranked),
            "schema_declared_gap_count": sum(1 for item in serializable_ranked if item["schema_declared"]),
            "kometa_declared_gap_count": sum(1 for item in serializable_ranked if item["kometa_declared"]),
            "kometa_missing_schema_gap_count": sum(1 for item in serializable_ranked if item["kometa_declared"] and not item["schema_declared"]),
            "value_shape_verified_gap_count": sum(1 for item in serializable_ranked if item["value_shape_verified_occurrences"] > 0),
            "quickstart_recommendation_count": len(quickstart_recommendation_ranked),
            "quickstart_recommendation_exclusion_count": len(quickstart_recommendation_excluded),
            "quickstart_runtime_supported_recommendation_count": sum(
                1 for item in quickstart_recommendation_ranked if item["supported_in_quickstart"] and not item["quickstart_declared"]
            ),
            "merged_fix_queue_count": len(merged_fix_queue_ranked),
            "verification_notes": {
                "name_verified": "Key name matched a variable declared or referenced in the corresponding built-in Kometa default or shared built-in templates.yml.",
                "quickstart_declared": "Key name was explicitly declared in Quickstart's shipped support metadata or modeled alias mapping, without relying on runtime-injected overlay controls.",
                "schema_declared": "Key name was found in Kometa's bundled config-schema.json. This is a secondary signal because the schema is not fully exhaustive.",
                "kometa_declared": "Key name was found in Kometa's bundled built-in defaults/templates, which is treated as the stronger local source of truth.",
                "validation_level": "works_in_kometa_missing_from_quickstart_and_schema means the key was not found in Quickstart or schema, but was found in Kometa built-in defaults/templates.",
                "value_shape_verified": "Best-effort local heuristic that the supplied value looks like the expected basic type. Null means no reliable local rule was inferred.",
                "merged_fix_queue": "Combined per-key action queue that merges schema gaps, Quickstart support gaps, and importer misses into one ranked backlog.",
                "runtime_guaranteed": False,
            },
            "verified_gaps_ranked": serializable_ranked,
            "verified_gaps_by_kind": by_kind,
            "quickstart_recommendations_ranked": quickstart_recommendation_ranked,
            "quickstart_recommendation_exclusions": quickstart_recommendation_excluded,
            "quickstart_recommendations_by_kind": quickstart_recommendations_by_kind,
            "importer_findings_ranked": importer_ranked,
            "importer_findings_by_kind": importer_by_kind,
            "merged_fix_queue_ranked": merged_fix_queue_ranked,
            "quickstart_backlog_by_default": quickstart_backlog_by_default,
            "schema_backlog_by_default": schema_backlog_by_default,
            "all_rows": all_rows,
            "importer_rows": importer_rows,
        }
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()

    json_output_path = ensure_json_output_path(root, args.output)
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    if verify_callback:
        verify_callback(f"writing JSON report to {json_output_path}")
    rendered = json.dumps(report, indent=2, default=json_default)
    write_text_atomic(json_output_path, rendered)
    if cache_enabled:
        save_cache(cache_path, cache_data)
    remove_tree(verification_checkpoint_dir)
    print(render_summary(report, json_output_path))


if __name__ == "__main__":
    main()
