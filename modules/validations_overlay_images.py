"""Overlay-source-override image handling.

Split out of ``modules.validations`` -- this is the largest thematic
cluster in that file (~450 lines) and it's completely self-contained:
image bytes, formats, dimensions, validation, storage, cleanup.

## What is an "overlay source override"?

Kometa's overlay YAML templates support Ratings, Language, Resolution,
etc. as "overlays".  Each overlay template has one or more image assets
that get composited onto poster art.  Users can override those images
per-library by uploading their own (either as a URL, git reference,
repo reference, or a local file path).

This module handles:

* **Validation** of uploaded images (PNG/WEBP only, transparent,
  size <= 1MB, dimension warnings when unusually large/small).
* **Storage** of override images in managed-config folders under
  ``<config>/<managed-overlay-image-dir>/<library>/<overlay>/``.
* **Cleanup** of orphaned override images.
* **Server wrappers** (``*_server`` functions) that return Flask
  ``jsonify()`` responses for the /validate-* endpoints.

## Public API

* ``MAX_OVERLAY_SOURCE_OVERRIDE_BYTES`` and the format-suffix /
  content-type / dimension constants.
* ``normalize_overlay_source_override_file_location(...)`` --
  copy a source file into managed storage, return the display path.
* ``store_overlay_source_override_image_bytes(...)`` -- write raw
  bytes into managed storage.
* ``validate_overlay_source_override_payload(data)`` --
  main validator (file / url / git / repo dispatch).
* ``make_overlay_source_override_local_payload(data)`` --
  fetch a remote source and save it locally.
* ``cleanup_overlay_source_override_payload(data)`` --
  prune orphaned override images.
* ``validate_overlay_source_override_server(data)``,
  ``make_overlay_source_override_local_server(data)``,
  ``cleanup_overlay_source_override_server(data)`` --
  Flask endpoint wrappers around the above.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import urllib.parse
import re
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from flask import jsonify

from modules import helpers, path_validation, url_validation
from modules.validations_shared import (
    _resolve_managed_library_path,
    _saved_custom_repo_base,
)

MAX_OVERLAY_SOURCE_OVERRIDE_BYTES = 1024 * 1024 - 1
OVERLAY_SOURCE_OVERRIDE_FORMAT_SUFFIXES = {
    "png": {".png"},
    "webp": {".webp"},
}
OVERLAY_SOURCE_OVERRIDE_FORMAT_CONTENT_TYPES = {
    "png": {"image/png", "image/x-png"},
    "webp": {"image/webp"},
}
OVERLAY_SOURCE_OVERRIDE_LARGE_DIMENSION = 800
OVERLAY_SOURCE_OVERRIDE_MIN_DIMENSION = 20
OVERLAY_SOURCE_OVERRIDE_POSTER_SIZES = (
    (1000, 1500),
    (1920, 1080),
)


# ---------------------------------------------------------------------------
# Slug + display helpers
# ---------------------------------------------------------------------------


def _safe_overlay_image_slug(value, fallback):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    slug = slug.strip("._-")
    return slug or fallback


def _display_managed_overlay_image_location(location):
    raw = str(location or "").strip().replace("\\", "/")
    if not raw:
        return raw
    normalized = raw.lstrip("/")
    if normalized.lower().startswith("config/"):
        return normalized
    return Path("config", normalized).as_posix()


def _is_managed_overlay_image_path(path):
    try:
        relative = Path(path).resolve().relative_to(Path(helpers.CONFIG_DIR).resolve())
    except Exception:
        return False
    parts = list(relative.parts)
    return len(parts) >= 2 and parts[1] == helpers.MANAGED_OVERLAY_IMAGE_DIR


# ---------------------------------------------------------------------------
# Storage: copy / write / scope resolution
# ---------------------------------------------------------------------------


def normalize_overlay_source_override_file_location(location, *, config_name, library_id, overlay_id, template_key):
    normalized_name = helpers.require_config_name_for_storage(config_name, context="Overlay image override storage")
    raw_location = str(location or "").strip()
    if not raw_location:
        raise ValueError("Overlay image source value is required.")

    source_path = Path(_resolve_managed_library_path(raw_location))
    try:
        source_path = source_path.resolve()
    except OSError:
        source_path = source_path

    if not source_path.exists() or not source_path.is_file():
        raise ValueError("Overlay image file path does not exist.")

    if _is_managed_overlay_image_path(source_path):
        relative = source_path.relative_to(Path(helpers.CONFIG_DIR).resolve())
        return _display_managed_overlay_image_location(relative), False

    library_slug = _safe_overlay_image_slug(library_id, "library")
    overlay_slug = _safe_overlay_image_slug(overlay_id, "overlay")
    template_slug = _safe_overlay_image_slug(template_key, "image")
    stem_slug = _safe_overlay_image_slug(source_path.stem, "image")
    source_key = str(source_path).replace("\\", "/").lower()
    digest_source = f"{source_key}|{library_slug}|{overlay_slug}|{template_slug}"
    digest = hashlib.sha1(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:10]
    suffix = source_path.suffix or ".png"

    target_dir = helpers.get_managed_config_artifact_root(normalized_name) / helpers.MANAGED_OVERLAY_IMAGE_DIR / library_slug / overlay_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = (target_dir / f"{template_slug}_{stem_slug}_{digest}{suffix}").resolve()
    if source_path != target_path:
        shutil.copy2(source_path, target_path)

    relative = target_path.relative_to(Path(helpers.CONFIG_DIR).resolve())
    return _display_managed_overlay_image_location(relative), True


def store_overlay_source_override_image_bytes(
    image_bytes,
    *,
    config_name,
    library_id,
    overlay_id,
    template_key,
    source_name="image.png",
    image_format=None,
):
    normalized_name = helpers.require_config_name_for_storage(config_name, context="Overlay image override storage")
    content = image_bytes or b""
    if not content:
        raise ValueError("Overlay image source bytes are required.")

    source_label = str(source_name or "image.png").strip()
    source_path = Path(source_label)
    inferred_format = str(image_format or source_path.suffix.lstrip(".") or "png").strip().lower()
    suffix = f".{inferred_format}" if inferred_format else ".png"

    library_slug = _safe_overlay_image_slug(library_id, "library")
    overlay_slug = _safe_overlay_image_slug(overlay_id, "overlay")
    template_slug = _safe_overlay_image_slug(template_key, "image")
    stem_slug = _safe_overlay_image_slug(source_path.stem, "image")
    digest_source = f"{hashlib.sha1(content).hexdigest()}|{library_slug}|{overlay_slug}|{template_slug}"
    digest = hashlib.sha1(digest_source.encode("utf-8", errors="ignore")).hexdigest()[:10]

    target_dir = helpers.get_managed_config_artifact_root(normalized_name) / helpers.MANAGED_OVERLAY_IMAGE_DIR / library_slug / overlay_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = (target_dir / f"{template_slug}_{stem_slug}_{digest}{suffix}").resolve()
    target_path.write_bytes(content)

    relative = target_path.relative_to(Path(helpers.CONFIG_DIR).resolve())
    return _display_managed_overlay_image_location(relative)


def _managed_overlay_scope_dir(*, config_name, library_id, overlay_id):
    normalized_name = helpers.require_config_name_for_storage(config_name, context="Managed overlay image cleanup")
    library_slug = _safe_overlay_image_slug(library_id, "library")
    overlay_slug = _safe_overlay_image_slug(overlay_id, "overlay")
    return helpers.get_managed_config_artifact_root(normalized_name) / helpers.MANAGED_OVERLAY_IMAGE_DIR / library_slug / overlay_slug


def _resolve_scoped_managed_overlay_image_path(location, *, config_name, library_id, overlay_id):
    raw_location = str(location or "").strip()
    if not raw_location:
        return None

    scope_dir = _managed_overlay_scope_dir(config_name=config_name, library_id=library_id, overlay_id=overlay_id)
    try:
        scope_resolved = scope_dir.resolve()
    except OSError:
        scope_resolved = scope_dir

    candidate = Path(_resolve_managed_library_path(raw_location))
    try:
        candidate_resolved = candidate.resolve()
    except OSError:
        candidate_resolved = candidate

    try:
        candidate_resolved.relative_to(scope_resolved)
    except Exception:
        return None
    return candidate_resolved


def _prune_empty_managed_overlay_dirs(path, *, config_name):
    config_root = helpers.get_managed_config_artifact_root(config_name)
    try:
        stop_dir = config_root.resolve()
    except OSError:
        stop_dir = config_root

    current = Path(path).parent
    while current.exists():
        try:
            current_resolved = current.resolve()
        except OSError:
            current_resolved = current
        if current_resolved == stop_dir:
            break
        try:
            next(current.iterdir())
            break
        except StopIteration:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent
        except OSError:
            break


def _coerce_overlay_source_locations(values):
    if isinstance(values, (list, tuple, set)):
        return [str(item or "").strip() for item in values if str(item or "").strip()]
    text = str(values or "").strip()
    return [text] if text else []


# ---------------------------------------------------------------------------
# Cleanup: remove orphaned override images
# ---------------------------------------------------------------------------


def cleanup_overlay_source_override_payload(data):
    config_name = str(data.get("config_name") or "").strip()
    library_id = str(data.get("library_id") or "").strip()
    overlay_id = str(data.get("overlay_id") or "").strip()
    if not config_name or not library_id or not overlay_id:
        return False, "Config, library, and overlay are required for overlay source cleanup.", {}

    remove_locations = _coerce_overlay_source_locations(data.get("remove_locations"))
    retain_locations = _coerce_overlay_source_locations(data.get("retain_locations"))
    sweep = helpers.booler(data.get("sweep"))

    removed = []
    skipped = []
    errors = []

    retain_paths = set()
    for location in retain_locations:
        resolved = _resolve_scoped_managed_overlay_image_path(
            location,
            config_name=config_name,
            library_id=library_id,
            overlay_id=overlay_id,
        )
        if resolved:
            retain_paths.add(resolved)

    processed = set()
    for location in remove_locations:
        resolved = _resolve_scoped_managed_overlay_image_path(
            location,
            config_name=config_name,
            library_id=library_id,
            overlay_id=overlay_id,
        )
        if not resolved:
            skipped.append(location)
            continue
        if resolved in processed:
            continue
        processed.add(resolved)
        if resolved in retain_paths:
            skipped.append(location)
            continue
        if not resolved.exists() or not resolved.is_file():
            skipped.append(location)
            continue
        try:
            resolved.unlink()
            relative = resolved.relative_to(Path(helpers.CONFIG_DIR).resolve())
            removed.append(_display_managed_overlay_image_location(relative))
            _prune_empty_managed_overlay_dirs(resolved, config_name=config_name)
        except Exception as exc:
            errors.append(f"Failed to remove {location}: {exc}")

    if sweep:
        scope_dir = _managed_overlay_scope_dir(config_name=config_name, library_id=library_id, overlay_id=overlay_id)
        if scope_dir.exists():
            try:
                for candidate in scope_dir.rglob("*"):
                    if not candidate.is_file():
                        continue
                    try:
                        candidate_resolved = candidate.resolve()
                    except OSError:
                        candidate_resolved = candidate
                    if candidate_resolved in retain_paths or candidate_resolved in processed:
                        continue
                    try:
                        candidate.unlink()
                        relative = candidate_resolved.relative_to(Path(helpers.CONFIG_DIR).resolve())
                        removed.append(_display_managed_overlay_image_location(relative))
                        processed.add(candidate_resolved)
                        _prune_empty_managed_overlay_dirs(candidate_resolved, config_name=config_name)
                    except Exception as exc:
                        errors.append(f"Failed to sweep {candidate}: {exc}")
            except Exception as exc:
                errors.append(f"Failed to sweep managed overlay image directory {scope_dir}: {exc}")

    return True, None, {"removed": removed, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Validation: bytes -> format / dimensions / transparency
# ---------------------------------------------------------------------------


def _validate_allowed_image_format(image_format, label):
    fmt = str(image_format or "").strip().lower()
    if fmt not in helpers.ALLOWED_EXTENSIONS:
        return False, f"{label}: Invalid file type. Allowed: {helpers.allowed_extensions_string()}."
    return True, None


def _validate_overlay_badge_image(image_format, image_obj, label):
    fmt = str(image_format or "").strip().lower()
    if fmt not in {"png", "webp"}:
        return False, f"{label}: Overlay source overrides must be PNG or WEBP images."

    rgba = image_obj.convert("RGBA")
    alpha_min, alpha_max = rgba.getchannel("A").getextrema()
    if alpha_max == 255 and alpha_min == 255:
        return False, f"{label}: Overlay source overrides must include transparency."

    return True, None


def _validate_overlay_badge_size(image_bytes, label):
    size_bytes = len(image_bytes or b"")
    if size_bytes > MAX_OVERLAY_SOURCE_OVERRIDE_BYTES:
        max_mb = MAX_OVERLAY_SOURCE_OVERRIDE_BYTES / (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        return False, f"{label}: Overlay source overrides must be {max_mb:.0f} MB or smaller. Current file is {actual_mb:.2f} MB."
    return True, None


def _normalize_content_type(content_type):
    return str(content_type or "").split(";", 1)[0].strip().lower()


def _validate_overlay_badge_suffix(source_name, image_format, label):
    suffix = Path(str(source_name or "").strip()).suffix.lower()
    if not suffix:
        return False, f"{label}: Overlay source override path must end in .{image_format}."
    allowed_suffixes = OVERLAY_SOURCE_OVERRIDE_FORMAT_SUFFIXES.get(str(image_format or "").strip().lower(), set())
    if suffix not in allowed_suffixes:
        expected = " or ".join(sorted(allowed_suffixes)) if allowed_suffixes else f".{image_format}"
        return False, f"{label}: Overlay source override path suffix must match the detected {str(image_format).upper()} format ({expected})."
    return True, None


def _validate_overlay_badge_content_type(content_type, image_format, label):
    normalized = _normalize_content_type(content_type)
    if not normalized:
        return False, f"{label}: Remote overlay image must return a Content-Type header."
    allowed_content_types = OVERLAY_SOURCE_OVERRIDE_FORMAT_CONTENT_TYPES.get(str(image_format or "").strip().lower(), set())
    if normalized not in allowed_content_types:
        expected = " or ".join(sorted(allowed_content_types)) if allowed_content_types else f"image/{image_format}"
        return False, f"{label}: Remote overlay image Content-Type must match the detected {str(image_format).upper()} format ({expected})."
    return True, None


def _collect_overlay_badge_warnings(width, height):
    warnings = []

    if width > OVERLAY_SOURCE_OVERRIDE_LARGE_DIMENSION or height > OVERLAY_SOURCE_OVERRIDE_LARGE_DIMENSION:
        warnings.append(f"This image is valid, but its dimensions ({width}x{height}) are unusually large for a badge overlay.")

    if width < OVERLAY_SOURCE_OVERRIDE_MIN_DIMENSION or height < OVERLAY_SOURCE_OVERRIDE_MIN_DIMENSION:
        warnings.append(f"This image is valid, but its dimensions ({width}x{height}) are extremely small and may render poorly.")

    for target_width, target_height in OVERLAY_SOURCE_OVERRIDE_POSTER_SIZES:
        width_match = abs(width - target_width) <= max(40, int(target_width * 0.05))
        height_match = abs(height - target_height) <= max(40, int(target_height * 0.05))
        if width_match and height_match:
            warnings.append(f"This image is valid, but its dimensions ({width}x{height}) are close to a full poster/canvas size and may not behave like a badge overlay.")
            break

    return warnings


def _validate_image_bytes(image_bytes, label, source_name="image", content_type=None):
    valid, message = _validate_overlay_badge_size(image_bytes, label)
    if not valid:
        return False, message, {}
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            image_format = str(img.format or "").strip().lower()
            valid, message = _validate_allowed_image_format(image_format, label)
            if not valid:
                return False, message, {}
            valid, message = _validate_overlay_badge_image(image_format, img, label)
            if not valid:
                return False, message, {}
            valid, message = _validate_overlay_badge_suffix(source_name, image_format, label)
            if not valid:
                return False, message, {}
            if content_type is not None:
                valid, message = _validate_overlay_badge_content_type(content_type, image_format, label)
                if not valid:
                    return False, message, {}
            width, height = img.size
    except Exception as exc:
        return False, f"{label}: Unable to read a valid image from {source_name}. {exc}", {}

    warnings = _collect_overlay_badge_warnings(width, height)
    details = {"image_format": image_format, "width": width, "height": height, "size_bytes": len(image_bytes or b"")}
    if warnings:
        details["warning"] = " ".join(warnings)
        details["warning_list"] = warnings
    return True, None, details


# ---------------------------------------------------------------------------
# Remote URL resolution + main payload validation
# ---------------------------------------------------------------------------


def _resolve_overlay_source_override_remote_url(source_type, source_value):
    source = str(source_value or "").strip()
    if source_type == "url":
        if not source.lower().startswith(("http://", "https://")):
            return None, "Overlay image URL must start with http:// or https://."
        valid, message = url_validation.validate_url(source, allow_local=True)
        if not valid:
            return None, f"Overlay image URL: {message}"
        return source, None

    if source.lower().startswith(("http://", "https://")):
        return None, f"Overlay image {source_type} value must not be a full URL."

    normalized_source = source.lstrip("/").replace("\\", "/")
    if source_type == "git":
        return f"https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/{normalized_source}", None

    custom_repo_base = _saved_custom_repo_base()
    if not custom_repo_base:
        return None, "Overlay image repo entries require Custom Repo to be configured and saved first within the Settings page."
    return f"{custom_repo_base}{normalized_source}", None


def validate_overlay_source_override_payload(data):
    source_type = str(data.get("source_type") or "").strip().lower()
    source_value = str(data.get("source_value") or "").strip()

    if source_type not in {"file", "url", "git", "repo"}:
        return False, "Overlay image source type must be file, url, git, or repo.", {}
    if not source_value:
        return False, "Overlay image source value is required.", {}

    if source_type == "file":
        if source_value.lower().startswith(("http://", "https://")):
            return False, "Overlay image file path must be a local file path.", {}
        resolved_location = _resolve_managed_library_path(source_value)
        valid, message = path_validation.validate_path(
            resolved_location,
            {"allow_relative": True, "must_exist": True, "mode": "input_file"},
        )
        if not valid:
            return False, f"Overlay image file path: {message}", {}

        try:
            with open(resolved_location, "rb") as handle:
                content = handle.read()
        except OSError as exc:
            return False, f"Overlay image file path: Unable to read file. {exc}", {}

        valid, message, details = _validate_image_bytes(content, "Overlay image file path", os.path.basename(resolved_location) or "image")
        if not valid:
            return False, message, {}
        details["resolved_location"] = str(Path(resolved_location))
        details["normalized_location"] = str(Path(resolved_location))
        details["target"] = "local"
        details["message"] = f"Validated local {details['image_format'].upper()} image ({details['width']}x{details['height']})."

        config_name = str(data.get("config_name") or "").strip()
        library_id = str(data.get("library_id") or "").strip()
        overlay_id = str(data.get("overlay_id") or "").strip()
        template_key = str(data.get("template_key") or "").strip()
        if config_name and library_id and overlay_id and template_key:
            try:
                normalized_location, organized = normalize_overlay_source_override_file_location(
                    resolved_location,
                    config_name=config_name,
                    library_id=library_id,
                    overlay_id=overlay_id,
                    template_key=template_key,
                )
            except ValueError as exc:
                return False, f"Overlay image file path: {exc}", {}
            details["normalized_location"] = normalized_location
            details["organized"] = organized
            if organized:
                details["message"] = (
                    f"Validated local {details['image_format'].upper()} image ({details['width']}x{details['height']}) and organized it into managed overlay storage."
                )
        return True, None, details

    resolved_url, resolve_error = _resolve_overlay_source_override_remote_url(source_type, source_value)
    if resolve_error:
        return False, resolve_error, {}

    try:
        response = requests.get(resolved_url, timeout=15)
    except requests.RequestException as exc:
        return False, f"Overlay image {source_type} path: Unable to fetch image. {exc}", {}
    if response.status_code >= 400:
        return False, f"Overlay image {source_type} path: URL returned HTTP {response.status_code} {response.reason}.", {}

    valid, message, details = _validate_image_bytes(
        response.content,
        f"Overlay image {source_type} path",
        os.path.basename(urllib.parse.urlparse(resolved_url).path) or "image",
        content_type=response.headers.get("Content-Type"),
    )
    if not valid:
        return False, message, {}
    details["resolved_url"] = resolved_url
    details["target"] = "remote"
    details["message"] = f"Validated {source_type} image as {details['image_format'].upper()} ({details['width']}x{details['height']})."
    return True, None, details


def make_overlay_source_override_local_payload(data):
    source_type = str(data.get("source_type") or "").strip().lower()
    if source_type not in {"url", "git", "repo"}:
        return False, "Only URL, git, or repo overlay sources can be made local.", {}

    config_name = str(data.get("config_name") or "").strip()
    library_id = str(data.get("library_id") or "").strip()
    overlay_id = str(data.get("overlay_id") or "").strip()
    template_key = str(data.get("template_key") or "").strip()
    if not config_name or not library_id or not overlay_id or not template_key:
        return False, "Config, library, overlay, and template key are required to make an overlay source local.", {}

    valid, message, details = validate_overlay_source_override_payload(data)
    if not valid:
        return False, message, details

    resolved_url = str(details.get("resolved_url") or "").strip()
    if not resolved_url:
        return False, "Unable to resolve the remote overlay image URL.", {}

    try:
        response = requests.get(resolved_url, timeout=15)
    except requests.RequestException as exc:
        return False, f"Overlay image {source_type} path: Unable to fetch image. {exc}", {}
    if response.status_code >= 400:
        return False, f"Overlay image {source_type} path: URL returned HTTP {response.status_code} {response.reason}.", {}

    source_name = os.path.basename(urllib.parse.urlparse(resolved_url).path) or "image"
    valid, message, image_details = _validate_image_bytes(
        response.content,
        f"Overlay image {source_type} path",
        source_name,
        content_type=response.headers.get("Content-Type"),
    )
    if not valid:
        return False, message, {}

    try:
        normalized_location = store_overlay_source_override_image_bytes(
            response.content,
            config_name=config_name,
            library_id=library_id,
            overlay_id=overlay_id,
            template_key=template_key,
            source_name=source_name,
            image_format=image_details.get("image_format"),
        )
    except ValueError as exc:
        return False, f"Overlay image {source_type} path: {exc}", {}

    payload = dict(image_details)
    payload["resolved_url"] = resolved_url
    payload["normalized_location"] = normalized_location
    payload["target"] = "local"
    payload["organized"] = True
    payload["message"] = f"Saved {source_type} image into managed overlay storage as {image_details['image_format'].upper()} ({image_details['width']}x{image_details['height']})."
    return True, None, payload


# ---------------------------------------------------------------------------
# Flask endpoint wrappers
# ---------------------------------------------------------------------------


def validate_overlay_source_override_server(data):
    valid, message, details = validate_overlay_source_override_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message"):
            payload["error_details"] = {"text": details.get("message")}
        return jsonify(payload), 400

    payload = {"valid": True}
    if details.get("message"):
        payload["message"] = details["message"]
    if details.get("warning"):
        payload["warning"] = details["warning"]
    for key in ("image_format", "width", "height", "resolved_url", "resolved_location", "normalized_location", "target", "organized", "size_bytes", "warning_list"):
        if key in details:
            payload[key] = details[key]
    return jsonify(payload), 200


def make_overlay_source_override_local_server(data):
    valid, message, details = make_overlay_source_override_local_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        if details.get("message"):
            payload["error_details"] = {"text": details.get("message")}
        return jsonify(payload), 400

    payload = {"valid": True, "source_type": "file"}
    if details.get("message"):
        payload["message"] = details["message"]
    if details.get("warning"):
        payload["warning"] = details["warning"]
    for key in ("image_format", "width", "height", "resolved_url", "normalized_location", "target", "organized", "size_bytes", "warning_list"):
        if key in details:
            payload[key] = details[key]
    return jsonify(payload), 200


def cleanup_overlay_source_override_server(data):
    valid, message, details = cleanup_overlay_source_override_payload(data)
    if not valid:
        payload = {"valid": False, "error": message}
        return jsonify(payload), 400

    payload = {"valid": True}
    for key in ("removed", "skipped", "errors"):
        if key in details:
            payload[key] = details[key]
    return jsonify(payload), 200
