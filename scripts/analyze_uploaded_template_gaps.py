import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import warnings
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.composer import ReusedAnchorWarning

ROOT = Path(__file__).resolve().parents[1]
CACHE_VERSION = 3
CACHE_SAVE_EVERY_ITEMS = 1000
CACHE_SAVE_EVERY_SECS = 60.0
VERIFY_CHECKPOINT_VERSION = 1
VERIFY_CHECKPOINT_EVERY_ITEMS = 1000
VERIFY_CHECKPOINT_EVERY_SECS = 30.0
VERIFY_CHECKPOINT_DIRNAME = "template_gap_verify_checkpoint"
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
    "vendor",
    "videos",
    "venv",
}


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


def load_yaml(path: Path) -> Any:
    with warnings.catch_warnings():
        warnings.simplefilter("error", ReusedAnchorWarning)
        return yaml.load(path.read_text(encoding="utf-8"))


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


def build_qs_overlay_map(qs_overlays_path: Path) -> dict[str, set[str]]:
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
            # Some Quickstart defaults intentionally reuse the same alias for
            # different media types. Merge their declared keys so later entries
            # do not erase earlier support and create false-positive gaps.
            mapping.setdefault(alias, set()).update(collect_qs_keys(overlay.get("template_variables")))
    return mapping


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
    shared_templates = kometa_defaults / "templates.yml"
    if shared_templates.exists():
        support_files.append(shared_templates)
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


def patterns_from_default_file(path: Path) -> set[str]:
    patterns: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        km = KEY_RE.match(line)
        lm = LIST_RE.match(line)
        token = None
        if km:
            token = km.group(1)
        elif lm:
            token = lm.group(1)
        if not token:
            continue
        if token in RESERVED:
            continue
        patterns.add(token)
        if token.endswith(".exists"):
            patterns.add(token[: -len(".exists")])
    return patterns


def key_matches_pattern(key: str, pattern: str) -> bool:
    if key == pattern:
        return True
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


def collect_yaml_files(
    inputs: list[Path],
    discovery_callback=None,
    exclude_defaults: bool = True,
) -> tuple[list[Path], list[tempfile.TemporaryDirectory]]:
    yaml_files: list[Path] = []
    temp_dirs: list[tempfile.TemporaryDirectory] = []
    for input_path in inputs:
        if input_path.is_dir():
            if discovery_callback:
                discovery_callback("root", input_path, len(yaml_files))
            for current_root, dirnames, filenames in os.walk(input_path, topdown=True):
                current_path = Path(current_root)
                if should_exclude_directory(current_path, input_path, enabled=exclude_defaults):
                    dirnames[:] = []
                    continue
                dirnames[:] = [dirname for dirname in dirnames if not should_exclude_directory(current_path / dirname, input_path, enabled=exclude_defaults)]
                if discovery_callback:
                    discovery_callback("dir", current_path, len(yaml_files))
                for filename in filenames:
                    lower = filename.lower()
                    if lower.endswith(".yml") or lower.endswith(".yaml"):
                        yaml_files.append(current_path / filename)
            if discovery_callback:
                discovery_callback("root_done", input_path, len(yaml_files))
        elif input_path.is_file() and input_path.suffix.lower() in {".yml", ".yaml"}:
            yaml_files.append(input_path)
        elif input_path.is_file() and input_path.suffix.lower() == ".zip":
            temp_dir = tempfile.TemporaryDirectory(prefix="qs_template_gap_")
            temp_dirs.append(temp_dir)
            extract_root = Path(temp_dir.name)
            with zipfile.ZipFile(input_path) as zf:
                zf.extractall(extract_root)
            if discovery_callback:
                discovery_callback("zip", input_path, len(yaml_files))
            for current_root, dirnames, filenames in os.walk(extract_root, topdown=True):
                current_path = Path(current_root)
                if should_exclude_directory(current_path, extract_root, enabled=exclude_defaults):
                    dirnames[:] = []
                    continue
                dirnames[:] = [dirname for dirname in dirnames if not should_exclude_directory(current_path / dirname, extract_root, enabled=exclude_defaults)]
                if discovery_callback:
                    discovery_callback("dir", current_path, len(yaml_files))
                for filename in filenames:
                    lower = filename.lower()
                    if lower.endswith(".yml") or lower.endswith(".yaml"):
                        yaml_files.append(current_path / filename)
        else:
            raise FileNotFoundError(f"Unsupported input path: {input_path}")
    return sorted(yaml_files), temp_dirs


def prefilter_yaml_files(
    input_files: list[Path],
    cache_data: dict[str, Any] | None = None,
    progress_callback=None,
    checkpoint_callback=None,
) -> tuple[list[Path], list[dict[str, str]], dict[str, int]]:
    candidate_files: list[Path] = []
    skipped_files: list[dict[str, str]] = []
    stats = {"cache_hits": 0, "cache_misses": 0}
    files_cache = cache_data.get("files", {}) if isinstance(cache_data, dict) else {}
    total_files = len(input_files)
    for idx, path in enumerate(input_files, start=1):
        cache_key = str(path)
        signature = file_signature(path)
        cached = files_cache.get(cache_key) if isinstance(files_cache, dict) else None
        if isinstance(cached, dict) and cached.get("signature") == signature and "contains_template_variables" in cached:
            stats["cache_hits"] += 1
            if cached.get("prefilter_skip"):
                skipped_files.append(dict(cached["prefilter_skip"]))
                if progress_callback:
                    progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
                if checkpoint_callback:
                    checkpoint_callback(idx, total_files)
                continue
            if cached.get("contains_template_variables"):
                candidate_files.append(path)
            if progress_callback:
                progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
            continue
        stats["cache_misses"] += 1
        try:
            raw_text = path.read_text(encoding="utf-8")
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
                files_cache[cache_key] = {"signature": signature, "prefilter_skip": skip_record, "contains_template_variables": False}
            if progress_callback:
                progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        contains_template_variables = "template_variables" in raw_text
        if isinstance(files_cache, dict):
            files_cache[cache_key] = {"signature": signature, "contains_template_variables": contains_template_variables}
        if contains_template_variables:
            candidate_files.append(path)
        if progress_callback:
            progress_callback(idx, total_files, len(candidate_files), len(skipped_files), path)
        if checkpoint_callback:
            checkpoint_callback(idx, total_files)
    return candidate_files, skipped_files, stats


def scan_uploaded_configs(
    input_files: list[Path],
    progress_callback=None,
    cache_data: dict[str, Any] | None = None,
    checkpoint_callback=None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str], dict[str, int]]:
    findings: list[dict[str, Any]] = []
    skipped_files: list[dict[str, str]] = []
    parsed_file_paths: list[str] = []
    parsed_count = 0
    total_files = len(input_files)
    stats = {"cache_hits": 0, "cache_misses": 0}
    files_cache = cache_data.get("files", {}) if isinstance(cache_data, dict) else {}
    for idx, path in enumerate(input_files, start=1):
        cache_key = str(path)
        signature = file_signature(path)
        cached = files_cache.get(cache_key) if isinstance(files_cache, dict) else None
        if isinstance(cached, dict) and cached.get("signature") == signature and "scan_result" in cached:
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
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        stats["cache_misses"] += 1
        try:
            data = load_yaml(path)
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
                files_cache[cache_key] = {"signature": signature, "contains_template_variables": True, "scan_result": {"status": "skip", "skip_record": skip_record}}
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
                files_cache[cache_key] = {"signature": signature, "contains_template_variables": True, "scan_result": {"status": "skip", "skip_record": skip_record}}
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        parsed_file_paths.append(str(path))
        if not isinstance(data, dict):
            parsed_count += 1
            if isinstance(files_cache, dict):
                files_cache[cache_key] = {"signature": signature, "contains_template_variables": True, "scan_result": {"status": "ok", "findings": []}}
            if progress_callback:
                progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
            if checkpoint_callback:
                checkpoint_callback(idx, total_files)
            continue
        file_findings = extract_findings_from_data(data, path)
        findings.extend(file_findings)
        parsed_count += 1
        if isinstance(files_cache, dict):
            files_cache[cache_key] = {"signature": signature, "contains_template_variables": True, "scan_result": {"status": "ok", "findings": file_findings}}
        if progress_callback:
            progress_callback(idx, total_files, parsed_count, len(skipped_files), path)
        if checkpoint_callback:
            checkpoint_callback(idx, total_files)
    return findings, skipped_files, parsed_file_paths, stats


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
        "--no-cache",
        action="store_true",
        help="Disable incremental file-result caching for this run.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable periodic progress output during long scans.",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="Disable built-in excludes such as Windows, Program Files, ProgramData, $Recycle.Bin, dot-prefixed folders, .git, node_modules, common virtualenv folders, all AppData trees, OneDrive, common media/output/cache/build directories, and VS Code history folders.",
    )
    return parser.parse_args()


def build_progress_callbacks(enabled: bool):
    if not enabled:
        return None, None, None, None

    start_time = time.monotonic()
    discovery_state = {"last_time": 0.0, "last_dirs": 0}
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

    def emit_discovery(event: str, current_path: Path, yaml_found: int) -> None:
        now = time.monotonic()
        if event == "root":
            print(f"[progress][{elapsed_label()}] scanning root {current_path}", file=sys.stderr, flush=True)
            discovery_state["last_time"] = now
            return
        if event == "zip":
            print(f"[progress][{elapsed_label()}] extracting and scanning zip {current_path}", file=sys.stderr, flush=True)
            discovery_state["last_time"] = now
            return
        if event == "root_done":
            print(
                f"[progress][{elapsed_label()}] finished root {current_path} | discovered {yaml_found} YAML files so far",
                file=sys.stderr,
                flush=True,
            )
            discovery_state["last_time"] = now
            return
        discovery_state["last_dirs"] += 1
        should_emit = discovery_state["last_dirs"] == 1 or discovery_state["last_dirs"] % 100 == 0 or now - discovery_state["last_time"] >= 5.0
        if not should_emit:
            return
        print(
            f"[progress][{elapsed_label()}] scanning directory {current_path} | discovered {yaml_found} YAML files",
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
            f"[progress][{elapsed_label()}] {index}/{total} files | parsed {parsed} | skipped {skipped} | {current_path}",
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
            f"[progress][{elapsed_label()}] prefilter {index}/{total} files | selected {selected} | skipped {skipped} | {current_path}",
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
    schema_backlog = report.get("schema_backlog_by_default", [])

    lines = [
        "Template Variable Gap Summary",
        f"  files discovered: {report.get('discovered_file_count', 0)}",
        f"  files prefiltered: {report.get('prefiltered_file_count', 0)}",
        f"  files parsed: {report.get('parsed_file_count', 0)}",
        f"  files skipped: {report.get('skipped_file_count', 0)}",
        f"  files with template variables: {report.get('files_with_template_variables_count', 0)}",
        f"  cache enabled: {report.get('cache_enabled', False)}",
        f"  default excludes: {report.get('default_excludes_enabled', True)}",
        f"  cache hits: {report.get('cache_hit_count', 0)}",
        f"  cache misses: {report.get('cache_miss_count', 0)}",
        "  cache invalidates on: analyzer, Quickstart support JSON, Kometa defaults, or source file changes",
        f"  template variable occurrences scanned: {report.get('template_variable_occurrences_scanned', 0)}",
        f"  verified gaps: {report.get('verified_gap_count', 0)}",
        f"  schema-declared verified gaps: {report.get('schema_declared_gap_count', 0)}",
        f"  kometa-declared verified gaps: {report.get('kometa_declared_gap_count', 0)}",
        f"  verified gaps missing from schema but supported by Kometa: {report.get('kometa_missing_schema_gap_count', 0)}",
        f"  value-shape verified gaps: {report.get('value_shape_verified_gap_count', 0)}",
        f"  overlay gaps: {len(overlays)}",
        f"  collection gaps: {len(collections)}",
        f"  playlist gaps: {len(playlists)}",
        f"  library gaps: {len(libraries)}",
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
            render_table("Overlay Gaps", overlays),
            render_table("Collection Gaps", collections),
        ]
    )
    if schema_backlog:
        lines.append(render_grouped_default_table("Schema Backlog By Default", schema_backlog))
    if playlists:
        lines.append(render_table("Playlist Gaps", playlists))
    if libraries:
        lines.append(render_table("Library Gaps", libraries))
    skipped_files = report.get("skipped_files", [])
    if skipped_files:
        lines.append("Skipped Files")
        for item in skipped_files[:10]:
            lines.append(f"  {item.get('file')}: {item.get('error_type')}")
        remaining = len(skipped_files) - min(len(skipped_files), 10)
        if remaining > 0:
            lines.append(f"  ... plus {remaining} more skipped files")
    if report.get("cache_enabled", False):
        lines.append(f"Cache file: {report.get('cache_path')}")
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
    )
    cache_path = get_cache_path(root, args.cache_path)
    verification_checkpoint_dir = get_verification_checkpoint_dir(root)
    verification_meta_path = verification_checkpoint_dir / "metadata.json"
    verification_rows_path = verification_checkpoint_dir / "all_rows.ndjson"
    cache_enabled = not args.no_cache
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
    )
    candidate_files, prefilter_skipped_files, prefilter_cache_stats = prefilter_yaml_files(
        input_files,
        cache_data=cache_data if cache_enabled else None,
        progress_callback=prefilter_progress_callback,
        checkpoint_callback=cache_persist,
    )

    try:
        qs_collections = build_qs_collection_map(qs_collections_path)
        qs_overlays = build_qs_overlay_map(qs_overlays_path)
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
                f"[progress][prefilter] selected {len(candidate_files)} YAML files containing template_variables",
                file=sys.stderr,
                flush=True,
            )
        uploaded, parse_skipped_files, parsed_file_paths, parse_cache_stats = scan_uploaded_configs(
            candidate_files,
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
                default_files = resolve_default_paths(alias or "", kind, kometa_defaults)
                name_verified, matched_files = key_is_valid_for_default(key, default_files)
            elif kind == "overlay":
                supported = key in qs_overlays.get(alias or "", set())
                default_files = resolve_default_paths(alias or "", kind, kometa_defaults)
                name_verified, matched_files = key_is_valid_for_default(key, default_files)
            elif kind == "playlist":
                supported = key in qs_playlist_keys
                default_files = resolve_default_paths(alias or "", kind, kometa_defaults)
                name_verified, matched_files = key_is_valid_for_default(key, default_files)
            else:
                supported = key in qs_library_keys or key in qs_global_keys
                name_verified = True
                matched_files = []

            value_shape_verified, value_shape_rule = infer_value_shape(row["value"], key)
            schema_declared = key in schema_keys
            validation_level = classify_validation_level(supported, schema_declared, name_verified)
            out = dict(row)
            out["supported_in_quickstart"] = supported
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

        by_kind: dict[str, list[dict[str, Any]]] = {"overlay": [], "collection": [], "playlist": [], "library": []}
        for item in serializable_ranked:
            kind_key = item["kind"] if item["kind"] in by_kind else "library"
            by_kind[kind_key].append(item)

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

        malformed_files = [item for item in skipped_files if item.get("malformed") is True]

        report = {
            "quickstart_root": str(root),
            "inputs": [str(p) for p in inputs],
            "cache_enabled": cache_enabled,
            "cache_path": str(cache_path),
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
            "parsed_files": sorted(parsed_file_paths),
            "uploaded_files_scanned": sorted({row["file"] for row in uploaded}),
            "skipped_files": skipped_files,
            "skipped_file_count": len(skipped_files),
            "malformed_files": malformed_files,
            "malformed_file_count": len(malformed_files),
            "parsed_file_count": len(parsed_file_paths),
            "files_with_template_variables_count": len(sorted({row["file"] for row in uploaded})),
            "template_variable_occurrences_scanned": len(uploaded),
            "verified_gap_count": len(serializable_ranked),
            "schema_declared_gap_count": sum(1 for item in serializable_ranked if item["schema_declared"]),
            "kometa_declared_gap_count": sum(1 for item in serializable_ranked if item["kometa_declared"]),
            "kometa_missing_schema_gap_count": sum(1 for item in serializable_ranked if item["kometa_declared"] and not item["schema_declared"]),
            "value_shape_verified_gap_count": sum(1 for item in serializable_ranked if item["value_shape_verified_occurrences"] > 0),
            "verification_notes": {
                "name_verified": "Key name matched a variable declared or referenced in the corresponding built-in Kometa default or shared built-in templates.yml.",
                "schema_declared": "Key name was found in Kometa's bundled config-schema.json. This is a secondary signal because the schema is not fully exhaustive.",
                "kometa_declared": "Key name was found in Kometa's bundled built-in defaults/templates, which is treated as the stronger local source of truth.",
                "validation_level": "works_in_kometa_missing_from_quickstart_and_schema means the key was not found in Quickstart or schema, but was found in Kometa built-in defaults/templates.",
                "value_shape_verified": "Best-effort local heuristic that the supplied value looks like the expected basic type. Null means no reliable local rule was inferred.",
                "runtime_guaranteed": False,
            },
            "verified_gaps_ranked": serializable_ranked,
            "verified_gaps_by_kind": by_kind,
            "schema_backlog_by_default": schema_backlog_by_default,
            "all_rows": all_rows,
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
