import hashlib
import os
import re
import shutil
import urllib.parse
from json import JSONDecodeError
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from ruamel.yaml import YAML
from flask import jsonify, flash
from plexapi.server import PlexServer

from modules import iso, helpers, path_validation, persistence, url_validation

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


def validate_iso3166_1(code):
    try:
        return iso.get_country(alpha2=code, alpha3=code).alpha2
    except (NameError, ValueError):
        return None


def validate_iso639_1(code):
    try:
        return iso.get_language(alpha2=code, alpha3=code).alpha2
    except (NameError, ValueError):
        return None


def _validate_service_url(raw_url, label, allow_local=True):
    if not raw_url:
        return False, f"{label} URL is required."
    valid, message = url_validation.validate_url(raw_url, allow_local=allow_local)
    if not valid:
        return False, f"{label} URL: {message}"
    return True, None


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


def _validate_yaml_location_suffix(location, label):
    lowered = str(location or "").strip().lower()
    if not lowered.endswith((".yml", ".yaml")):
        return False, f"{label} must end with .yml or .yaml."
    return True, None


def _resolve_managed_library_path(location):
    raw = str(location or "").strip()
    if not raw:
        return raw
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        return str(expanded)
    normalized_parts = [part for part in str(expanded).replace("\\", "/").split("/") if part]
    if normalized_parts and normalized_parts[0] == "config":
        return str(Path(helpers.CONFIG_DIR) / Path(*normalized_parts[1:]))
    if len(normalized_parts) >= 3 and normalized_parts[1] in helpers.MANAGED_LIBRARY_FILE_DIRS:
        return str(Path(helpers.CONFIG_DIR) / Path(*normalized_parts))
    if len(normalized_parts) >= 3 and normalized_parts[1] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        return str(Path(helpers.CONFIG_DIR) / Path(*normalized_parts))
    if normalized_parts and normalized_parts[0] in helpers.MANAGED_LIBRARY_FILE_DIRS:
        return str(Path(helpers.CONFIG_DIR) / expanded)
    if normalized_parts and normalized_parts[0] == helpers.MANAGED_OVERLAY_IMAGE_DIR:
        return str(Path(helpers.CONFIG_DIR) / expanded)
    return raw


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
    digest_source = f"{str(source_path).replace('\\', '/').lower()}|{library_slug}|{overlay_slug}|{template_slug}"
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


def _normalize_custom_repo_base(custom_repo):
    repo = str(custom_repo or "").strip()
    if not repo or repo.lower() == "none":
        return None
    if "https://github.com/" in repo:
        repo = repo.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/tree/", "/")
        if not repo.endswith("/"):
            repo += "/"
    return repo


def _saved_custom_repo_base():
    settings_data = persistence.retrieve_settings("150-settings") or {}
    settings_section = settings_data.get("settings", {}) if isinstance(settings_data, dict) else {}
    return _normalize_custom_repo_base(settings_section.get("custom_repo"))


def _normalize_metadata_validation_result(result):
    if isinstance(result, tuple):
        if len(result) == 3:
            valid, message, details = result
            return bool(valid), message, details or {}
        if len(result) == 2:
            valid, message = result
            return bool(valid), message, {}
    return False, "Validation failed.", {}


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


def validate_plex_server(data):
    plex_url = data.get("plex_url")
    plex_token = data.get("plex_token")

    ok, msg = _validate_service_url(plex_url, "Plex", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    # Validate Plex URL and Token
    try:
        cached = helpers.get_cached_plex_validation(plex_url, plex_token)
        if cached:
            helpers.ts_log("Using cached Plex validation payload.", level="DEBUG")
            return jsonify(cached)

        plex = PlexServer(plex_url, plex_token, timeout=8)

        # Fetch Plex settings
        srv_settings = plex.settings

        # Retrieve db_cache from Plex settings
        db_cache_setting = srv_settings.get("DatabaseCacheSize")

        # Get the value of db_cache
        db_cache = db_cache_setting.value

        # Log db_cache value
        helpers.ts_log(f"db_cache returned from Plex: {db_cache}", level="INFO")

        # If db_cache is None, treat it as invalid.
        if db_cache is None:
            raise Exception("Unable to retrieve db_cache from Plex settings.")

        # Retrieve user list with only usernames
        user_list = [user.title for user in plex.myPlexAccount().users()]
        has_plex_pass = plex.myPlexAccount().subscriptionActive

        helpers.ts_log(f"User list retrieved from Plex: {user_list}", level="INFO")
        helpers.ts_log(f"User has Plex Pass: {has_plex_pass}", level="INFO")

        # Retrieve library sections once. This can be expensive on large Plex servers.
        sections = plex.library.sections()
        music_libraries = [section.title for section in sections if section.type == "artist"]
        movie_libraries = [section.title for section in sections if section.type == "movie"]
        show_libraries = [section.title for section in sections if section.type == "show"]

        helpers.ts_log(f"Music libraries: {music_libraries}", level="INFO")
        helpers.ts_log(f"Movie libraries: {movie_libraries}", level="INFO")
        helpers.ts_log(f"Show libraries: {show_libraries}", level="INFO")

    except Exception as e:
        helpers.ts_log(f"Error validating Plex server: {str(e)}", level="ERROR")
        flash(f"Invalid Plex URL or Token: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Plex URL or Token: {str(e)}"})

    # If PlexServer instance is successfully created and db_cache is retrieved, return success response
    payload = {
        "validated": True,
        "db_cache": db_cache,  # Send back the integer value of db_cache
        "user_list": user_list,
        "music_libraries": music_libraries,
        "movie_libraries": movie_libraries,
        "show_libraries": show_libraries,
        "has_plex_pass": has_plex_pass,
    }
    helpers.set_cached_plex_validation(plex_url, plex_token, payload)
    return jsonify(payload)


def validate_tautulli_server(data):
    tautulli_url = data.get("tautulli_url")
    tautulli_apikey = data.get("tautulli_apikey")

    ok, msg = _validate_service_url(tautulli_url, "Tautulli", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    api_url = f"{tautulli_url}/api/v2"
    params = {"apikey": tautulli_apikey, "cmd": "get_tautulli_info"}

    try:
        response = requests.get(api_url, params=params, timeout=10)

        # Raise an exception for HTTP errors
        response.raise_for_status()

        data = response.json()

        is_valid = data.get("response", {}).get("result") == "success"
        # Check if the response contains the expected data
        if is_valid:
            helpers.ts_log("Tautulli connection successful.")
        else:
            helpers.ts_log("Tautulli connection failed.")

    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Tautulli connection: {e}", level="ERROR")
        flash(f"Invalid Tautulli URL or API Key: {str(e)}", "error")
        return jsonify({"valid": False, "error": f"Invalid Tautulli URL or Apikey: {str(e)}"})

    # return success response
    return jsonify({"valid": is_valid})


def validate_trakt_server(data):
    trakt_client_id = data.get("trakt_client_id")
    trakt_client_secret = data.get("trakt_client_secret")
    trakt_pin = data.get("trakt_pin")

    redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    base_url = "https://api.trakt.tv"

    try:
        response = requests.post(
            f"{base_url}/oauth/token",
            json={
                "code": trakt_pin,
                "client_id": trakt_client_id,
                "client_secret": trakt_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code != 200:
            return jsonify({"valid": False, "error": "Trakt Error: Invalid trakt pin, client_id, or client_secret."})

        validation_response = requests.get(
            f"{base_url}/users/settings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {response.json()['access_token']}",
                "trakt-api-version": "2",
                "trakt-api-key": trakt_client_id,
            },
            timeout=10,
        )

        if validation_response.status_code == 423:
            return jsonify({"valid": False, "error": "Account is locked; please contact Trakt Support"})

        return jsonify(
            {
                "valid": True,
                "error": "",
                "trakt_authorization_access_token": response.json()["access_token"],
                "trakt_authorization_token_type": response.json()["token_type"],
                "trakt_authorization_expires_in": response.json()["expires_in"],
                "trakt_authorization_refresh_token": response.json()["refresh_token"],
                "trakt_authorization_scope": response.json()["scope"],
                "trakt_authorization_created_at": response.json()["created_at"],
            }
        )

    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Trakt connection: {e}", level="ERROR")
        flash("Invalid Trakt ID, Secret, or PIN.", "error")
        return jsonify({"valid": False, "error": "Invalid Trakt ID, Secret, or PIN."})


def validate_gotify_server(data):
    gotify_url = data.get("gotify_url")
    gotify_token = data.get("gotify_token")
    ok, msg = _validate_service_url(gotify_url, "Gotify", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400
    gotify_url = gotify_url.rstrip("#")
    gotify_url = gotify_url.rstrip("/")

    response = requests.get(f"{gotify_url}/version", timeout=10)

    try:
        response_json = response.json()
    except JSONDecodeError:
        status = response.status_code
        content_type = response.headers.get("Content-Type")
        helpers.ts_log(
            f"Gotify validation returned non-JSON response " f"(status={status}, content-type={content_type})",
            level="ERROR",
        )
        return jsonify(
            {
                "valid": False,
                "error": f"Gotify returned a non-JSON response (status {status}). Check the base URL.",
            }
        )

    if response.status_code >= 400:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    json = {"message": "Kometa Quickstart Test Gotify Message", "title": "Kometa Quickstart Gotify Test"}

    response = requests.post(f"{gotify_url}/message", headers={"X-Gotify-Key": gotify_token}, json=json, timeout=10)

    if response.status_code != 200:
        return jsonify({"valid": False, "error": f"({response.status_code} [{response.reason}]) {response_json['errorDescription']}"})

    return jsonify({"valid": True})


def validate_ntfy_server(data):
    ntfy_url = data.get("ntfy_url")
    ntfy_token = data.get("ntfy_token")
    ntfy_topic = data.get("ntfy_topic")

    ok, msg = _validate_service_url(ntfy_url, "ntfy", allow_local=True)
    if not ok:
        return jsonify({"valid": False, "error": msg}), 400

    # Ensure the URL is formatted correctly
    ntfy_url = ntfy_url.rstrip("#").rstrip("/")

    headers = {"Content-Type": "text/plain"}
    if ntfy_token:
        headers["Authorization"] = f"Bearer {ntfy_token}"

    test_message = "🔔 Kometa Quickstart Test ntfy Message"

    try:
        # Step 1: Send test notification
        response = requests.post(f"{ntfy_url}/{ntfy_topic}", headers=headers, data=test_message, timeout=10)

        if response.status_code != 200:
            return jsonify({"valid": False, "error": f"Failed to send test message ({response.status_code} [{response.reason}])."})

        # Step 2: Auto-subscribe the sender to the topic
        sub_headers = headers.copy()
        sub_headers["X-Subscriber"] = "true"  # Tell ntfy.sh to subscribe this client

        sub_response = requests.put(f"{ntfy_url}/{ntfy_topic}", headers=sub_headers, timeout=10)

        if sub_response.status_code == 200:
            return jsonify({"valid": True})
        else:
            return jsonify({"valid": False, "error": f"Failed to auto-subscribe ({sub_response.status_code} [{sub_response.reason}])."})

    except requests.RequestException as e:
        return jsonify({"valid": False, "error": f"Connection error: {str(e)}"})


def validate_apprise_server(data):
    apprise_location = str(data.get("apprise_location") or "").strip()
    if not apprise_location:
        return jsonify({"valid": False, "error": "Apprise YAML path or URL is required."}), 400

    valid, message = _validate_yaml_location(apprise_location, "Apprise location")
    if not valid:
        return jsonify({"valid": False, "error": message}), 400

    return jsonify({"valid": True})


def validate_mal_server(data):
    mal_client_id = data.get("mal_client_id")
    mal_client_secret = data.get("mal_client_secret")
    mal_code_verifier = data.get("mal_code_verifier")
    mal_localhost_url = data.get("mal_localhost_url")

    match = re.search("code=([^&]+)", str(mal_localhost_url))

    if not match:
        return jsonify({"valid": False, "error": "MAL Error: No required code in localhost URL."})

    new_authorization = requests.post(
        "https://myanimelist.net/v1/oauth2/token",
        data={
            "client_id": mal_client_id,
            "client_secret": mal_client_secret,
            "code": match.group(1),
            "code_verifier": mal_code_verifier,
            "grant_type": "authorization_code",
        },
        timeout=10,
    ).json()

    if "error" in new_authorization:
        return jsonify({"valid": False, "error": "MAL Error: invalid code."})

    # return success response
    return jsonify(
        {
            "valid": True,
            "mal_authorization_access_token": new_authorization["access_token"],
            "mal_authorization_token_type": new_authorization["token_type"],
            "mal_authorization_expires_in": new_authorization["expires_in"],
            "mal_authorization_refresh_token": new_authorization["refresh_token"],
        }
    )


def validate_webhook_server(data):
    webhook_url = data.get("webhook_url")
    message = data.get("message")

    if not webhook_url:
        return jsonify({"error": "Webhook URL is required"}), 400

    ok, msg = _validate_service_url(webhook_url, "Webhook", allow_local=True)
    if not ok:
        return jsonify({"error": msg}), 400

    message_data = {"content": message}

    response = requests.post(webhook_url, json=message_data, timeout=10)

    if response.status_code == 204:
        return jsonify({"success": "Test message sent successfully! Go and ensure that you see the message on the server side."}), 200
    else:
        return jsonify({"error": f"Failed to send message: {response.status_code}, {response.text}"}), 400


def validate_radarr_server(data):
    result, status_code = validate_radarr_payload(data)
    if not result.get("valid"):
        error = result.get("error")
        if error:
            flash(f"Invalid Radarr URL or API Key: {error}", "error")
    return (jsonify(result), status_code) if status_code != 200 else jsonify(result)


def validate_sonarr_server(data):
    result, status_code = validate_sonarr_payload(data)
    if not result.get("valid"):
        error = result.get("error")
        if error:
            flash(f"Invalid Sonarr URL or API Key: {error}", "error")
    return (jsonify(result), status_code) if status_code != 200 else jsonify(result)


def validate_radarr_payload(data):
    radarr_url = data.get("radarr_url") or data.get("url")
    radarr_apikey = data.get("radarr_token") or data.get("token")

    ok, msg = _validate_service_url(radarr_url, "Radarr", allow_local=True)
    if not ok:
        return {"valid": False, "error": msg}, 400

    status_api_url = f"{radarr_url}/api/v3/system/status?apikey={radarr_apikey}"
    root_folder_api_url = f"{radarr_url}/api/v3/rootfolder?apikey={radarr_apikey}"
    quality_profile_api_url = f"{radarr_url}/api/v3/qualityprofile?apikey={radarr_apikey}"

    try:
        response = requests.get(status_api_url, timeout=10)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            helpers.ts_log("Radarr connection failed. Invalid response data.")
            return {"valid": False, "error": "Invalid Radarr URL or Apikey"}, 200

        response = requests.get(root_folder_api_url, timeout=10)
        response.raise_for_status()
        root_folders = response.json()

        response = requests.get(quality_profile_api_url, timeout=10)
        response.raise_for_status()
        quality_profiles = response.json()

        helpers.ts_log("Radarr connection successful.")
        return {
            "valid": True,
            "root_folders": root_folders,
            "quality_profiles": quality_profiles,
        }, 200
    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Radarr connection: {e}", level="ERROR")
        return {"valid": False, "error": f"Invalid Radarr URL or Apikey: {str(e)}"}, 200


def validate_sonarr_payload(data):
    sonarr_url = data.get("sonarr_url") or data.get("url")
    sonarr_apikey = data.get("sonarr_token") or data.get("token")

    ok, msg = _validate_service_url(sonarr_url, "Sonarr", allow_local=True)
    if not ok:
        return {"valid": False, "error": msg}, 400

    status_api_url = f"{sonarr_url}/api/v3/system/status?apikey={sonarr_apikey}"
    root_folder_api_url = f"{sonarr_url}/api/v3/rootfolder?apikey={sonarr_apikey}"
    quality_profile_api_url = f"{sonarr_url}/api/v3/qualityprofile?apikey={sonarr_apikey}"
    language_profile_api_url = f"{sonarr_url}/api/v3/language?apikey={sonarr_apikey}"

    try:
        response = requests.get(status_api_url, timeout=10)
        response.raise_for_status()
        status_data = response.json()

        if "version" not in status_data:
            helpers.ts_log("Sonarr connection failed. Invalid response data.")
            return {"valid": False, "error": "Invalid Sonarr URL or Apikey"}, 200

        response = requests.get(root_folder_api_url, timeout=10)
        response.raise_for_status()
        root_folders = response.json()

        response = requests.get(quality_profile_api_url, timeout=10)
        response.raise_for_status()
        quality_profiles = response.json()

        response = requests.get(language_profile_api_url, timeout=10)
        response.raise_for_status()
        language_profiles = response.json()

        helpers.ts_log("Sonarr connection successful.")
        return {
            "valid": True,
            "root_folders": root_folders,
            "quality_profiles": quality_profiles,
            "language_profiles": language_profiles,
        }, 200
    except requests.exceptions.RequestException as e:
        helpers.ts_log(f"Error validating Sonarr connection: {e}", level="ERROR")
        return {"valid": False, "error": f"Invalid Sonarr URL or Apikey: {str(e)}"}, 200


def validate_omdb_server(data):
    omdb_apikey = data.get("omdb_apikey")

    api_url = f"https://www.omdbapi.com/?apikey={omdb_apikey}&s=test"
    try:
        response = requests.get(api_url, timeout=10)
        data = response.json()
        if data.get("Response") == "True" or data.get("Error") == "Movie not found!":
            return jsonify({"valid": True, "message": "OMDb API key is valid"})
        else:
            return jsonify({"valid": False, "message": data.get("Error", "Invalid API key")})
    except Exception as e:
        helpers.ts_log(f"Error validating OMDb connection: {e}", level="ERROR")
        flash(f"Invalid OMDb API Key: {str(e)}", "error")
        return jsonify({"valid": False, "message": str(e)})


def validate_github_server(data):
    github_token = data.get("github_token")

    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=10,
        )
        if response.status_code == 200:
            user_data = response.json()
            return jsonify({"valid": True, "message": f"GitHub token is valid. User: {user_data.get('login')}"})
        else:
            return jsonify({"valid": False, "message": "Invalid GitHub token"}), 400
    except Exception as e:
        return jsonify({"valid": False, "message": str(e)})


def validate_tmdb_server(data):
    api_key = data.get("tmdb_apikey")

    # Validate the API key
    movie_response = requests.get(f"https://api.themoviedb.org/3/movie/550?api_key={api_key}", timeout=10)
    if movie_response.status_code == 200:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_mdblist_server(data):
    api_key = data.get("mdblist_apikey")

    response = requests.get(f"https://mdblist.com/api/?apikey={api_key}&s=test", timeout=10)
    if response.status_code == 200 and response.json().get("response") is True:
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})


def validate_notifiarr_server(data):
    api_key = data.get("notifiarr_apikey")

    response = requests.get(f"https://notifiarr.com/api/v1/user/validate/{api_key}", timeout=10)
    if response.status_code == 200 and response.json().get("result") == "success":
        return jsonify({"valid": True, "message": "API key is valid!"})
    else:
        return jsonify({"valid": False, "message": "Invalid API key"})
