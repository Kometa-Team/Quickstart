"""Bundle / overlay-image asset helpers extracted from ``quickstart.py``.

This module owns the logic for:

* **Bundle inspection** -- decide which paths inside an uploaded config
  ZIP are safe to extract (``is_allowed_bundle_member``,
  ``normalize_bundle_member_name``, ``yaml_path_suffix``,
  ``is_bundled_overlay_image_archive_member``).
* **Path rewriting on import** -- after a bundle is extracted into a
  temp directory, rewrite YAML library/overlay-image references so they
  point at the extracted on-disk files
  (``rewrite_bundle_library_paths``, ``rewrite_bundle_overlay_image_paths``).
* **Managed-location resolution** -- map between on-disk paths under
  ``CONFIG_DIR`` and the canonical "config-relative" archive paths used
  inside bundles and in YAML
  (``managed_bundle_location_for_path``, the overlay-image variants,
  ``display_managed_overlay_image_location``).
* **Bundle build** -- collect referenced library files + overlay-image
  source files + custom fonts and pack them into a ZIP for the
  ``/download`` and ``/download_redacted`` routes
  (``iter_bundle_artifacts``, ``iter_overlay_source_bundle_artifacts``,
  ``bundle_write_path``, ``bundle_write_artifact``,
  ``bundle_artifacts_from_yaml``, ``build_config_bundle``,
  ``get_custom_font_files``, ``safe_bundle_name``,
  ``normalize_config_name``).

These functions lost their leading ``_`` when moved here -- the module
*is* the namespace now.  ``quickstart.py`` and the routes that still
live there re-import each one under its original ``_leading_underscore``
alias so callers (and the YAML preview blueprint introduced in PR E)
work without modification.

External dependencies (intentionally narrow):

* ``modules.helpers`` -- ``CONFIG_DIR``, ``ALLOWED_EXTENSIONS``,
  ``FONT_EXTENSIONS``, ``MANAGED_OVERLAY_IMAGE_DIR``,
  ``redact_sensitive_data``, custom-fonts helpers
* ``modules.importer`` -- ``load_yaml_config``
* ``modules.validations`` -- ``normalize_overlay_source_override_file_location``
* ``modules.library_file_entries`` -- the four already-modular library
  path helpers (``_is_bundled_library_archive_member``,
  ``_normalized_managed_library_relative_path``,
  ``_parse_managed_library_relative_path``,
  ``_resolve_local_library_source``).
"""

import hashlib
import io
import os
import re
import zipfile
from io import BytesIO
from pathlib import Path

from ruamel.yaml import YAML
from werkzeug.utils import secure_filename

from modules import helpers, importer, validations
from modules.library_file_entries import (
    LIBRARY_FILE_KINDS,
    LOCAL_LIBRARY_FILE_TYPES,
    _is_bundled_library_archive_member,
    _normalized_managed_library_relative_path,
    _parse_managed_library_relative_path,
    _resolve_local_library_source,
)


def yaml_path_suffix(path_value):
    return str(path_value or "").strip().lower().endswith((".yml", ".yaml"))


def normalize_bundle_member_name(path_value):
    normalized = str(path_value or "").replace("\\", "/").lstrip("/")
    return "/".join(part for part in normalized.split("/") if part)


def is_allowed_bundle_member(path_value):
    normalized = normalize_bundle_member_name(path_value)
    if not normalized:
        return True
    lowered = normalized.lower()
    if _is_bundled_library_archive_member(normalized):
        return yaml_path_suffix(normalized)
    if is_bundled_overlay_image_archive_member(normalized):
        return lowered.endswith(tuple(f".{ext}" for ext in helpers.ALLOWED_EXTENSIONS))
    if yaml_path_suffix(normalized):
        return True
    if lowered.endswith((".ttf", ".otf")):
        return True
    if lowered == "readme.txt":
        return True
    return False


def dump_yaml_text(data):
    buffer = io.StringIO()
    YAML().dump(data, buffer)
    return buffer.getvalue()


def managed_bundle_location_for_path(path):
    config_root = Path(helpers.CONFIG_DIR).resolve()
    try:
        relative = Path(path).resolve().relative_to(config_root)
    except Exception:
        return None
    normalized_relative = _normalized_managed_library_relative_path(Path(*relative.parts).as_posix())
    if not normalized_relative:
        return None
    info = _parse_managed_library_relative_path(normalized_relative)
    if not info or info["layout"] != "config_first":
        return None
    return normalized_relative


def is_overlay_source_override_file_key(key):
    normalized = str(key or "").strip()
    return normalized == "file" or normalized.startswith("file_")


def parse_managed_overlay_image_relative_path(path_value):
    normalized = str(path_value or "").replace("\\", "/").lstrip("/")
    if not normalized:
        return None
    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 3 and parts[1] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        return {"config_name": parts[0], "remainder": parts[2:], "layout": "config_root"}
    if len(parts) >= 4 and parts[0] == "config" and parts[2] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        return {"config_name": parts[1], "remainder": parts[3:], "layout": "display"}
    return None


def normalized_managed_overlay_image_relative_path(path_value):
    info = parse_managed_overlay_image_relative_path(path_value)
    if not info:
        return None
    return Path(info["config_name"], helpers.MANAGED_OVERLAY_IMAGE_DIR, *info["remainder"]).as_posix()


def is_bundled_overlay_image_archive_member(path_value):
    return normalized_managed_overlay_image_relative_path(str(path_value or "").replace("\\", "/").lstrip("/")) is not None


def resolve_local_overlay_image_source(location):
    raw = str(location or "").strip()
    if not raw:
        return None
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        try:
            return expanded.resolve()
        except OSError:
            return expanded
    managed_relative = normalized_managed_overlay_image_relative_path(expanded)
    if managed_relative:
        try:
            return (Path(helpers.CONFIG_DIR) / managed_relative).resolve()
        except OSError:
            return Path(helpers.CONFIG_DIR) / managed_relative
    normalized_parts = [part for part in str(expanded).replace("\\", "/").split("/") if part]
    if normalized_parts and normalized_parts[0] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        try:
            return (Path(helpers.CONFIG_DIR) / expanded).resolve()
        except OSError:
            return Path(helpers.CONFIG_DIR) / expanded
    try:
        return (Path.cwd() / expanded).resolve()
    except OSError:
        return Path.cwd() / expanded


def managed_overlay_image_bundle_location_for_path(path):
    config_root = Path(helpers.CONFIG_DIR).resolve()
    try:
        relative = Path(path).resolve().relative_to(config_root)
    except Exception:
        return None
    normalized_relative = normalized_managed_overlay_image_relative_path(Path(*relative.parts).as_posix())
    if not normalized_relative:
        return None
    return normalized_relative


def safe_overlay_bundle_slug(value, fallback):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    slug = slug.strip("._-")
    return slug or fallback


def display_managed_overlay_image_location(location):
    raw = str(location or "").strip().replace("\\", "/")
    if not raw:
        return raw
    normalized_relative = normalized_managed_overlay_image_relative_path(raw)
    if normalized_relative:
        return Path("config", *normalized_relative.split("/")).as_posix()
    return raw


def normalize_overlay_source_override_entries_payload(libraries_data, config_name):
    if not isinstance(libraries_data, dict):
        return {}, [], False

    normalized = dict(libraries_data)
    errors = []
    changed = False
    pattern = re.compile(r"^(?P<library_id>(?:mov|sho)-library_.+?)-(?P<builder>movie|show|season|episode)-template_(?P<overlay_id>[^\[]+)\[(?P<template_key>[^\]]+)\]$")

    for key, raw_value in list(normalized.items()):
        if not isinstance(key, str) or "-template_overlay_" not in key or not key.endswith("]"):
            continue
        match = pattern.match(key)
        if not match:
            continue
        template_key = str(match.group("template_key") or "").strip()
        if not is_overlay_source_override_file_key(template_key):
            continue
        location = str(raw_value or "").strip()
        if not location:
            continue
        try:
            normalized_location, entry_changed = validations.normalize_overlay_source_override_file_location(
                location,
                config_name=config_name,
                library_id=match.group("library_id"),
                overlay_id=match.group("overlay_id"),
                template_key=template_key,
            )
        except ValueError as exc:
            errors.append(f"{match.group('library_id')}: {match.group('overlay_id')}[{template_key}] {exc}")
            continue
        normalized[key] = normalized_location
        changed = changed or bool(entry_changed) or normalized_location != location

    return normalized, errors, changed


def rewrite_bundle_library_paths(config_data, bundle_root):
    if not isinstance(config_data, dict):
        return config_data
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return config_data
    root = Path(bundle_root).resolve()
    for lib_cfg in libraries.values():
        if not isinstance(lib_cfg, dict):
            continue
        for kind in LIBRARY_FILE_KINDS:
            entries = lib_cfg.get(kind)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for entry_type in LOCAL_LIBRARY_FILE_TYPES:
                    location = entry.get(entry_type)
                    if not location:
                        continue
                    raw_location = str(location).strip()
                    candidate = root / Path(raw_location)
                    if not candidate.exists():
                        normalized_relative = _normalized_managed_library_relative_path(raw_location)
                        if normalized_relative:
                            candidate = root / Path(normalized_relative)
                    if not candidate.exists():
                        continue
                    entry[entry_type] = str(candidate.resolve())
                    break
    return config_data


def rewrite_bundle_overlay_image_paths(config_data, bundle_root):
    if not isinstance(config_data, dict):
        return config_data
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return config_data
    root = Path(bundle_root).resolve()
    for lib_cfg in libraries.values():
        if not isinstance(lib_cfg, dict):
            continue
        overlay_entries = lib_cfg.get("overlay_files")
        if not isinstance(overlay_entries, list):
            continue
        for entry in overlay_entries:
            if not isinstance(entry, dict):
                continue
            template_vars = entry.get("template_variables")
            if not isinstance(template_vars, dict):
                continue
            for key, value in list(template_vars.items()):
                if not is_overlay_source_override_file_key(key) or not value:
                    continue
                raw_location = str(value).strip()
                candidate = root / Path(raw_location)
                if not candidate.exists():
                    normalized_relative = normalized_managed_overlay_image_relative_path(raw_location)
                    if normalized_relative:
                        candidate = root / Path(normalized_relative)
                if not candidate.exists():
                    continue
                template_vars[key] = str(candidate.resolve())
    return config_data


def iter_bundle_artifacts(config_data):
    seen = set()
    if not isinstance(config_data, dict):
        return []
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return []
    artifacts = []
    for lib_cfg in libraries.values():
        if not isinstance(lib_cfg, dict):
            continue
        for kind in LIBRARY_FILE_KINDS:
            entries = lib_cfg.get(kind)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for entry_type in LOCAL_LIBRARY_FILE_TYPES:
                    location = entry.get(entry_type)
                    if not location:
                        continue
                    raw_location = str(location).strip()
                    if not raw_location:
                        continue
                    source_path = _resolve_local_library_source(raw_location)
                    if source_path is None:
                        continue
                    if not source_path.exists():
                        continue
                    archive_path = managed_bundle_location_for_path(source_path)
                    if not archive_path:
                        archive_path = _normalized_managed_library_relative_path(raw_location) or Path(raw_location).as_posix()
                    dedupe_key = (str(source_path), archive_path)
                    if dedupe_key in seen:
                        break
                    seen.add(dedupe_key)
                    artifacts.append(
                        {
                            "source": source_path,
                            "archive": archive_path,
                            "type": entry_type,
                        }
                    )
                    break
    return artifacts


def iter_overlay_source_bundle_artifacts(config_data, config_name):
    seen = set()
    changed = False
    if not isinstance(config_data, dict):
        return [], changed
    libraries = config_data.get("libraries")
    if not isinstance(libraries, dict):
        return [], changed

    config_slug = normalize_config_name(config_name)
    artifacts = []
    for library_name, lib_cfg in libraries.items():
        if not isinstance(lib_cfg, dict):
            continue
        overlay_entries = lib_cfg.get("overlay_files")
        if not isinstance(overlay_entries, list):
            continue
        for entry in overlay_entries:
            if not isinstance(entry, dict):
                continue
            template_vars = entry.get("template_variables")
            if not isinstance(template_vars, dict):
                continue
            overlay_name = str(entry.get("default") or "overlay").strip()
            for template_key, raw_value in list(template_vars.items()):
                if not is_overlay_source_override_file_key(template_key):
                    continue
                raw_location = str(raw_value or "").strip()
                if not raw_location:
                    continue
                source_path = resolve_local_overlay_image_source(raw_location)
                if source_path is None or not source_path.exists() or not source_path.is_file():
                    continue

                archive_path = managed_overlay_image_bundle_location_for_path(source_path)
                if not archive_path:
                    library_slug = safe_overlay_bundle_slug(library_name, "library")
                    overlay_slug = safe_overlay_bundle_slug(overlay_name, "overlay")
                    template_slug = safe_overlay_bundle_slug(template_key, "image")
                    stem_slug = safe_overlay_bundle_slug(source_path.stem, "image")
                    digest_source = f"{str(source_path).replace('\\', '/').lower()}|{library_slug}|{overlay_slug}|{template_slug}"
                    digest = hashlib.sha1(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:10]
                    suffix = source_path.suffix or ".png"
                    archive_path = Path(
                        config_slug,
                        helpers.MANAGED_OVERLAY_IMAGE_DIR,
                        library_slug,
                        overlay_slug,
                        f"{template_slug}_{stem_slug}_{digest}{suffix}",
                    ).as_posix()

                display_location = display_managed_overlay_image_location(archive_path)
                if raw_location != display_location:
                    template_vars[template_key] = display_location
                    changed = True

                dedupe_key = (str(source_path), archive_path)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                artifacts.append({"source": source_path, "archive": archive_path, "type": "overlay_image"})

    return artifacts, changed


def bundle_write_path(zf, archive_name, source_path, redacted=False):
    source_path = Path(source_path)
    archive_name = Path(archive_name).as_posix()
    if redacted and source_path.is_file() and yaml_path_suffix(source_path.name):
        text = source_path.read_text(encoding="utf-8", errors="replace")
        zf.writestr(archive_name, helpers.redact_sensitive_data(text))
        return
    zf.write(source_path, archive_name)


def bundle_write_artifact(zf, artifact, redacted=False):
    source_path = Path((artifact or {}).get("source", ""))
    archive_path = Path(str((artifact or {}).get("archive", "")).replace("\\", "/"))
    if not source_path.exists() or not str(archive_path):
        return
    if source_path.is_dir():
        for child in sorted(source_path.rglob("*"), key=lambda item: item.as_posix().lower()):
            if not child.is_file():
                continue
            relative_child = child.relative_to(source_path)
            bundle_write_path(zf, (archive_path / relative_child).as_posix(), child, redacted=redacted)
        return
    bundle_write_path(zf, archive_path.as_posix(), source_path, redacted=redacted)


def normalize_config_name(raw_name: str | None) -> str:
    name = (raw_name or "").strip().lower().replace(" ", "_")
    return name or "default"


def safe_bundle_name(raw_name: str | None) -> str:
    safe = secure_filename(normalize_config_name(raw_name))
    return safe or "default"


def get_custom_font_files(config_name: str | None = None) -> list[Path]:
    font_files: list[Path] = []
    seen: set[str] = set()
    candidate_dirs: list[Path] = []
    if config_name:
        helpers.migrate_legacy_custom_fonts_to_config(config_name)
        candidate_dirs.append(helpers.get_custom_fonts_dir(config_name))
    candidate_dirs.append(helpers.get_legacy_custom_fonts_dir())
    for custom_dir in candidate_dirs:
        if not custom_dir.is_dir():
            continue
        for entry in sorted(custom_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_file() or entry.suffix.lower() not in helpers.FONT_EXTENSIONS:
                continue
            if entry.name in seen:
                continue
            font_files.append(entry)
            seen.add(entry.name)
    return font_files


def bundle_artifacts_from_yaml(yaml_text, config_name=None):
    parsed = importer.load_yaml_config(yaml_text)
    if not parsed:
        return [], yaml_text
    artifact_files = list(iter_bundle_artifacts(parsed))
    overlay_artifacts, overlay_changed = iter_overlay_source_bundle_artifacts(parsed, config_name)
    artifact_files.extend(overlay_artifacts)
    if overlay_changed:
        return artifact_files, dump_yaml_text(parsed)
    return artifact_files, yaml_text


def build_config_bundle(
    config_text: str,
    config_filename: str,
    font_files: list[Path],
    artifact_files: list[dict] | None = None,
    config_name: str | None = None,
    redacted: bool = False,
) -> BytesIO | None:
    artifact_files = artifact_files or []
    if not config_text or (not font_files and not artifact_files):
        return None
    name = normalize_config_name(config_name)
    font_names = [font.name for font in font_files]
    has_artifacts = bool(artifact_files)
    readme_lines = [
        "Quickstart config bundle",
        f"Config name: {name}",
        "",
        "This bundle includes:",
        f"- {config_filename}",
    ]
    if font_names:
        readme_lines.append(f"- {name}/fonts/ (custom fonts uploaded in Quickstart)")
        readme_lines.append(f"- Fonts included: {', '.join(font_names)}")
    if has_artifacts:
        readme_lines.append(f"- {name}/metadata_files/, {name}/collection_files/, {name}/overlay_files/, {name}/overlay_images/ (config-owned library files and overlay images)")
    readme_lines += [
        "",
        "Install steps:",
        "1) Copy the config file into your Kometa config folder (config/).",
    ]
    if font_names:
        readme_lines.append(f"2) Copy the font files from {name}/fonts/ into your Kometa config/fonts/ folder.")
    if has_artifacts:
        readme_lines.append(f"3) Copy {name}/ into your Kometa config/ folder.")
    readme_lines += [
        "",
        "Note: Validate Kometa and Run Now both sync config-owned library files automatically.",
        "Note: The Quickstart Run Now button also syncs referenced fonts automatically.",
        "This bundle is for manual installs.",
    ]
    if redacted:
        readme_lines += [
            "",
            "This bundle uses a redacted config and is safe to share.",
            "Review before sharing in case you manually added sensitive data.",
        ]
    readme_lines.append("")
    bundle = BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(config_filename, config_text)
        for font_path in font_files:
            zf.write(font_path, f"{name}/fonts/{font_path.name}")
        for artifact in artifact_files:
            bundle_write_artifact(zf, artifact, redacted=redacted)
        zf.writestr("README.txt", "\n".join(readme_lines))
    bundle.seek(0)
    return bundle
