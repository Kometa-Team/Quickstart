import argparse
import io
import json
import os
import hashlib
import platform
import psutil
import shutil
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
import secrets
from io import BytesIO
from threading import Thread
from pathlib import Path
from collections import deque
from urllib.parse import urlparse

import namesgenerator
import requests
from PIL import Image, ImageDraw, ImageFont, ImageColor
from cachelib.file import FileSystemCache
from datetime import datetime
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
    send_from_directory,
)
from waitress import serve
from werkzeug.datastructures import MultiDict
from werkzeug.utils import secure_filename

from werkzeug.wrappers import Request

Request.max_form_parts = 100000  # Allow more form fields if needed

from flask_session import Session
from modules import validations, output, persistence, helpers, database
from typing import Dict, Any

# A very simple in-memory progress store
CLONE_PROGRESS: Dict[str, Dict[str, Any]] = {}

DOTENV = os.path.relpath(os.path.join(helpers.CONFIG_DIR, ".env"))
load_dotenv(DOTENV, override=True)

UPLOAD_FOLDER = os.path.join(helpers.CONFIG_DIR, "uploads")
UPLOAD_FOLDERS = {
    "movie": os.path.join(UPLOAD_FOLDER, "movies"),
    "show": os.path.join(UPLOAD_FOLDER, "shows"),
    "season": os.path.join(UPLOAD_FOLDER, "seasons"),
    "episode": os.path.join(UPLOAD_FOLDER, "episodes"),
}
# Ensure all upload subdirectories exist
for folder in UPLOAD_FOLDERS.values():
    os.makedirs(folder, exist_ok=True)
IMAGES_FOLDER = os.path.join(helpers.MEIPASS_DIR, "static", "images")
OVERLAY_FOLDER = os.path.join(IMAGES_FOLDER, "overlays")
FONTS_FOLDER = os.path.join(helpers.MEIPASS_DIR, "static", "fonts")
DEFAULT_IMAGE_MAP = {
    "movie": os.path.join(IMAGES_FOLDER, "default.png"),
    "show": os.path.join(IMAGES_FOLDER, "default-sho_preview.png"),
    "season": os.path.join(IMAGES_FOLDER, "default-season_preview.png"),
    "episode": os.path.join(IMAGES_FOLDER, "default-episode_preview.png"),
}
PREVIEW_FOLDER = os.path.join(helpers.CONFIG_DIR, "previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)
OVERLAY_CACHE_FOLDER = os.path.join(helpers.CONFIG_DIR, "cache", "overlays")
os.makedirs(OVERLAY_CACHE_FOLDER, exist_ok=True)
OVERLAY_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30
_FONT_CACHE: list[str] = []


# Font discovery (TTF/OTF) across common static dirs
def list_overlay_fonts() -> list[str]:
    global _FONT_CACHE
    if _FONT_CACHE:
        return _FONT_CACHE
    fonts: list[str] = []
    font_dirs = [
        os.path.join(helpers.MEIPASS_DIR, "static", "fonts"),
        os.path.join(helpers.BASE_DIR, "static", "fonts"),
        os.path.join(helpers.WORKING_DIR, "static", "fonts"),
    ]
    for fdir in font_dirs:
        try:
            if os.path.isdir(fdir):
                for fname in os.listdir(fdir):
                    if fname.lower().endswith((".ttf", ".otf")) and fname not in fonts:
                        fonts.append(fname)
        except Exception:
            continue
    _FONT_CACHE = fonts
    return fonts


# Initialize logging
helpers.initialize_logging()

GITHUB_MASTER_VERSION_URL = "https://raw.githubusercontent.com/Kometa-Team/Quickstart/master/VERSION"
GITHUB_DEVELOP_VERSION_URL = "https://raw.githubusercontent.com/Kometa-Team/Quickstart/develop/VERSION"

basedir = os.path.abspath
kometa_process = None

app = Flask(__name__)

# Run version check at startup
app.config["VERSION_CHECK"] = helpers.check_for_update()

# Path to the 'kometa' directory next to 'quickstart'
base_dir = os.path.dirname(os.path.abspath(__file__))
kometa_path = os.path.abspath(os.path.join(base_dir, "..", "kometa"))

app.config["KOMETA_ROOT"] = os.environ.get("QS_KOMETA_PATH", kometa_path)


def start_update_thread():
    """Ensure update_checker_loop runs inside the Flask app context."""
    with app.app_context():
        while True:
            app.config["VERSION_CHECK"] = helpers.check_for_update()
            time.sleep(86400)  # Sleep for 24 hours


# Start the background version checker safely
threading.Thread(target=start_update_thread, daemon=True).start()


@app.context_processor
def inject_version_info():
    """Ensure latest version info is injected dynamically in templates"""
    return {
        "version_info": helpers.check_for_update(),
        "overlay_fonts": list_overlay_fonts(),
    }


def inject_kometa_root():
    return {"kometa_root": app.config["KOMETA_ROOT"]}


# Use booler() for FLASK_DEBUG conversion
app.config["QS_DEBUG"] = helpers.booler(os.getenv("QS_DEBUG", "0"))
app.config["QUICKSTART_DOCKER"] = helpers.booler(os.getenv("QUICKSTART_DOCKER", "0"))

app.config["SESSION_TYPE"] = "cachelib"

# Flask session cache dir (portable default)
flask_cache_dir = os.environ.get("QS_FLASK_SESSION_DIR", os.path.join(helpers.CONFIG_DIR, "flask_session"))
os.makedirs(flask_cache_dir, exist_ok=True)

app.config["SESSION_CACHELIB"] = FileSystemCache(cache_dir=flask_cache_dir, threshold=500)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = False

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB, adjust as needed
app.config["MAX_FORM_MEMORY_SIZE"] = 16 * 1024 * 1024  # 16 MB


@app.before_request
def before_request():
    # Assign user UUID if not already present
    if "qs_session_id" not in session:
        session["qs_session_id"] = str(uuid.uuid4())[:8]

    # Log request size if applicable
    if request.content_length:
        helpers.ts_log(f"Incoming request size: {request.content_length / 1024:.2f} KB", level="DEBUG")

    # Only applies to form-encoded POSTs
    if request.method == "POST" and (request.content_type or "").startswith("application/x-www-form-urlencoded"):
        try:
            form_data = request.form
            helpers.ts_log(f"Form field count: {len(form_data)}", level="DEBUG")
        except Exception as e:
            helpers.ts_log(f"Failed to parse form: {e}", level="ERROR")


@app.route("/update-quickstart", methods=["POST"])
def update_quickstart():
    logs = []

    try:
        data = request.get_json(silent=True) or {}
        branch = data.get("branch", "master")

        result = helpers.perform_quickstart_update(app.root_path, branch=branch)
        logs.extend(result.get("log", []))
        status = 200 if result.get("success") else 500

        return (
            jsonify(
                {
                    "success": result.get("success", False),
                    "log": logs,
                    "branch": branch,
                }
            ),
            status,
        )

    except Exception as e:
        logs.append(f"Exception during Quickstart update: {e}")
        return jsonify({"success": False, "log": logs}), 500


# Initialize Flask-Session
server_session = Session(app)
server_thread = None
shutdown_event = threading.Event()

# Ensure json-schema files are up to date at startup
helpers.ensure_json_schema()

parser = argparse.ArgumentParser(description="Run Quickstart Flask App")
parser.add_argument("--port", type=int, help="Specify the port number to run the server")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
args = parser.parse_args()

port = args.port if args.port else int(os.getenv("QS_PORT", "7171"))
running_port = port
debug_mode = args.debug if args.debug else helpers.booler(os.getenv("QS_DEBUG", "0"))

helpers.ts_log(f"Running on port: {port} | Debug Mode: {'Enabled' if debug_mode else 'Disabled'}", level="INFO")


@app.route("/upload_library_image", methods=["POST"])
def upload_library_image():
    if "image" not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400
    image = request.files["image"]
    image_type = request.form.get("type")

    if not image or image_type not in UPLOAD_FOLDERS:
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
    save_folder = UPLOAD_FOLDERS[image_type]
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


@app.route("/fetch_library_image", methods=["POST"])
def fetch_library_image():
    data = request.json
    image_url = data.get("url")
    image_type = data.get("type")

    if not image_url or image_type not in UPLOAD_FOLDERS:
        return (
            jsonify({"status": "error", "message": "Invalid request parameters"}),
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
        save_folder = UPLOAD_FOLDERS[image_type]
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


@app.route("/rename_library_image", methods=["POST"])
def rename_library_image():
    data = request.json
    old_name = data.get("old_name")
    new_name = data.get("new_name")
    image_type = data.get("type")

    if not old_name or not new_name or image_type not in UPLOAD_FOLDERS:
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    save_folder = UPLOAD_FOLDERS[image_type]
    old_path = os.path.join(save_folder, old_name)

    if not os.path.exists(old_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    old_ext = os.path.splitext(old_name)[1]
    if "." not in new_name:
        new_name += old_ext
    elif not new_name.endswith(old_ext):
        new_name += old_ext

    new_path = os.path.join(save_folder, new_name)
    if os.path.exists(new_path):
        return (
            jsonify({"status": "error", "message": "File with new name already exists"}),
            400,
        )

    try:
        os.rename(old_path, new_path)
        return jsonify({"status": "success", "message": "File renamed successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/list_uploaded_images", methods=["GET"])
def list_uploaded_images():
    image_type = request.args.get("type")
    if image_type not in UPLOAD_FOLDERS:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    uploads_dir = UPLOAD_FOLDERS[image_type]
    if not os.path.exists(uploads_dir):
        return jsonify({"images": []})

    images = [img for img in os.listdir(uploads_dir) if any(img.lower().endswith(f".{ext}") for ext in helpers.ALLOWED_EXTENSIONS)]

    return jsonify({"status": "success", "images": images})


@app.route("/generate_preview", methods=["POST"])
def generate_preview():
    data = request.json
    img_type = data.get("type", "movie")
    selected_image = data.get("selected_image", "default.png")
    library_id = data.get("library_id", "default-library")

    # Lazy-load overlay metadata so we can honor JSON-defined URLs (e.g., edition overlays)
    if not hasattr(generate_preview, "_overlay_meta"):
        overlay_cfg = helpers.load_quickstart_config("quickstart_overlays.json") or []
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
                cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()
                cache_path = os.path.join(OVERLAY_CACHE_FOLDER, f"{cache_key}{ext}")
                if os.path.exists(cache_path):
                    age = time.time() - os.path.getmtime(cache_path)
                    if age <= OVERLAY_CACHE_TTL_SECONDS:
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

    if not os.path.exists(PREVIEW_FOLDER):
        os.makedirs(PREVIEW_FOLDER)

    preview_filename = f"{library_id}-{img_type}_preview.png"
    preview_filepath = os.path.join(PREVIEW_FOLDER, preview_filename)

    # Resolve base image
    if not selected_image or selected_image == "default":
        base_image_path = DEFAULT_IMAGE_MAP.get(img_type, DEFAULT_IMAGE_MAP["movie"])
        if not os.path.exists(base_image_path):
            fallback_size = (1920, 1080) if img_type == "episode" else (1000, 1500)
            base_img = Image.new("RGBA", fallback_size, (128, 128, 128, 255))
            base_img.save(base_image_path)
    else:
        base_image_path = os.path.join(UPLOAD_FOLDERS[img_type], selected_image)

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
                font_candidates.append(os.path.join(FONTS_FOLDER, os.path.basename(font_path)))
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
        overlay_path = os.path.join(OVERLAY_FOLDER, filename)

        # Fallback to default overlay if specific style not found
        if not os.path.exists(overlay_path) and suffix:
            fallback_filename = f"{prefix}{img_type}-{overlay_id}.png"
            fallback_path = os.path.join(OVERLAY_FOLDER, fallback_filename)
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

            # Stack edition overlay below resolution when enabled
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


@app.route("/config/previews/<path:filename>")
def serve_previews(filename):
    return send_from_directory(PREVIEW_FOLDER, filename)


@app.route("/config/uploads/<path:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/get_preview_image/<img_type>", methods=["GET"])
def get_preview_image(img_type):
    preview_filename = f"{img_type}_preview.png"
    preview_path = os.path.join(PREVIEW_FOLDER, preview_filename)

    if not os.path.exists(preview_path):
        generate_preview()

    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype="image/png")

    return jsonify({"status": "error", "message": "Preview image not found"}), 400


@app.route("/config/previews/<filename>")
def serve_preview_image(filename):
    path = os.path.join(PREVIEW_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    return send_file(os.path.join(IMAGES_FOLDER, "default.png"), mimetype="image/png")
    try:
        data = request.get_json()
        helpers.ts_log(f"Received data: %s", data, level="INFO")  # Log the received data
        return jsonify({"status": "success"})
    except Exception as e:
        helpers.ts_log(f"Error updating libraries: %s", str(e), level="ERROR")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/delete_library_image/<filename>", methods=["DELETE"])
def delete_library_image(filename):
    image_type = request.args.get("type")

    if image_type not in UPLOAD_FOLDERS:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    uploads_dir = UPLOAD_FOLDERS[image_type]
    file_path = os.path.join(uploads_dir, filename)

    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    try:
        os.remove(file_path)
        return jsonify({"status": "success", "message": f"Deleted {filename}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/")
def start():
    return redirect(url_for("step", name="001-start"))


@app.route("/clear_session", methods=["POST"])
def clear_session():
    data = request.values
    try:
        config_name = data["name"]
        if config_name != session["config_name"]:
            session["config_name"] = config_name
    except KeyError:  # Handle missing `name` key safely
        config_name = session.get("config_name")

    persistence.flush_session_storage(config_name)

    # Send message to toast
    return jsonify(
        {
            "status": "success",
            "message": f"Session storage cleared for '{config_name}'.",
        }
    )


@app.route("/clear_data/<name>/<section>")
def clear_data_section(name, section):
    database.reset_data(name, section)
    flash("SQLite storage cleared successfully.", "success")
    return redirect(url_for("start"))


@app.route("/clear_data/<name>")
def clear_data(name):
    database.reset_data(name)
    flash("SQLite storage cleared successfully.", "success")
    return redirect(url_for("start"))


@app.route("/switch-config", methods=["POST"])
def switch_config():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(success=False, message="Config name is required."), 400

    available = database.get_unique_config_names() or []
    if name not in available:
        return jsonify(success=False, message="Config not found."), 404

    session["config_name"] = name
    return jsonify(success=True, name=name)


@app.route("/bulk-delete-configs", methods=["POST"])
def bulk_delete_configs():
    data = request.get_json(silent=True) or {}
    names = data.get("names") or []
    if not isinstance(names, list):
        return jsonify(success=False, message="Invalid request payload."), 400

    cleaned = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    if not cleaned:
        return jsonify(success=False, message="No profiles selected."), 400

    available = set(database.get_unique_config_names() or [])
    deleted = []
    for name in cleaned:
        if name in available:
            database.reset_data(name)
            deleted.append(name)

    remaining = database.get_unique_config_names() or []
    current = session.get("config_name")
    if current in deleted:
        session["config_name"] = remaining[0] if remaining else namesgenerator.get_random_name()
        current = session["config_name"]

    return jsonify(success=True, deleted=deleted, remaining=remaining, current=current)


@app.route("/step/<name>", methods=["GET", "POST"])
def step(name):
    page_info = {}
    header_style = "standard"  # Default to 'standard' font

    if request.method == "POST":
        persistence.save_settings(request.referrer, request.form)
        header_style = request.form.get("header_style", "standard")

    # --- Detect config change ---
    previous_config = session.get("config_name")
    selected_config = request.form.get("configSelector") or previous_config
    new_config_name = request.form.get("newConfigName")

    if selected_config == "add_config" and new_config_name:
        selected_config = new_config_name.strip()

    if not selected_config:
        selected_config = previous_config or namesgenerator.get_random_name()

    config_changed = selected_config != previous_config

    # Retrieve available fonts (ensuring "none" and "single line" are always included)
    available_fonts = helpers.get_pyfiglet_fonts()

    page_info["available_fonts"] = available_fonts

    # Ensure session["config_name"] always exists
    if "config_name" not in session:
        session["config_name"] = namesgenerator.get_random_name()
        helpers.ts_log(f"Assigned new config_name: {session['config_name']}")

    # Retrieve stored settings from DB
    saved_settings = persistence.retrieve_settings(name)  # Retrieve from DB

    # Ensure we correctly access header_style from "final"
    if "final" in saved_settings and "header_style" in saved_settings["final"]:
        header_style = saved_settings["final"]["header_style"]

    if header_style is None:
        header_style = "none"

    # Ensure the selected font is valid
    if header_style not in available_fonts:
        header_style = "standard"

    page_info["header_style"] = header_style  # Now properly restored

    # Get selected config from form data (sent from the dropdown)
    selected_config = request.form.get("configSelector")  # Comes from the dropdown
    new_config_name = request.form.get("newConfigName")  # If "Add Config" is used

    # If "Add Config" is selected, use newConfigName instead
    if selected_config == "add_config" and new_config_name:
        selected_config = new_config_name.strip()

    # If no config is selected, fall back to the session or generate a new one
    if not selected_config:
        selected_config = session.get("config_name") or namesgenerator.get_random_name()

    # Update session with the chosen config
    session["config_name"] = selected_config
    page_info["config_name"] = selected_config
    page_info["header_style"] = header_style
    page_info["template_name"] = name
    if name == "001-start":
        session["shutdown_nonce"] = secrets.token_urlsafe(16)
        page_info["shutdown_nonce"] = session["shutdown_nonce"]

    # Generate a placeholder name for "Add Config"
    page_info["new_config_name"] = namesgenerator.get_random_name()

    # Fetch available configurations from the database
    available_configs = database.get_unique_config_names() or []

    # Ensure the selected config is either in the dropdown or newly created
    if selected_config not in available_configs:
        page_info["new_config_name"] = selected_config  # Use the new config name

    file_list = helpers.get_menu_list()
    template_list = helpers.get_template_list()
    total_steps = len(template_list)

    stem, num, b = helpers.get_bits(name)

    try:
        current_index = list(template_list).index(num)
        item = template_list[num]
    except (ValueError, IndexError, KeyError):
        return f"ERROR WITH NAME {name}; stem, num, b: {stem}, {num}, {b}"

    page_info["progress"] = round((current_index + 1) / total_steps * 100)
    page_info["title"] = item["name"]
    page_info["next_page"] = item["next"]
    page_info["prev_page"] = item["prev"]

    try:
        # Only split if the value is not None or empty
        if page_info["next_page"]:
            next_num = page_info["next_page"].split("-")[0]
            page_info["next_page_name"] = template_list.get(next_num, {}).get("name", "Next")
        else:
            page_info["next_page_name"] = "Next"

        if page_info["prev_page"]:
            prev_num = page_info["prev_page"].split("-")[0]
            page_info["prev_page_name"] = template_list.get(prev_num, {}).get("name", "Previous")
        else:
            page_info["prev_page_name"] = "Previous"

    except Exception as e:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Failed to get page names: {e}", level="ERROR")
        page_info["next_page_name"] = "Next"
        page_info["prev_page_name"] = "Previous"

    # Retrieve data from storage
    data = persistence.retrieve_settings(name)
    debug_dir = os.path.join(helpers.CONFIG_DIR, "debug_logs")
    os.makedirs(debug_dir, exist_ok=True)

    debug_path = os.path.join(debug_dir, f"{name}_retrieved_data.json")

    if app.config["QS_DEBUG"]:
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        helpers.ts_log(f"Raw data written to {debug_path}", level="DEBUG")

    # Check for kometa_root
    if "kometa_root" not in session:
        session["kometa_root"] = app.config.get("KOMETA_ROOT", "")

    # Fetch Plex settings
    all_libraries = persistence.retrieve_settings("010-plex")

    # Ensure 'plex' key exists before accessing sub-keys
    plex_data = all_libraries.get("plex", {})

    # --- Refresh Plex data if needed ---
    if name in ["010-plex", "025-libraries", "900-final"] or config_changed:
        refresh_plex_libraries()
        telemetry = persistence.retrieve_settings("plex_telemetry")
    else:
        telemetry = persistence.retrieve_settings("plex_telemetry")

    telemetry_data = telemetry.get("plex_telemetry")

    # If telemetry is fresher in plex_data, use that
    telemetry_data = plex_data.get("telemetry")
    if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
        telemetry_data = telemetry.get("plex_telemetry", {})

        # Fallback if DB is also missing it
        if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
            telemetry_data = {
                "plex_pass": None,
                "server_name": "Unavailable",
                "version": "Unavailable",
                "platform": "Unavailable",
                "update_channel": "Unavailable",
                "libraries": {},
            }
            helpers.ts_log(f"Telemetry fallback triggered due to missing or invalid telemetry for config: {selected_config}", level="WARNING")
    else:
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Using telemetry from fresh plex_data", level="DEBUG")

    page_info["telemetry"] = telemetry_data

    # Extract the movie and show libraries
    movie_libraries_raw = plex_data.get("tmp_movie_libraries", "")
    show_libraries_raw = plex_data.get("tmp_show_libraries", "")

    # Debugging extracted values
    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Extracted movie libraries:", movie_libraries_raw, level="DEBUG")
        helpers.ts_log(f"Extracted show libraries:", show_libraries_raw, level="DEBUG")

    # Ensure it's a string before splitting
    if not isinstance(movie_libraries_raw, str):
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"tmp_movie_libraries is not a string!", level="ERROR")

        movie_libraries_raw = ""

    if not isinstance(show_libraries_raw, str):
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"tmp_show_libraries is not a string!", level="ERROR")

        show_libraries_raw = ""

    existing_ids = set()  # Track used IDs to prevent duplicates

    movie_libraries = [
        {
            "id": f"mov-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "movie",
        }
        for lib in movie_libraries_raw.split(",")
        if lib.strip()
    ]

    show_libraries = [
        {
            "id": f"sho-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "show",
        }
        for lib in show_libraries_raw.split(",")
        if lib.strip()
    ]

    # Ensure `libraries` dictionary exists
    if "libraries" not in data:
        data["libraries"] = {}

    # Ensure `mov-template_variables` and `sho-template_variables` exist inside `libraries`
    if "mov-template_variables" not in data["libraries"]:
        data["libraries"]["mov-template_variables"] = {}

    if "sho-template_variables" not in data["libraries"]:
        data["libraries"]["sho-template_variables"] = {}

    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"************************************************************************", level="DEBUG")
        helpers.ts_log(f"Data retrieved for {name}", level="DEBUG")

    (
        page_info["plex_valid"],
        page_info["tmdb_valid"],
        page_info["libs_valid"],
        page_info["sett_valid"],
    ) = persistence.check_minimum_settings()

    (
        page_info["notifiarr_available"],
        page_info["gotify_available"],
        page_info["ntfy_available"],
    ) = persistence.notification_systems_available()

    # Ensure template variables exist
    if "mov-template_variables" not in data:
        data["mov-template_variables"] = {}
    if "sho-template_variables" not in data:
        data["sho-template_variables"] = {}

    # Ensure these are lists
    plex_data["tmp_movie_libraries"] = plex_data.get("tmp_movie_libraries", "").split(",") if isinstance(plex_data.get("tmp_movie_libraries"), str) else []
    plex_data["tmp_show_libraries"] = plex_data.get("tmp_show_libraries", "").split(",") if isinstance(plex_data.get("tmp_show_libraries"), str) else []
    plex_data["tmp_music_libraries"] = plex_data.get("tmp_music_libraries", "").split(",") if isinstance(plex_data.get("tmp_music_libraries"), str) else []
    plex_data["tmp_user_list"] = plex_data.get("tmp_user_list", "").split(",") if isinstance(plex_data.get("tmp_user_list"), str) else []

    # Ensure correct rendering for the final validation page
    config_name = session.get("config_name") or page_info.get("config_name", "default")
    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Start render_template for {name}", level="DEBUG")

    start_time = time.perf_counter()

    helpers.ts_log(f"Loading attribute_config...", level="TIMING")
    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json")
    helpers.ts_log(f"Loading collection_config...", level="TIMING")
    collection_config = helpers.load_quickstart_config("quickstart_collections.json")
    helpers.ts_log(f"Loading overlay_config...", level="TIMING")
    overlay_config = helpers.load_quickstart_config("quickstart_overlays.json")

    def add_offset_vars(config):
        """
        Ensure each overlay exposes positional offsets with sensible defaults.
        """
        for group in config or []:
            overlays = group.get("overlays", [])
            for ov in overlays:
                tv = ov.get("template_variables")
                if tv is None:
                    tv = {}
                    ov["template_variables"] = tv
                elif not isinstance(tv, dict):
                    # leave lists (legacy) untouched
                    continue
                offsets = ov.get("default_offsets", {}) if isinstance(ov.get("default_offsets"), dict) else {}
                # Respect initial_* overrides (used for YAML naming) but surface as horizontal/vertical inputs
                if "initial_horizontal_offset" in tv and isinstance(tv["initial_horizontal_offset"], dict):
                    offsets["horizontal"] = tv["initial_horizontal_offset"].get("default", offsets.get("horizontal", 0))
                if "initial_vertical_offset" in tv and isinstance(tv["initial_vertical_offset"], dict):
                    offsets["vertical"] = tv["initial_vertical_offset"].get("default", offsets.get("vertical", 0))
                h_def = offsets.get("horizontal", 0)
                v_def = offsets.get("vertical", 0)
                # Only add if not already present
                tv.setdefault(
                    "horizontal_offset",
                    {
                        "input_type": "number",
                        "default": h_def,
                        "label": "Horizontal Offset",
                    },
                )
                tv.setdefault(
                    "vertical_offset",
                    {
                        "input_type": "number",
                        "default": v_def,
                        "label": "Vertical Offset",
                    },
                )

    add_offset_vars(overlay_config)

    if name == "900-final":
        validated, validation_error, config_data, yaml_content = output.build_config(header_style, config_name=config_name)
        saved_filename = helpers.save_to_named_config(yaml_content, config_name)
        page_info["saved_filename"] = saved_filename
        page_info["yaml_valid"] = validated
        page_info["quickstart_root"] = helpers.get_app_root()
        session["yaml_content"] = yaml_content
        library_settings = persistence.retrieve_settings("025-libraries").get("libraries", {})
        movie_libraries = []
        show_libraries = []
        existing_ids = set()

        for key, value in library_settings.items():
            if key.startswith("mov-library_") and key.endswith("-library"):
                movie_libraries.append({"id": key.split("-library")[0], "name": value, "type": "movie"})
            elif key.startswith("sho-library_") and key.endswith("-library"):
                show_libraries.append({"id": key.split("-library")[0], "name": value, "type": "show"})

        html = render_template(
            "900-final.html",
            page_info=page_info,
            data=data,
            yaml_content=yaml_content,
            validation_error=validation_error,
            template_list=file_list,
            available_configs=available_configs,
            movie_libraries=movie_libraries,
            show_libraries=show_libraries,
            config_dir=str(Path(helpers.CONFIG_DIR).resolve()),
            overlay_fonts=list_overlay_fonts(),
        )

        end_time = time.perf_counter()
        if app.config["QS_DEBUG"]:
            helpers.ts_log(f"Rendered 900-final.html in {end_time - start_time:.2f} seconds", level="PROFILE")
        return html

    else:
        helpers.ts_log(f"Loading quickstart_root...", level="TIMING")
        page_info["quickstart_root"] = helpers.get_app_root()
        helpers.ts_log(f"Start render_template...", level="TIMING")

    configured_ids = _configured_library_ids(data.get("libraries", {}))
    configured_counts = {
        "movie": sum(1 for lib in movie_libraries if lib["id"] in configured_ids),
        "show": sum(1 for lib in show_libraries if lib["id"] in configured_ids),
    }

    html = render_template(
        name + ".html",
        page_info=page_info,
        data=data,
        telemetry=telemetry,
        plex_data=plex_data,
        movie_libraries=movie_libraries,
        show_libraries=show_libraries,
        attribute_config=attribute_config,
        collection_config=collection_config,
        overlay_config=overlay_config,
        template_list=file_list,
        available_configs=available_configs,
        overlay_fonts=list_overlay_fonts(),
        image_data={
            "movie": os.listdir(UPLOAD_FOLDERS["movie"]),
            "show": os.listdir(UPLOAD_FOLDERS["show"]),
            "season": os.listdir(UPLOAD_FOLDERS["season"]),
            "episode": os.listdir(UPLOAD_FOLDERS["episode"]),
        },
        config_dir=str(Path(helpers.CONFIG_DIR).resolve()),
        configured_ids=configured_ids,
        configured_counts=configured_counts,
    )

    end_time = time.perf_counter()
    if app.config["QS_DEBUG"]:
        helpers.ts_log(f"Rendered {name}.html in {end_time - start_time:.2f} seconds", level="PROFILE")
    return html


@app.route("/get_top_imdb_items/<library_name>")
def get_top_imdb_items_route(library_name):
    media_type = request.args.get("type", "movie")
    placeholder_id = request.args.get("placeholder_id")
    settings = persistence.retrieve_settings("010-plex")
    plex_settings = settings.get("plex", {})

    tmp_key = f"tmp_{media_type}_libraries"
    raw_libraries = plex_settings.get(tmp_key, "")
    library_names = [lib.strip() for lib in raw_libraries.split(",") if lib.strip()]

    helpers.ts_log(f"Searching for library name: {library_name}", level="DEBUG")
    helpers.ts_log(f"Available libraries of type '{media_type}': {library_names}", level="DEBUG")

    if library_name not in library_names:
        return jsonify(
            {
                "status": "error",
                "message": f"Library '{library_name}' not found in Plex settings.",
            }
        )

    # Call with placeholder_id
    items, saved_item = helpers.get_top_imdb_items(library_name, media_type, placeholder_id)

    return jsonify({"status": "success", "items": items, "saved_item": saved_item})


def _configured_library_ids(library_data):
    """Return set of library IDs that have an active '-library' value saved."""
    if not isinstance(library_data, dict):
        return set()
    return {key.rsplit("-library", 1)[0] for key, value in library_data.items() if key.endswith("-library") and value not in [None, "", False]}


def _build_library_lists():
    """Shared helper to return movie/show library descriptors and telemetry data."""
    all_libraries = persistence.retrieve_settings("010-plex")
    plex_data = all_libraries.get("plex", {})
    telemetry = persistence.retrieve_settings("plex_telemetry")

    telemetry_data = plex_data.get("telemetry")
    if not isinstance(telemetry_data, dict) or "plex_pass" not in telemetry_data:
        telemetry_data = telemetry.get("plex_telemetry", {})

    movie_raw = plex_data.get("tmp_movie_libraries", "") if isinstance(plex_data.get("tmp_movie_libraries"), str) else ""
    show_raw = plex_data.get("tmp_show_libraries", "") if isinstance(plex_data.get("tmp_show_libraries"), str) else ""

    existing_ids = set()

    movie_libraries = [
        {
            "id": f"mov-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "movie",
        }
        for lib in movie_raw.split(",")
        if lib.strip()
    ]

    show_libraries = [
        {
            "id": f"sho-library_{helpers.normalize_id(lib.strip(), existing_ids)}",
            "name": lib.strip(),
            "type": "show",
        }
        for lib in show_raw.split(",")
        if lib.strip()
    ]

    return movie_libraries, show_libraries, telemetry_data


@app.route("/library_fragment/<library_id>")
def library_fragment(library_id):
    """Return a single library form fragment so we can lazy-load library settings on the page."""
    movie_libraries, show_libraries, telemetry_data = _build_library_lists()
    all_libraries = {lib["id"]: lib for lib in movie_libraries + show_libraries}
    library = all_libraries.get(library_id)

    if not library:
        return jsonify({"error": "Library not found"}), 404

    attribute_config = helpers.load_quickstart_config("quickstart_attributes.json")
    collection_config = helpers.load_quickstart_config("quickstart_collections.json")
    overlay_config = helpers.load_quickstart_config("quickstart_overlays.json")

    data = persistence.retrieve_settings("025-libraries")
    configured_ids = _configured_library_ids(data.get("libraries", {}))

    image_data = {
        "movie": os.listdir(UPLOAD_FOLDERS["movie"]),
        "show": os.listdir(UPLOAD_FOLDERS["show"]),
        "season": os.listdir(UPLOAD_FOLDERS["season"]),
        "episode": os.listdir(UPLOAD_FOLDERS["episode"]),
    }

    page_info = {"telemetry": telemetry_data}

    html = render_template(
        "partials/_library_card.html",
        library=library,
        data=data,
        page_info=page_info,
        attribute_config=attribute_config,
        collection_config=collection_config,
        overlay_config=overlay_config,
        image_data=image_data,
        movie_images=image_data["movie"],
        configured_ids=configured_ids,
    )

    return html


@app.route("/autosave_library/<library_id>", methods=["POST"])
def autosave_library(library_id):
    """Merge-save a single library when switching cards without requiring full navigation submit."""
    try:
        incoming = request.get_json(silent=True) or request.form
        persistence.save_settings("025-libraries", incoming)
        return jsonify({"success": True})
    except Exception as e:
        helpers.ts_log(f"Autosave failed for library {library_id}: {e}", level="ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/copy_library_settings", methods=["POST"])
def copy_library_settings():
    """Copy saved settings from one library to multiple targets of the same type."""
    try:
        payload = request.get_json(force=True, silent=True) or {}
        source_id = payload.get("source_library_id")
        target_ids = payload.get("target_library_ids") or []
        source_payload = payload.get("source_payload") or {}

        if not source_id or not target_ids:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Missing source or targets (source={source_id}, targets={target_ids})",
                    }
                ),
                400,
            )

        source_prefix = source_id.split("-card-container")[0] if source_id.endswith("-card-container") else source_id
        source_type = source_prefix[:3]  # mov or sho

        if any(not str(t).startswith(source_type) for t in target_ids):
            helpers.ts_log(
                f"Copy aborted: targets must match source type '{source_type}', got targets={target_ids}",
                level="ERROR",
            )
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"Targets must match source type '{source_type}'",
                        "targets": target_ids,
                    }
                ),
                400,
            )

        settings = persistence.retrieve_settings("025-libraries")
        libraries_data = settings.get("libraries", {}) if isinstance(settings, dict) else {}

        # If the client sent a fresh payload for the source card, merge it in before copying
        if isinstance(source_payload, dict) and source_payload:
            try:
                clean_payload = persistence.clean_form_data(MultiDict(source_payload))
                incoming_dict = helpers.build_config_dict("libraries", clean_payload).get("libraries", {})

                merged = libraries_data.copy()
                prefixes = set()
                for key in incoming_dict:
                    if key.startswith(("mov-library_", "sho-library_")):
                        parts = key.split("-", 2)
                        if len(parts) >= 2:
                            prefixes.add("-".join(parts[:2]))

                for prefix in prefixes:
                    for existing_key in list(merged.keys()):
                        if existing_key.startswith(prefix + "-") or existing_key == f"{prefix}-library":
                            merged.pop(existing_key, None)

                for k, v in incoming_dict.items():
                    if k.endswith("-library") and (v in [None, False, ""]):
                        continue
                    merged[k] = v

                libraries_data = merged
                helpers.ts_log(f"Copy request merged live source payload for {source_prefix}: {len(incoming_dict)} fields", level="DEBUG")
            except Exception as merge_err:
                helpers.ts_log(f"Failed to merge live source payload during copy: {merge_err}", level="ERROR")

        source_items = {k: v for k, v in libraries_data.items() if k.startswith(f"{source_prefix}-")}
        if not source_items:
            helpers.ts_log(f"Copy aborted: no saved settings found for source {source_prefix}", level="ERROR")
            return jsonify({"success": False, "error": "No saved settings found for source library"}), 404

        movie_libraries, show_libraries, _telemetry = _build_library_lists()
        name_map = {lib["id"]: lib["name"] for lib in (movie_libraries + show_libraries)}

        helpers.ts_log(
            f"Copy request for config={session.get('config_name')} source={source_prefix} targets={target_ids} "
            f"source_items={len(source_items)} existing_keys={len(libraries_data)}",
            level="DEBUG",
        )

        filtered_targets = [tid for tid in target_ids if str(tid).startswith(source_type)]
        if len(filtered_targets) != len(target_ids):
            helpers.ts_log(
                f"Copy filtering targets for type '{source_type}': accepted={filtered_targets} dropped={set(target_ids) - set(filtered_targets)}",
                level="WARNING",
            )
        if not filtered_targets:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"No valid target libraries of type '{source_type}' were selected.",
                    }
                ),
                400,
            )

        merged = libraries_data.copy()
        targets_to_process = [source_prefix] + [tid for tid in filtered_targets if tid != source_prefix]

        for target_id in targets_to_process:
            target_name = name_map.get(target_id, "")
            # Wipe any existing settings for this target before copying fresh
            for existing_key in list(merged.keys()):
                if existing_key.startswith(f"{target_id}-"):
                    merged.pop(existing_key, None)

            for key, value in source_items.items():
                # Do not mirror the include toggle; require explicit include after mirroring
                if target_id != source_prefix and key.endswith("-library"):
                    merged[f"{target_id}-library"] = ""
                    continue
                new_key = key.replace(source_prefix, target_id, 1)
                new_value = value
                if key.endswith("-library"):
                    new_value = target_name or value
                merged[new_key] = new_value

        # Update the aggregated libraries list to include all configured library names
        configured_names = []
        for key, val in merged.items():
            if key.endswith("-library") and val not in [None, "", False]:
                configured_names.append(str(val))
        merged["libraries"] = ",".join(sorted(set(configured_names)))

        # Persist directly to the DB to avoid any loss of data during merge
        config_name = session.get("config_name") or namesgenerator.get_random_name()
        database.save_section_data(
            name=config_name,
            section="libraries",
            validated=settings.get("validated", False),
            user_entered=True,
            data={"libraries": merged, "validated": settings.get("validated", False)},
        )

        helpers.ts_log(
            f"Copy complete for config={session.get('config_name')} source={source_prefix} targets={target_ids} " f"merged_keys={len(merged)}",
            level="DEBUG",
        )

        return jsonify({"success": True, "updated": target_ids})

    except Exception as e:
        helpers.ts_log(f"Failed to copy library settings: {e}", level="ERROR")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/download")
def download():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        return send_file(
            io.BytesIO(yaml_content.encode("utf-8")),
            mimetype="text/yaml",
            as_attachment=True,
            download_name="config.yml",
        )
    flash("No configuration to download", "danger")
    return redirect(request.referrer or url_for("step", page="900-final"))


@app.route("/download_redacted")
def download_redacted():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        # Redact sensitive information
        redacted_content = helpers.redact_sensitive_data(yaml_content)

        # Serve the redacted YAML as a file download
        return send_file(
            io.BytesIO(redacted_content.encode("utf-8")),
            mimetype="text/yaml",
            as_attachment=True,
            download_name="config_redacted.yml",
        )
    flash("No configuration to download", "danger")
    return redirect(request.referrer or url_for("step", page="900-final"))


@app.route("/validate_gotify", methods=["POST"])
def validate_gotify():
    data = request.json
    return validations.validate_gotify_server(data)


@app.route("/validate_ntfy", methods=["POST"])
def validate_ntfy():
    data = request.json
    return validations.validate_ntfy_server(data)


@app.route("/validate_plex", methods=["POST"])
def validate_plex():
    data = request.json
    return validations.validate_plex_server(data)


@app.route("/refresh_plex_libraries", methods=["POST"])
def refresh_plex_libraries():
    try:
        config_name = session.get("config_name")
        if not config_name:
            return jsonify({"valid": False, "error": "Missing config_name"}), 400

        # Get stored Plex credentials
        plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
        dummy = persistence.get_dummy_data("plex")
        default_plex_url = dummy.get("url", "")
        default_plex_token = dummy.get("token", "")

        # Validate credentials
        if not plex_url or not plex_token or plex_url == default_plex_url or plex_token == default_plex_token:
            return (
                jsonify(
                    {
                        "valid": False,
                        "error": "Plex credentials are using default placeholder values",
                    }
                ),
                400,
            )

        # Validate Plex server and get updated libraries
        plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
        plex_data = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response

        if not plex_data.get("validated"):
            return jsonify({"valid": False, "error": "Plex validation failed"}), 500

        # Update stored libraries
        persistence.update_stored_plex_libraries(
            "010-plex",
            plex_data.get("movie_libraries", []),
            plex_data.get("show_libraries", []),
            plex_data.get("music_libraries", []),
        )

        # Get fresh telemetry using helpers and store it
        telemetry = helpers.get_plex_metadata()
        persistence.save_settings("plex_telemetry", telemetry)

        # Merge both plex_data and telemetry for response
        merged_response = {**plex_data, **telemetry}

        return jsonify(merged_response)

    except Exception as e:
        return jsonify({"valid": False, "error": f"Server error: {str(e)}"}), 500


@app.route("/validate_tautulli", methods=["POST"])
def validate_tautulli():
    data = request.json
    return validations.validate_tautulli_server(data)


@app.route("/validate_trakt", methods=["POST"])
def validate_trakt():
    data = request.json
    return validations.validate_trakt_server(data)


@app.route("/validate_mal", methods=["POST"])
def validate_mal():
    data = request.json
    return validations.validate_mal_server(data)


@app.route("/validate_anidb", methods=["POST"])
def validate_anidb():
    data = request.json
    return validations.validate_anidb_server(data)


@app.route("/validate_webhook", methods=["POST"])
def validate_webhook():
    data = request.json
    return validations.validate_webhook_server(data)


@app.route("/validate_radarr", methods=["POST"])
def validate_radarr():
    data = request.json
    result = validations.validate_radarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_sonarr", methods=["POST"])
def validate_sonarr():
    data = request.json
    result = validations.validate_sonarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_omdb", methods=["POST"])
def validate_omdb():
    data = request.json
    result = validations.validate_omdb_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_github", methods=["POST"])
def validate_github():
    data = request.json
    result = validations.validate_github_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_tmdb", methods=["POST"])
def validate_tmdb():
    data = request.json
    result = validations.validate_tmdb_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_mdblist", methods=["POST"])
def validate_mdblist():
    data = request.json
    result = validations.validate_mdblist_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_notifiarr", methods=["POST"])
def validate_notifiarr():
    data = request.json
    result = validations.validate_notifiarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/shutdown", methods=["POST"])
def shutdown():
    if app.config.get("QUICKSTART_DOCKER"):
        return jsonify(success=False, message="Shutdown is disabled in Docker."), 403

    data = request.get_json(silent=True) or {}
    nonce = data.get("nonce")
    confirmed = data.get("confirmed") is True
    session_nonce = session.get("shutdown_nonce")

    if not confirmed or not nonce or nonce != session_nonce:
        return jsonify(success=False, message="Shutdown not authorized."), 403

    session.pop("shutdown_nonce", None)

    shutdown_func = request.environ.get("werkzeug.server.shutdown")

    def shutdown_later():
        # Allow the response to flush before stopping the process.
        time.sleep(0.5)

        if shutdown_func:
            try:
                shutdown_func()
            except Exception as e:
                helpers.ts_log(f"Werkzeug shutdown failed: {e}", level="DEBUG")

        shutdown_event.set()

        try:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QApplication

            qt_app = QApplication.instance()
            if qt_app:
                QTimer.singleShot(0, qt_app.quit)
        except Exception:
            pass

        # Fallback: ensure the process exits even if threads linger.
        time.sleep(2)
        os._exit(0)

    threading.Thread(target=shutdown_later, daemon=True).start()
    return jsonify(success=True, message="Shutting down..."), 200


@app.route("/start-kometa", methods=["POST"])
def start_kometa():
    data = request.get_json() or {}
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"error": "No command provided"}), 400

    if helpers.is_kometa_running():
        pid = helpers.get_kometa_pid()
        try:
            proc = psutil.Process(pid)
            started_at = datetime.fromtimestamp(proc.create_time()).isoformat()
            return jsonify({"error": f"Kometa is already running (PID: {pid}) since {started_at}.", "status": "running", "pid": pid, "started_at": started_at}), 400
        except Exception:
            return jsonify({"error": f"Kometa is already running (PID: {pid}).", "status": "running", "pid": pid}), 400

    kometa_root = helpers.get_kometa_root_path()  # ✅ unified source of truth
    is_win = sys.platform.startswith("win")
    venv_python = kometa_root / "kometa-venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python3")
    kometa_py = kometa_root / "kometa.py"

    if not kometa_py.exists():
        return jsonify({"error": f"kometa.py not found at: {kometa_py}"}), 404
    if not venv_python.exists():
        return jsonify({"error": f"Kometa venv python not found at: {venv_python}"}), 500

    try:
        # Use posix=False so Windows backslashes/quotes are preserved
        command_parts = shlex.split(command, posix=not is_win)

        # Clean up double-wrapped args (affects --run-libraries, --times, etc.)
        helpers.normalize_cli_args_inplace(command_parts)

        # If the UI-built command already starts with python, replace it with our venv python
        if command_parts and os.path.basename(command_parts[0]).lower() in {"python", "python3", "python.exe"}:
            command_parts[0] = str(venv_python)
        else:
            command_parts.insert(0, str(venv_python))

        # Make sure kometa.py is the script, even if the UI command omitted it
        if not any(p.endswith("kometa.py") for p in command_parts):
            command_parts.insert(1, str(kometa_py))

        helpers.normalize_flag_values(command_parts)

        helpers.ts_log(f"argv={command_parts!r}", level="DEBUG")

        proc = subprocess.Popen(command_parts, cwd=str(kometa_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

        with open(helpers.get_kometa_pid_file(), "w", encoding="utf-8") as f:
            f.write(str(proc.pid))

        return jsonify({"status": "Kometa started", "pid": proc.pid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/stop-kometa", methods=["POST"])
def stop_kometa():
    pid = helpers.get_kometa_pid()
    pid_file = helpers.get_kometa_pid_file()

    if not pid:
        return jsonify({"warning": "No active Kometa PID"}), 200

    try:
        proc = psutil.Process(pid)

        # Ensure this really looks like a Kometa run before killing
        cmdline = " ".join(proc.cmdline() or [])
        if "kometa.py" not in cmdline:
            try:
                os.remove(pid_file)
            except Exception:
                pass
            return jsonify({"warning": f"PID {pid} is not a Kometa process. Cleaned PID file."}), 200

        # First try graceful termination
        try:
            proc.terminate()  # POSIX: SIGTERM, Windows: TerminateProcess
        except psutil.NoSuchProcess:
            pass

        gone, alive = psutil.wait_procs([proc], timeout=3)
        if alive:
            # Kill children then parent as a fallback
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Cleanup PID file regardless
        try:
            os.remove(pid_file)
        except Exception:
            pass

        return jsonify({"success": True, "message": "Kometa stopped (or was not running)."}), 200

    except psutil.NoSuchProcess:
        # Process already gone; just clean up PID file
        try:
            os.remove(pid_file)
        except Exception:
            pass
        return jsonify({"warning": "Process not found. Cleaned up PID file."}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to stop Kometa: {str(e)}"}), 500


@app.route("/kometa-status", methods=["GET"])
def kometa_status():
    pid = helpers.get_kometa_pid()
    if not pid:
        return jsonify(status="not started")

    try:
        proc = psutil.Process(pid)
        # psutil can raise if finished between checks
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            # Extra guard: ensure it's actually kometa.py
            cmdline = " ".join(proc.cmdline() or [])
            if "kometa.py" in cmdline:
                return jsonify(status="running", pid=pid)
        # If we’re here, it likely ended; try to get a return code
        try:
            rc = proc.wait(timeout=0.1)
        except psutil.TimeoutExpired:
            rc = None
        finally:
            # Clean PID if no longer an active kometa proc
            try:
                os.remove(helpers.get_kometa_pid_file())
            except Exception:
                pass
        return jsonify(status="done", return_code=rc if rc is not None else -1)
    except psutil.NoSuchProcess:
        try:
            os.remove(helpers.get_kometa_pid_file())
        except Exception:
            pass
        return jsonify(status="not started")


@app.route("/tail-log")
def tail_log():
    kometa_root = helpers.get_kometa_root_path()
    log_path = kometa_root / "config" / "logs" / "meta.log"

    if not log_path.exists():
        return jsonify({"error": f"Log file not found at: {log_path}"}), 404

    try:
        from collections import deque

        size_param = request.args.get("size", "2000")
        download = request.args.get("download")
        max_lines = None
        if size_param.lower() not in ("all", "full"):
            try:
                max_lines = max(1, min(int(size_param), 20000))
            except Exception:
                max_lines = 2000

        if max_lines:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = deque(f, maxlen=max_lines)
            log_content = "".join(lines)
        else:
            log_content = log_path.read_text(encoding="utf-8", errors="replace")

        if download:
            return send_file(
                io.BytesIO(log_content.encode("utf-8")),
                mimetype="text/plain",
                as_attachment=True,
                download_name="meta.log",
            )

        return jsonify({"log": log_content})
    except Exception as e:
        return jsonify({"error": f"Failed to read log: {str(e)}"}), 500


@app.route("/support-info")
def support_info():
    def format_mb(value):
        return int(value / (1024 * 1024))

    def normalize_config_name(name):
        cleaned = (name or "").strip().lower().replace(" ", "_")
        return cleaned or "default"

    config_name = session.get("config_name") or "default"
    normalized_name = normalize_config_name(config_name)
    config_path = Path(helpers.CONFIG_DIR) / f"{normalized_name}_config.yml"

    if config_path.exists():
        created_ts = datetime.fromtimestamp(config_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created_line = f"# {config_name} config created by Quickstart on {created_ts}"
    else:
        created_line = f"# {config_name} config created by Quickstart on Unavailable"

    version_info = app.config.get("VERSION_CHECK") or helpers.check_for_update()
    quickstart_version = version_info.get("local_version", "unknown")
    quickstart_branch = version_info.get("branch", "unknown")
    quickstart_environment = version_info.get("running_on", "unknown")

    system_name = platform.system() or "Unknown OS"
    system_release = platform.release() or ""
    cpu_name = platform.processor() or platform.uname().processor or "Unknown CPU"
    cpu_cores = psutil.cpu_count(logical=True) or 0
    vm = psutil.virtual_memory()
    mem_total = format_mb(vm.total)
    mem_available = format_mb(vm.available)
    mem_used = format_mb(vm.total - vm.available)
    mem_percent = int(vm.percent)
    is_docker = bool(app.config.get("QUICKSTART_DOCKER")) or "Docker" in str(quickstart_environment)

    plex_summary = helpers.get_plex_summary()
    if not plex_summary or plex_summary.lower().startswith("plex summary unavailable"):
        plex_summary = "Plex info unavailable."

    library_settings = persistence.retrieve_settings("025-libraries").get("libraries", {})
    movie_libraries = []
    show_libraries = []
    for key, value in library_settings.items():
        if not key.endswith("-library") or value in [None, "", False]:
            continue
        if key.startswith("mov-library_"):
            movie_libraries.append(str(value))
        elif key.startswith("sho-library_"):
            show_libraries.append(str(value))

    library_names = movie_libraries + show_libraries
    if library_names:
        library_details = helpers.get_library_summaries(library_names)
        if library_details.lower().startswith("plex library summary unavailable"):
            library_details = "Library details unavailable."
    else:
        library_details = "No libraries configured."

    lines = []
    lines.append(f"#==================== {config_name} ====================#")
    lines.append(created_line)
    lines.append("# System Information")
    lines.append(f"# OS: {system_name} {system_release}".strip())
    lines.append(f"# Docker: {is_docker}")
    lines.append(f"# CPU: {cpu_name} ({cpu_cores} cores)")
    lines.append(f"# Memory: {mem_used} MB / {mem_total} MB ({mem_percent}%) | {mem_available} MB Free")
    lines.extend([f"# {line}" for line in plex_summary.splitlines()])
    lines.append(f"# Quickstart: {quickstart_version} | Branch: {quickstart_branch} | Environment: {quickstart_environment}")
    lines.append("###")
    lines.append(f"# Libraries configured with Quickstart: {len(movie_libraries)} movie, {len(show_libraries)} show")
    if library_details:
        for line in library_details.splitlines():
            if line.strip():
                lines.append(f"# {line}")
            else:
                lines.append("#")
    lines.append("###")
    lines.append("# Quickstart log tail (last 200 lines)")
    lines.append("")

    log_path = Path(helpers.LOG_FILE).resolve()
    log_lines = []

    if log_path.exists():
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                tail = deque(f, maxlen=200)
            for line in tail:
                log_lines.append(helpers.redact_string(line.rstrip("\n")))
            if not log_lines:
                log_lines.append("Quickstart log is empty.")
        except Exception:
            log_lines.append("Quickstart log unavailable.")
    else:
        log_lines.append("Quickstart log unavailable.")

    text = "\n".join(lines + log_lines)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"text": text, "generated_at": generated_at})


@app.route("/validate-kometa-root", methods=["POST"])
def validate_kometa_root():
    root_path = request.json.get("path", "").strip()
    logs = []

    def log(msg):
        print(msg, file=sys.stderr)
        logs.append(msg)

    if not root_path:
        log("❌ No path provided.")
        return jsonify(success=False, error="No path provided.", log=logs), 400

    p = Path(root_path).resolve()

    session["kometa_root"] = p.as_posix()
    app.config["KOMETA_ROOT"] = str(p)

    # Auto-create the Kometa root and config/ if missing
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
            log(f"📁 Created Kometa root: {p}")
        except Exception as e:
            log(f"❌ Failed to create Kometa root: {e}")
            return jsonify(success=False, error="Failed to create Kometa root.", log=logs), 500

    try:
        (p / "config").mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"❌ Failed to create config folder: {e}")
        return jsonify(success=False, error="Failed to create config folder.", log=logs), 500

    # Keep POSIX (internal) and native (display) versions
    kometa_root_posix = p.as_posix()
    kometa_root_display = str(p)  # native (Windows => backslashes)
    session["kometa_root"] = kometa_root_posix  # store normalized internally

    log(f"🔍 Checking path: {kometa_root_display}")

    # --- External tool check (python is required) ---
    missing_tools = []
    if shutil.which("python") is None and shutil.which("python3") is None:
        missing_tools.append("python or python3")

    if missing_tools:
        for tool in missing_tools:
            log(f"❌ Required tool not found: {tool}")
        return jsonify(success=False, error=f"Missing required tools: {', '.join(missing_tools)}", log=logs), 400

    log("✅ All required external tools are available.")

    # Python version (best-effort)
    try:
        python_cmd = shutil.which("python") or shutil.which("python3")
        version_output = subprocess.check_output([python_cmd, "--version"], stderr=subprocess.STDOUT, text=True)
        log(f"🐍 Detected Python version: {version_output.strip()}")
    except Exception as e:
        log(f"⚠️ Failed to detect Python version: {e}")

    # Git version (optional/best-effort)
    try:
        git_output = subprocess.check_output(["git", "--version"], stderr=subprocess.STDOUT, text=True)
        log(f"🔧 Detected Git version: {git_output.strip()}")
    except Exception as e:
        log(f"⚠️ Failed to detect Git version: {e}")

    # --- Kometa files check (if you're expecting them to already be present) ---
    kometa_version = "Unknown"
    version_path = p / "VERSION"
    if version_path.exists():
        try:
            kometa_version = version_path.read_text(encoding="utf-8").strip()
            log(f"📦 Kometa version detected: {kometa_version}")
        except Exception as e:
            log(f"⚠️ Failed to read VERSION file: {e}")

    required_files = ["kometa.py", "requirements.txt"]
    for fname in required_files:
        fpath = p / fname
        if not fpath.exists():
            log(f"❌ Required file missing: {fname}")
            return jsonify(success=False, error=f"{fname} not found.", log=logs), 400
        log(f"✔️ Found required file: {fname}")

    # --- Virtualenv & deps under <root>/kometa-venv ---
    is_windows = sys.platform.startswith("win")
    venv_dir = p / "kometa-venv"
    bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
    python_bin = bin_dir / ("python.exe" if is_windows else "python")
    pip_bin = bin_dir / ("pip.exe" if is_windows else "pip")

    if not venv_dir.exists():
        log("📦 Creating virtual environment...")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
            log("✅ Virtual environment created.")
        except subprocess.CalledProcessError as e:
            log(f"❌ Failed to create venv: {str(e)}")
            return jsonify(success=False, error="Failed to create venv.", log=logs), 500
    else:
        log("ℹ️ Virtual environment already exists.")

    if not pip_bin.exists():
        log(f"❌ pip not found in venv at {pip_bin}")
        return jsonify(success=False, error=f"pip not found in {pip_bin}", log=logs), 500

    log("⬆️ Checking pip version and attempting upgrade...")
    try:
        result = subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
        output = result.stdout.strip()
        log("ℹ️ pip is already up to date." if "Requirement already satisfied" in output else "✅ pip upgraded.")
        for line in output.splitlines():
            log(f"    {line}")
    except subprocess.CalledProcessError as e:
        log(f"❌ pip upgrade failed: {e}")
        return jsonify(success=False, error="pip upgrade failed.", log=logs), 500

    log("📦 Installing requirements.txt...")
    try:
        result = subprocess.run(
            [str(python_bin), "-m", "pip", "install", "-r", str(p / "requirements.txt")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True
        )
        output = result.stdout.strip()
        log(
            "ℹ️ All requirements are already satisfied."
            if "Requirement already satisfied" in output and "Successfully installed" not in output
            else "✅ requirements.txt installed or updated."
        )
        for line in output.splitlines():
            log(f"    {line}")
    except subprocess.CalledProcessError as e:
        log(f"❌ Error installing requirements: {str(e)}")
        return jsonify(success=False, error="Failed pip install.", log=logs), 500

    # Copy generated YAML into <root>/config/<file>
    config_name = request.json.get("config_name", "kometa")
    src_yaml = Path("config") / f"{config_name}"
    if not src_yaml.exists():
        log(f"❌ Source YAML does not exist: {src_yaml}")
        return jsonify(success=False, error="Generated YAML not found.", log=logs), 500

    dest_yaml = p / "config" / f"{config_name}"
    try:
        shutil.copy2(src_yaml, dest_yaml)
        log(f"✅ YAML copied to Kometa config folder at: {dest_yaml}")
    except Exception as e:
        log(f"⚠️ Failed to copy YAML: {e}")

    log("✅ Kometa root is valid and ready.")

    kometa_update_info = helpers.check_kometa_update(p)
    if kometa_update_info["update_available"]:
        log(f"⬆️ Update available: {kometa_update_info['local_version']} → {kometa_update_info['remote_version']}")
    else:
        log(f"✅ Kometa is up to date: {kometa_update_info['local_version']}")

    return (
        jsonify(
            success=True,
            # internal normalized for any future backend use
            kometa_root=kometa_root_posix,
            venv_python=python_bin.as_posix(),
            # native-display for UI/command builder
            kometa_root_display=kometa_root_display,
            venv_python_display=str(python_bin),
            kometa_version=kometa_version,
            local_version=kometa_update_info["local_version"],
            remote_version=kometa_update_info["remote_version"],
            kometa_update_available=kometa_update_info["update_available"],
            log=logs,
        ),
        200,
    )


@app.route("/update-kometa", methods=["POST"])
def update_kometa():
    # hard-stop if Kometa is currently running
    if helpers.is_kometa_running():
        pid = helpers.get_kometa_pid()
        return jsonify({"success": False, "error": f"Kometa is currently running (PID {pid}). Stop it before updating."}), 409
    logs = []
    try:
        cfg_dir = helpers.CONFIG_DIR

        # (optional) allow the caller to pass qs branch; otherwise detect from repo
        data = request.get_json(silent=True) or {}
        qs_branch = data.get("branch") or helpers.detect_git_branch(app.root_path)
        kometa_branch = "master" if qs_branch == "master" else "nightly"

        logs.append(f"🔎 Quickstart branch: {qs_branch}")
        logs.append(f"⚙️ Kometa branch selected: {kometa_branch} (ZIP mode)")

        result = helpers.perform_kometa_update_zip_only(cfg_dir, branch=kometa_branch)
        logs.extend(result.get("log", []))
        status = 200 if result.get("success") else 500

        return jsonify({"success": result.get("success", False), "log": logs, "qs_branch": qs_branch, "kometa_branch": kometa_branch}), status

    except Exception as e:
        logs.append(f"Exception during Kometa update: {e}")
        return jsonify({"success": False, "log": logs}), 500


@app.route("/check-test-libraries", methods=["POST"])
def check_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    # legacy flag ignored; we always use the config dir now
    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    # Always use config/<plex_test_libraries>
    base_config_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else quickstart_root
    target_path = os.path.join(base_config_dir, "config", "plex_test_libraries")
    resolved_path = os.path.abspath(target_path)

    found = os.path.isdir(target_path)
    has_expected = all(os.path.isdir(os.path.join(target_path, name)) for name in ["test_tv_lib", "test_movie_lib"])

    local_sha = ""
    remote_sha = ""
    is_outdated = False

    if found and has_expected:
        sha_path = os.path.join(target_path, ".test_libraries_version")
        if os.path.exists(sha_path):
            try:
                with open(sha_path, "r") as f:
                    local_sha = f.read().strip()
            except Exception:
                local_sha = ""
            try:
                commit_info = requests.get(
                    "https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main",
                    timeout=5,
                ).json()
                remote_sha = commit_info.get("sha", "")[:7]
            except Exception:
                remote_sha = ""
            if local_sha and remote_sha and local_sha != remote_sha:
                is_outdated = True

    return jsonify(
        {
            "found": bool(found and has_expected),
            "target_path": resolved_path,
            "is_outdated": is_outdated,
            "local_sha": local_sha,
            "remote_sha": remote_sha,
        }
    )


@app.route("/clone-test-libraries-start", methods=["POST"])
def clone_test_libraries_start():
    """
    Starts a background job to download and install plex_test_libraries,
    reporting rich progress via CLONE_PROGRESS[job_id].

    Progress payload shapes by phase:
      download: {"phase":"download","pct":<int|None>,"text":str,"downloaded":int,"total":int}
      extract : {"phase":"extract","pct":int,"text":str,"files_done":int,"files_total":int}
      finalize: {"phase":"finalize","pct":int,"text":str}
      done    : {"phase":"done","pct":100,"text":str,"target_path":str}
      error   : {"phase":"error","pct":0,"text":str}
    """
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    use_config_dir = True  # always managed

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    # Resolve target path (managed/config dir)
    base_config_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else quickstart_root
    target_path = os.path.join(base_config_dir, "config", "plex_test_libraries")
    resolved_path = os.path.abspath(target_path)

    # Ensure CLONE_PROGRESS dict exists
    try:
        _ = CLONE_PROGRESS
    except NameError:
        # Create if missing (keeps function drop-in friendly)
        globals()["CLONE_PROGRESS"] = {}
    job_id = str(uuid.uuid4())
    CLONE_PROGRESS[job_id] = {"phase": "queued", "pct": 0, "text": "Queued..."}

    def worker():
        zip_url = "https://github.com/chazlarson/plex-test-libraries/archive/refs/heads/main.zip"
        commit_sha = ""

        try:
            # Best-effort SHA for UI banner
            try:
                commit_info = requests.get(
                    "https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main",
                    timeout=5,
                ).json()
                commit_sha = commit_info.get("sha", "")[:7]
            except Exception:
                commit_sha = ""

            # Try to get total size first (lets UI show determination early)
            total_size = 0
            try:
                head = requests.head(zip_url, allow_redirects=True, timeout=10)
                total_size = int(head.headers.get("Content-Length", "0") or 0)
            except Exception:
                total_size = 0

            CLONE_PROGRESS[job_id] = {
                "phase": "download",
                "pct": None,  # None => indeterminate until we know size
                "text": "Downloading zip…",
                "downloaded": 0,
                "total": total_size,
            }

            # Use a stable tmp folder under the config dir to avoid /tmp RAM mounts
            tmp_root = os.path.join(base_config_dir, "config", "tmp")
            # Proactively clean stale tmp folders from previous runs
            if os.path.isdir(tmp_root):
                for entry in os.listdir(tmp_root):
                    try:
                        shutil.rmtree(os.path.join(tmp_root, entry), ignore_errors=True)
                    except Exception:
                        pass
            os.makedirs(tmp_root, exist_ok=True)

            with tempfile.TemporaryDirectory(dir=tmp_root) as tmpdir:
                zip_path = os.path.join(tmpdir, "main.zip")

                # Stream download with throttled progress updates
                downloaded = 0
                last_push = 0.0
                with requests.get(zip_url, stream=True, timeout=30) as r:
                    r.raise_for_status()

                    # If HEAD failed, try to get size from GET
                    if not total_size:
                        try:
                            total_size = int(r.headers.get("Content-Length", "0") or 0)
                            CLONE_PROGRESS[job_id]["total"] = total_size
                        except Exception:
                            total_size = 0

                    chunk = 1024 * 1024  # 1 MiB
                    with open(zip_path, "wb") as f:
                        for part in r.iter_content(chunk_size=chunk):
                            if not part:
                                continue
                            f.write(part)
                            downloaded += len(part)

                            now = time.time()
                            if (now - last_push) > 0.5 or (total_size and downloaded >= total_size):
                                pct = None
                                if total_size:
                                    pct = int(downloaded * 100 / total_size)
                                CLONE_PROGRESS[job_id] = {
                                    "phase": "download",
                                    "pct": pct,
                                    "text": "Downloading zip…",
                                    "downloaded": downloaded,
                                    "total": total_size,
                                }
                                last_push = now

                # Extract with per-file progress
                CLONE_PROGRESS[job_id] = {"phase": "extract", "pct": 0, "text": "Extracting…", "files_done": 0, "files_total": 0}
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    members = zip_ref.infolist()
                    total_files = len(members) or 1
                    files_done = 0
                    last_push = 0.0

                    for info in members:
                        zip_ref.extract(info, tmpdir)
                        files_done += 1

                        now = time.time()
                        if (now - last_push) > 0.2 or files_done == total_files:
                            pct = int(files_done * 100 / total_files)
                            CLONE_PROGRESS[job_id] = {
                                "phase": "extract",
                                "pct": pct,
                                "text": f"Extracting… {files_done}/{total_files} files",
                                "files_done": files_done,
                                "files_total": total_files,
                            }
                            last_push = now

                extracted_dir = os.path.join(tmpdir, "plex-test-libraries-main")

                # Finalize (replace folder)
                CLONE_PROGRESS[job_id] = {"phase": "finalize", "pct": 95, "text": "Finalizing…"}
                if os.path.exists(target_path):
                    shutil.rmtree(target_path, onerror=helpers.handle_remove_readonly)
                shutil.move(extracted_dir, target_path)

                # Write version marker (best effort)
                if commit_sha:
                    try:
                        with open(os.path.join(target_path, ".test_libraries_version"), "w") as f:
                            f.write(commit_sha)
                    except Exception as e:
                        helpers.ts_log(f"Warning: Failed to write SHA version file: {e}", level="WARNING")

                # Permissions for non-Windows
                if platform.system() in ["Linux", "Darwin"]:
                    subprocess.run(["chmod", "-R", "777", target_path], check=False)

                CLONE_PROGRESS[job_id] = {
                    "phase": "done",
                    "pct": 100,
                    "text": "Installed/updated successfully.",
                    "target_path": resolved_path,
                }

        except Exception as e:
            CLONE_PROGRESS[job_id] = {
                "phase": "error",
                "pct": 0,
                "text": f"Error: {str(e)}",
            }

    threading.Thread(target=worker, daemon=True).start()
    return jsonify(success=True, job_id=job_id)


@app.route("/clone-test-libraries-progress", methods=["GET"])
def clone_test_libraries_progress():
    job_id = request.args.get("job_id", "")
    info = CLONE_PROGRESS.get(job_id)
    if not info:
        return jsonify(success=False, message="Unknown job_id"), 404

    # avoid duplicate kwarg: remove job's 'success' if present
    info_no_flag = dict(info)
    info_no_flag.pop("success", None)

    return jsonify(success=True, **info_no_flag)


@app.route("/clone-test-libraries", methods=["POST"])
def clone_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    use_config_dir = data.get("use_config_dir", False)

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    if use_config_dir:
        base_config_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else quickstart_root
        target_path = os.path.join(base_config_dir, "config", "plex_test_libraries")
    else:
        parent_dir = os.path.dirname(quickstart_root)
        target_path = os.path.join(parent_dir, "plex_test_libraries")

    resolved_path = os.path.abspath(target_path)

    try:
        # If already exists
        if os.path.exists(target_path):
            if use_config_dir:
                return jsonify(success=True, message="Test libraries already present (ZIP install).", target_path=resolved_path)

        # ZIP fallback if git not found or Download failed
        zip_url = "https://github.com/chazlarson/plex-test-libraries/archive/refs/heads/main.zip"
        commit_sha = None
        try:
            commit_info = requests.get("https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main", timeout=5).json()
            commit_sha = commit_info.get("sha", "")[:7]
        except Exception:
            commit_sha = None

        tmp_root = os.path.join(base_config_dir if use_config_dir else parent_dir, "config", "tmp") if use_config_dir else os.path.join(parent_dir, "tmp")
        # Clean stale tmp folders if they exist
        if os.path.isdir(tmp_root):
            for entry in os.listdir(tmp_root):
                try:
                    shutil.rmtree(os.path.join(tmp_root, entry), ignore_errors=True)
                except Exception:
                    pass
        os.makedirs(tmp_root, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=tmp_root) as tmpdir:
            zip_path = os.path.join(tmpdir, "main.zip")

            r = requests.get(zip_url)
            if r.status_code != 200:
                return jsonify(success=False, message="Failed to download ZIP fallback from GitHub.")
            with open(zip_path, "wb") as f:
                f.write(r.content)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            extracted_dir = os.path.join(tmpdir, "plex-test-libraries-main")
            if os.path.exists(target_path):
                shutil.rmtree(target_path, onerror=helpers.handle_remove_readonly)
            shutil.move(extracted_dir, target_path)

            if commit_sha:
                try:
                    with open(os.path.join(target_path, ".test_libraries_version"), "w") as f:
                        f.write(commit_sha)
                except Exception as e:
                    helpers.ts_log(f"Warning: Failed to write SHA version file: {e}", level="WARNING")

        if use_config_dir and platform.system() in ["Linux", "Darwin"]:
            subprocess.run(["chmod", "-R", "777", target_path], check=False)

        return jsonify(success=True, message="Test libraries installed successfully.", target_path=resolved_path)

    except Exception as e:
        return jsonify(success=False, message=f"Unexpected error: {str(e)}")


@app.route("/purge-test-libraries", methods=["POST"])
def purge_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    use_config_dir = data.get("use_config_dir", False)

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    if use_config_dir:
        base_config_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else quickstart_root
        target_path = os.path.join(base_config_dir, "config", "plex_test_libraries")
    else:
        parent_dir = os.path.dirname(quickstart_root)
        target_path = os.path.join(parent_dir, "plex_test_libraries")

    resolved_path = os.path.abspath(target_path)

    try:
        if not os.path.exists(resolved_path):
            return jsonify(success=False, message="Test libraries folder does not exist.")

        shutil.rmtree(resolved_path, onerror=helpers.handle_remove_readonly)
        return jsonify(success=True, message=f"Test libraries deleted at: {resolved_path}")

    except Exception as e:
        return jsonify(success=False, message=f"Failed to delete folder:\n{str(e)}")


@app.route("/restart", methods=["POST"])
def restart_quickstart():
    def restart():
        # Give time for the response to complete before restarting
        time.sleep(1)
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    threading.Thread(target=restart).start()
    return jsonify(success=True, message="Quickstart is restarting...")


server_thread = None
update_thread = None
if __name__ == "__main__":

    def start_flask_app():
        serve(app, host="0.0.0.0", port=port, max_request_body_size=16 * 1024 * 1024)

    def start_update_thread(app_in):
        with app_in.app_context():
            while True:
                app_in.config["VERSION_CHECK"] = helpers.check_for_update()
                helpers.ts_log(f"Checked for updates.", level="INFO")
                time.sleep(86400)

    update_thread = threading.Thread(target=start_update_thread, args=(app,), daemon=True)
    update_thread.start()

    def get_lan_ip():
        try:
            # Connect to a dummy address to get the local IP used
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    try:
        from PyQt5.QtGui import QIcon
        from PyQt5.QtWidgets import (
            QApplication,
            QSystemTrayIcon,
            QMenu,
            QAction,
            QInputDialog,
            QMessageBox,
            QWidget,
        )
        from PyQt5.QtCore import Qt, QTimer

        if app.config["QUICKSTART_DOCKER"]:
            has_tray = False
        elif sys.platform.startswith("linux"):
            has_tray = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        elif sys.platform == "darwin" or sys.platform.startswith("win"):
            has_tray = True
        else:
            has_tray = False
    except (ModuleNotFoundError, ImportError) as ie:
        has_tray = False

    if not has_tray:
        # Headless mode: skip system tray
        helpers.ts_log(f"Running in headless mode — no system tray will be shown...", level="INFO")
        if app.config["QUICKSTART_DOCKER"]:
            helpers.ts_log(f"Quickstart is Running inside Docker.", level="INFO")
            helpers.ts_log(f"Access it at http://<your-server-ip>:{running_port}", level="INFO")
            helpers.ts_log(f"Note: This IP is the HOST machine IP, not the container IP.", level="INFO")
        else:
            ip_address = get_lan_ip()
            helpers.ts_log(f"Quickstart is Running", level="INFO")
            helpers.ts_log(f"Access it at http://{ip_address}:{running_port}", level="INFO")

        helpers.ts_log(f"Port and Debug Settings can be amended by editing your {DOTENV} file", level="INFO")
        server_thread = Thread(target=start_flask_app)
        server_thread.daemon = True
        server_thread.start()

        try:
            while not shutdown_event.is_set():
                time.sleep(1)  # Keep main thread alive
        except KeyboardInterrupt:
            helpers.ts_log("\nShutting down Quickstart...", level="INFO")
            sys.exit(0)

        helpers.ts_log("Shutting down Quickstart...", level="INFO")
        sys.exit(0)

    else:
        # GUI mode: show tray

        server_thread = Thread(target=start_flask_app)
        server_thread.daemon = True
        server_thread.start()

        class QuickstartTrayApp:
            def __init__(self):
                self.app = QApplication(sys.argv)
                self.app.setQuitOnLastWindowClosed(False)
                self.app.setApplicationName("Quickstart")

                self.dialog_parent = QWidget()
                self.dialog_parent.setWindowTitle("Quickstart")
                self.dialog_parent.setAttribute(Qt.WA_DontShowOnScreen, True)

                self.tray = QSystemTrayIcon()
                self.icon_path = os.path.join(helpers.MEIPASS_DIR, "static", "favicon.png")

                self.tray.setIcon(QIcon(self.icon_path))
                self.tray.setToolTip(f"Quickstart (Port: {running_port})")

                self.menu = QMenu()

                self.open_action = QAction(f"Open Quickstart (Port: {running_port})")
                self.open_action.triggered.connect(self.open_quickstart)

                self.github_action = QAction("Quickstart GitHub")
                self.github_action.triggered.connect(lambda: webbrowser.open("https://github.com/Kometa-Team/Quickstart"))

                self.toggle_debug_action = QAction(f"{'Disable' if debug_mode else 'Enable'} Debug")
                self.toggle_debug_action.triggered.connect(self.toggle_debug)

                self.change_port_action = QAction("Change Port")
                self.change_port_action.triggered.connect(self.change_port)

                self.quit_action = QAction("Exit")
                self.quit_action.triggered.connect(self.quit_app)

                self.menu.addAction(self.open_action)
                self.menu.addAction(self.github_action)
                self.menu.addSeparator()
                self.menu.addAction(self.toggle_debug_action)
                self.menu.addAction(self.change_port_action)
                self.menu.addSeparator()
                self.menu.addAction(self.quit_action)

                self.tray.setContextMenu(self.menu)
                self.tray.show()

                ip_address = get_lan_ip()

                self.tray.showMessage(
                    "Quickstart is Running",
                    f"Local: http://localhost:{running_port}\nLAN: http://{ip_address}:{running_port}",
                    QSystemTrayIcon.NoIcon,
                    8000,
                )

                helpers.ts_log(f"Quickstart is Running", level="INFO")
                helpers.ts_log(f"Access it locally at: http://localhost:{running_port}", level="INFO")
                helpers.ts_log(f"Access it from other devices at: http://{ip_address}:{running_port}", level="INFO")
                helpers.ts_log(f"Shutdown locally at: http://localhost:{running_port}/shutdown", level="INFO")
                helpers.ts_log(f"Shutdown from other devices at: http://{ip_address}:{running_port}/shutdown", level="INFO")
                helpers.ts_log(
                    f"Port and Debug Settings can be amended by right-clicking the system tray icon or by editing your {DOTENV} file", level="INFO"
                )  # Open the browser automatically
                webbrowser.open(f"http://localhost:{running_port}")

                # Keep the invisible parent alive
                self.dialog_parent.showMinimized()
                self.dialog_parent.hide()

                # Ensure Qt stays alive (important in tray-only apps)
                QTimer.singleShot(0, lambda: None)  # No-op to lock event loop

            def exec(self):
                """Run the Qt app loop."""
                self.app.exec()

            def open_quickstart(self):
                webbrowser.open(f"http://localhost:{running_port}")

            def toggle_debug(self):
                global debug_mode
                debug_mode = not debug_mode
                helpers.update_env_variable("QS_DEBUG", "1" if debug_mode else "0")
                app.config["QS_DEBUG"] = debug_mode
                self.toggle_debug_action.setText(f"{'Disable' if debug_mode else 'Enable'} Debug")

            def show_messagebox(self, box_type, title, text):
                box = QMessageBox(self.dialog_parent)
                box.setWindowTitle(title)
                box.setText(text)
                box.setIcon(box_type)
                box.setStandardButtons(QMessageBox.Ok)
                box.setWindowFlags(box.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                box.setWindowIcon(QIcon(self.icon_path))
                box.exec()

            def change_port(self):
                global port
                try:
                    helpers.ts_log(f"Launching custom port input dialog...", level="DEBUG")

                    dialog = QInputDialog(self.dialog_parent)
                    dialog.setWindowTitle("Change Port")
                    dialog.setLabelText("Enter a new port number:")
                    dialog.setInputMode(QInputDialog.IntInput)
                    dialog.setIntMinimum(1)
                    dialog.setIntMaximum(65535)
                    dialog.setIntValue(port)

                    # Remove help button and set custom icon
                    dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
                    dialog.setWindowIcon(QIcon(self.icon_path))

                    # Execute dialog
                    if dialog.exec() != QInputDialog.Accepted:
                        helpers.ts_log(f"Port change canceled by user.", level="INFO")
                        return

                    new_port = dialog.intValue()
                    helpers.ts_log(f"User entered new port: {new_port}", level="INFO")

                    if new_port == port:
                        self.show_messagebox(
                            QMessageBox.Information,
                            "Port Already Selected",
                            f"Port {new_port} is already selected.",
                        )
                    else:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                            if sock.connect_ex(("localhost", new_port)) == 0:
                                self.show_messagebox(
                                    QMessageBox.Warning,
                                    "Port Conflict",
                                    f"Port {new_port} is already in use.\nClose any conflicting applications or choose another port.",
                                )
                            else:
                                helpers.update_env_variable("QS_PORT", new_port)
                                self.show_messagebox(
                                    QMessageBox.Information,
                                    "Port Updated",
                                    f"Port number updated to {new_port}.\nQuickstart will now restart automatically.",
                                )
                                self.restart_quickstart()

                except Exception as e:
                    helpers.ts_log(f"Port change error: {e}", level="ERROR")

            def quit_app(self):
                global server_thread, update_thread

                helpers.ts_log(f"Shutting down Quickstart...", level="INFO")

                # Stop tray icon
                self.tray.hide()

                # Optionally stop Flask server (if you have added a stop hook)
                # For now, just wait for background threads to finish
                if server_thread and server_thread.is_alive():
                    helpers.ts_log(f"Waiting for server thread to exit...", level="DEBUG")
                    server_thread.join(timeout=2)

                if update_thread and update_thread.is_alive():
                    helpers.ts_log(f"Waiting for update thread to exit...", level="DEBUG")
                    update_thread.join(timeout=2)

                # Exit the Qt app loop
                self.app.quit()

            def restart_quickstart(self):
                """Cleanly restart the Quickstart application."""
                helpers.ts_log(f"Restarting Quickstart...", level="INFO")
                self.tray.hide()

                python = sys.executable
                os.execl(python, python, *sys.argv)

        QuickstartTrayApp().exec()
