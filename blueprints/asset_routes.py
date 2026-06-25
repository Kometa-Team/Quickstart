import hashlib
import os
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Blueprint, abort, has_request_context, jsonify, request, send_file, send_from_directory, session
from PIL import Image, ImageColor, ImageDraw, ImageFont
from werkzeug.utils import secure_filename

from modules import assets, helpers, url_validation, validations

bp = Blueprint("asset_routes", __name__)

OVERLAY_PREVIEW_ROOT = Path(__file__).resolve().parent.parent / "static" / "images" / "overlay-defaults"

STREAMING_PREVIEW_FILENAME_MAP = {
    "amazon": "Prime Video",
    "amc": "AMC+",
    "appletv": "AppleTV",
    "atresplayer": "Atres Player",
    "bet": "BET+",
    "channel4": "Channel 4",
    "crave": "Crave",
    "crunchyroll": "Crunchyroll",
    "discovery": "discovery+",
    "disney": "Disney",
    "filmin": "Filmin",
    "hayu": "hayu",
    "hbomax": "HBO Max",
    "hulu": "Hulu",
    "itvx": "ITVX",
    "max": "Max",
    "movistar": "Movistar Plus+",
    "netflix": "Netflix",
    "now": "NOW",
    "paramount": "Paramount+",
    "peacock": "Peacock",
    "tubi": "tubi",
    "youtube": "YouTube",
}


def _overlay_preview_basename(badge_key, family=None):
    normalized_family = str(family or "").strip().lower()
    normalized_key = str(badge_key or "").strip()
    if normalized_family in {"audio_codec", "ribbon"}:
        return normalized_key
    if normalized_family == "streaming":
        return STREAMING_PREVIEW_FILENAME_MAP.get(normalized_key, normalized_key)
    return normalized_key.replace("_", "")


def _overlay_preview_filename(badge_key, family=None):
    normalized_key = _overlay_preview_basename(badge_key, family)
    return f"{normalized_key}.png" if normalized_key else ""


def _overlay_preview_mimetype_from_format(image_format):
    fmt = str(image_format or "").strip().lower()
    if fmt == "webp":
        return "image/webp"
    if fmt in {"jpg", "jpeg"}:
        return "image/jpeg"
    return "image/png"


def _read_overlay_preview_source_bytes(source_type, source_value):
    normalized_type = str(source_type or "").strip().lower()
    normalized_value = str(source_value or "").strip()

    if normalized_type not in {"file", "url", "git", "repo"}:
        raise ValueError("Invalid overlay source type.")
    if not normalized_value:
        raise ValueError("Missing overlay source value.")

    if normalized_type == "file":
        try:
            resolved_path = Path(validations._resolve_managed_library_path(normalized_value)).resolve()  # noqa: SLF001
            config_root = Path(helpers.CONFIG_DIR).resolve()
            resolved_path.relative_to(config_root)
        except Exception as exc:
            raise ValueError("Unable to resolve overlay file path.") from exc

        if not resolved_path.exists() or not resolved_path.is_file():
            raise ValueError("Overlay preview file must be within managed config storage.")

        return resolved_path.read_bytes(), _overlay_preview_mimetype_from_format(resolved_path.suffix.lstrip(".")), str(resolved_path)

    resolved_url, resolve_error = validations._resolve_overlay_source_override_remote_url(normalized_type, normalized_value)  # noqa: SLF001
    if resolve_error or not resolved_url:
        raise ValueError(resolve_error or "Unable to resolve overlay preview URL.")

    try:
        response = requests.get(resolved_url, timeout=15)
    except requests.RequestException as exc:
        raise ValueError(f"Unable to fetch overlay preview image. {exc}") from exc

    if response.status_code >= 400:
        raise ValueError(f"Overlay preview URL returned HTTP {response.status_code} {response.reason}.")

    content_type = response.headers.get("Content-Type") or "application/octet-stream"
    return response.content, content_type, resolved_url


def _load_overlay_preview_image(source_type, source_value):
    content, _content_type, source_label = _read_overlay_preview_source_bytes(source_type, source_value)
    try:
        with Image.open(BytesIO(content)) as preview_img:
            return preview_img.convert("RGBA"), source_label
    except Exception as exc:
        raise ValueError(f"Unable to read overlay preview image from {source_label}. {exc}") from exc


def _load_bundled_overlay_preview_image(family, badge_key, variant=None):
    normalized_family = str(family or "").strip().lower()
    filename = _overlay_preview_filename(badge_key, normalized_family)
    normalized_variant = str(variant or "").strip().lower()
    if normalized_family == "language_count":
        if normalized_variant not in {"audio", "subs"} or not str(badge_key or "").strip():
            raise ValueError("Invalid bundled overlay preview request.")
        filename = f"{str(badge_key or '').strip()}_{normalized_variant}.png"

    if (
        normalized_family not in {"resolution", "edition", "audio_codec", "streaming", "network", "studio", "ribbon", "language_count", "versions", "mediastinger", "direct_play"}
        or not filename
    ):
        raise ValueError("Invalid bundled overlay preview request.")

    image_root = OVERLAY_PREVIEW_ROOT / normalized_family
    if normalized_family == "audio_codec":
        normalized_variant = normalized_variant if normalized_variant in {"compact", "standard"} else "compact"
        image_root = image_root / normalized_variant
    elif normalized_family == "streaming":
        normalized_variant = normalized_variant if normalized_variant in {"color", "white"} else "color"
        image_root = image_root / normalized_variant
    elif normalized_family == "network":
        normalized_variant = normalized_variant if normalized_variant in {"color", "white"} else "color"
        image_root = image_root / normalized_variant
    elif normalized_family == "studio":
        normalized_variant = normalized_variant if normalized_variant in {"standard", "bigger"} else "standard"
        image_root = image_root / normalized_variant
    elif normalized_family == "ribbon":
        normalized_variant = normalized_variant if normalized_variant in {"yellow", "gray", "black", "red"} else "yellow"
        image_root = image_root / normalized_variant

    image_path = image_root.resolve() / filename
    image_path = image_path.resolve()
    try:
        image_path.relative_to(OVERLAY_PREVIEW_ROOT.resolve())
    except Exception as exc:
        raise ValueError("Invalid bundled overlay preview path.") from exc

    if not image_path.exists() or not image_path.is_file():
        raise ValueError(f"Bundled overlay preview image not found for {normalized_family}:{badge_key}.")

    try:
        with Image.open(image_path) as preview_img:
            return preview_img.convert("RGBA"), str(image_path)
    except Exception as exc:
        raise ValueError(f"Unable to read bundled overlay preview image {image_path.name}. {exc}") from exc


def _list_bundled_overlay_preview_keys(family):
    normalized_family = str(family or "").strip().lower()
    if normalized_family not in {"network", "studio"}:
        raise ValueError("Unsupported bundled overlay key family.")

    image_root = (OVERLAY_PREVIEW_ROOT / normalized_family).resolve()
    if not image_root.exists() or not image_root.is_dir():
        raise ValueError(f"Bundled overlay preview folder not found for {normalized_family}.")

    keys = sorted(
        {image_path.stem for image_path in image_root.rglob("*.png") if image_path.is_file()},
        key=lambda item: item.casefold(),
    )
    if not keys:
        raise ValueError(f"No bundled overlay preview keys were found for {normalized_family}.")
    return keys


def _load_render_preview_image(payload, family):
    family_payload = payload.get(family) if isinstance(payload.get(family), dict) else {}
    source_type = str(family_payload.get("source_type") or "").strip().lower()
    source_value = str(family_payload.get("source_value") or "").strip()
    badge_key = str(family_payload.get("badge_key") or "").strip()
    variant = str(family_payload.get("variant") or "").strip()

    if source_type and source_value:
        return _load_overlay_preview_image(source_type, source_value)
    return _load_bundled_overlay_preview_image(family, badge_key, variant)


@bp.route("/upload_library_image", methods=["POST"])
def upload_library_image():
    if "image" not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400
    image = request.files["image"]
    image_type = request.form.get("type")

    if not image or image_type not in assets.UPLOAD_FOLDERS:
        return (
            jsonify({"status": "error", "message": "Invalid request parameters"}),
            400,
        )

    # Validate extension
    filename = secure_filename(image.filename)
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in helpers.ALLOWED_EXTENSIONS:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": f"Invalid file type. Allowed: {helpers.allowed_extensions_string()}",
                }
            ),
            400,
        )

    # Open and validate image
    img = Image.open(image)
    aspect_ratio = "16:9" if image_type == "episode" else "2:3"
    if not helpers.is_valid_aspect_ratio(img, target_ratio=aspect_ratio):
        message = "Image must have a 16:9 aspect ratio (e.g., 1920x1080)." if image_type == "episode" else "Image must have a 1:1.5 aspect ratio (e.g., 1000x1500)."
        return jsonify({"status": "error", "message": message}), 400

    # Resize to target size
    target_size = (1920, 1080) if image_type == "episode" else (1000, 1500)
    img = img.resize(target_size, Image.LANCZOS)

    # Save image
    save_folder = assets.UPLOAD_FOLDERS[image_type]
    os.makedirs(save_folder, exist_ok=True)
    save_path = os.path.join(save_folder, filename)
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(save_path):
        filename = f"{base}_{counter}{ext}"
        save_path = os.path.join(save_folder, filename)
        counter += 1
    img.save(save_path)

    return jsonify(
        {
            "status": "success",
            "message": f"Image uploaded and saved as {filename}",
            "filename": filename,
        }
    )


@bp.route("/upload-fonts", methods=["POST"])
def upload_fonts():
    files = request.files.getlist("fonts")
    if not files:
        return jsonify({"status": "error", "message": "No fonts uploaded"}), 400

    config_name = (request.form.get("config_name") or session.get("config_name") or "").strip()
    fonts_dir = helpers.get_custom_fonts_dir(config_name or None)

    os.makedirs(fonts_dir, exist_ok=True)
    saved = []
    errors = []

    for font_file in files:
        if not font_file or not font_file.filename:
            continue
        filename = secure_filename(font_file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in helpers.FONT_EXTENSIONS:
            errors.append(f"Invalid font type: {filename}")
            continue
        save_path = os.path.join(str(fonts_dir), filename)
        font_file.save(save_path)
        saved.append(filename)

    if saved:
        assets.clear_font_cache()

    if not saved:
        return jsonify({"status": "error", "message": "No valid fonts uploaded.", "errors": errors}), 400

    return jsonify(
        {
            "status": "success",
            "message": f"Uploaded {len(saved)} font(s).",
            "saved": saved,
            "errors": errors,
            "fonts": assets.list_overlay_fonts(),
        }
    )


@bp.route("/custom-fonts/<path:filename>", methods=["GET"])
def custom_fonts(filename):
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        abort(404)
    if not safe_name.lower().endswith((".ttf", ".otf")):
        abort(404)

    current_config = session.get("config_name") if has_request_context() else None
    for fdir in helpers.get_font_dirs(include_static=True, include_custom=True, config_name=current_config):
        candidate = os.path.join(str(fdir), safe_name)
        if os.path.exists(candidate):
            return send_from_directory(str(fdir), safe_name)

    abort(404)


@bp.route("/fetch_library_image", methods=["POST"])
def fetch_library_image():
    data = request.json
    image_url = data.get("url")
    image_type = data.get("type")

    if not image_url or image_type not in assets.UPLOAD_FOLDERS:
        return (
            jsonify({"status": "error", "message": "Invalid request parameters"}),
            400,
        )

    valid_url, url_message = url_validation.validate_url(image_url, allow_local=False)
    if not valid_url:
        return (
            jsonify({"status": "error", "message": f"Invalid image URL: {url_message}"}),
            400,
        )

    try:
        response = requests.get(image_url, stream=True, timeout=5)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))

        file_extension = img.format.lower()
        if file_extension not in helpers.ALLOWED_EXTENSIONS:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Invalid file type. Allowed: {helpers.allowed_extensions_string()}",
                    }
                ),
                400,
            )

        # Validate aspect ratio
        aspect_ratio = "16:9" if image_type == "episode" else "2:3"
        if not helpers.is_valid_aspect_ratio(img, target_ratio=aspect_ratio):
            message = "Image must have a 16:9 aspect ratio (e.g., 1920x1080)." if image_type == "episode" else "Image must have a 1:1.5 aspect ratio (e.g., 1000x1500)."
            return jsonify({"status": "error", "message": message}), 400

        # Resize to target size
        target_size = (1920, 1080) if image_type == "episode" else (1000, 1500)
        img = img.resize(target_size, Image.LANCZOS)

        # Generate filename
        filename = secure_filename(os.path.basename(image_url))
        if "." not in filename or filename.split(".")[-1].lower() not in helpers.ALLOWED_EXTENSIONS:
            filename += ".png"

        # Save image
        save_folder = assets.UPLOAD_FOLDERS[image_type]
        os.makedirs(save_folder, exist_ok=True)
        save_path = os.path.join(save_folder, filename)
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(save_folder, filename)
            counter += 1
        img.save(save_path)

        return jsonify(
            {
                "status": "success",
                "message": f"Image fetched and saved as {filename}",
                "filename": filename,
            }
        )

    except requests.exceptions.RequestException as e:
        return (
            jsonify({"status": "error", "message": f"Failed to fetch image: {str(e)}"}),
            400,
        )
    except Exception as e:
        return (
            jsonify({"status": "error", "message": f"Processing error: {str(e)}"}),
            400,
        )


@bp.route("/rename_library_image", methods=["POST"])
def rename_library_image():
    data = request.json
    old_name = data.get("old_name")
    new_name = data.get("new_name")
    image_type = data.get("type")

    if not old_name or not new_name or image_type not in assets.UPLOAD_FOLDERS:
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    save_folder = assets.UPLOAD_FOLDERS[image_type]
    old_path = helpers.safe_join(save_folder, old_name)
    if not old_path:
        return jsonify({"status": "error", "message": "Invalid file name"}), 400

    if not old_path.exists():
        return jsonify({"status": "error", "message": "File not found"}), 404

    old_ext = old_path.suffix
    safe_new_name = str(new_name).strip()
    if not safe_new_name:
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400
    if old_ext:
        if "." not in safe_new_name:
            safe_new_name += old_ext
        elif not safe_new_name.endswith(old_ext):
            safe_new_name += old_ext

    new_path = helpers.safe_join(save_folder, safe_new_name)
    if not new_path:
        return jsonify({"status": "error", "message": "Invalid file name"}), 400
    if new_path.exists():
        return (
            jsonify({"status": "error", "message": "File with new name already exists"}),
            400,
        )

    try:
        os.rename(old_path, new_path)
        return jsonify({"status": "success", "message": "File renamed successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/list_uploaded_images", methods=["GET"])
def list_uploaded_images():
    image_type = request.args.get("type")
    if image_type not in assets.UPLOAD_FOLDERS:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    return jsonify({"status": "success", "images": assets.list_preview_images_for_type(image_type)})


@bp.route("/overlay-source-preview", methods=["GET"])
def overlay_source_preview():
    source_type = str(request.args.get("source_type") or "").strip().lower()
    source_value = str(request.args.get("source_value") or "").strip()

    try:
        content, content_type, resolved_location = _read_overlay_preview_source_bytes(source_type, source_value)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    if source_type == "file":
        return send_file(Path(resolved_location))

    return send_file(BytesIO(content), mimetype=content_type)


@bp.route("/overlay-preview-keys", methods=["GET"])
def overlay_preview_keys():
    family = str(request.args.get("family") or "").strip().lower()
    try:
        keys = _list_bundled_overlay_preview_keys(family)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "success", "family": family, "keys": keys})


@bp.route("/overlay-render-preview", methods=["POST"])
def overlay_render_preview():
    data = request.get_json(silent=True) or {}
    overlay_id = str(data.get("overlay_id") or "").strip()

    if overlay_id not in {
        "overlay_resolution",
        "overlay_audio_codec",
        "overlay_streaming",
        "overlay_network",
        "overlay_studio",
        "overlay_ribbon",
        "overlay_language_count",
        "overlay_versions",
        "overlay_mediastinger",
        "overlay_direct_play",
    }:
        return jsonify({"status": "error", "message": "Unsupported overlay render preview request."}), 400

    if overlay_id in {
        "overlay_audio_codec",
        "overlay_streaming",
        "overlay_network",
        "overlay_studio",
        "overlay_ribbon",
        "overlay_language_count",
        "overlay_versions",
        "overlay_mediastinger",
        "overlay_direct_play",
    }:
        family = {
            "overlay_audio_codec": "audio_codec",
            "overlay_streaming": "streaming",
            "overlay_network": "network",
            "overlay_studio": "studio",
            "overlay_ribbon": "ribbon",
            "overlay_language_count": "language_count",
            "overlay_versions": "versions",
            "overlay_mediastinger": "mediastinger",
            "overlay_direct_play": "direct_play",
        }.get(overlay_id)
        try:
            rendered, _ = _load_render_preview_image(data, family)
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc)}), 400

        image_bytes = BytesIO()
        rendered.save(image_bytes, format="PNG")
        image_bytes.seek(0)
        return send_file(image_bytes, mimetype="image/png")

    use_resolution = bool(data.get("use_resolution", True))
    use_edition = bool(data.get("use_edition", True))
    spacing = data.get("spacing", 15)
    try:
        spacing = max(0, int(spacing))
    except (TypeError, ValueError):
        spacing = 15

    if not use_resolution and not use_edition:
        return jsonify({"status": "error", "message": "No resolution or edition badge is enabled for preview."}), 400

    try:
        resolution_img = None
        edition_img = None
        if use_resolution:
            resolution_img, _ = _load_render_preview_image(data, "resolution")
        if use_edition:
            edition_img, _ = _load_render_preview_image(data, "edition")
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    if resolution_img and edition_img:
        canvas_width = max(resolution_img.width, edition_img.width)
        canvas_height = resolution_img.height + spacing + edition_img.height
        rendered = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 0))
        rendered.paste(resolution_img, ((canvas_width - resolution_img.width) // 2, 0), resolution_img)
        rendered.paste(edition_img, ((canvas_width - edition_img.width) // 2, resolution_img.height + spacing), edition_img)
    elif resolution_img:
        rendered = resolution_img
    elif edition_img:
        rendered = edition_img
    else:
        return jsonify({"status": "error", "message": "Unable to build overlay render preview."}), 400

    image_bytes = BytesIO()
    rendered.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    return send_file(image_bytes, mimetype="image/png")


@bp.route("/generate_preview", methods=["POST"])
def generate_preview():
    data = request.json
    img_type = data.get("type", "movie")
    selected_image = data.get("selected_image", "default.png")
    library_id = data.get("library_id", "default-library")

    # Lazy-load overlay metadata so we can honor JSON-defined URLs (e.g., edition overlays)
    if not hasattr(generate_preview, "_overlay_meta"):
        overlay_cfg = helpers.load_quickstart_overlay_config() or []
        meta = {}
        for group in overlay_cfg:
            for ov in group.get("overlays", []):
                ov_id = ov.get("id")
                if ov_id:
                    meta[ov_id] = ov
        generate_preview._overlay_meta = meta
    overlay_meta = getattr(generate_preview, "_overlay_meta", {})

    def fetch_image_from_url(url: str) -> Image.Image | None:
        try:
            if not url:
                return None
            cache_path = None
            try:
                ext = os.path.splitext(urlparse(url).path)[1].lower()
                if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
                    ext = ".png"
                cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
                cache_path = os.path.join(assets.OVERLAY_CACHE_FOLDER, f"{cache_key}{ext}")
                if os.path.exists(cache_path):
                    age = time.time() - os.path.getmtime(cache_path)
                    if age <= assets.OVERLAY_CACHE_TTL_SECONDS:
                        with Image.open(cache_path) as cached_img:
                            return cached_img.copy()
            except Exception:
                cache_path = None

            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            content = resp.content
            if cache_path:
                try:
                    with open(cache_path, "wb") as handle:
                        handle.write(content)
                except Exception as e:
                    helpers.ts_log(f"Failed to cache overlay image {cache_path}: {e}", level="WARNING")
            return Image.open(BytesIO(content))
        except Exception as e:
            helpers.ts_log(f"Failed to fetch overlay image from {url}: {e}", level="WARNING")
            return None

    # Normalize overlays from dict (by type) or flat list
    raw_overlays = data.get("overlays", {})
    if isinstance(raw_overlays, dict):
        overlays = raw_overlays.get(img_type, [])
    elif isinstance(raw_overlays, list):
        overlays = raw_overlays
    else:
        overlays = []

    if img_type not in ["movie", "show", "season", "episode"]:
        return jsonify({"status": "error", "message": "Invalid type"}), 400

    if not os.path.exists(assets.PREVIEW_FOLDER):
        os.makedirs(assets.PREVIEW_FOLDER)

    preview_filename = f"{library_id}-{img_type}_preview.png"
    preview_filepath = os.path.join(assets.PREVIEW_FOLDER, preview_filename)

    # Resolve base image
    base_image_path = assets.resolve_preview_base_image_path(img_type, selected_image)
    if not os.path.exists(base_image_path):
        fallback_size = (1920, 1080) if img_type == "episode" else (1000, 1500)
        base_img = Image.new("RGBA", fallback_size, (128, 128, 128, 255))
        base_img.save(base_image_path)

    if not os.path.exists(base_image_path):
        return jsonify({"status": "error", "message": "Selected image not found."}), 400

    # Open and resize base image
    base_img = Image.open(base_image_path).convert("RGBA")
    size = (1920, 1080) if img_type == "episode" else (1000, 1500)
    base_img = base_img.resize(size, Image.LANCZOS)

    # Determine filename prefix
    if img_type == "movie":
        prefix = "mov-"
    elif img_type == "episode":
        prefix = "epi-sho-"
    elif img_type == "season":
        prefix = "sho-season-"
    elif img_type == "show":
        prefix = "sho-"
    else:
        prefix = ""

    def render_runtime_overlay(tv: dict, canvas_size: tuple[int, int]) -> Image.Image | None:
        try:
            width, height = canvas_size
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            prefix = str(tv.get("text", "Runtime: "))
            fmt = str(tv.get("format", "<<runtimeH>>h <<runtimeM>>m"))
            runtime_minutes = tv.get("runtime_minutes", 93)
            try:
                runtime_minutes = int(runtime_minutes)
            except Exception:
                runtime_minutes = 93
            runtime_h = runtime_minutes // 60
            runtime_m = runtime_minutes % 60

            rendered_fmt = (
                fmt.replace("<<runtimeH>>", str(runtime_h))
                .replace("<<runtimeM>>", str(runtime_m))
                .replace("<<runtime_total>>", str(runtime_minutes))
                .replace("<<runtime>>", str(runtime_minutes))
            )
            text = f"{prefix}{rendered_fmt}"

            font_size = tv.get("font_size", 55)
            try:
                font_size = int(font_size)
            except Exception:
                font_size = 55
            font_path = str(tv.get("font", "") or "").strip()

            # Resolve font path against known font directory if a basename is given
            font = None
            font_candidates = []
            if font_path:
                font_candidates.append(font_path)
                base_font = os.path.basename(font_path)
                for fdir in helpers.get_font_dirs(include_static=True, include_custom=True):
                    font_candidates.append(os.path.join(str(fdir), base_font))
            seen_candidates = set()
            font_candidates = [c for c in font_candidates if c and not (c in seen_candidates or seen_candidates.add(c))]
            for candidate in font_candidates:
                if candidate and os.path.exists(candidate):
                    try:
                        font = ImageFont.truetype(candidate, font_size)
                        break
                    except Exception:
                        font = None
            if font is None:
                font = ImageFont.load_default()

            color_val = tv.get("font_color", "#FFFFFF")
            try:
                fill = ImageColor.getcolor(str(color_val), "RGBA")
            except Exception:
                fill = (255, 255, 255, 255)

            margin = 20
            draw.text((width - margin, height - margin), text, fill=fill, font=font, anchor="rb")
            return img
        except Exception as e:
            helpers.ts_log(f"Failed to render runtime overlay: {e}", level="WARNING")
            return None

    # Apply overlays with template_variables support
    for overlay_entry in overlays:
        if isinstance(overlay_entry, str):
            overlay_id = overlay_entry
            template_vars = {}
        elif isinstance(overlay_entry, dict):
            overlay_id = overlay_entry.get("id")
            template_vars = overlay_entry.get("template_variables", {})

            # Normalize booleans to lowercase strings (e.g., True → "true")
            template_vars = {k: str(v).lower() if isinstance(v, bool) else v for k, v in template_vars.items()}
        else:
            continue  # skip invalid overlay data

        # Build filename suffix from all template_variables (sorted for consistency)
        suffix_parts = [f"{key}_{value}" for key, value in sorted(template_vars.items()) if key in {"style", "size", "color"}]
        suffix = "_" + "_".join(suffix_parts) if suffix_parts else ""
        filename = f"{prefix}{img_type}-{overlay_id}{suffix}.png"
        overlay_path = os.path.join(assets.OVERLAY_FOLDER, filename)

        # Fallback to default overlay if specific style not found
        if not os.path.exists(overlay_path) and suffix:
            fallback_filename = f"{prefix}{img_type}-{overlay_id}.png"
            fallback_path = os.path.join(assets.OVERLAY_FOLDER, fallback_filename)
            if os.path.exists(fallback_path):
                overlay_path = fallback_path

        if os.path.exists(overlay_path):
            if overlay_id == "overlay_runtimes":
                runtime_img = render_runtime_overlay(template_vars, base_img.size)
                if runtime_img:
                    base_img.paste(runtime_img, (0, 0), runtime_img)
                    continue  # skip default image paste

            overlay_img = Image.open(overlay_path).convert("RGBA")
            base_img.paste(overlay_img, (0, 0), overlay_img)

            # Stack edition overlay below resolution when enabled.
            if overlay_id == "overlay_resolution":
                use_edition = str(template_vars.get("use_edition", "false")).lower() == "true"
                if use_edition:
                    bbox = overlay_img.getbbox()
                    if bbox:
                        edition_url = overlay_meta.get("overlay_resolution", {}).get("edition_overlay_url")
                        edition_img = fetch_image_from_url(edition_url) if edition_url else None
                        if edition_img:
                            edition_img = edition_img.convert("RGBA")
                            x_offset = bbox[0]
                            spacing = 15
                            y_offset = bbox[3] + spacing
                            base_img.paste(edition_img, (x_offset, y_offset), edition_img)

    base_img.save(preview_filepath)

    return jsonify({"status": "success", "preview_url": f"/{preview_filepath}"})


@bp.route("/config/previews/<path:filename>")
def serve_previews(filename):
    return send_from_directory(assets.PREVIEW_FOLDER, filename)


@bp.route("/config/uploads/<path:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(assets.UPLOAD_FOLDER, filename)


@bp.route("/get_preview_image/<img_type>", methods=["GET"])
def get_preview_image(img_type):
    preview_filename = f"{img_type}_preview.png"
    preview_path = os.path.join(assets.PREVIEW_FOLDER, preview_filename)

    if not os.path.exists(preview_path):
        generate_preview()

    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype="image/png")

    return jsonify({"status": "error", "message": "Preview image not found"}), 400


@bp.route("/config/previews/<filename>")
def serve_preview_image(filename):
    safe_path = helpers.safe_join(assets.PREVIEW_FOLDER, filename)
    if safe_path and safe_path.exists():
        return send_file(safe_path, mimetype="image/png")
    return send_file(os.path.join(assets.IMAGES_FOLDER, "default.png"), mimetype="image/png")


@bp.route("/delete_library_image/<filename>", methods=["DELETE"])
def delete_library_image(filename):
    image_type = request.args.get("type")

    if image_type not in assets.UPLOAD_FOLDERS:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    uploads_dir = assets.UPLOAD_FOLDERS[image_type]
    file_path = helpers.safe_join(uploads_dir, filename)
    if not file_path:
        return jsonify({"status": "error", "message": "Invalid file name"}), 400

    if not file_path.exists():
        return jsonify({"status": "error", "message": "File not found"}), 404

    try:
        os.remove(file_path)
        return jsonify({"status": "success", "message": f"Deleted {filename}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
