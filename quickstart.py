import argparse
import io
import json
import os
import hashlib
import platform
import psutil
import re
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
from datetime import datetime, timezone, timedelta
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
    abort,
)
from waitress import serve
from ruamel.yaml import YAML
from werkzeug.datastructures import MultiDict
from werkzeug.utils import secure_filename

from werkzeug.wrappers import Request

Request.max_form_parts = 100000  # Allow more form fields if needed

from flask_session import Session
from modules import validations, output, persistence, helpers, database, logscan, importer, path_validation, url_validation
from typing import Dict, Any

# A very simple in-memory progress store
CLONE_PROGRESS: Dict[str, Dict[str, Any]] = {}
ACTIVE_TEST_LIB_JOB: Dict[str, Any] = {}
LOG_STATS_CACHE = {"mtime": None, "size": None, "stats": None}
LOGSCAN_ANALYSIS_CACHE = {"mtime": None, "size": None, "data": None}
KOMETA_CPU_CACHE = {}
SYSTEM_CPU_CACHE = {"total": None, "idle": None}

VALIDATION_DOC_BASE = "/step/"
VALIDATION_DOC_FALLBACK = "/step/900-final"
VALIDATION_DOCS = {
    "settings": f"{VALIDATION_DOC_BASE}150-settings",
    "libraries": f"{VALIDATION_DOC_BASE}025-libraries",
    "plex": f"{VALIDATION_DOC_BASE}010-plex",
    "tmdb": f"{VALIDATION_DOC_BASE}020-tmdb",
    "trakt": f"{VALIDATION_DOC_BASE}130-trakt",
    "radarr": f"{VALIDATION_DOC_BASE}110-radarr",
    "sonarr": f"{VALIDATION_DOC_BASE}120-sonarr",
    "tautulli": f"{VALIDATION_DOC_BASE}030-tautulli",
    "omdb": f"{VALIDATION_DOC_BASE}050-omdb",
    "mdblist": f"{VALIDATION_DOC_BASE}060-mdblist",
    "notifiarr": f"{VALIDATION_DOC_BASE}070-notifiarr",
    "github": f"{VALIDATION_DOC_BASE}040-github",
    "gotify": f"{VALIDATION_DOC_BASE}080-gotify",
    "ntfy": f"{VALIDATION_DOC_BASE}085-ntfy",
    "mal": f"{VALIDATION_DOC_BASE}140-mal",
    "anidb": f"{VALIDATION_DOC_BASE}100-anidb",
    "webhooks": f"{VALIDATION_DOC_BASE}090-webhooks",
    "collections": f"{VALIDATION_DOC_BASE}025-libraries",
    "overlays": f"{VALIDATION_DOC_BASE}025-libraries",
    "playlist_files": f"{VALIDATION_DOC_BASE}027-playlist_files",
}
VALIDATION_REASON_LABELS = {
    "missing_credentials": "Missing credentials",
    "missing_plex_validation": "Plex not validated",
    "no_libraries": "No libraries selected",
    "invalid_paths": "Invalid paths",
    "missing_placeholder_imdb": "Missing placeholder IMDb ID",
    "invalid_fields": "Invalid fields",
    "no_webhooks": "No webhooks configured",
    "disabled": "Disabled",
    "missing_settings": "Settings missing",
    "missing_tokens": "Missing tokens",
    "token_invalid": "Invalid tokens",
    "account_locked": "Account locked",
    "validation_error": "Validation error",
}
VALIDATION_KEY_SUGGESTIONS = {
    "settings": {
        "playlist_sync_to_user": "playlist_sync_to_users",
    }
}


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_validation_summary(errors):
    summary = []
    if not errors:
        return summary
    for err in errors[:20]:
        path_parts = [str(p) for p in err.path]
        section = path_parts[0] if path_parts else ""
        path_display = ".".join(path_parts) if path_parts else (section or "config")
        doc_url = VALIDATION_DOCS.get(section, VALIDATION_DOC_FALLBACK)
        title = f"{path_display}: {err.message}"
        details = ""
        suggestions = []

        if err.validator == "additionalProperties":
            extras = []
            try:
                extras = list(err.params.get("additionalProperties") or [])
            except Exception:
                extras = []
            if extras:
                title = f"{section or 'config'}: Unexpected key(s)"
                details = f"Unknown keys: {', '.join(extras)}."
                for key in extras:
                    suggestion = VALIDATION_KEY_SUGGESTIONS.get(section, {}).get(key)
                    if suggestion:
                        suggestions.append(f"{key} → {suggestion}")
        elif err.validator == "type":
            expected = err.validator_value
            details = f"Expected type: {expected}."
        elif err.validator == "enum":
            values = err.validator_value or []
            details = f"Expected one of: {', '.join(map(str, values))}."
        elif err.validator == "minimum":
            details = f"Minimum allowed: {err.validator_value}."
        elif err.validator == "maximum":
            details = f"Maximum allowed: {err.validator_value}."
        elif err.validator == "pattern":
            details = "Value does not match the expected format."

        summary.append(
            {
                "title": title,
                "details": details,
                "doc_url": doc_url,
                "section": section or "config",
                "suggestions": suggestions,
            }
        )

    return summary


def _calculate_process_cpu_percent(proc):
    try:
        cpu_times = proc.cpu_times()
    except Exception:
        return None
    total_cpu = cpu_times.user + cpu_times.system
    try:
        for child in proc.children(recursive=True):
            try:
                child_times = child.cpu_times()
                total_cpu += child_times.user + child_times.system
            except Exception:
                continue
    except Exception:
        pass
    now = time.time()
    entry = KOMETA_CPU_CACHE.get(proc.pid)
    KOMETA_CPU_CACHE[proc.pid] = {"time": now, "cpu": total_cpu}
    if not entry:
        return None
    elapsed = now - entry.get("time", now)
    if elapsed <= 0:
        return None
    delta_cpu = total_cpu - entry.get("cpu", total_cpu)
    if delta_cpu < 0:
        return None
    percent = (delta_cpu / elapsed) * 100.0
    return max(0.0, percent)


def _calculate_system_cpu_percent():
    try:
        cpu_times = psutil.cpu_times()
    except Exception:
        return None
    total = sum(cpu_times)
    idle = getattr(cpu_times, "idle", 0)
    last_total = SYSTEM_CPU_CACHE.get("total")
    last_idle = SYSTEM_CPU_CACHE.get("idle")
    SYSTEM_CPU_CACHE["total"] = total
    SYSTEM_CPU_CACHE["idle"] = idle
    if last_total is None or last_idle is None:
        return None
    delta_total = total - last_total
    if delta_total <= 0:
        return None
    delta_idle = idle - last_idle
    busy = max(0.0, delta_total - delta_idle)
    percent = (busy / delta_total) * 100.0
    return max(0.0, min(100.0, percent))


def _write_quickstart_run_marker(kometa_root, config_name=None):
    try:
        log_dir = Path(kometa_root) / "config" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "meta.log"
        version_info = app.config.get("VERSION_CHECK") or {}
        qs_version = version_info.get("local_version") or "unknown"
        qs_branch = version_info.get("branch") or "unknown"
        safe_config = (config_name or "default").strip() or "default"
        timestamp = datetime.now(timezone.utc).isoformat()
        marker = f"[Quickstart] Run marker: started={timestamp} " f"config={safe_config} quickstart={qs_version} branch={qs_branch}"
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(marker + "\n")
    except Exception:
        pass


def _schedule_quickstart_run_marker(kometa_root, config_name=None, timeout_seconds=20):
    log_path = Path(kometa_root) / "config" / "logs" / "meta.log"
    state = {"mtime": None, "size": None}
    if log_path.exists():
        try:
            stat = log_path.stat()
            state["mtime"] = stat.st_mtime
            state["size"] = stat.st_size
        except OSError:
            pass

    def worker():
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                if log_path.exists():
                    stat = log_path.stat()
                    if state["mtime"] is None:
                        if stat.st_size > 0:
                            _write_quickstart_run_marker(kometa_root, config_name)
                            return
                    else:
                        if stat.st_mtime != state["mtime"] and stat.st_size > 0:
                            _write_quickstart_run_marker(kometa_root, config_name)
                            return
            except OSError:
                pass
            time.sleep(0.5)
        _write_quickstart_run_marker(kometa_root, config_name)

    threading.Thread(target=worker, daemon=True).start()


def _extract_kometa_config_path(command_parts, kometa_root):
    config_value = None
    for idx, part in enumerate(command_parts):
        if part in {"-c", "--config"} and idx + 1 < len(command_parts):
            config_value = command_parts[idx + 1]
            break
        if part.startswith("--config="):
            config_value = part.split("=", 1)[1]
            break
        if part.startswith("-c="):
            config_value = part.split("=", 1)[1]
            break
    if not config_value:
        return None
    try:
        path = Path(config_value)
    except Exception:
        return None
    if not path.is_absolute():
        path = Path(kometa_root) / path
    return path


def _stamp_quickstart_config_marker(config_path, config_name=None):
    if not config_path:
        return False
    path = Path(config_path)
    if not path.exists() or not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = content.splitlines()
    lines = [line for line in lines if not line.lstrip().startswith("# Quickstart run marker:")]
    version_info = app.config.get("VERSION_CHECK") or {}
    qs_version = version_info.get("local_version") or "unknown"
    qs_branch = version_info.get("branch") or "unknown"
    safe_config = (config_name or "default").strip() or "default"
    timestamp = datetime.now(timezone.utc).isoformat()
    marker = f"# Quickstart run marker: started={timestamp} " f"config={safe_config} quickstart={qs_version} branch={qs_branch}"
    if lines and lines[-1].strip():
        lines.append("")
    lines.append(marker)
    try:
        path.write_text(newline.join(lines) + newline, encoding="utf-8")
        return True
    except Exception:
        return False


def _sanitize_config_name(raw_name: str | None) -> str:
    if not isinstance(raw_name, str):
        return ""
    return re.sub(r"[^a-z0-9_]", "", raw_name.strip().lower())


def _normalize_config_filename(config_name: str | None) -> str:
    name = (config_name or "").strip().lower().replace(" ", "_")
    return name or "default"


def _rename_config_files(old_name: str, new_name: str, dry_run: bool = False) -> dict:
    result = {"success": False, "renamed": [], "skipped": [], "errors": [], "rollback_errors": []}
    old_norm = _normalize_config_filename(old_name)
    new_norm = _normalize_config_filename(new_name)
    if old_norm == new_norm:
        result["skipped"].append("Normalized filenames are identical.")
        return result

    config_dir = Path(helpers.CONFIG_DIR)
    kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    config_file = config_dir / f"{old_norm}_config.yml"
    new_config_file = config_dir / f"{new_norm}_config.yml"
    kometa_file = kometa_root / "config" / f"{old_norm}_config.yml"
    new_kometa_file = kometa_root / "config" / f"{new_norm}_config.yml"

    if new_config_file.exists() or new_kometa_file.exists():
        result["errors"].append("Target config filename already exists.")
        return result

    archive_root = config_dir / "archives"
    old_archive = archive_root / old_norm
    new_archive = archive_root / new_norm
    if old_archive.exists():
        if new_archive.exists():
            result["errors"].append("Target archive directory already exists.")
            return result
        existing_names = {p.name for p in old_archive.glob("*.yml")}
        for path in old_archive.glob(f"{old_norm}_config_*.yml"):
            target_name = path.name.replace(f"{old_norm}_config_", f"{new_norm}_config_", 1)
            if target_name in existing_names and target_name != path.name:
                result["errors"].append(f"Archive file already exists: {target_name}")
                return result

    if dry_run:
        result["success"] = True
        return result

    completed = []
    try:
        if config_file.exists():
            config_file.rename(new_config_file)
            completed.append((config_file, new_config_file))
            result["renamed"].append(str(new_config_file))
        if kometa_file.exists():
            kometa_file.rename(new_kometa_file)
            completed.append((kometa_file, new_kometa_file))
            result["renamed"].append(str(new_kometa_file))

        if old_archive.exists():
            old_archive.rename(new_archive)
            completed.append((old_archive, new_archive))
            result["renamed"].append(str(new_archive))
            file_ops = []
            for path in new_archive.glob(f"{old_norm}_config_*.yml"):
                new_path = new_archive / path.name.replace(f"{old_norm}_config_", f"{new_norm}_config_", 1)
                if new_path.exists() and new_path != path:
                    raise FileExistsError(f"Archive file already exists: {new_path.name}")
                file_ops.append((path, new_path))
            for src, dst in file_ops:
                src.rename(dst)
                completed.append((src, dst))
                result["renamed"].append(str(dst))
    except Exception as exc:
        result["errors"].append(f"Rename failed: {exc}")
        for src, dst in reversed(completed):
            try:
                if Path(dst).exists():
                    Path(dst).rename(src)
            except Exception as rollback_exc:
                result["rollback_errors"].append(str(rollback_exc))
        return result

    result["success"] = True
    return result


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
CUSTOM_FONTS_FOLDER = os.path.join(helpers.CONFIG_DIR, "fonts")
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
    font_dirs = helpers.get_font_dirs(include_static=True, include_custom=True)
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

# Default Kometa root lives under Quickstart's config directory
kometa_path = os.path.abspath(os.path.join(helpers.CONFIG_DIR, "kometa"))

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
app.config["QS_THEME"] = os.getenv("QS_THEME", "kometa").strip() or "kometa"
app.config["QS_OPTIMIZE_DEFAULTS"] = helpers.booler(os.getenv("QS_OPTIMIZE_DEFAULTS", "1"))
try:
    app.config["QS_CONFIG_HISTORY"] = max(0, int(str(os.getenv("QS_CONFIG_HISTORY", "0")).strip()))
except (TypeError, ValueError):
    app.config["QS_CONFIG_HISTORY"] = 0
try:
    app.config["QS_KOMETA_LOG_KEEP"] = max(0, int(str(os.getenv("QS_KOMETA_LOG_KEEP", "0")).strip()))
except (TypeError, ValueError):
    app.config["QS_KOMETA_LOG_KEEP"] = 0
default_test_libs_path = os.path.join(helpers.CONFIG_DIR, "plex_test_libraries")
default_test_libs_tmp = os.path.join(helpers.CONFIG_DIR, "tmp")
app.config["QS_TEST_LIBS_PATH"] = os.getenv("QS_TEST_LIBS_PATH", default_test_libs_path).strip() or default_test_libs_path
app.config["QS_TEST_LIBS_TMP"] = os.getenv("QS_TEST_LIBS_TMP", default_test_libs_tmp).strip() or default_test_libs_tmp
app.config["QUICKSTART_DOCKER"] = helpers.booler(os.getenv("QUICKSTART_DOCKER", "0"))
restart_notice = helpers.consume_restart_notice()
app.config["QS_RESTART_NOTICE"] = restart_notice
app.config["QS_SKIP_AUTO_OPEN"] = bool(restart_notice and restart_notice.get("reason") == "update")

cleanup_flag = os.getenv("QS_CONFIG_CLEANUP_DONE", "").strip().lower()
if cleanup_flag not in {"1", "true", "yes"}:
    result = helpers.migrate_config_archives(history_limit=app.config.get("QS_CONFIG_HISTORY", 0))
    if result.get("moved"):
        helpers.ts_log(f"Config cleanup moved {result['moved']} archived file(s).", level="INFO")
    if result.get("errors"):
        for msg in result["errors"]:
            helpers.ts_log(msg, level="WARNING")
    else:
        helpers.update_env_variable("QS_CONFIG_CLEANUP_DONE", "1")
        os.environ["QS_CONFIG_CLEANUP_DONE"] = "1"


def _load_or_create_secret_key():
    env_key = os.getenv("QS_SECRET_KEY", "").strip()
    if env_key:
        return env_key
    secret_path = os.path.join(helpers.CONFIG_DIR, ".secret_key")
    try:
        if os.path.exists(secret_path):
            with open(secret_path, "r", encoding="utf-8") as handle:
                existing = handle.read().strip()
            if existing:
                return existing
        new_key = secrets.token_hex(32)
        with open(secret_path, "w", encoding="utf-8") as handle:
            handle.write(new_key)
        return new_key
    except Exception:
        return secrets.token_hex(32)


def _get_session_lifetime_days():
    raw_days = os.getenv("QS_SESSION_LIFETIME_DAYS", "").strip()
    if raw_days:
        try:
            days = max(1, int(raw_days))
        except (TypeError, ValueError):
            days = 30
    else:
        days = 30
    return days


def _get_session_lifetime_seconds():
    return int(timedelta(days=_get_session_lifetime_days()).total_seconds())


app.config["SECRET_KEY"] = _load_or_create_secret_key()
app.config["SESSION_TYPE"] = "cachelib"

# Flask session cache dir (portable default)
flask_cache_dir = os.environ.get("QS_FLASK_SESSION_DIR", os.path.join(helpers.CONFIG_DIR, "flask_session"))
flask_cache_dir = os.path.abspath(os.path.expanduser(flask_cache_dir))
os.makedirs(flask_cache_dir, exist_ok=True)

logscan_reingest_lock = threading.Lock()
logscan_ingest_lock = threading.Lock()
logscan_reingest_state = {
    "status": "idle",
    "job_id": None,
}

session_ttl = _get_session_lifetime_seconds()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=session_ttl)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["QS_SESSION_LIFETIME_DAYS"] = _get_session_lifetime_days()
app.config["QS_FLASK_SESSION_DIR"] = flask_cache_dir
app.config["SESSION_CACHELIB"] = FileSystemCache(cache_dir=flask_cache_dir, threshold=500, default_timeout=session_ttl)
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

    try:
        ua = request.user_agent
        session["qs_user_agent"] = ua.string or ""
        session["qs_user_agent_browser"] = ua.browser or ""
        session["qs_user_agent_version"] = ua.version or ""
        session["qs_user_agent_platform"] = ua.platform or ""
        session["qs_user_agent_raw"] = request.headers.get("User-Agent", "") or ""
    except Exception:
        pass


def _render_header_style_preview(font: str) -> str:
    if font == "none":
        return "No header will be added."
    return output.section_heading("Quickstart", font=font)


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
app.config["QS_PORT"] = running_port
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


@app.route("/upload-fonts", methods=["POST"])
def upload_fonts():
    files = request.files.getlist("fonts")
    if not files:
        return jsonify({"status": "error", "message": "No fonts uploaded"}), 400

    os.makedirs(CUSTOM_FONTS_FOLDER, exist_ok=True)
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
        save_path = os.path.join(CUSTOM_FONTS_FOLDER, filename)
        font_file.save(save_path)
        saved.append(filename)

    if saved:
        global _FONT_CACHE
        _FONT_CACHE = []

    if not saved:
        return jsonify({"status": "error", "message": "No valid fonts uploaded.", "errors": errors}), 400

    return jsonify(
        {
            "status": "success",
            "message": f"Uploaded {len(saved)} font(s).",
            "saved": saved,
            "errors": errors,
            "fonts": list_overlay_fonts(),
        }
    )


@app.route("/custom-fonts/<path:filename>", methods=["GET"])
def custom_fonts(filename):
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        abort(404)
    if not safe_name.lower().endswith((".ttf", ".otf")):
        abort(404)

    for fdir in helpers.get_font_dirs(include_static=True, include_custom=True):
        candidate = os.path.join(str(fdir), safe_name)
        if os.path.exists(candidate):
            return send_from_directory(str(fdir), safe_name)

    abort(404)


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
        return jsonify(success=False, message="No configs selected."), 400

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


@app.route("/rename-config", methods=["POST"])
def rename_config():
    data = request.get_json(silent=True) or {}
    old_name = str(data.get("old_name", "")).strip()
    new_name = _sanitize_config_name(data.get("new_name"))
    if not old_name or not new_name:
        return jsonify(success=False, message="Config names are required."), 400
    if old_name == new_name:
        return jsonify(success=False, message="New name must be different."), 400

    available = database.get_unique_config_names() or []
    if old_name not in available:
        return jsonify(success=False, message="Config not found."), 404

    for name in available:
        if name.lower() == new_name.lower() and name != old_name:
            return jsonify(success=False, message="Config name already exists."), 400

    file_check = _rename_config_files(old_name, new_name, dry_run=True)
    if not file_check.get("success"):
        return jsonify(success=False, message="Config files are not safe to rename.", details=file_check), 400

    file_result = _rename_config_files(old_name, new_name)
    if not file_result.get("success"):
        return jsonify(success=False, message="Failed to rename config files.", details=file_result), 500

    try:
        update_result = database.rename_config(old_name, new_name)
    except Exception as exc:
        rollback = _rename_config_files(new_name, old_name)
        return jsonify(success=False, message=f"Failed to update database: {exc}", details=rollback), 500

    if not update_result.get("success"):
        rollback = _rename_config_files(new_name, old_name)
        return jsonify(success=False, message="Failed to update database.", details=rollback), 500

    if session.get("config_name") == old_name:
        session["config_name"] = new_name

    return jsonify(success=True, old_name=old_name, new_name=new_name, files=file_result)


def count_annotated_lines(text: str) -> dict:
    imported = 0
    not_imported = 0
    if not isinstance(text, str):
        return {"imported": 0, "not_imported": 0}
    imported_pattern = re.compile(r"(?:#|\|) imported(?:\s*-.*)?$")
    not_imported_pattern = re.compile(r"(?:#|\|) not imported(?:\s*-.*)?$")
    for line in text.splitlines():
        trimmed = line.rstrip()
        if imported_pattern.search(trimmed):
            imported += 1
        elif not_imported_pattern.search(trimmed):
            not_imported += 1
    return {"imported": imported, "not_imported": not_imported}


@app.route("/import-config/preview", methods=["POST"])
def import_config_preview():
    def count_comment_lines(text: str) -> int:
        if not isinstance(text, str):
            return 0
        return sum(1 for line in text.splitlines() if line.lstrip().startswith("#"))

    def count_blank_lines(text: str) -> int:
        if not isinstance(text, str):
            return 0
        return sum(1 for line in text.splitlines() if not line.strip())

    def count_annotated_lines(text: str) -> dict:
        imported = 0
        not_imported = 0
        if not isinstance(text, str):
            return {"imported": 0, "not_imported": 0}
        imported_pattern = re.compile(r"(?:#|\|) imported(?:\s*-.*)?$")
        not_imported_pattern = re.compile(r"(?:#|\|) not imported(?:\s*-.*)?$")
        for line in text.splitlines():
            trimmed = line.rstrip()
            if imported_pattern.search(trimmed):
                imported += 1
            elif not_imported_pattern.search(trimmed):
                not_imported += 1
        return {"imported": imported, "not_imported": not_imported}

    upload = request.files.get("file")
    raw_name = request.form.get("config_name")
    config_name = importer.sanitize_config_name(raw_name)
    merge_mode = str(request.form.get("merge_mode") or "").strip().lower() in {"1", "true", "yes", "merge"}
    base_config = (request.form.get("base_config") or "").strip()

    if not upload or not upload.filename:
        return jsonify(success=False, message="No config file uploaded."), 400
    file_name = upload.filename.lower()
    if not file_name.endswith((".yml", ".yaml", ".zip")):
        return jsonify(success=False, message="Only .yml, .yaml, or .zip files are supported."), 400
    if not config_name:
        return jsonify(success=False, message="Config name is required."), 400

    available = database.get_unique_config_names() or []
    if any(name.lower() == config_name.lower() for name in available):
        return jsonify(success=False, message="Config name already exists."), 400
    if merge_mode:
        base_match = next((name for name in available if name.lower() == base_config.lower()), "")
        if not base_match:
            return jsonify(success=False, message="Base config not found. Select an existing config to merge."), 400
        base_config = base_match

    raw_text = upload.read()
    config_text = ""
    extracted_fonts = []
    extracted_dir = None
    if file_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(raw_text)) as archive:
                config_files = [n for n in archive.namelist() if n.lower().endswith((".yml", ".yaml"))]
                if not config_files:
                    return jsonify(success=False, message="No YAML config found in zip file."), 400
                if len(config_files) > 1:
                    return jsonify(success=False, message="Zip file must contain exactly one YAML config."), 400

                try:
                    with archive.open(config_files[0]) as handle:
                        config_text = handle.read().decode("utf-8", errors="ignore")
                except Exception:
                    return jsonify(success=False, message="Unable to read config from zip."), 400

                font_files = [n for n in archive.namelist() if n.lower().endswith((".ttf", ".otf"))]
                if font_files:
                    cache_dir = Path(helpers.CONFIG_DIR) / "import_cache"
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    extracted_dir = cache_dir / f"fonts_{secrets.token_urlsafe(8)}"
                    extracted_dir.mkdir(parents=True, exist_ok=True)
                    seen_names = set()
                    for font_name in font_files:
                        base_name = os.path.basename(font_name)
                        if not base_name:
                            continue
                        safe_name = base_name
                        counter = 1
                        while safe_name in seen_names:
                            stem, ext = os.path.splitext(base_name)
                            safe_name = f"{stem}_{counter}{ext}"
                            counter += 1
                        seen_names.add(safe_name)
                        try:
                            with archive.open(font_name) as source:
                                target = extracted_dir / safe_name
                                with open(target, "wb") as dest:
                                    dest.write(source.read())
                                extracted_fonts.append(safe_name)
                        except Exception:
                            continue
        except Exception:
            return jsonify(success=False, message="Unable to read zip file."), 400
    else:
        try:
            config_text = raw_text.decode("utf-8")
        except UnicodeDecodeError:
            config_text = raw_text.decode("utf-8", errors="ignore")

    parsed = importer.load_yaml_config(config_text)
    if not parsed:
        if extracted_dir:
            try:
                shutil.rmtree(extracted_dir)
            except OSError:
                pass
        return jsonify(success=False, message="Unable to parse config file."), 400

    def parse_list(value):
        if isinstance(value, str):
            return {v.strip() for v in value.split(",") if v.strip()}
        if isinstance(value, list):
            return {str(v).strip() for v in value if str(v).strip()}
        return set()

    def parse_base_plex_libraries(base_name: str):
        if not base_name:
            return set(), set()
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return set(), set()
        if not isinstance(stored, dict):
            return set(), set()
        plex_block = stored.get("plex") if isinstance(stored.get("plex"), dict) else stored
        if not isinstance(plex_block, dict):
            return set(), set()
        return parse_list(plex_block.get("tmp_movie_libraries", "")), parse_list(plex_block.get("tmp_show_libraries", ""))

    def parse_base_plex_libraries(base_name: str):
        if not base_name:
            return set(), set()
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return set(), set()
        if not isinstance(stored, dict):
            return set(), set()
        plex_block = stored.get("plex") if isinstance(stored.get("plex"), dict) else stored
        if not isinstance(plex_block, dict):
            return set(), set()
        return parse_list(plex_block.get("tmp_movie_libraries", "")), parse_list(plex_block.get("tmp_show_libraries", ""))

    def parse_plex_credentials(config_data):
        plex_block = config_data.get("plex", {}) if isinstance(config_data, dict) else {}
        if not isinstance(plex_block, dict):
            return "", ""
        url = plex_block.get("url") or plex_block.get("plex_url") or ""
        token = plex_block.get("token") or plex_block.get("plex_token") or ""
        return str(url).strip(), str(token).strip()

    def parse_base_plex_credentials(base_name: str):
        if not base_name:
            return "", ""
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return "", ""
        if not isinstance(stored, dict):
            return "", ""
        if "plex" in stored:
            return parse_plex_credentials(stored)
        url = stored.get("url") or stored.get("plex_url") or ""
        token = stored.get("token") or stored.get("plex_token") or ""
        return str(url).strip(), str(token).strip()

    def parse_form_plex_credentials(form_data):
        url = form_data.get("plex_url", "") or ""
        token = form_data.get("plex_token", "") or ""
        return str(url).strip(), str(token).strip()

    def parse_tmdb_credentials(config_data):
        tmdb_block = config_data.get("tmdb", {}) if isinstance(config_data, dict) else {}
        if not isinstance(tmdb_block, dict):
            return ""
        api_key = tmdb_block.get("apikey") or tmdb_block.get("api_key") or tmdb_block.get("tmdb_apikey") or tmdb_block.get("token") or ""
        return str(api_key).strip()

    def parse_base_tmdb_credentials(base_name: str):
        if not base_name:
            return ""
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "tmdb")
        except Exception:
            return ""
        if not isinstance(stored, dict):
            return ""
        if "tmdb" in stored:
            return parse_tmdb_credentials(stored)
        api_key = stored.get("apikey") or stored.get("api_key") or stored.get("tmdb_apikey") or stored.get("token") or ""
        return str(api_key).strip()

    def parse_form_tmdb_credentials(form_data):
        api_key = form_data.get("tmdb_apikey", "") or ""
        return str(api_key).strip()

    needs_plex = isinstance(parsed.get("libraries"), dict) and bool(parsed.get("libraries"))
    needs_tmdb = isinstance(parsed, dict) and bool(parsed.get("tmdb") or parsed.get("libraries") or parsed.get("collections") or parsed.get("overlays"))
    plex_data = persistence.retrieve_settings("010-plex").get("plex", {})
    movie_names = parse_list(plex_data.get("tmp_movie_libraries", ""))
    show_names = parse_list(plex_data.get("tmp_show_libraries", ""))
    plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}

    if needs_plex:
        base_movie_names, base_show_names = (set(), set())
        skip_plex_validation = False
        if merge_mode and base_config:
            base_movie_names, base_show_names = parse_base_plex_libraries(base_config)
            if base_movie_names or base_show_names:
                movie_names = base_movie_names
                show_names = base_show_names
                plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
                skip_plex_validation = True

        form_plex_url, form_plex_token = parse_form_plex_credentials(request.form or {})
        imported_plex_url, imported_plex_token = parse_plex_credentials(parsed)
        base_plex_url, base_plex_token = parse_base_plex_credentials(base_config) if merge_mode else ("", "")
        has_form = bool(form_plex_url and form_plex_token)
        has_imported = bool(imported_plex_url and imported_plex_token)
        has_base = bool(base_plex_url and base_plex_token)
        used_plex_url = ""
        used_plex_token = ""

        if not skip_plex_validation and not has_form and not has_imported and not has_base:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return (
                jsonify(
                    success=False,
                    needs_plex_credentials=True,
                    message=("Plex credentials are required to import library settings. " "Enter a Plex URL and token to continue."),
                    plex_url="",
                    plex_token="",
                ),
                400,
            )

        if not skip_plex_validation:
            plex_result = None
            last_error = None
            if has_form:
                used_plex_url = form_plex_url
                used_plex_token = form_plex_token
                plex_response = validations.validate_plex_server({"plex_url": form_plex_url, "plex_token": form_plex_token})
                plex_result = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
                if not plex_result or not plex_result.get("validated"):
                    if isinstance(plex_result, dict):
                        last_error = plex_result.get("error")
                    if extracted_dir:
                        try:
                            shutil.rmtree(extracted_dir)
                        except OSError:
                            pass
                    return (
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=last_error or "Plex validation failed. Please enter valid credentials.",
                            plex_url=form_plex_url or "",
                            plex_token=form_plex_token or "",
                        ),
                        400,
                    )
            else:
                candidates = []
                if merge_mode and has_base:
                    candidates.append((base_plex_url, base_plex_token))
                if has_imported:
                    candidates.append((imported_plex_url, imported_plex_token))
                if not candidates:
                    candidates.append((imported_plex_url or base_plex_url, imported_plex_token or base_plex_token))
                for candidate_url, candidate_token in candidates:
                    used_plex_url = candidate_url
                    used_plex_token = candidate_token
                    plex_response = validations.validate_plex_server({"plex_url": used_plex_url, "plex_token": used_plex_token})
                    plex_result = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
                    if plex_result and plex_result.get("validated"):
                        last_error = None
                        break
                    if isinstance(plex_result, dict):
                        last_error = plex_result.get("error")
                if not plex_result or not plex_result.get("validated"):
                    if extracted_dir:
                        try:
                            shutil.rmtree(extracted_dir)
                        except OSError:
                            pass
                    return (
                        jsonify(
                            success=False,
                            needs_plex_credentials=True,
                            message=("Plex credentials from the import/base config could not be validated. " "Please enter a valid Plex URL and token."),
                            plex_url=imported_plex_url or base_plex_url or "",
                            plex_token=imported_plex_token or base_plex_token or "",
                        ),
                        400,
                    )
        if not skip_plex_validation:
            session["import_preview_plex_url"] = used_plex_url
            session["import_preview_plex_token"] = used_plex_token
        if used_plex_url and used_plex_token:
            plex_block = parsed.get("plex")
            if not isinstance(plex_block, dict):
                plex_block = {}
                parsed["plex"] = plex_block
            plex_block["url"] = used_plex_url
            plex_block["token"] = used_plex_token
        if not skip_plex_validation:
            movie_names = parse_list(plex_result.get("movie_libraries", []))
            show_names = parse_list(plex_result.get("show_libraries", []))
            plex_libraries = {"movie": sorted(movie_names), "show": sorted(show_names)}
            if not movie_names and not show_names:
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        message="No movie or show libraries found in Plex.",
                    ),
                    400,
                )

    if needs_tmdb:
        form_tmdb_key = parse_form_tmdb_credentials(request.form or {})
        imported_tmdb_key = parse_tmdb_credentials(parsed)
        base_tmdb_key = parse_base_tmdb_credentials(base_config) if merge_mode else ""
        has_form = bool(form_tmdb_key)
        has_imported = bool(imported_tmdb_key)
        has_base = bool(base_tmdb_key)
        used_tmdb_key = ""

        if not has_form and not has_imported and not has_base:
            if extracted_dir:
                try:
                    shutil.rmtree(extracted_dir)
                except OSError:
                    pass
            return (
                jsonify(
                    success=False,
                    needs_tmdb_credentials=True,
                    message="TMDb API key is required to import metadata settings. Enter a valid TMDb API key to continue.",
                    tmdb_apikey="",
                ),
                400,
            )

        tmdb_result = None
        last_error = None
        if has_form:
            used_tmdb_key = form_tmdb_key
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": form_tmdb_key})
            tmdb_result = tmdb_response.get_json() if isinstance(tmdb_response, Flask.response_class) else tmdb_response
            if not tmdb_result or not tmdb_result.get("valid"):
                if isinstance(tmdb_result, dict):
                    last_error = tmdb_result.get("message")
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        needs_tmdb_credentials=True,
                        message=last_error or "TMDb validation failed. Please enter a valid API key.",
                        tmdb_apikey=form_tmdb_key or "",
                    ),
                    400,
                )
        else:
            candidates = []
            if merge_mode and has_base:
                candidates.append(base_tmdb_key)
            if has_imported:
                candidates.append(imported_tmdb_key)
            if not candidates:
                candidates.append(imported_tmdb_key or base_tmdb_key)
            for candidate_key in candidates:
                used_tmdb_key = candidate_key
                tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": used_tmdb_key})
                tmdb_result = tmdb_response.get_json() if isinstance(tmdb_response, Flask.response_class) else tmdb_response
                if tmdb_result and tmdb_result.get("valid"):
                    last_error = None
                    break
                if isinstance(tmdb_result, dict):
                    last_error = tmdb_result.get("message")
            if not tmdb_result or not tmdb_result.get("valid"):
                if extracted_dir:
                    try:
                        shutil.rmtree(extracted_dir)
                    except OSError:
                        pass
                return (
                    jsonify(
                        success=False,
                        needs_tmdb_credentials=True,
                        message="TMDb API key from the import/base config could not be validated. Please enter a valid key.",
                        tmdb_apikey=imported_tmdb_key or base_tmdb_key or "",
                    ),
                    400,
                )
        session["import_preview_tmdb_apikey"] = used_tmdb_key
        if used_tmdb_key:
            tmdb_block = parsed.get("tmdb")
            if not isinstance(tmdb_block, dict):
                tmdb_block = {}
                parsed["tmdb"] = tmdb_block
            tmdb_block["apikey"] = used_tmdb_key

    _library_types, library_inference, _ = importer.build_library_type_plan(parsed, movie_names, show_names)
    payload, report = importer.prepare_import_payload(
        parsed,
        movie_names,
        show_names,
    )
    if not payload:
        if extracted_dir:
            try:
                shutil.rmtree(extracted_dir)
            except OSError:
                pass
        return jsonify(success=False, message="No importable sections found."), 400
    importable_sections = sorted(payload.keys())

    report_lines = list(report.lines)
    if extracted_fonts:
        for font in extracted_fonts:
            report_lines.append(f"imported: bundle.fonts.{font}")
    annotated_report = importer.annotate_yaml_with_report(config_text, report_lines, binary=True)
    comments_count = count_comment_lines(config_text)
    blank_count = count_blank_lines(config_text)
    total_lines = len(config_text.splitlines()) if isinstance(config_text, str) else 0
    annotated_counts = count_annotated_lines(annotated_report)
    diff_count = total_lines - (annotated_counts.get("imported", 0) + annotated_counts.get("not_imported", 0) + blank_count + comments_count)
    line_counts = {
        "imported_lines": annotated_counts.get("imported", 0),
        "not_imported_lines": annotated_counts.get("not_imported", 0),
        "comments": comments_count,
        "blank": blank_count,
        "total": total_lines,
        "diff": diff_count,
    }

    previous_path = session.get("import_preview_path")
    if previous_path:
        try:
            os.remove(previous_path)
        except OSError:
            pass
    previous_dir = session.get("import_preview_fonts_dir")
    if previous_dir:
        try:
            shutil.rmtree(previous_dir)
        except OSError:
            pass

    cache_dir = Path(helpers.CONFIG_DIR) / "import_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(12)
    cache_path = cache_dir / f"import_{token}.json"
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "config_name": config_name,
                "config_data": parsed,
                "config_text": config_text,
                "payload": payload,
                "fonts_dir": str(extracted_dir) if extracted_dir else None,
                "fonts": extracted_fonts,
                "report_lines": report_lines,
                "report_summary": report.summary(),
                "annotated_report": annotated_report,
                "comments_count": comments_count,
                "line_counts": line_counts,
                "plex_movie_names": sorted(movie_names) if isinstance(movie_names, (set, list)) else [],
                "plex_show_names": sorted(show_names) if isinstance(show_names, (set, list)) else [],
                "merge_mode": merge_mode,
                "base_config": base_config,
                "importable_sections": importable_sections,
            },
            handle,
            ensure_ascii=True,
        )

    session["import_preview_token"] = token
    session["import_preview_path"] = str(cache_path)
    session["import_preview_name"] = config_name
    session["import_preview_fonts_dir"] = str(extracted_dir) if extracted_dir else ""

    lines = list(report_lines)
    max_lines = 500
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines] + [f"skipped: report truncated ({truncated} more lines)"]

    library_mapping = []
    if needs_plex and isinstance(parsed.get("libraries"), dict):
        inference_map = {item.get("name"): item for item in library_inference}
        for lib_name in parsed.get("libraries", {}).keys():
            if lib_name in movie_names or lib_name in show_names:
                continue
            info = inference_map.get(lib_name, {})
            library_mapping.append(
                {
                    "name": lib_name,
                    "inferred_type": info.get("type"),
                    "confidence": info.get("confidence"),
                    "movie_score": info.get("movie_score", 0),
                    "show_score": info.get("show_score", 0),
                }
            )

    return jsonify(
        success=True,
        token=token,
        config_name=config_name,
        summary=report.summary(),
        comments_count=comments_count,
        line_counts=line_counts,
        report_lines=lines,
        annotated_report=annotated_report,
        report_url=f"/import-config/report?token={token}",
        library_mapping=library_mapping,
        plex_libraries=plex_libraries,
        merge_mode=merge_mode,
        base_config=base_config,
        importable_sections=importable_sections,
    )


@app.route("/import-config/report", methods=["GET"])
def import_config_report():
    token = request.args.get("token")
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_name = cached.get("config_name") or "import"
    report_lines = cached.get("report_lines") or []
    summary = cached.get("report_summary") or {}
    annotated_report = cached.get("annotated_report")
    line_counts = cached.get("line_counts") or {}
    imported_count = line_counts.get("imported_lines", summary.get("imported", 0))
    not_imported_count = line_counts.get(
        "not_imported_lines",
        (summary.get("unmapped", 0) + summary.get("skipped", 0)),
    )
    comments_count = line_counts.get("comments", cached.get("comments_count", 0))
    blank_count = line_counts.get("blank", 0)
    total_count = line_counts.get("total", 0)
    diff_count = line_counts.get(
        "diff",
        total_count - (imported_count + not_imported_count + blank_count + comments_count),
    )

    if annotated_report:
        header = [
            f"# Import Report for {config_name}",
            f"# Imported: {imported_count}",
            f"# Not Imported: {not_imported_count}",
            f"# Comments: {comments_count}",
            f"# Blank: {blank_count}",
            f"# Total: {total_count}",
            f"# Diff: {diff_count}",
            "",
        ]
        text = "\n".join(header) + str(annotated_report)
    else:
        header = [
            f"Import Report for {config_name}",
            f"Imported: {imported_count}",
            f"Not Imported: {not_imported_count}",
            f"Comments: {comments_count}",
            f"Blank: {blank_count}",
            f"Total: {total_count}",
            f"Diff: {diff_count}",
            "",
        ]
        text = "\n".join(header + [str(line) for line in report_lines])
    response = app.response_class(text, mimetype="text/plain")
    response.headers["Content-Disposition"] = f'attachment; filename="{config_name}_import_report.txt"'
    return response


def _map_playlist_libraries(payload, library_mapping, plex_names):
    if not isinstance(payload, dict):
        return
    playlist_payload = payload.get("playlist_files")
    if not isinstance(playlist_payload, list):
        return
    mapped_entries = []
    for entry in playlist_payload:
        if not isinstance(entry, dict):
            mapped_entries.append(entry)
            continue
        tv = entry.get("template_variables")
        if isinstance(tv, dict):
            libs = tv.get("libraries")
            if isinstance(libs, list):
                mapped = []
                for lib in libs:
                    name = str(lib).strip()
                    if not name:
                        continue
                    mapped_name = library_mapping.get(name, name)
                    if mapped_name is None:
                        mapped_name = name
                    mapped_name = str(mapped_name).strip()
                    if not mapped_name or mapped_name == "__ignore__":
                        continue
                    mapped.append(mapped_name)
                deduped = []
                seen = set()
                for lib_name in mapped:
                    if lib_name in seen:
                        continue
                    seen.add(lib_name)
                    deduped.append(lib_name)
                if plex_names:
                    deduped = [lib_name for lib_name in deduped if lib_name in plex_names]
                tv = dict(tv)
                tv["libraries"] = deduped
                entry = dict(entry)
                entry["template_variables"] = tv
        mapped_entries.append(entry)
    payload["playlist_files"] = mapped_entries


@app.route("/import-config/preview-mapped", methods=["POST"])
def import_config_preview_mapped():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    library_mapping = data.get("library_mapping") or {}
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400
    if library_mapping and not isinstance(library_mapping, dict):
        return jsonify(success=False, message="Invalid library mapping."), 400

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_data = cached.get("config_data") or {}
    if not isinstance(config_data, dict):
        config_data = {}
    config_text = cached.get("config_text") or ""

    def parse_list(value):
        if isinstance(value, str):
            return {v.strip() for v in value.split(",") if v.strip()}
        if isinstance(value, list):
            return {str(v).strip() for v in value if str(v).strip()}
        return set()

    movie_names = parse_list(cached.get("plex_movie_names") or [])
    show_names = parse_list(cached.get("plex_show_names") or [])
    needs_plex = isinstance(config_data.get("libraries"), dict) and bool(config_data.get("libraries"))

    if needs_plex and not movie_names and not show_names:
        plex_url = session.get("import_preview_plex_url") or ""
        plex_token = session.get("import_preview_plex_token") or ""
        if plex_url and plex_token:
            plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
            plex_result = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
            if plex_result and plex_result.get("validated"):
                movie_names = parse_list(plex_result.get("movie_libraries", []))
                show_names = parse_list(plex_result.get("show_libraries", []))

    plex_names = set(movie_names) | set(show_names)

    mapping_skip_reasons = {}
    mapping_stats = {"mapped": 0, "ignored": 0, "missing": 0, "invalid": 0, "duplicate": 0}
    if isinstance(config_data.get("libraries"), dict):
        mapped_libraries = {}
        used_targets = set()
        for lib_name, lib_cfg in config_data.get("libraries", {}).items():
            name = str(lib_name)
            if name in plex_names:
                target = name
            else:
                mapped = library_mapping.get(name)
                if mapped is None or str(mapped).strip() == "":
                    mapping_skip_reasons[name] = "Library mapping not provided."
                    mapping_stats["missing"] += 1
                    continue
                mapped = str(mapped).strip()
                if mapped == "__ignore__":
                    mapping_skip_reasons[name] = "Mapping set to ignore library."
                    mapping_stats["ignored"] += 1
                    continue
                if mapped not in plex_names:
                    mapping_skip_reasons[name] = "Mapped library not found in Plex."
                    mapping_stats["invalid"] += 1
                    continue
                target = mapped

            if target in used_targets:
                mapping_skip_reasons[name] = "Mapped library already assigned to another entry."
                if name not in plex_names:
                    mapping_stats["duplicate"] += 1
                continue
            used_targets.add(target)
            mapped_libraries[target] = lib_cfg
            if name not in plex_names:
                mapping_stats["mapped"] += 1

        config_copy = json.loads(json.dumps(config_data))
        if mapped_libraries:
            config_copy["libraries"] = mapped_libraries
        else:
            config_copy.pop("libraries", None)
    else:
        config_copy = config_data

    _map_playlist_libraries(config_copy, library_mapping, plex_names)

    payload, report = importer.prepare_import_payload(config_copy, movie_names, show_names)
    importable_sections = sorted(payload.keys()) if isinstance(payload, dict) else []
    report_lines = list(report.lines)
    if mapping_skip_reasons:
        seen = set(report_lines)
        for lib_name, reason in mapping_skip_reasons.items():
            if not lib_name:
                continue
            line = f"skipped: libraries.{lib_name} - {reason}"
            if line not in seen:
                report_lines.append(line)
                seen.add(line)
    if library_mapping and isinstance(config_data.get("libraries"), dict):
        alias_lines = []
        seen = set(report_lines)
        for original_name, mapped_name in library_mapping.items():
            if not original_name:
                continue
            mapped_name = str(mapped_name).strip()
            if not mapped_name or mapped_name == "__ignore__":
                continue
            if mapped_name == original_name:
                continue
            prefix = f"libraries.{mapped_name}"
            for line in report_lines:
                if not isinstance(line, str) or ":" not in line:
                    continue
                status, rest = line.split(":", 1)
                status = status.strip()
                path = rest.strip()
                suffix = ""
                if " - " in path:
                    path, reason = path.split(" - ", 1)
                    path = path.strip()
                    suffix = f" - {reason}"
                if path == prefix or path.startswith(prefix + "."):
                    alias_path = f"libraries.{original_name}{path[len(prefix):]}"
                    alias_line = f"{status}: {alias_path}{suffix}"
                    if alias_line not in seen:
                        alias_lines.append(alias_line)
                        seen.add(alias_line)
        if alias_lines:
            report_lines.extend(alias_lines)
    annotated_report = importer.annotate_yaml_with_report(config_text, report_lines, binary=True)
    comments_count = cached.get("comments_count")
    if not isinstance(comments_count, int):
        comments_count = sum(1 for line in str(config_text).splitlines() if line.lstrip().startswith("#"))
    blank_count = sum(1 for line in str(config_text).splitlines() if not line.strip())
    total_lines = len(str(config_text).splitlines())
    annotated_counts = count_annotated_lines(str(annotated_report))
    imported_lines = annotated_counts.get("imported", 0)
    not_imported_lines = annotated_counts.get("not_imported", 0)
    diff_count = total_lines - (imported_lines + not_imported_lines + blank_count + comments_count)
    line_counts = {
        "imported_lines": imported_lines,
        "not_imported_lines": not_imported_lines,
        "comments": comments_count,
        "blank": blank_count,
        "total": total_lines,
        "diff": diff_count,
    }

    cached["payload"] = payload
    cached["report_lines"] = report_lines
    cached["report_summary"] = report.summary()
    cached["annotated_report"] = annotated_report
    cached["comments_count"] = comments_count
    cached["line_counts"] = line_counts
    cached["plex_movie_names"] = sorted(movie_names)
    cached["plex_show_names"] = sorted(show_names)
    cached["importable_sections"] = importable_sections

    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(cached, handle, ensure_ascii=True)

    lines = list(report_lines)
    max_lines = 500
    if len(lines) > max_lines:
        truncated = len(lines) - max_lines
        lines = lines[:max_lines] + [f"skipped: report truncated ({truncated} more lines)"]

    mapping_total = sum(mapping_stats.values())
    mapping_summary = mapping_stats if mapping_total else {}

    return jsonify(
        success=True,
        config_name=cached.get("config_name") or "",
        summary=report.summary(),
        comments_count=comments_count,
        line_counts=line_counts,
        report_lines=lines,
        annotated_report=annotated_report,
        mapping_summary=mapping_summary,
        report_url=f"/import-config/report?token={token}",
        importable_sections=importable_sections,
    )


@app.route("/import-config/confirm", methods=["POST"])
def import_config_confirm():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    library_mapping = data.get("library_mapping") or {}
    raw_merge_mode = data.get("merge_mode")
    base_config = (data.get("base_config") or "").strip()
    merge_sections = data.get("merge_sections")
    if not token or token != session.get("import_preview_token"):
        return jsonify(success=False, message="Import token is invalid."), 400
    if library_mapping and not isinstance(library_mapping, dict):
        return jsonify(success=False, message="Invalid library mapping."), 400

    def _boolish(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "merge", "on"}
        return False

    merge_mode = _boolish(raw_merge_mode)

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return jsonify(success=False, message="Import preview not found."), 400

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return jsonify(success=False, message="Import preview is unavailable."), 400

    config_name = cached.get("config_name")
    payload = cached.get("payload") or {}
    config_data = cached.get("config_data") or {}
    fonts_dir = cached.get("fonts_dir")
    fonts = cached.get("fonts") or []
    cached_merge_mode = helpers.booler(cached.get("merge_mode"))
    if not merge_mode:
        merge_mode = cached_merge_mode
    if not base_config:
        base_config = cached.get("base_config") or ""
    if merge_sections is None:
        merge_sections = cached.get("merge_sections")
    if isinstance(merge_sections, str):
        merge_sections = [entry.strip() for entry in merge_sections.split(",") if entry.strip()]
    elif not isinstance(merge_sections, list):
        merge_sections = []
    merge_sections = [str(entry).strip() for entry in merge_sections if str(entry).strip()]
    if not isinstance(config_data, dict):
        config_data = {}
    importable_sections = set(cached.get("importable_sections") or payload.keys())
    selected_sections = set()
    if merge_mode:
        if not base_config:
            return jsonify(success=False, message="Base config is required for merge."), 400
        available = database.get_unique_config_names() or []
        base_match = next((name for name in available if name.lower() == base_config.lower()), "")
        if not base_match:
            return jsonify(success=False, message="Base config not found. Select an existing config to merge."), 400
        base_config = base_match
        if merge_sections:
            selected_sections = {section for section in merge_sections if section in importable_sections}
        else:
            selected_sections = set(importable_sections)
        if not selected_sections:
            return jsonify(success=False, message="Select at least one section to merge."), 400
        config_data = {key: value for key, value in config_data.items() if key in selected_sections}
    if not config_name:
        return jsonify(success=False, message="Import payload is invalid."), 400

    available = database.get_unique_config_names() or []
    if any(name.lower() == str(config_name).lower() for name in available):
        return jsonify(success=False, message="Config name already exists."), 400

    def parse_list(value):
        if isinstance(value, str):
            return {v.strip() for v in value.split(",") if v.strip()}
        if isinstance(value, list):
            return {str(v).strip() for v in value if str(v).strip()}
        return set()

    def parse_base_plex_libraries(base_name: str):
        if not base_name:
            return set(), set()
        try:
            _validated, _user_entered, stored = database.retrieve_section_data(base_name, "plex")
        except Exception:
            return set(), set()
        if not isinstance(stored, dict):
            return set(), set()
        plex_block = stored.get("plex") if isinstance(stored.get("plex"), dict) else stored
        if not isinstance(plex_block, dict):
            return set(), set()
        return parse_list(plex_block.get("tmp_movie_libraries", "")), parse_list(plex_block.get("tmp_show_libraries", ""))

    movie_names = set()
    show_names = set()
    if config_data:
        libraries_payload = config_data.get("libraries")
        needs_plex = isinstance(libraries_payload, dict) and bool(libraries_payload)
        needs_tmdb = isinstance(config_data, dict) and bool(
            config_data.get("tmdb") or config_data.get("libraries") or config_data.get("collections") or config_data.get("overlays")
        )
        if needs_plex:
            skip_plex_validation = False
            if merge_mode and base_config:
                base_movie_names, base_show_names = parse_base_plex_libraries(base_config)
                if base_movie_names or base_show_names:
                    movie_names = base_movie_names
                    show_names = base_show_names
                    skip_plex_validation = True

            if skip_plex_validation:
                plex_names = set(movie_names) | set(show_names)
                if not plex_names:
                    skip_plex_validation = False
            if skip_plex_validation:
                # Skip Plex validation when base config provides library cache.
                pass
            else:
                plex_url = session.get("import_preview_plex_url") or ""
                plex_token = session.get("import_preview_plex_token") or ""
                if not plex_url or not plex_token:
                    return (
                        jsonify(
                            success=False,
                            message="Plex credentials are required to confirm the import. Re-run Preview Import.",
                        ),
                        400,
                    )

                plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})
                plex_result = plex_response.get_json() if isinstance(plex_response, Flask.response_class) else plex_response
                if not plex_result or not plex_result.get("validated"):
                    error_message = plex_result.get("error") if isinstance(plex_result, dict) else None
                    return (
                        jsonify(
                            success=False,
                            message=error_message or "Plex validation failed. Re-run Preview Import.",
                        ),
                        400,
                    )
                movie_names = parse_list(plex_result.get("movie_libraries", []))
                show_names = parse_list(plex_result.get("show_libraries", []))
                if not movie_names and not show_names:
                    return (
                        jsonify(
                            success=False,
                            message="No movie or show libraries found in Plex.",
                        ),
                        400,
                    )
        else:
            plex_data = persistence.retrieve_settings("010-plex").get("plex", {})
            movie_names = parse_list(plex_data.get("tmp_movie_libraries", ""))
            show_names = parse_list(plex_data.get("tmp_show_libraries", ""))

        if needs_tmdb:
            tmdb_apikey = session.get("import_preview_tmdb_apikey") or ""
            if not tmdb_apikey:
                return (
                    jsonify(
                        success=False,
                        message="TMDb API key is required to confirm the import. Re-run Preview Import.",
                    ),
                    400,
                )
            tmdb_response = validations.validate_tmdb_server({"tmdb_apikey": tmdb_apikey})
            tmdb_result = tmdb_response.get_json() if isinstance(tmdb_response, Flask.response_class) else tmdb_response
            if not tmdb_result or not tmdb_result.get("valid"):
                error_message = tmdb_result.get("message") if isinstance(tmdb_result, dict) else None
                return (
                    jsonify(
                        success=False,
                        message=error_message or "TMDb validation failed. Re-run Preview Import.",
                    ),
                    400,
                )

        plex_names = set(movie_names) | set(show_names)

        if isinstance(libraries_payload, dict):
            if needs_plex and not plex_names:
                return (
                    jsonify(
                        success=False,
                        message="Plex libraries are unavailable. Validate Plex and preview the import again.",
                    ),
                    400,
                )

            missing = []
            invalid_targets = []
            duplicates = []
            used_targets = set()
            mapped_libraries = {}

            for lib_name, lib_cfg in libraries_payload.items():
                name = str(lib_name)
                if name in plex_names:
                    target = name
                else:
                    mapped = library_mapping.get(name)
                    if mapped is None:
                        missing.append(name)
                        continue
                    mapped = str(mapped).strip()
                    if not mapped:
                        missing.append(name)
                        continue
                    if mapped == "__ignore__":
                        continue
                    if mapped not in plex_names:
                        invalid_targets.append(mapped)
                        continue
                    target = mapped

                if target in used_targets:
                    duplicates.append(target)
                    continue
                used_targets.add(target)
                mapped_libraries[target] = lib_cfg

            if missing:
                return (
                    jsonify(
                        success=False,
                        message=f"Library mapping required for: {', '.join(missing)}",
                    ),
                    400,
                )
            if invalid_targets:
                unique_targets = sorted(set(invalid_targets))
                return (
                    jsonify(
                        success=False,
                        message=f"Invalid Plex libraries selected: {', '.join(unique_targets)}",
                    ),
                    400,
                )
            if duplicates:
                unique_targets = sorted(set(duplicates))
                return (
                    jsonify(
                        success=False,
                        message=f"Multiple imports mapped to the same Plex library: {', '.join(unique_targets)}",
                    ),
                    400,
                )

            if mapped_libraries:
                config_data["libraries"] = mapped_libraries
            else:
                config_data.pop("libraries", None)

        _map_playlist_libraries(config_data, library_mapping, plex_names)

        payload, report = importer.prepare_import_payload(config_data, movie_names, show_names)
        if merge_mode and selected_sections:
            payload = {section: data_blob for section, data_blob in payload.items() if section in selected_sections}
        if not payload:
            return jsonify(success=False, message="No importable sections found."), 400

    if merge_mode and selected_sections:
        payload = {section: data_blob for section, data_blob in payload.items() if section in selected_sections}
    if not payload:
        return jsonify(success=False, message="No importable sections found."), 400

    imported_sections = []
    if merge_mode:
        base_sections = database.retrieve_config_sections(base_config)
        if not base_sections:
            return jsonify(success=False, message="Base config has no saved data to merge."), 400
        for entry in base_sections:
            section = entry.get("section")
            data_blob = entry.get("data")
            if not section or data_blob is None:
                continue
            database.save_section_data(
                name=config_name,
                section=section,
                validated=helpers.booler(entry.get("validated")),
                user_entered=helpers.booler(entry.get("user_entered")),
                data=data_blob,
            )
    for section, data_blob in payload.items():
        database.save_section_data(
            name=config_name,
            section=section,
            validated=False,
            user_entered=True,
            data=data_blob,
        )
        imported_sections.append(section)

    fonts_copied = []
    fonts_skipped = []
    fonts_skipped_existing = []
    fonts_skipped_failed = []
    if fonts_dir and fonts:
        os.makedirs(CUSTOM_FONTS_FOLDER, exist_ok=True)
        for font_name in fonts:
            src_path = os.path.join(fonts_dir, font_name)
            dest_path = os.path.join(CUSTOM_FONTS_FOLDER, font_name)
            if os.path.exists(dest_path):
                fonts_skipped.append(font_name)
                fonts_skipped_existing.append(font_name)
                continue
            try:
                shutil.copy2(src_path, dest_path)
                fonts_copied.append(font_name)
            except OSError:
                fonts_skipped.append(font_name)
                fonts_skipped_failed.append(font_name)
        if fonts_copied:
            global _FONT_CACHE
            _FONT_CACHE = []

    try:
        os.remove(cache_path)
    except OSError:
        pass
    if fonts_dir:
        try:
            shutil.rmtree(fonts_dir)
        except OSError:
            pass

    session.pop("import_preview_token", None)
    session.pop("import_preview_path", None)
    session.pop("import_preview_name", None)
    session.pop("import_preview_fonts_dir", None)
    session.pop("import_preview_plex_url", None)
    session.pop("import_preview_plex_token", None)
    session.pop("import_preview_tmdb_apikey", None)
    session["config_name"] = config_name

    return jsonify(
        success=True,
        config_name=config_name,
        imported_sections=imported_sections,
        fonts_copied=fonts_copied,
        fonts_skipped=fonts_skipped,
        fonts_skipped_existing=fonts_skipped_existing,
        fonts_skipped_failed=fonts_skipped_failed,
    )


@app.route("/step/<name>", methods=["GET", "POST"])
def step(name):
    page_info = {}
    header_style = "standard"  # Default to 'standard' font
    save_error = None
    persistence.ensure_session_config_name()

    if request.method == "POST":
        path_errors = path_validation.validate_payload(request.form)
        url_errors = url_validation.validate_payload(request.form)
        validation_errors = path_errors + url_errors
        if validation_errors:
            save_error = "Invalid values: " + " ".join(validation_errors)
        else:
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
    page_info["running_port"] = running_port
    page_info["qs_debug"] = app.config["QS_DEBUG"]
    page_info["qs_theme"] = app.config.get("QS_THEME", "kometa")
    page_info["qs_optimize_defaults"] = app.config.get("QS_OPTIMIZE_DEFAULTS", True)
    page_info["qs_config_history"] = app.config.get("QS_CONFIG_HISTORY", 0)
    page_info["qs_kometa_log_keep"] = app.config.get("QS_KOMETA_LOG_KEEP", 0)
    page_info["qs_session_lifetime_days"] = app.config.get("QS_SESSION_LIFETIME_DAYS", 30)
    page_info["qs_flask_session_dir"] = app.config.get("QS_FLASK_SESSION_DIR", "")
    _, test_libs_path, test_libs_tmp, _, _ = _resolve_test_libraries_paths(helpers.get_app_root())
    page_info["qs_test_libs_path"] = test_libs_path
    page_info["qs_test_libs_tmp"] = test_libs_tmp
    page_info["header_style"] = header_style
    page_info["save_error"] = save_error
    page_info["template_name"] = name
    if "shutdown_nonce" not in session:
        session["shutdown_nonce"] = secrets.token_urlsafe(16)
    page_info["shutdown_nonce"] = session["shutdown_nonce"]
    if name == "905-analytics":
        return redirect(url_for("logscan_trends_page"))

    # Generate a placeholder name for "Add Config"
    page_info["new_config_name"] = namesgenerator.get_random_name()

    # Fetch available configurations from the database
    available_configs = database.get_unique_config_names() or []

    # Ensure the selected config is either in the dropdown or newly created
    if selected_config not in available_configs:
        page_info["new_config_name"] = selected_config  # Use the new config name

    file_list = helpers.get_menu_list()
    template_list = helpers.get_template_list()
    progress_excludes = {"sponsor", "analytics"}
    progress_keys = [key for key in template_list if template_list[key].get("raw_name") not in progress_excludes]
    total_steps = len(progress_keys)

    stem, num, b = helpers.get_bits(name)

    try:
        item = template_list[num]
    except (ValueError, IndexError, KeyError):
        return f"ERROR WITH NAME {name}; stem, num, b: {stem}, {num}, {b}"

    if num in progress_keys and total_steps:
        progress_index = progress_keys.index(num)
    else:
        progress_index = max(total_steps - 1, 0)
    page_info["progress"] = round(((progress_index + 1) / total_steps) * 100) if total_steps else 0
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
        if all_libraries.get("validated"):
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

    service_validation_sources = [
        ("010-plex", "plex"),
        ("020-tmdb", "tmdb"),
        ("050-omdb", "omdb"),
        ("060-mdblist", "mdblist"),
        ("100-anidb", "anidb"),
        ("130-trakt", "trakt"),
        ("140-mal", "mal"),
    ]
    validation_pages = {
        "010-plex",
        "020-tmdb",
        "025-libraries",
        "027-playlist_files",
        "030-tautulli",
        "040-github",
        "050-omdb",
        "060-mdblist",
        "070-notifiarr",
        "080-gotify",
        "085-ntfy",
        "090-webhooks",
        "100-anidb",
        "110-radarr",
        "120-sonarr",
        "130-trakt",
        "140-mal",
        "150-settings",
    }
    service_validations = {}
    for section, key in service_validation_sources:
        settings = persistence.retrieve_settings(section)
        service_validations[key] = helpers.booler(settings.get("validated", False))
    validation_sections = {key: key.split("-", 1)[1] for key in validation_pages}
    validated_sections = database.retrieve_validated_map(config_name, list(validation_sections.values()))
    jump_to_validations = {key: validated_sections.get(section, False) for key, section in validation_sections.items()}

    if name == "900-final":
        validation_meta = []
        for file, display_name in file_list:
            template_key = file.rsplit(".", 1)[0]
            settings = persistence.retrieve_settings(template_key)
            has_validation = template_key in validation_pages
            validation_status = None
            validation_reason = None
            validation_details = None
            if has_validation:
                section_name = template_key.split("-", 1)[1]
                stored_section = database.retrieve_section_data(config_name, section_name)
                stored_payload = stored_section[2] if stored_section else None
                if isinstance(stored_payload, dict):
                    validation_status = stored_payload.get("validation_status")
                    validation_reason = stored_payload.get("validation_reason")
                    validation_details = stored_payload.get("validation_details")
            if not validation_status and has_validation:
                if helpers.booler(settings.get("validated", False)):
                    validation_status = "validated"
                elif settings.get("validated_at"):
                    validation_status = "failed"

            validation_result = ""
            if validation_status:
                label = validation_status.capitalize()
                if validation_reason:
                    pretty = VALIDATION_REASON_LABELS.get(validation_reason, validation_reason.replace("_", " "))
                    detail_text = ""
                    if isinstance(validation_details, (list, tuple)):
                        detail_text = ", ".join(str(item) for item in validation_details if str(item))
                    elif validation_details is not None:
                        detail_text = str(validation_details)
                    if detail_text:
                        validation_result = f"{label}: {pretty}: {detail_text}"
                    else:
                        validation_result = f"{label}: {pretty}"
                else:
                    validation_result = label

            validation_meta.append(
                {
                    "key": template_key,
                    "label": display_name,
                    "page": template_key,
                    "has_validation": has_validation,
                    "validated": helpers.booler(settings.get("validated", False)) if has_validation else None,
                    "validated_at": settings.get("validated_at", "") if has_validation else "",
                    "validation_result": validation_result,
                }
            )
        validated, validation_error, config_data, yaml_content, validation_errors = output.build_config(header_style, config_name=config_name)
        validation_summary = build_validation_summary(validation_errors)
        validation_rollup = None
        validation_rollup_at = None
        try:
            stored_validation = database.retrieve_section_data(config_name, "validation_summary")
            stored_payload = stored_validation[2] if stored_validation else None
            if isinstance(stored_payload, dict):
                validation_rollup = stored_payload.get("summary_text")
                validation_rollup_at = stored_payload.get("updated_at")
        except Exception:
            validation_rollup = None
            validation_rollup_at = None
        used_fonts = helpers.collect_font_references(config_data)
        saved_filename = helpers.save_to_named_config(yaml_content, config_name, used_fonts)
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
            validation_summary=validation_summary,
            validation_rollup=validation_rollup,
            validation_rollup_at=validation_rollup_at,
            template_list=file_list,
            available_configs=available_configs,
            movie_libraries=movie_libraries,
            show_libraries=show_libraries,
            config_dir=str(Path(helpers.CONFIG_DIR).resolve()),
            overlay_fonts=list_overlay_fonts(),
            service_validations=service_validations,
            validation_meta=validation_meta,
            jump_to_validations=jump_to_validations,
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
        service_validations=service_validations,
        jump_to_validations=jump_to_validations,
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
        errors = path_validation.validate_payload(incoming)
        if errors:
            return jsonify({"success": False, "error": "Invalid path values.", "errors": errors}), 400
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
            payload_errors = path_validation.validate_payload(source_payload)
            if payload_errors:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "Invalid path values in source payload: " + " ".join(payload_errors),
                            "errors": payload_errors,
                        }
                    ),
                    400,
                )
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
        source_errors = path_validation.validate_payload(source_items)
        if source_errors:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "Invalid path values found in source library: " + " ".join(source_errors),
                        "errors": source_errors,
                    }
                ),
                400,
            )
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


def _normalize_config_name(raw_name: str | None) -> str:
    name = (raw_name or "").strip().lower().replace(" ", "_")
    return name or "default"


def _safe_bundle_name(raw_name: str | None) -> str:
    safe = secure_filename(_normalize_config_name(raw_name))
    return safe or "default"


def _get_custom_font_files() -> list[Path]:
    custom_dir = helpers.get_custom_fonts_dir()
    if not custom_dir.is_dir():
        return []
    fonts = [entry for entry in custom_dir.iterdir() if entry.is_file() and entry.suffix.lower() in helpers.FONT_EXTENSIONS]
    return sorted(fonts, key=lambda p: p.name.lower())


def _build_config_bundle(
    config_text: str,
    config_filename: str,
    font_files: list[Path],
    config_name: str | None = None,
    redacted: bool = False,
) -> BytesIO | None:
    if not config_text or not font_files:
        return None
    name = _normalize_config_name(config_name)
    font_names = [font.name for font in font_files]
    readme_lines = [
        "Quickstart config bundle",
        f"Config name: {name}",
        "",
        "This bundle includes:",
        f"- {config_filename}",
        "- fonts/ (custom fonts uploaded in Quickstart)",
    ]
    if font_names:
        readme_lines.append(f"- Fonts included: {', '.join(font_names)}")
    readme_lines += [
        "",
        "Install steps:",
        "1) Copy the config file into your Kometa config folder (config/).",
        "2) Copy the font files from fonts/ into your Kometa config/fonts/ folder.",
        "",
        "Note: The Quickstart Run Now button syncs fonts automatically.",
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
            zf.write(font_path, f"fonts/{font_path.name}")
        zf.writestr("README.txt", "\n".join(readme_lines))
    bundle.seek(0)
    return bundle


@app.route("/download")
def download():
    yaml_content = session.get("yaml_content", "")
    if yaml_content:
        custom_fonts = _get_custom_font_files()
        config_name = session.get("config_name")
        if custom_fonts:
            bundle = _build_config_bundle(yaml_content, "config.yml", custom_fonts, config_name=config_name)
            if bundle:
                bundle_name = f"{_safe_bundle_name(config_name)}_config_bundle.zip"
                return send_file(
                    bundle,
                    mimetype="application/zip",
                    as_attachment=True,
                    download_name=bundle_name,
                )
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
        custom_fonts = _get_custom_font_files()
        config_name = session.get("config_name")
        if custom_fonts:
            bundle = _build_config_bundle(
                redacted_content,
                "config_redacted.yml",
                custom_fonts,
                config_name=config_name,
                redacted=True,
            )
            if bundle:
                bundle_name = f"{_safe_bundle_name(config_name)}_config_bundle_redacted.zip"
                return send_file(
                    bundle,
                    mimetype="application/zip",
                    as_attachment=True,
                    download_name=bundle_name,
                )
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


@app.route("/path-validation-rules", methods=["GET"])
def path_validation_rules():
    rules = path_validation.load_rules()
    return jsonify(
        {
            "rules": rules,
            "platform": path_validation.get_platform_key(),
            "is_docker": bool(app.config.get("QUICKSTART_DOCKER")),
        }
    )


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


@app.route("/validate_trakt_token", methods=["POST"])
def validate_trakt_token():
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    refresh_token = data.get("refresh_token")
    debug_enabled = helpers.booler(app.config.get("QS_DEBUG", False)) or helpers.booler(data.get("debug", False))

    def is_blank(value):
        if value is None:
            return True
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "" or trimmed.lower() in ("none", "null"):
                return True
        return False

    if is_blank(access_token) or is_blank(client_id) or is_blank(client_secret) or is_blank(refresh_token):
        settings = persistence.retrieve_settings("130-trakt") or {}
        trakt_data = settings.get("trakt", {}) if isinstance(settings, dict) else {}
        auth = trakt_data.get("authorization", {}) if isinstance(trakt_data, dict) else {}
        if is_blank(access_token):
            access_token = auth.get("access_token")
        if is_blank(client_id):
            client_id = trakt_data.get("client_id") or auth.get("client_id")
        if is_blank(client_secret):
            client_secret = trakt_data.get("client_secret") or auth.get("client_secret")
        if is_blank(refresh_token):
            refresh_token = auth.get("refresh_token")

    if is_blank(access_token) or is_blank(client_id):
        debug_payload = None
        if debug_enabled:
            settings = persistence.retrieve_settings("130-trakt") or {}
            trakt_data = settings.get("trakt", {}) if isinstance(settings, dict) else {}
            auth = trakt_data.get("authorization", {}) if isinstance(trakt_data, dict) else {}
            debug_payload = {
                "config_name": session.get("config_name"),
                "request": {
                    "access_token": not is_blank(data.get("access_token")),
                    "client_id": not is_blank(data.get("client_id")),
                    "client_secret": not is_blank(data.get("client_secret")),
                    "refresh_token": not is_blank(data.get("refresh_token")),
                },
                "stored": {
                    "access_token": not is_blank(auth.get("access_token")),
                    "client_id": not is_blank(trakt_data.get("client_id") or auth.get("client_id")),
                    "client_secret": not is_blank(trakt_data.get("client_secret") or auth.get("client_secret")),
                    "refresh_token": not is_blank(auth.get("refresh_token")),
                },
            }
        response = {"valid": False, "error": "Missing Trakt access token or client ID."}
        if debug_payload:
            response["debug"] = debug_payload
        return jsonify(response), 400
    try:
        response = requests.get(
            "https://api.trakt.tv/users/settings",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "trakt-api-version": "2",
                "trakt-api-key": client_id,
            },
            timeout=10,
        )
        if debug_enabled:
            helpers.ts_log(f"Trakt token check status={response.status_code}", level="DEBUG")
        if response.status_code == 200:
            return jsonify({"valid": True})
        if response.status_code == 423:
            return jsonify({"valid": False, "error": "Account is locked; please contact Trakt Support."}), 400
        if response.status_code in (401, 403):
            if is_blank(refresh_token) or is_blank(client_secret):
                return jsonify({"valid": False, "error": "Access token is invalid or expired."}), 400

            refresh_response = requests.post(
                "https://api.trakt.tv/oauth/token",
                json={
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if refresh_response.status_code != 200:
                debug_payload = None
                if debug_enabled:
                    debug_payload = {
                        "status": response.status_code,
                        "refresh_status": refresh_response.status_code,
                    }
                response_body = {"valid": False, "error": "Access token is invalid or expired."}
                if debug_payload:
                    response_body["debug"] = debug_payload
                return jsonify(response_body), 400

            refreshed = refresh_response.json()
            new_access = refreshed.get("access_token")
            if is_blank(new_access):
                return jsonify({"valid": False, "error": "Access token refresh failed."}), 400

            config_name = session.get("config_name") or persistence.ensure_session_config_name()
            stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, "trakt")
            if not isinstance(stored_data, dict):
                stored_data = {}
            trakt_data = stored_data.get("trakt", {}) if isinstance(stored_data.get("trakt"), dict) else {}
            auth = trakt_data.get("authorization", {}) if isinstance(trakt_data.get("authorization"), dict) else {}
            auth["access_token"] = new_access
            if refreshed.get("refresh_token"):
                auth["refresh_token"] = refreshed.get("refresh_token")
            if refreshed.get("token_type"):
                auth["token_type"] = refreshed.get("token_type")
            if refreshed.get("expires_in"):
                auth["expires_in"] = refreshed.get("expires_in")
            if refreshed.get("scope"):
                auth["scope"] = refreshed.get("scope")
            if refreshed.get("created_at"):
                auth["created_at"] = refreshed.get("created_at")
            trakt_data["authorization"] = auth
            stored_data["trakt"] = trakt_data
            stored_data["validated"] = True
            stored_data["validated_at"] = utc_now_iso()
            database.save_section_data(
                name=config_name,
                section="trakt",
                validated=True,
                user_entered=user_entered,
                data=stored_data,
            )
            return jsonify({"valid": True, "refreshed": True, "authorization": auth})
        response_body = {"valid": False, "error": f"Trakt validation failed ({response.status_code})."}
        if debug_enabled:
            response_body["debug"] = {"status": response.status_code}
        return jsonify(response_body), 400
    except requests.exceptions.RequestException as exc:
        response_body = {"valid": False, "error": f"Trakt validation error: {exc}"}
        if debug_enabled:
            response_body["debug"] = {"status": "request_exception"}
        return jsonify(response_body), 400


@app.route("/validate_mal", methods=["POST"])
def validate_mal():
    data = request.json
    return validations.validate_mal_server(data)


@app.route("/validate_mal_token", methods=["POST"])
def validate_mal_token():
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token")
    debug_enabled = helpers.booler(app.config.get("QS_DEBUG", False)) or helpers.booler(data.get("debug", False))

    def is_blank(value):
        if value is None:
            return True
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "" or trimmed.lower() in ("none", "null"):
                return True
        return False

    if is_blank(access_token):
        settings = persistence.retrieve_settings("140-mal") or {}
        mal_data = settings.get("mal", {}) if isinstance(settings, dict) else {}
        auth = mal_data.get("authorization", {}) if isinstance(mal_data, dict) else {}
        access_token = auth.get("access_token")

    if is_blank(access_token):
        debug_payload = None
        if debug_enabled:
            settings = persistence.retrieve_settings("140-mal") or {}
            mal_data = settings.get("mal", {}) if isinstance(settings, dict) else {}
            auth = mal_data.get("authorization", {}) if isinstance(mal_data.get("authorization"), dict) else {}
            debug_payload = {
                "config_name": session.get("config_name"),
                "request": {"access_token": not is_blank(data.get("access_token"))},
                "stored": {"access_token": not is_blank(auth.get("access_token"))},
            }
        response = {"valid": False, "error": "Missing MyAnimeList access token."}
        if debug_payload:
            response["debug"] = debug_payload
        return jsonify(response), 400
    try:
        response = requests.get(
            "https://api.myanimelist.net/v2/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return jsonify({"valid": True})
        if response.status_code in (401, 403):
            return jsonify({"valid": False, "error": "Access token is invalid or expired."}), 400
        return jsonify({"valid": False, "error": f"MyAnimeList validation failed ({response.status_code})."}), 400
    except requests.exceptions.RequestException as exc:
        return jsonify({"valid": False, "error": f"MyAnimeList validation error: {exc}"}), 400


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


@app.route("/validate_all_services", methods=["POST"])
def validate_all_services():
    config_name = session.get("config_name") or persistence.ensure_session_config_name()

    def is_blank_value(value):
        if value is None:
            return True
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed == "":
                return True
            if trimmed.lower() == "none":
                return True
        return False

    def has_required_credentials(payload, required_keys):
        for key in required_keys:
            value = payload.get(key)
            if value is None:
                return False
            if isinstance(value, str) and not value.strip():
                return False
            if isinstance(value, str) and value.strip().lower() == "none":
                return False
        return True

    def apply_validation_metadata(stored_data, status, reason=None, details=None, updated_at=None):
        if not isinstance(stored_data, dict):
            stored_data = {}
        stored_data["validation_status"] = status
        if reason is not None:
            stored_data["validation_reason"] = reason
        if details is not None:
            stored_data["validation_details"] = details
        stored_data["validation_updated_at"] = updated_at or utc_now_iso()
        return stored_data

    def persist_validation_metadata(section, status, reason=None, details=None, validated_override=None):
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        stored_data = apply_validation_metadata(stored_data, status, reason=reason, details=details)
        validated_value = stored_validated if validated_override is None else validated_override
        database.save_section_data(
            name=config_name,
            section=section,
            validated=validated_value,
            user_entered=user_entered,
            data=stored_data,
        )

    targets = [
        (
            "010-plex",
            "plex",
            validations.validate_plex_server,
            lambda s: {"plex_url": s.get("plex", {}).get("url"), "plex_token": s.get("plex", {}).get("token")},
            ["plex_url", "plex_token"],
        ),
        ("020-tmdb", "tmdb", validations.validate_tmdb_server, lambda s: {"tmdb_apikey": s.get("tmdb", {}).get("apikey")}, ["tmdb_apikey"]),
        (
            "030-tautulli",
            "tautulli",
            validations.validate_tautulli_server,
            lambda s: {"tautulli_url": s.get("tautulli", {}).get("url"), "tautulli_apikey": s.get("tautulli", {}).get("apikey")},
            ["tautulli_url", "tautulli_apikey"],
        ),
        ("040-github", "github", validations.validate_github_server, lambda s: {"github_token": s.get("github", {}).get("token")}, ["github_token"]),
        ("050-omdb", "omdb", validations.validate_omdb_server, lambda s: {"omdb_apikey": s.get("omdb", {}).get("apikey")}, ["omdb_apikey"]),
        ("060-mdblist", "mdblist", validations.validate_mdblist_server, lambda s: {"mdblist_apikey": s.get("mdblist", {}).get("apikey")}, ["mdblist_apikey"]),
        ("070-notifiarr", "notifiarr", validations.validate_notifiarr_server, lambda s: {"notifiarr_apikey": s.get("notifiarr", {}).get("apikey")}, ["notifiarr_apikey"]),
        (
            "080-gotify",
            "gotify",
            validations.validate_gotify_server,
            lambda s: {"gotify_url": s.get("gotify", {}).get("url"), "gotify_token": s.get("gotify", {}).get("token")},
            ["gotify_url", "gotify_token"],
        ),
        (
            "085-ntfy",
            "ntfy",
            validations.validate_ntfy_server,
            lambda s: {"ntfy_url": s.get("ntfy", {}).get("url"), "ntfy_token": s.get("ntfy", {}).get("token"), "ntfy_topic": s.get("ntfy", {}).get("topic")},
            ["ntfy_url", "ntfy_token", "ntfy_topic"],
        ),
        (
            "110-radarr",
            "radarr",
            validations.validate_radarr_server,
            lambda s: {"radarr_url": s.get("radarr", {}).get("url"), "radarr_token": s.get("radarr", {}).get("token")},
            ["radarr_url", "radarr_token"],
        ),
        (
            "120-sonarr",
            "sonarr",
            validations.validate_sonarr_server,
            lambda s: {"sonarr_url": s.get("sonarr", {}).get("url"), "sonarr_token": s.get("sonarr", {}).get("token")},
            ["sonarr_url", "sonarr_token"],
        ),
    ]

    results = {}
    summary = {"validated": 0, "failed": 0, "skipped": 0}

    for template_key, section, validator, payload_builder, required_keys in targets:
        settings = persistence.retrieve_settings(template_key)
        validated_at = settings.get("validated_at")
        payload = payload_builder(settings) or {}
        if not has_required_credentials(payload, required_keys):
            results[template_key] = {
                "status": "skipped",
                "validated_at": validated_at or "",
                "reason": "missing_credentials",
            }
            persist_validation_metadata(section, "skipped", reason="missing_credentials")
            summary["skipped"] += 1
            continue
        try:
            response = validator(payload)
            if isinstance(response, tuple) and response:
                response = response[0]
            response_data = response.get_json() if hasattr(response, "get_json") else response
            if not isinstance(response_data, dict):
                response_data = {}
        except Exception as e:
            response_data = {"valid": False, "error": str(e)}

        is_valid = helpers.booler(response_data.get("validated", response_data.get("valid", False)))
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        if not isinstance(stored_data, dict):
            stored_data = {}
        existing_validated_at = stored_data.get("validated_at") or validated_at or ""

        if is_valid:
            new_validated_at = utc_now_iso()
            stored_data["validated"] = True
            stored_data["validated_at"] = new_validated_at
            stored_data = apply_validation_metadata(stored_data, "validated")
            database.save_section_data(
                name=config_name,
                section=section,
                validated=True,
                user_entered=user_entered,
                data=stored_data,
            )
            results[template_key] = {"status": "validated", "validated_at": new_validated_at}
            summary["validated"] += 1
        else:
            stored_data["validated"] = False
            if existing_validated_at:
                stored_data["validated_at"] = existing_validated_at
            message = response_data.get("message") or response_data.get("error")
            fail_reason = None
            if isinstance(message, str) and "invalid" in message.lower():
                fail_reason = "token_invalid"
            else:
                fail_reason = "validation_error"
            stored_data = apply_validation_metadata(stored_data, "failed", reason=fail_reason, details=message)
            database.save_section_data(
                name=config_name,
                section=section,
                validated=False,
                user_entered=user_entered,
                data=stored_data,
            )
            results[template_key] = {"status": "failed", "validated_at": existing_validated_at, "reason": fail_reason}
            if message:
                results[template_key]["details"] = message
            summary["failed"] += 1

    def update_section_validation(template_key, section, is_valid, reason=None, details=None):
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        if not isinstance(stored_data, dict):
            stored_data = {}
        existing_validated_at = stored_data.get("validated_at") or ""

        if is_valid:
            new_validated_at = utc_now_iso()
            stored_data["validated"] = True
            stored_data["validated_at"] = new_validated_at
            stored_data = apply_validation_metadata(stored_data, "validated")
            database.save_section_data(
                name=config_name,
                section=section,
                validated=True,
                user_entered=user_entered,
                data=stored_data,
            )
            results[template_key] = {"status": "validated", "validated_at": new_validated_at}
            summary["validated"] += 1
            return

        stored_data["validated"] = False
        if existing_validated_at:
            stored_data["validated_at"] = existing_validated_at
        stored_data = apply_validation_metadata(stored_data, "failed", reason=reason, details=details)
        database.save_section_data(
            name=config_name,
            section=section,
            validated=False,
            user_entered=user_entered,
            data=stored_data,
        )
        result = {"status": "failed", "validated_at": existing_validated_at}
        if reason:
            result["reason"] = reason
        if details:
            result["details"] = details
        results[template_key] = result
        summary["failed"] += 1

    def skip_section_validation(template_key, section, reason=None, details=None):
        stored_validated, user_entered, stored_data = database.retrieve_section_data(config_name, section)
        if not isinstance(stored_data, dict):
            stored_data = {}
        existing_validated_at = stored_data.get("validated_at") or ""
        stored_data = apply_validation_metadata(stored_data, "skipped", reason=reason, details=details)
        database.save_section_data(
            name=config_name,
            section=section,
            validated=stored_validated,
            user_entered=user_entered,
            data=stored_data,
        )
        result = {"status": "skipped", "validated_at": existing_validated_at}
        if reason:
            result["reason"] = reason
        if details:
            result["details"] = details
        results[template_key] = result
        summary["skipped"] += 1

    # Bulk validation for libraries
    plex_settings = persistence.retrieve_settings("010-plex") or {}
    plex_is_valid = helpers.booler(plex_settings.get("validated", False)) if isinstance(plex_settings, dict) else False
    if not plex_is_valid:
        skip_section_validation("025-libraries", "libraries", reason="missing_plex_validation")
        skip_section_validation("027-playlist_files", "playlist_files", reason="missing_plex_validation")
    else:
        libraries_settings = persistence.retrieve_settings("025-libraries") or {}
        libraries_data = libraries_settings.get("libraries", {}) if isinstance(libraries_settings, dict) else {}
        selected_library_ids = [
            key[: -len("-library")]
            for key, value in libraries_data.items()
            if isinstance(key, str) and key.startswith(("mov-library_", "sho-library_")) and key.endswith("-library") and not is_blank_value(value)
        ]

        if not selected_library_ids:
            skip_section_validation("025-libraries", "libraries", reason="no_libraries")
        else:
            libraries_reason = None
            path_errors = path_validation.validate_payload(libraries_data)
            if path_errors:
                libraries_reason = "invalid_paths"
            else:
                missing_placeholders = []
                library_names = {}
                for lib_id in selected_library_ids:
                    name = libraries_data.get(f"{lib_id}-library")
                    library_names[lib_id] = name if isinstance(name, str) and name.strip() else lib_id

                def find_library_value(lib_id, suffixes):
                    for suffix in suffixes:
                        direct = f"{lib_id}-{suffix}"
                        if direct in libraries_data:
                            return libraries_data.get(direct)
                    for key, value in libraries_data.items():
                        if not isinstance(key, str) or not key.startswith(f"{lib_id}-"):
                            continue
                        if any(key.endswith(suffix) for suffix in suffixes):
                            return value
                    return None

                for lib_id in selected_library_ids:
                    use_separator = find_library_value(lib_id, ["template_variables[use_separator]", "attribute_use_separator"])
                    if is_blank_value(use_separator) or str(use_separator).strip().lower() == "none":
                        continue
                    placeholder = find_library_value(lib_id, ["attribute_template_variables[placeholder_imdb_id]", "template_variables[placeholder_imdb_id]"])
                    if is_blank_value(placeholder):
                        missing_placeholders.append(library_names.get(lib_id, lib_id))
                if missing_placeholders:
                    libraries_reason = "missing_placeholder_imdb"

            update_section_validation(
                "025-libraries",
                "libraries",
                libraries_reason is None,
                reason=libraries_reason,
                details=missing_placeholders if libraries_reason == "missing_placeholder_imdb" else None,
            )

        playlist_settings = persistence.retrieve_settings("027-playlist_files") or {}
        playlist_payload = playlist_settings.get("playlist_files", {}) if isinstance(playlist_settings, dict) else {}
        if isinstance(playlist_payload, dict) and isinstance(playlist_payload.get("playlist_files"), dict):
            playlist_payload = playlist_payload.get("playlist_files", {})
        libraries_value = ""
        if isinstance(playlist_payload, dict):
            libraries_value = playlist_payload.get("libraries") or ""
        playlist_libraries = [lib.strip() for lib in str(libraries_value).split(",") if lib.strip()]
        if playlist_libraries:
            update_section_validation("027-playlist_files", "playlist_files", True)
        else:
            skip_section_validation("027-playlist_files", "playlist_files", reason="no_libraries")

    # Bulk validation for settings
    settings_settings = persistence.retrieve_settings("150-settings") or {}
    settings_section = settings_settings.get("settings", {}) if isinstance(settings_settings, dict) else {}
    if not isinstance(settings_section, dict) or not settings_section:
        skip_section_validation("150-settings", "settings", reason="missing_settings")
    else:
        invalid_fields = []

        def check_regex(key, pattern, flags=0):
            if key not in settings_section:
                return
            value = settings_section.get(key)
            if value is None:
                return
            if isinstance(value, str) and not value.strip():
                invalid_fields.append(key)
                return
            value_text = str(value).strip()
            if not re.match(pattern, value_text, flags):
                invalid_fields.append(key)

        check_regex("asset_depth", r"^(0|[1-9]\d*)$")
        check_regex("overlay_artwork_quality", r"^(100|[1-9][0-9]?)$")
        check_regex("cache_expiration", r"^[1-9]\d*$")
        check_regex("item_refresh_delay", r"^(0|[1-9]\d*)$")
        check_regex("minimum_items", r"^[1-9]\d*$")
        check_regex("run_again_delay", r"^(0|[1-9]\d*)$")
        check_regex("ignore_ids", r"^(None|\d{1,8}(,\d{1,8})*)$", flags=re.IGNORECASE)
        check_regex("ignore_imdb_ids", r"^(None|tt\d{7,8}(,tt\d{7,8})*)$", flags=re.IGNORECASE)
        check_regex("custom_repo", r"^(None|https?:\/\/[\da-z.-]+\.[a-z.]{2,6}([/\w.-]*)*\/?)$", flags=re.IGNORECASE)

        asset_dirs = settings_section.get("asset_directory") if isinstance(settings_section, dict) else None
        if isinstance(asset_dirs, str):
            asset_dirs = [line.strip() for line in asset_dirs.splitlines() if line.strip()]
        elif isinstance(asset_dirs, list):
            asset_dirs = [str(item).strip() for item in asset_dirs if str(item).strip()]
        else:
            asset_dirs = []

        if asset_dirs:
            md = MultiDict()
            for entry in asset_dirs:
                md.add("asset_directory", entry)
            path_errors = path_validation.validate_payload(md)
            if path_errors:
                invalid_fields.append("asset_directory")

        if invalid_fields:
            update_section_validation("150-settings", "settings", False, reason="invalid_fields")
        else:
            update_section_validation("150-settings", "settings", True)

    # Bulk validation for AniDB
    anidb_settings = persistence.retrieve_settings("100-anidb") or {}
    anidb_data = anidb_settings.get("anidb", {}) if isinstance(anidb_settings, dict) else {}
    anidb_enabled = helpers.booler(anidb_data.get("enable")) if isinstance(anidb_data, dict) else False
    if anidb_enabled:
        update_section_validation("100-anidb", "anidb", True)
    else:
        skip_section_validation("100-anidb", "anidb", reason="disabled")

    # Bulk validation for Webhooks
    webhooks_settings = persistence.retrieve_settings("090-webhooks") or {}
    webhooks_data = webhooks_settings.get("webhooks", {}) if isinstance(webhooks_settings, dict) else {}
    configured_webhooks = False
    if isinstance(webhooks_data, dict):
        for value in webhooks_data.values():
            if is_blank_value(value):
                continue
            configured_webhooks = True
            break
    if configured_webhooks:
        update_section_validation("090-webhooks", "webhooks", True)
    else:
        skip_section_validation("090-webhooks", "webhooks", reason="no_webhooks")

    # Bulk validation for Trakt (token check if present)
    trakt_settings = persistence.retrieve_settings("130-trakt") or {}
    trakt_data = trakt_settings.get("trakt", {}) if isinstance(trakt_settings, dict) else {}
    trakt_auth = trakt_data.get("authorization", {}) if isinstance(trakt_data, dict) else {}
    trakt_access = trakt_auth.get("access_token") if isinstance(trakt_auth, dict) else None
    trakt_client_id = trakt_data.get("client_id") if isinstance(trakt_data, dict) else None
    if is_blank_value(trakt_access) or is_blank_value(trakt_client_id):
        skip_section_validation("130-trakt", "trakt", reason="missing_tokens")
    else:
        try:
            response = requests.get(
                "https://api.trakt.tv/users/settings",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {trakt_access}",
                    "trakt-api-version": "2",
                    "trakt-api-key": trakt_client_id,
                },
                timeout=10,
            )
            if response.status_code == 200:
                update_section_validation("130-trakt", "trakt", True)
            elif response.status_code == 423:
                update_section_validation("130-trakt", "trakt", False, reason="account_locked")
            elif response.status_code in (401, 403):
                update_section_validation("130-trakt", "trakt", False, reason="token_invalid")
            else:
                update_section_validation("130-trakt", "trakt", False, reason="validation_error")
        except requests.exceptions.RequestException:
            update_section_validation("130-trakt", "trakt", False, reason="validation_error")

    # Bulk validation for MAL (token check if present)
    mal_settings = persistence.retrieve_settings("140-mal") or {}
    mal_data = mal_settings.get("mal", {}) if isinstance(mal_settings, dict) else {}
    mal_auth = mal_data.get("authorization", {}) if isinstance(mal_data, dict) else {}
    mal_access = mal_auth.get("access_token") if isinstance(mal_auth, dict) else None
    if is_blank_value(mal_access):
        skip_section_validation("140-mal", "mal", reason="missing_tokens")
    else:
        try:
            response = requests.get(
                "https://api.myanimelist.net/v2/users/@me",
                headers={"Authorization": f"Bearer {mal_access}"},
                timeout=10,
            )
            if response.status_code == 200:
                update_section_validation("140-mal", "mal", True)
            elif response.status_code in (401, 403):
                update_section_validation("140-mal", "mal", False, reason="token_invalid")
            else:
                update_section_validation("140-mal", "mal", False, reason="validation_error")
        except requests.exceptions.RequestException:
            update_section_validation("140-mal", "mal", False, reason="validation_error")

    reason_labels = {
        "missing_credentials": "Missing credentials",
        "missing_plex_validation": "Plex not validated",
        "no_libraries": "No libraries selected",
        "invalid_paths": "Invalid paths",
        "missing_placeholder_imdb": "Missing placeholder IMDb ID",
        "invalid_fields": "Invalid fields",
        "no_webhooks": "No webhooks configured",
        "disabled": "Disabled",
        "missing_settings": "Settings missing",
        "missing_tokens": "Missing tokens",
        "token_invalid": "Invalid tokens",
        "account_locked": "Account locked",
        "validation_error": "Validation error",
    }
    label_map = {}
    try:
        for file, display_name in helpers.get_menu_list():
            label_map[file.rsplit(".", 1)[0]] = display_name
    except Exception:
        label_map = {}

    def label_for_key(key):
        return label_map.get(key, key)

    def format_with_reason(key, result):
        label = label_for_key(key)
        reason = result.get("reason")
        details = result.get("details")
        if not reason:
            return label
        pretty = reason_labels.get(reason, reason.replace("_", " "))
        detail_text = ""
        if isinstance(details, (list, tuple)):
            detail_text = ", ".join(str(item) for item in details if str(item))
        elif details is not None:
            detail_text = str(details)
        if detail_text:
            return f"{label} ({pretty}: {detail_text})"
        return f"{label} ({pretty})"

    failed_keys = [key for key, result in results.items() if result.get("status") == "failed"]
    failed_labels = [format_with_reason(key, results[key]) for key in failed_keys]
    failed_detail = f" Failed: {', '.join(failed_labels)}." if failed_labels else ""
    skipped_keys = [key for key, result in results.items() if result.get("status") == "skipped"]
    skipped_labels = [format_with_reason(key, results[key]) for key in skipped_keys]
    skipped_detail = f" Skipped: {', '.join(skipped_labels)}." if skipped_labels else ""
    ok = summary.get("validated", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    separator = "\u2022"
    summary_text = f"Completed. Validated: {ok} {separator} Failed: {failed} {separator} Skipped: {skipped}."
    summary_updated_at = utc_now_iso()
    summary_payload = {
        "summary_text": summary_text,
        "summary": summary,
        "results": results,
        "updated_at": summary_updated_at,
    }
    database.save_section_data(
        name=config_name,
        section="validation_summary",
        validated=True,
        user_entered=True,
        data=summary_payload,
    )
    return jsonify({"success": True, "results": results, "summary": summary, "summary_text": summary_text, "summary_updated_at": summary_updated_at})


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

        config_path = _extract_kometa_config_path(command_parts, kometa_root)
        _stamp_quickstart_config_marker(config_path, session.get("config_name"))

        helpers.ts_log(f"argv={command_parts!r}", level="DEBUG")

        proc = subprocess.Popen(command_parts, cwd=str(kometa_root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

        with open(helpers.get_kometa_pid_file(), "w", encoding="utf-8") as f:
            f.write(str(proc.pid))

        _schedule_quickstart_run_marker(kometa_root, session.get("config_name"))

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
                started_at_ts = proc.create_time()
                started_at = datetime.fromtimestamp(started_at_ts).isoformat()
                elapsed_seconds = max(0, int(time.time() - started_at_ts))
                cpu_percent = _calculate_process_cpu_percent(proc)
                mem_rss = proc.memory_info().rss
                try:
                    for child in proc.children(recursive=True):
                        try:
                            mem_rss += child.memory_info().rss
                        except Exception:
                            continue
                except Exception:
                    pass
                mem_rss_mb = mem_rss / (1024 * 1024)
                system_cpu_percent = _calculate_system_cpu_percent()
                vm = psutil.virtual_memory()
                system_mem_used_mb = (vm.total - vm.available) / (1024 * 1024)
                system_mem_total_mb = vm.total / (1024 * 1024)
                mem_percent = (mem_rss / vm.total) * 100.0 if vm.total else None
                return jsonify(
                    status="running",
                    pid=pid,
                    started_at=started_at,
                    started_at_ts=started_at_ts,
                    elapsed_seconds=elapsed_seconds,
                    cpu_percent=round(cpu_percent, 1) if cpu_percent is not None else None,
                    memory_rss_mb=round(mem_rss_mb, 1),
                    memory_percent=round(mem_percent, 2) if mem_percent is not None else None,
                    system_cpu_percent=round(system_cpu_percent, 1) if system_cpu_percent is not None else None,
                    system_memory_percent=round(vm.percent, 1),
                    system_memory_used_mb=round(system_mem_used_mb, 1),
                    system_memory_total_mb=round(system_mem_total_mb, 1),
                )
        # If we're here, it likely ended; try to get a return code
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
        KOMETA_CPU_CACHE.pop(pid, None)
        return jsonify(status="done", return_code=rc if rc is not None else -1)
    except psutil.NoSuchProcess:
        KOMETA_CPU_CACHE.pop(pid, None)
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
        stats_param = request.args.get("stats", "")
        include_stats = str(stats_param).lower() in ("1", "true", "yes", "on", "total")
        max_lines = None
        if size_param.lower() not in ("all", "full"):
            try:
                max_lines = max(1, min(int(size_param), 20000))
            except Exception:
                max_lines = 2000

        log_stats = None
        try:
            log_stats = log_path.stat()
        except Exception:
            log_stats = None

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

        def get_log_stats(path):
            try:
                stats = path.stat()
            except Exception:
                return None

            cached = LOG_STATS_CACHE
            if cached.get("mtime") == stats.st_mtime and cached.get("size") == stats.st_size:
                return cached.get("stats")

            counts = {
                "cache": 0,
                "debug": 0,
                "info": 0,
                "warning": 0,
                "error": 0,
                "critical": 0,
                "trace": 0,
            }
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        upper = line.upper()
                        if "FROM CACHE" in upper:
                            counts["cache"] += 1
                        if "[DEBUG]" in upper:
                            counts["debug"] += 1
                        if "[INFO]" in upper:
                            counts["info"] += 1
                        if "[WARNING]" in upper:
                            counts["warning"] += 1
                        if "[ERROR]" in upper:
                            counts["error"] += 1
                        if "[CRITICAL]" in upper:
                            counts["critical"] += 1
                        if "TRACEBACK" in upper:
                            counts["trace"] += 1
            except Exception:
                return None

            LOG_STATS_CACHE.update({"mtime": stats.st_mtime, "size": stats.st_size, "stats": counts})
            return counts

        log_mtime = log_stats.st_mtime if log_stats else None
        log_age_seconds = None
        if log_mtime is not None:
            log_age_seconds = max(0, int(time.time() - log_mtime))

        kometa_started_at = None
        pid = helpers.get_kometa_pid()
        if pid:
            try:
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    cmdline = " ".join(proc.cmdline() or [])
                    if "kometa.py" in cmdline:
                        kometa_started_at = proc.create_time()
            except Exception:
                kometa_started_at = None

        log_is_stale = False
        if log_mtime is not None and kometa_started_at is not None:
            log_is_stale = log_mtime < (kometa_started_at - 30)

        response = {
            "log": log_content,
            "log_mtime": log_mtime,
            "log_age_seconds": log_age_seconds,
            "log_is_stale": log_is_stale,
            "log_path": str(log_path),
        }
        if include_stats:
            stats = get_log_stats(log_path)
            if stats:
                response["stats"] = stats

        return jsonify(response)
    except Exception as e:
        return jsonify({"error": f"Failed to read log: {str(e)}"}), 500


@app.route("/logscan/analyze", methods=["GET"])
def logscan_analyze():
    kometa_root = helpers.get_kometa_root_path()
    log_path = kometa_root / "config" / "logs" / "meta.log"
    config_name = session.get("config_name")
    normalized_name = (config_name or "").strip().lower().replace(" ", "_") or "default"
    config_path = kometa_root / "config" / f"{normalized_name}_config.yml"

    if not log_path.exists():
        return jsonify({"error": f"Log file not found at: {log_path}"}), 404

    try:
        stats = log_path.stat()
    except Exception as e:
        return jsonify({"error": f"Failed to stat log: {str(e)}"}), 500

    cached = LOGSCAN_ANALYSIS_CACHE
    if cached.get("mtime") == stats.st_mtime and cached.get("size") == stats.st_size:
        data = cached.get("data") or {}
        data["cached"] = True
        return jsonify(data)

    analyzer = logscan.LogscanAnalyzer()
    result = analyzer.analyze_log_file(
        log_path,
        config_name=config_name,
        config_path=config_path,
    )
    summary = result.get("summary") if isinstance(result, dict) else None
    if summary:
        is_running = helpers.is_kometa_running()
        has_finish = bool(summary.get("finished_at"))
        run_complete = bool(summary.get("run_complete"))
        can_ingest = run_complete and has_finish and not is_running
        result["ingest_skipped"] = not can_ingest
        if can_ingest:
            ingest_cache = _load_logscan_ingest_cache()
            cache_logs = ingest_cache["logs"]
            cache_key = str(log_path.resolve())
            cached_entry = cache_logs.get(cache_key, {})
            cached_run_key = cached_entry.get("run_key")
            if not (cached_entry.get("run_complete") is True and cached_run_key == summary.get("run_key")):
                database.save_log_run(summary, recommendations=result.get("recommendations"))
            cache_logs[cache_key] = {
                "mtime": stats.st_mtime,
                "size": stats.st_size,
                "run_key": summary.get("run_key"),
                "run_complete": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _save_logscan_ingest_cache(ingest_cache)
            try:
                _archive_rotated_logs(log_path.parent)
            except Exception:
                pass
            if _logscan_needs_reingest(cache_logs, log_path.parent):
                _start_logscan_auto_reingest(log_path.parent)

    LOGSCAN_ANALYSIS_CACHE.update({"mtime": stats.st_mtime, "size": stats.st_size, "data": result})
    result["cached"] = False
    return jsonify(result)


@app.route("/logscan/trends", methods=["GET"])
def logscan_trends():
    try:
        limit = int(request.args.get("limit", "50"))
    except Exception:
        limit = 50
    limit = max(1, min(limit, 500))
    total_runs = database.get_log_runs_count()
    ingest_health = _logscan_ingest_health()
    return jsonify({"runs": database.get_log_runs(limit=limit), "total_runs": total_runs, "ingest_health": ingest_health})


@app.route("/logscan/trends/recommendations", methods=["GET"])
def logscan_trends_recommendations():
    run_key = request.args.get("run_key")
    if not run_key:
        return jsonify({"error": "run_key required"}), 400
    recommendations = database.get_log_run_recommendations(run_key)
    return jsonify({"run_key": run_key, "recommendations": recommendations})


@app.route("/logscan/trends/reset", methods=["POST"])
def logscan_trends_reset():
    database.clear_log_runs()
    _clear_logscan_ingest_cache()
    try:
        missing_log = _get_logscan_cache_dir() / "meta_people_missing.log"
        if missing_log.exists():
            missing_log.unlink()
    except Exception:
        pass
    return jsonify({"success": True})


def _logscan_reingest_snapshot():
    with logscan_reingest_lock:
        return dict(logscan_reingest_state)


def _update_logscan_reingest_state(**updates):
    with logscan_reingest_lock:
        logscan_reingest_state.update(updates)


def _reset_logscan_reingest_state():
    with logscan_reingest_lock:
        logscan_reingest_state.clear()
        logscan_reingest_state.update(
            {
                "status": "idle",
                "job_id": None,
            }
        )


def _get_logscan_cache_dir():
    cache_dir = Path(helpers.CONFIG_DIR) / "cache" / "logscan"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _get_logscan_archive_dir():
    archive_dir = _get_logscan_cache_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def _get_logscan_log_files(log_dir=None, include_archive=True):
    log_dir = Path(log_dir) if log_dir else helpers.get_kometa_root_path() / "config" / "logs"
    archive_dir = _get_logscan_archive_dir() if include_archive else None
    log_files = []
    dirs = [log_dir]
    if include_archive and archive_dir:
        dirs.append(archive_dir)
    for base_dir in dirs:
        if not base_dir.exists():
            continue
        for path in base_dir.glob("*meta*.log*"):
            if not path.is_file():
                continue
            suffixes = [suffix.lower() for suffix in path.suffixes]
            if suffixes and suffixes[-1] in (".gz", ".zip", ".7z"):
                continue
            if ".log" not in path.name.lower():
                continue
            log_files.append(path)

    def _mtime(value):
        try:
            return value.stat().st_mtime
        except Exception:
            return 0

    return sorted({path.resolve() for path in log_files}, key=_mtime)


def _get_logscan_ingest_cache_path():
    return _get_logscan_cache_dir() / "ingest_cache.json"


def _load_logscan_ingest_cache():
    cache_path = _get_logscan_ingest_cache_path()
    if not cache_path.exists():
        return {"version": 1, "logs": {}}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "logs": {}}
    if not isinstance(data, dict):
        return {"version": 1, "logs": {}}
    logs = data.get("logs")
    if not isinstance(logs, dict):
        logs = {}
    data["version"] = data.get("version", 1)
    data["logs"] = logs
    return data


def _save_logscan_ingest_cache(cache):
    if not isinstance(cache, dict):
        return
    if "version" not in cache:
        cache["version"] = 1
    if "logs" not in cache or not isinstance(cache["logs"], dict):
        cache["logs"] = {}
    cache_path = _get_logscan_ingest_cache_path()
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def _clear_logscan_ingest_cache():
    cache_path = _get_logscan_ingest_cache_path()
    try:
        if cache_path.exists():
            cache_path.unlink()
    except Exception:
        pass


def _logscan_needs_reingest(cache_logs, log_dir):
    log_files = _get_logscan_log_files(log_dir=log_dir, include_archive=True)
    for path in log_files:
        entry = cache_logs.get(str(path.resolve()), {})
        if not entry or not entry.get("run_complete"):
            return True
    return False


def _logscan_ingest_health(log_dir=None):
    log_dir = Path(log_dir) if log_dir else helpers.get_kometa_root_path() / "config" / "logs"
    log_dir_exists = log_dir.exists()
    log_files = _get_logscan_log_files(log_dir=log_dir, include_archive=True) if log_dir_exists else []
    ingest_cache = _load_logscan_ingest_cache()
    cache_logs = ingest_cache["logs"]
    missing = []
    incomplete = []
    tracked = 0
    complete = 0
    pending_active = False
    latest_updated = None
    is_running = helpers.is_kometa_running()

    for path in log_files:
        if is_running and path.name.lower() == "meta.log":
            pending_active = True
            continue
        entry = cache_logs.get(str(path.resolve()))
        if not entry:
            missing.append(path.name)
            continue
        tracked += 1
        updated_at = entry.get("updated_at")
        if updated_at and (latest_updated is None or updated_at > latest_updated):
            latest_updated = updated_at
        if entry.get("run_complete"):
            complete += 1
        else:
            incomplete.append(path.name)

    total = len(log_files) - (1 if pending_active else 0)
    if total < 0:
        total = 0
    needs_reingest = bool(missing or incomplete)

    return {
        "source": "health",
        "log_dir_missing": not log_dir_exists,
        "total": total,
        "tracked": tracked,
        "complete": complete,
        "missing": len(missing),
        "incomplete": len(incomplete),
        "missing_sample": missing[:5],
        "incomplete_sample": incomplete[:5],
        "needs_reingest": needs_reingest,
        "pending_active": pending_active,
        "last_updated": latest_updated,
    }


def _start_logscan_auto_reingest(log_dir):
    if logscan_ingest_lock.locked():
        return False

    def _runner():
        _perform_logscan_reingest(reset=False, job_id=None, update_state=False)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    return True


def _archive_log_file(path, archive_dir, log_dir=None):
    try:
        path = Path(path)
        if not path.exists() or not path.is_file():
            return None
        if path.name.lower() == "meta.log":
            return None
        if log_dir and path.resolve().parent != Path(log_dir).resolve():
            return None
        archive_dir = Path(archive_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        src_stats = path.stat()
        dest = archive_dir / path.name
        if dest.exists():
            try:
                dst_stats = dest.stat()
                if dst_stats.st_size == src_stats.st_size and dst_stats.st_mtime == src_stats.st_mtime:
                    path.unlink()
                    return dest
            except Exception:
                pass
            suffix = "".join(path.suffixes)
            base = path.name[: -len(suffix)] if suffix else path.stem
            candidate = archive_dir / f"{base}-{int(src_stats.st_mtime)}-{src_stats.st_size}{suffix}"
            counter = 1
            while candidate.exists():
                candidate = archive_dir / f"{base}-{int(src_stats.st_mtime)}-{src_stats.st_size}-{counter}{suffix}"
                counter += 1
            dest = candidate
        shutil.move(str(path), str(dest))
        return dest
    except Exception:
        return None


def _archive_rotated_logs(log_dir):
    archived = 0
    archive_dir = _get_logscan_archive_dir()
    for path in Path(log_dir).glob("*meta*.log*"):
        if not path.is_file():
            continue
        suffixes = [suffix.lower() for suffix in path.suffixes]
        if suffixes and suffixes[-1] in (".gz", ".zip", ".7z"):
            continue
        if ".log" not in path.name.lower():
            continue
        if path.name.lower() == "meta.log":
            continue
        if _archive_log_file(path, archive_dir, log_dir=log_dir):
            archived += 1
    _prune_logscan_archive(archive_dir)
    return archived


def _prune_logscan_archive(archive_dir):
    keep_limit = app.config.get("QS_KOMETA_LOG_KEEP", 0)
    if keep_limit <= 0:
        return 0
    archive_dir = Path(archive_dir)
    if not archive_dir.exists():
        return 0
    candidates = []
    for path in archive_dir.glob("*meta*.log*"):
        if not path.is_file():
            continue
        suffixes = [suffix.lower() for suffix in path.suffixes]
        if suffixes and suffixes[-1] in (".gz", ".zip", ".7z"):
            continue
        if ".log" not in path.name.lower():
            continue
        candidates.append(path)
    if len(candidates) <= keep_limit:
        return 0
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    to_remove = candidates[keep_limit:]
    removed = 0
    for path in to_remove:
        try:
            path.unlink()
            removed += 1
        except Exception:
            continue
    if removed:
        cache = _load_logscan_ingest_cache()
        logs = cache.get("logs", {})
        changed = False
        for path in to_remove:
            key = str(path.resolve())
            if key in logs:
                logs.pop(key, None)
                changed = True
        if changed:
            cache["logs"] = logs
            _save_logscan_ingest_cache(cache)
    return removed


def _perform_logscan_reingest(reset, job_id=None, update_state=True):
    if not logscan_ingest_lock.acquire(blocking=False):
        message = "Logscan ingest already running."
        if update_state:
            _update_logscan_reingest_state(status="error", error=message, finished_at=datetime.now(timezone.utc).isoformat())
        return {"success": False, "error": message}
    started_at = datetime.now(timezone.utc).isoformat()
    if update_state:
        _update_logscan_reingest_state(
            status="running",
            job_id=job_id,
            started_at=started_at,
            finished_at=None,
            total=0,
            scanned=0,
            ingested=0,
            duplicates=0,
            skipped_incomplete=0,
            skipped_invalid=0,
            errors=0,
            current_file=None,
            missing_people_unique=0,
            missing_people_logs=0,
            missing_people_log_ready=False,
            missing_people_log_lines=0,
            sample_incomplete=[],
            sample_errors=[],
        )

    def _extract_fake_people_header(text, max_lines=200):
        header_lines = []
        for line in text.splitlines():
            header_lines.append(line)
            if "Locating config..." in line:
                break
            if len(header_lines) >= max_lines:
                break
        return "\n".join(header_lines).rstrip()

    try:
        ingest_cache = _load_logscan_ingest_cache()
        cache_dirty = False
        if reset:
            database.clear_log_runs()
            ingest_cache = {"version": 1, "logs": {}}
            _clear_logscan_ingest_cache()
            cache_dirty = True
        cache_logs = ingest_cache["logs"]

        kometa_root = helpers.get_kometa_root_path()
        log_dir = kometa_root / "config" / "logs"
        if not log_dir.exists():
            message = f"Log folder not found at: {log_dir}"
            if update_state:
                _update_logscan_reingest_state(status="error", error=message, finished_at=datetime.now(timezone.utc).isoformat())
            return {"success": False, "error": message}

        log_files = _get_logscan_log_files(log_dir=log_dir, include_archive=True)
        total_files = len(log_files)
        if update_state:
            _update_logscan_reingest_state(total=total_files)

        analyzer = logscan.LogscanAnalyzer()
        if log_files:
            analyzer.preload_people_index(log_files[0])
        ingested = 0
        duplicates = 0
        skipped_incomplete = 0
        skipped_invalid = 0
        errors = 0
        missing_people_unique = set()
        missing_people_logs = 0
        missing_people_blocks = []
        missing_people_seen_blocks = set()
        missing_people_seen_names = set()
        missing_people_header = None
        sample_incomplete = []
        sample_errors = []

        archive_dir = _get_logscan_archive_dir()
        for idx, path in enumerate(log_files, start=1):
            if update_state:
                _update_logscan_reingest_state(current_file=path.name, scanned=max(0, idx - 1))
            try:
                stats = path.stat()
                cache_key = str(path.resolve())
                cached_entry = cache_logs.get(cache_key, {})
                cached_run_key = cached_entry.get("run_key")
                skip_save_if_cached = cached_entry.get("run_complete") is True and cached_run_key

                content = path.read_text(encoding="utf-8", errors="replace")
                result = analyzer.analyze_content(
                    content,
                    log_path=path,
                    include_people_scan=True,
                )
                summary = result.get("summary") if isinstance(result, dict) else None
                if not summary:
                    skipped_invalid += 1
                    continue
                if not summary.get("run_complete"):
                    skipped_incomplete += 1
                    if len(sample_incomplete) < 5:
                        sample_incomplete.append(path.name)
                    cache_logs[cache_key] = {
                        "mtime": stats.st_mtime,
                        "size": stats.st_size,
                        "run_key": summary.get("run_key"),
                        "run_complete": False,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    cache_dirty = True
                    continue
                missing_people = result.get("missing_people") if isinstance(result, dict) else None
                if missing_people:
                    missing_people_logs += 1
                    missing_people_unique.update({name.lower() for name in missing_people})
                    if missing_people_header is None:
                        missing_people_header = _extract_fake_people_header(content)
                people_items = analyzer.collect_missing_people_lines(content, available_index=analyzer._people_index)
                if people_items:
                    for item in people_items:
                        names = {name for name in item.get("names", set()) if name in missing_people_unique}
                        if not names:
                            continue
                        if names.issubset(missing_people_seen_names):
                            continue
                        block = item.get("block")
                        if block and block not in missing_people_seen_blocks:
                            missing_people_blocks.append(block)
                            missing_people_seen_blocks.add(block)
                        missing_people_seen_names.update(names)
                if skip_save_if_cached and cached_run_key == summary.get("run_key"):
                    duplicates += 1
                else:
                    if database.save_log_run(summary, recommendations=result.get("recommendations")):
                        ingested += 1
                    else:
                        duplicates += 1
                cache_logs[cache_key] = {
                    "mtime": stats.st_mtime,
                    "size": stats.st_size,
                    "run_key": summary.get("run_key"),
                    "run_complete": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                cache_dirty = True
                if path.parent.resolve() == log_dir.resolve():
                    archived_path = _archive_log_file(path, archive_dir, log_dir=log_dir)
                    if archived_path:
                        try:
                            archived_stats = archived_path.stat()
                            cache_logs[str(archived_path.resolve())] = {
                                "mtime": archived_stats.st_mtime,
                                "size": archived_stats.st_size,
                                "run_key": summary.get("run_key"),
                                "run_complete": True,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                            cache_dirty = True
                        except Exception:
                            pass
            except Exception as exc:
                errors += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"{path.name}: {exc}")
            if update_state:
                _update_logscan_reingest_state(
                    scanned=idx,
                    ingested=ingested,
                    duplicates=duplicates,
                    skipped_incomplete=skipped_incomplete,
                    skipped_invalid=skipped_invalid,
                    errors=errors,
                    missing_people_unique=len(missing_people_unique),
                    missing_people_logs=missing_people_logs,
                    sample_incomplete=sample_incomplete,
                    sample_errors=sample_errors,
                )

        cache_dir = _get_logscan_cache_dir()
        missing_people_log = cache_dir / "meta_people_missing.log"
        missing_people_meta = cache_dir / "meta_people_missing.json"
        missing_people_log_ready = False
        missing_people_log_lines = 0
        if missing_people_blocks:
            try:
                missing_people_log_lines = sum(len(block.splitlines()) for block in missing_people_blocks)
                output_parts = []
                if missing_people_header:
                    output_parts.append(missing_people_header)
                    missing_people_log_lines += len(missing_people_header.splitlines())
                output_parts.extend(missing_people_blocks)
                missing_people_log.write_text("\n".join(output_parts).rstrip() + "\n", encoding="utf-8")
                missing_people_log_ready = True
                try:
                    missing_people_meta.write_text(
                        json.dumps(
                            {
                                "missing_people_unique": len(missing_people_unique),
                                "missing_people_logs": missing_people_logs,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            },
                            ensure_ascii=True,
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                except Exception:
                    pass
            except Exception as exc:
                errors += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"{missing_people_log.name}: {exc}")
        else:
            try:
                if missing_people_log.exists():
                    missing_people_log.unlink()
                if missing_people_meta.exists():
                    missing_people_meta.unlink()
            except Exception:
                pass

        result = {
            "success": True,
            "scanned": len(log_files),
            "ingested": ingested,
            "duplicates": duplicates,
            "skipped_incomplete": skipped_incomplete,
            "skipped_invalid": skipped_invalid,
            "errors": errors,
            "missing_people_unique": len(missing_people_unique),
            "missing_people_logs": missing_people_logs,
            "missing_people_log_ready": missing_people_log_ready,
            "missing_people_log_lines": missing_people_log_lines,
            "sample_incomplete": sample_incomplete,
            "sample_errors": sample_errors,
        }
        if update_state:
            _update_logscan_reingest_state(
                status="complete",
                finished_at=datetime.now(timezone.utc).isoformat(),
                current_file=None,
                **result,
            )
        if cache_dirty:
            _save_logscan_ingest_cache(ingest_cache)
        return result
    finally:
        logscan_ingest_lock.release()


def _run_logscan_reingest_job(job_id, reset):
    try:
        with app.app_context():
            _perform_logscan_reingest(reset=reset, job_id=job_id, update_state=True)
    except Exception as exc:
        _update_logscan_reingest_state(
            status="error",
            error=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
            current_file=None,
        )


@app.route("/logscan/trends/reingest/status", methods=["GET"])
def logscan_trends_reingest_status():
    job_id = request.args.get("job")
    snapshot = _logscan_reingest_snapshot()
    if not snapshot or snapshot.get("status") == "idle":
        return jsonify({"status": "idle"})
    if job_id and snapshot.get("job_id") != job_id:
        return jsonify({"status": "idle"}), 404
    return jsonify(snapshot)


@app.route("/logscan/trends/reingest", methods=["POST"])
def logscan_trends_reingest():
    data = request.get_json(silent=True) or {}
    reset = data.get("reset") is True
    background = data.get("background") is True
    if logscan_ingest_lock.locked():
        return jsonify({"error": "Reingest already running."}), 409
    if background:
        snapshot = _logscan_reingest_snapshot()
        if snapshot.get("status") == "running":
            return (
                jsonify(
                    {
                        "error": "Reingest already running.",
                        "job_id": snapshot.get("job_id"),
                        "status": snapshot.get("status"),
                    }
                ),
                409,
            )
        job_id = secrets.token_urlsafe(8)
        _update_logscan_reingest_state(
            status="running",
            job_id=job_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            total=0,
            scanned=0,
            ingested=0,
            duplicates=0,
            skipped_incomplete=0,
            skipped_invalid=0,
            errors=0,
            current_file=None,
            missing_people_unique=0,
            missing_people_logs=0,
            missing_people_log_ready=False,
            missing_people_log_lines=0,
            sample_incomplete=[],
            sample_errors=[],
        )
        thread = threading.Thread(target=_run_logscan_reingest_job, args=(job_id, reset), daemon=True)
        thread.start()
        return jsonify({"success": True, "job_id": job_id, "status": "running"})

    result = _perform_logscan_reingest(reset=reset, job_id=None, update_state=True)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code


@app.route("/logscan-trends", methods=["GET"])
def logscan_trends_page():
    persistence.ensure_session_config_name()
    if "shutdown_nonce" not in session:
        session["shutdown_nonce"] = secrets.token_urlsafe(16)

    page_info = {
        "title": "Analytics",
        "template_name": "905-analytics",
        "config_name": session.get("config_name"),
        "running_port": running_port,
        "qs_debug": app.config["QS_DEBUG"],
        "qs_theme": app.config.get("QS_THEME", "kometa"),
        "qs_optimize_defaults": app.config.get("QS_OPTIMIZE_DEFAULTS", True),
        "qs_config_history": app.config.get("QS_CONFIG_HISTORY", 0),
        "qs_kometa_log_keep": app.config.get("QS_KOMETA_LOG_KEEP", 0),
        "qs_session_lifetime_days": app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
        "qs_flask_session_dir": app.config.get("QS_FLASK_SESSION_DIR", ""),
        "shutdown_nonce": session["shutdown_nonce"],
        "hide_step_nav": False,
    }

    template_list = helpers.get_menu_list()
    step_templates = helpers.get_template_list()
    _, num, _ = helpers.get_bits(page_info["template_name"])
    item = step_templates.get(num)
    if item:
        page_info["next_page"] = item["next"]
        page_info["prev_page"] = item["prev"]
        if page_info["next_page"]:
            next_num = page_info["next_page"].split("-")[0]
            page_info["next_page_name"] = step_templates.get(next_num, {}).get("name", "Next")
        else:
            page_info["next_page_name"] = "Next"

        if page_info["prev_page"]:
            prev_num = page_info["prev_page"].split("-")[0]
            page_info["prev_page_name"] = step_templates.get(prev_num, {}).get("name", "Previous")
        else:
            page_info["prev_page_name"] = "Previous"

    progress_excludes = {"sponsor", "analytics"}
    progress_keys = [key for key in step_templates if step_templates[key].get("raw_name") not in progress_excludes]
    total_steps = len(progress_keys)
    if num in progress_keys and total_steps:
        progress_index = progress_keys.index(num)
    else:
        progress_index = max(total_steps - 1, 0)
    page_info["progress"] = round(((progress_index + 1) / total_steps) * 100) if total_steps else 0
    available_configs = database.get_unique_config_names() or []
    return render_template(
        "905-analytics.html",
        page_info=page_info,
        template_list=template_list,
        available_configs=available_configs,
    )


@app.route("/logscan/trends/preferences", methods=["GET"])
def logscan_trends_preferences():
    config_name = request.args.get("config_name", "").strip() or "all"
    preferences = database.get_analytics_preferences(config_name)
    return jsonify({"success": True, "config_name": config_name, "preferences": preferences})


@app.route("/logscan/trends/preferences", methods=["POST"])
def logscan_trends_preferences_update():
    payload = request.get_json(silent=True) or {}
    config_name = str(payload.get("config_name", "")).strip() or "all"
    preferences = payload.get("preferences")
    saved = database.save_analytics_preferences(config_name, preferences)
    result = database.get_analytics_preferences(config_name)
    status_code = 200 if saved else 400
    return jsonify({"success": saved, "config_name": config_name, "preferences": result}), status_code


@app.route("/logscan/trends/people-missing", methods=["GET"])
def logscan_trends_people_missing():
    missing_log = _get_logscan_cache_dir() / "meta_people_missing.log"
    if not missing_log.exists():
        return jsonify({"error": "Missing people log not found."}), 404
    return send_file(
        missing_log,
        mimetype="text/plain",
        as_attachment=True,
        download_name="meta_people_missing.log",
    )


@app.route("/logscan/trends/people-missing/status", methods=["GET"])
def logscan_trends_people_missing_status():
    cache_dir = _get_logscan_cache_dir()
    missing_log = cache_dir / "meta_people_missing.log"
    if not missing_log.exists():
        return jsonify({"exists": False, "missing_people_unique": 0})
    meta_path = cache_dir / "meta_people_missing.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    return jsonify(
        {
            "exists": True,
            "missing_people_unique": meta.get("missing_people_unique"),
            "updated_at": meta.get("updated_at"),
        }
    )


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
    python_version = platform.python_version() or sys.version.split()[0]
    git_version = "Unavailable"
    git_path = shutil.which("git")
    if git_path:
        try:
            git_result = subprocess.run(
                [git_path, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            git_output = (git_result.stdout or git_result.stderr or "").strip()
            if git_output:
                git_version = git_output
        except Exception:
            git_version = "Unavailable"

    ua = request.user_agent
    browser_name = ua.browser or ""
    browser_version = ua.version or ""
    browser_platform = ua.platform or ""
    browser_line = browser_name
    if browser_name:
        if browser_version:
            browser_line = f"{browser_line} {browser_version}"
        if browser_platform:
            browser_line = f"{browser_line} ({browser_platform})"
    else:
        browser_line = request.headers.get("User-Agent", "") or session.get("qs_user_agent_raw") or session.get("qs_user_agent") or "Unknown"

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
    lines.append(f"# Python: {python_version}")
    lines.append(f"# Git: {git_version}")
    lines.append(f"# Browser: {browser_line}")
    lines.extend(helpers.get_quickstart_settings_summary())
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

    lines.append("# Quickstart log tail (last 200 lines)")
    lines.append("")

    text = "\n".join(lines + log_lines)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"text": text, "generated_at": generated_at})


@app.route("/update-quickstart-settings", methods=["POST"])
def update_quickstart_settings():
    data = request.get_json(silent=True) or {}
    errors = []
    restart_required = False
    changes_applied = False
    theme_changed = False

    allowed_themes = {
        "kometa",
        "dark",
        "plex",
        "jellyfin",
        "emby",
        "seerr",
        "mind",
        "power",
        "reality",
        "soul",
        "space",
        "time",
    }

    new_port = None
    if "port" in data:
        try:
            new_port = int(str(data.get("port", "")).strip())
        except (TypeError, ValueError):
            new_port = None
        if not new_port or new_port < 1 or new_port > 65535:
            errors.append("Port must be a number between 1 and 65535.")

    debug_raw = data.get("debug")
    debug_value = None
    if debug_raw is not None:
        debug_value = helpers.booler(str(debug_raw))

    optimize_raw = data.get("optimize_defaults")
    optimize_value = None
    if optimize_raw is not None:
        optimize_value = helpers.booler(str(optimize_raw))

    history_raw = data.get("config_history")
    history_value = None
    if history_raw is not None:
        try:
            history_value = int(str(history_raw).strip())
        except (TypeError, ValueError):
            errors.append("Config history must be a non-negative number.")
            history_value = None
        if history_value is not None and history_value < 0:
            errors.append("Config history must be a non-negative number.")

    log_keep_raw = data.get("kometa_log_keep")
    log_keep_value = None
    if log_keep_raw is not None:
        try:
            log_keep_value = int(str(log_keep_raw).strip())
        except (TypeError, ValueError):
            errors.append("Kometa log retention must be a non-negative number.")
            log_keep_value = None
        if log_keep_value is not None and log_keep_value < 0:
            errors.append("Kometa log retention must be a non-negative number.")

    session_lifetime_raw = data.get("session_lifetime_days")
    session_lifetime_value = None
    if session_lifetime_raw is not None:
        try:
            session_lifetime_value = int(str(session_lifetime_raw).strip())
        except (TypeError, ValueError):
            errors.append("Session lifetime must be a positive number of days.")
            session_lifetime_value = None
        if session_lifetime_value is not None and session_lifetime_value < 1:
            errors.append("Session lifetime must be at least 1 day.")

    session_dir_raw = data.get("session_dir")
    session_dir_value = None
    if session_dir_raw is not None:
        session_dir_value = str(session_dir_raw).strip()

    regenerate_secret = data.get("regenerate_secret") is True

    theme_raw = data.get("theme")
    theme_value = None
    if theme_raw is not None:
        theme_value = str(theme_raw).strip().lower()
        if not theme_value:
            theme_value = "kometa"
        if theme_value not in allowed_themes:
            errors.append("Theme must be one of: " + ", ".join(sorted(allowed_themes)) + ".")

    if errors:
        return jsonify(success=False, message=" ".join(errors)), 400

    if new_port and new_port != running_port:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sock.connect_ex(("localhost", new_port)) == 0:
                return jsonify(success=False, message=f"Port {new_port} is already in use."), 409
        finally:
            sock.close()

        helpers.update_env_variable("QS_PORT", str(new_port))
        app.config["QS_PORT"] = new_port
        restart_required = True
        changes_applied = True

    if debug_value is not None and debug_value != app.config["QS_DEBUG"]:
        helpers.update_env_variable("QS_DEBUG", "1" if debug_value else "0")
        app.config["QS_DEBUG"] = debug_value
        changes_applied = True

    if theme_value and theme_value != app.config.get("QS_THEME", "kometa"):
        helpers.update_env_variable("QS_THEME", theme_value)
        app.config["QS_THEME"] = theme_value
        changes_applied = True
        theme_changed = True

    if optimize_value is not None and optimize_value != app.config.get("QS_OPTIMIZE_DEFAULTS", True):
        helpers.update_env_variable("QS_OPTIMIZE_DEFAULTS", "1" if optimize_value else "0")
        app.config["QS_OPTIMIZE_DEFAULTS"] = optimize_value
        changes_applied = True

    if history_value is not None and history_value != app.config.get("QS_CONFIG_HISTORY", 0):
        helpers.update_env_variable("QS_CONFIG_HISTORY", str(history_value))
        app.config["QS_CONFIG_HISTORY"] = history_value
        changes_applied = True

    if log_keep_value is not None and log_keep_value != app.config.get("QS_KOMETA_LOG_KEEP", 0):
        helpers.update_env_variable("QS_KOMETA_LOG_KEEP", str(log_keep_value))
        app.config["QS_KOMETA_LOG_KEEP"] = log_keep_value
        changes_applied = True

    if session_lifetime_value is not None and session_lifetime_value != app.config.get("QS_SESSION_LIFETIME_DAYS", 30):
        helpers.update_env_variable("QS_SESSION_LIFETIME_DAYS", str(session_lifetime_value))
        app.config["QS_SESSION_LIFETIME_DAYS"] = session_lifetime_value
        app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=session_lifetime_value)
        cache_dir = app.config.get("QS_FLASK_SESSION_DIR", flask_cache_dir)
        app.config["SESSION_CACHELIB"] = FileSystemCache(
            cache_dir=cache_dir,
            threshold=500,
            default_timeout=int(timedelta(days=session_lifetime_value).total_seconds()),
        )
        changes_applied = True

    if session_dir_value is not None:
        default_session_dir = os.path.abspath(os.path.expanduser(os.path.join(helpers.CONFIG_DIR, "flask_session")))
        desired_session_dir = os.path.abspath(os.path.expanduser(session_dir_value or default_session_dir))
        current_session_dir = app.config.get("QS_FLASK_SESSION_DIR", default_session_dir)
        if desired_session_dir != current_session_dir:
            try:
                os.makedirs(desired_session_dir, exist_ok=True)
            except Exception:
                return jsonify(success=False, message="Failed to create the session storage directory."), 500
            helpers.update_env_variable("QS_FLASK_SESSION_DIR", desired_session_dir)
            app.config["QS_FLASK_SESSION_DIR"] = desired_session_dir
            app.config["SESSION_CACHELIB"] = FileSystemCache(
                cache_dir=desired_session_dir,
                threshold=500,
                default_timeout=int(timedelta(days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30)).total_seconds()),
            )
            changes_applied = True

    if regenerate_secret:
        new_secret = secrets.token_hex(32)
        helpers.update_env_variable("QS_SECRET_KEY", new_secret)
        app.config["SECRET_KEY"] = new_secret
        app.secret_key = new_secret
        try:
            with open(os.path.join(helpers.CONFIG_DIR, ".secret_key"), "w", encoding="utf-8") as handle:
                handle.write(new_secret)
        except Exception:
            pass
        changes_applied = True

    if not changes_applied:
        return jsonify(
            success=True,
            message="No changes applied.",
            restart=False,
            theme=app.config.get("QS_THEME", "kometa"),
            optimize_defaults=app.config.get("QS_OPTIMIZE_DEFAULTS", True),
            config_history=app.config.get("QS_CONFIG_HISTORY", 0),
            kometa_log_keep=app.config.get("QS_KOMETA_LOG_KEEP", 0),
            session_lifetime_days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
            session_dir=app.config.get("QS_FLASK_SESSION_DIR", ""),
        )

    if restart_required:
        return jsonify(
            success=True,
            message="Settings updated. Restarting Quickstart...",
            restart=True,
            new_port=new_port or running_port,
            theme=app.config.get("QS_THEME", "kometa"),
            theme_changed=theme_changed,
            optimize_defaults=app.config.get("QS_OPTIMIZE_DEFAULTS", True),
            config_history=app.config.get("QS_CONFIG_HISTORY", 0),
            kometa_log_keep=app.config.get("QS_KOMETA_LOG_KEEP", 0),
            session_lifetime_days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
            session_dir=app.config.get("QS_FLASK_SESSION_DIR", ""),
        )

    return jsonify(
        success=True,
        message="Settings updated.",
        restart=False,
        theme=app.config.get("QS_THEME", "kometa"),
        theme_changed=theme_changed,
        optimize_defaults=app.config.get("QS_OPTIMIZE_DEFAULTS", True),
        config_history=app.config.get("QS_CONFIG_HISTORY", 0),
        kometa_log_keep=app.config.get("QS_KOMETA_LOG_KEEP", 0),
        session_lifetime_days=app.config.get("QS_SESSION_LIFETIME_DAYS", 30),
        session_dir=app.config.get("QS_FLASK_SESSION_DIR", ""),
    )


@app.route("/header-style-preview", methods=["GET"])
def header_style_preview():
    font = str(request.args.get("font", "") or "").strip()
    available_fonts = helpers.get_pyfiglet_fonts()
    if not font:
        font = "standard"
    if font not in available_fonts:
        return jsonify(success=False, message="Unknown header style."), 404

    preview = _render_header_style_preview(font)

    return jsonify(success=True, font=font, preview=preview)


@app.route("/header-style-previews", methods=["POST"])
def header_style_previews():
    data = request.get_json(silent=True) or {}
    fonts = data.get("fonts") or []
    if not isinstance(fonts, list):
        return jsonify(success=False, message="Fonts must be a list."), 400

    available = set(helpers.get_pyfiglet_fonts())
    previews = []
    for font in fonts:
        font_name = str(font or "").strip()
        if not font_name or font_name not in available:
            continue
        previews.append({"font": font_name, "preview": _render_header_style_preview(font_name)})

    return jsonify(success=True, previews=previews)


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

    try:
        yaml_parser = YAML(typ="safe")
        with src_yaml.open("r", encoding="utf-8") as f:
            parsed_config = yaml_parser.load(f) or {}
        font_refs = helpers.collect_font_references(parsed_config)
        if font_refs:
            font_result = helpers.copy_fonts_to_kometa(font_refs, kometa_root=p)
            copied = font_result.get("copied", [])
            missing = font_result.get("missing", [])
            errors = font_result.get("errors", [])
            if copied:
                log(f"✅ Synced {len(copied)} font(s) referenced in the config to Kometa config/fonts.")
            if missing:
                log(f"⚠️ Fonts referenced in the config not found: {', '.join(missing)}")
            for err in errors:
                log(f"⚠️ {err}")
    except Exception as e:
        log(f"⚠️ Failed to sync fonts referenced in the config: {e}")

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
        force_update = helpers.booler(data.get("force", False))

        logs.append(f"🔎 Quickstart branch: {qs_branch}")
        logs.append(f"⚙️ Kometa branch selected: {kometa_branch} (ZIP mode)")
        if force_update:
            logs.append("Force update enabled.")

        result = helpers.perform_kometa_update_zip_only(cfg_dir, branch=kometa_branch, force=force_update)
        logs.extend(result.get("log", []))
        status = 200 if result.get("success") else 500

        return (
            jsonify(
                {
                    "success": result.get("success", False),
                    "log": logs,
                    "qs_branch": qs_branch,
                    "kometa_branch": kometa_branch,
                    "up_to_date": result.get("up_to_date", False),
                    "skipped": result.get("skipped", False),
                    "force": force_update,
                }
            ),
            status,
        )

    except Exception as e:
        logs.append(f"Exception during Kometa update: {e}")
        return jsonify({"success": False, "log": logs}), 500


def _normalize_test_libraries_path(raw_path, base_dir):
    value = str(raw_path or "").strip().strip('"').strip("'")
    if not value:
        return ""
    value = os.path.expandvars(value)
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.abspath(os.path.join(base_dir, value))
    return os.path.abspath(value)


def _resolve_test_libraries_paths(quickstart_root):
    base_config_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else quickstart_root
    default_final = os.path.join(base_config_dir, "config", "plex_test_libraries")
    default_tmp = os.path.join(base_config_dir, "config", "tmp")
    raw_final = app.config.get("QS_TEST_LIBS_PATH") or os.getenv("QS_TEST_LIBS_PATH") or default_final
    raw_tmp = app.config.get("QS_TEST_LIBS_TMP") or os.getenv("QS_TEST_LIBS_TMP") or default_tmp
    final_path = _normalize_test_libraries_path(raw_final, base_config_dir) or os.path.abspath(default_final)
    tmp_path = _normalize_test_libraries_path(raw_tmp, base_config_dir) or os.path.abspath(default_tmp)
    return base_config_dir, final_path, tmp_path, default_final, default_tmp


def _test_libraries_present(path):
    if not path or not os.path.isdir(path):
        return False
    expected_dirs = [
        os.path.join(path, "test_tv_lib"),
        os.path.join(path, "test_movie_lib"),
    ]
    marker = os.path.join(path, ".test_libraries_version")
    return all(os.path.isdir(p) for p in expected_dirs) or os.path.exists(marker)


def _paths_overlap(path_a, path_b):
    if not path_a or not path_b:
        return False
    try:
        common = os.path.commonpath([os.path.abspath(path_a), os.path.abspath(path_b)])
    except ValueError:
        return False
    return common == os.path.abspath(path_a) or common == os.path.abspath(path_b)


def _ensure_rw_dir(path):
    if not path:
        return False, "Path is empty."
    if os.path.exists(path) and not os.path.isdir(path):
        return False, "Path exists but is not a directory."
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        return False, f"Unable to create folder: {path} ({e})"
    test_file = os.path.join(path, f".qs_write_test_{uuid.uuid4().hex}")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        return False, f"Unable to write to folder: {path} ({e})"
    return True, ""


def _safe_to_replace_test_libraries(path):
    if not path:
        return False
    if not os.path.exists(path):
        return True
    if _test_libraries_present(path):
        return True
    if os.path.isdir(path) and not os.listdir(path):
        return True
    return False


@app.route("/check-test-libraries", methods=["POST"])
def check_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, _, _, _ = _resolve_test_libraries_paths(quickstart_root)
    resolved_path = os.path.abspath(target_path)

    found = _test_libraries_present(target_path)
    target_exists = os.path.exists(target_path)
    unrecognized = bool(target_exists and not found)

    local_sha = ""
    remote_sha = ""
    is_outdated = False

    if found:
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
            "found": bool(found),
            "target_path": resolved_path,
            "is_outdated": is_outdated,
            "local_sha": local_sha,
            "remote_sha": remote_sha,
            "target_exists": target_exists,
            "unrecognized": unrecognized,
        }
    )


@app.route("/test-libraries-settings", methods=["POST"])
def update_test_libraries_settings():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    temp_raw = data.get("temp_path", "")
    final_raw = data.get("final_path", "")
    confirm = helpers.booler(str(data.get("confirm", "")))

    path_errors = path_validation.validate_payload(
        {
            "temp_path": temp_raw,
            "final_path": final_raw,
        }
    )
    if path_errors:
        return jsonify(success=False, message="Invalid path values: " + " ".join(path_errors)), 400

    base_config_dir, _, _, default_final, default_tmp = _resolve_test_libraries_paths(quickstart_root)
    temp_path = _normalize_test_libraries_path(temp_raw or default_tmp, base_config_dir)
    final_path = _normalize_test_libraries_path(final_raw or default_final, base_config_dir)

    if not temp_path or not final_path:
        return jsonify(success=False, message="Temp and final paths are required."), 400

    if _paths_overlap(temp_path, final_path):
        return jsonify(success=False, message="Temp and final paths must be different and cannot be nested."), 400

    ok, msg = _ensure_rw_dir(temp_path)
    if not ok:
        return jsonify(success=False, message=msg), 400
    ok, msg = _ensure_rw_dir(final_path)
    if not ok:
        return jsonify(success=False, message=msg), 400

    old_final = _normalize_test_libraries_path(app.config.get("QS_TEST_LIBS_PATH") or default_final, base_config_dir)
    old_has_libs = _test_libraries_present(old_final)
    if old_final and final_path != old_final and old_has_libs and not confirm:
        return (
            jsonify(
                success=False,
                needs_confirm=True,
                message=f"Test libraries exist at the previous path: {old_final}. Quickstart will not move them.",
                old_path=old_final,
            ),
            409,
        )

    final_has_content = False
    if os.path.isdir(final_path):
        try:
            final_has_content = any(os.scandir(final_path))
        except Exception:
            final_has_content = True
    final_is_test_libs = _test_libraries_present(final_path)
    if final_has_content and not final_is_test_libs and not confirm:
        return (
            jsonify(
                success=False,
                needs_confirm=True,
                message=f"The final path is not empty and does not look like test libraries: {final_path}. Quickstart will replace this folder during install/update.",
                final_path=final_path,
            ),
            409,
        )

    helpers.update_env_variable("QS_TEST_LIBS_TMP", temp_path)
    helpers.update_env_variable("QS_TEST_LIBS_PATH", final_path)
    os.environ["QS_TEST_LIBS_TMP"] = temp_path
    os.environ["QS_TEST_LIBS_PATH"] = final_path
    app.config["QS_TEST_LIBS_TMP"] = temp_path
    app.config["QS_TEST_LIBS_PATH"] = final_path

    return jsonify(
        success=True,
        message="Test library paths saved.",
        temp_path=temp_path,
        final_path=final_path,
        old_path=old_final if old_final and final_path != old_final else "",
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

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, tmp_root, _, _ = _resolve_test_libraries_paths(quickstart_root)
    resolved_path = os.path.abspath(target_path)
    if _paths_overlap(tmp_root, target_path):
        return jsonify(success=False, message="Temp and final paths must be different and cannot be nested.")
    if not _safe_to_replace_test_libraries(target_path):
        return jsonify(
            success=False,
            message="Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.",
        )

    # Ensure CLONE_PROGRESS dict exists
    try:
        _ = CLONE_PROGRESS
    except NameError:
        # Create if missing (keeps function drop-in friendly)
        globals()["CLONE_PROGRESS"] = {}
    # If a job is already running, return it so other clients can follow along
    active_job_id = ACTIVE_TEST_LIB_JOB.get("job_id")
    if active_job_id:
        info = CLONE_PROGRESS.get(active_job_id) or {}
        phase = info.get("phase")
        if phase and phase not in ["done", "error"]:
            return jsonify(success=True, job_id=active_job_id, existing_job=True, started_at=ACTIVE_TEST_LIB_JOB.get("started_at"))
        ACTIVE_TEST_LIB_JOB.clear()
    job_id = str(uuid.uuid4())
    CLONE_PROGRESS[job_id] = {"phase": "queued", "pct": 0, "text": "Queued..."}
    ACTIVE_TEST_LIB_JOB["job_id"] = job_id
    ACTIVE_TEST_LIB_JOB["started_at"] = time.time()

    def worker():
        zip_url = "https://github.com/chazlarson/plex-test-libraries/archive/refs/heads/main.zip"
        commit_sha = ""
        estimated_total = 0
        estimated = False
        estimated_note = ""
        fallback_total = 5 * 1024 * 1024 * 1024  # 5 GiB

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
            if not total_size:
                try:
                    release_info = requests.get(
                        "https://api.github.com/repos/chazlarson/plex-test-libraries/releases/latest",
                        timeout=5,
                    ).json()
                    assets = release_info.get("assets") or []
                    release_zip = next(
                        (a for a in assets if str(a.get("name", "")).lower().endswith(".zip")),
                        None,
                    )
                    if release_zip and int(release_zip.get("size", 0) or 0) > 0:
                        estimated_total = int(release_zip.get("size", 0) or 0)
                        total_size = estimated_total
                        estimated = True
                        estimated_note = "release"
                except Exception:
                    estimated_total = 0
                    estimated = False
            if not total_size:
                try:
                    repo_info = requests.get(
                        "https://api.github.com/repos/chazlarson/plex-test-libraries",
                        timeout=5,
                    ).json()
                    size_kb = int(repo_info.get("size", 0) or 0)
                    if size_kb > 0:
                        estimated_total = size_kb * 1024
                        total_size = estimated_total
                        estimated = True
                        estimated_note = "repo"
                except Exception:
                    estimated_total = 0
                    estimated = False
            if not total_size or (estimated and total_size < fallback_total):
                total_size = fallback_total
                estimated = True
                estimated_note = "fallback"

            CLONE_PROGRESS[job_id] = {
                "phase": "download",
                "pct": 0 if total_size else None,  # None => indeterminate until we know size
                "text": "Downloading zip…",
                "downloaded": 0,
                "total": total_size,
                "estimated": estimated,
                "estimated_note": estimated_note,
            }

            ok, msg = _ensure_rw_dir(tmp_root)
            if not ok:
                raise RuntimeError(msg)
            # Clean only our own stale temp folders
            try:
                for entry in os.listdir(tmp_root):
                    if entry.startswith("qs_test_libs_"):
                        shutil.rmtree(os.path.join(tmp_root, entry), ignore_errors=True)
            except Exception:
                pass

            with tempfile.TemporaryDirectory(prefix="qs_test_libs_", dir=tmp_root) as tmpdir:
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
                            if total_size:
                                estimated = False
                                CLONE_PROGRESS[job_id]["estimated"] = False
                                CLONE_PROGRESS[job_id]["estimated_note"] = ""
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
                                    "estimated": estimated,
                                    "estimated_note": estimated_note,
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
                    if not _safe_to_replace_test_libraries(target_path):
                        raise RuntimeError("Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.")
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
                if ACTIVE_TEST_LIB_JOB.get("job_id") == job_id:
                    ACTIVE_TEST_LIB_JOB.clear()

        except Exception as e:
            CLONE_PROGRESS[job_id] = {
                "phase": "error",
                "pct": 0,
                "text": f"Error: {str(e)}",
            }
            if ACTIVE_TEST_LIB_JOB.get("job_id") == job_id:
                ACTIVE_TEST_LIB_JOB.clear()

    threading.Thread(target=worker, daemon=True).start()
    return jsonify(success=True, job_id=job_id, started_at=ACTIVE_TEST_LIB_JOB.get("started_at"))


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


@app.route("/clone-test-libraries-active", methods=["GET"])
def clone_test_libraries_active():
    job_id = ACTIVE_TEST_LIB_JOB.get("job_id")
    if not job_id:
        return jsonify(success=True, active=False)

    info = CLONE_PROGRESS.get(job_id) or {}
    phase = info.get("phase")
    if phase in ["done", "error"]:
        ACTIVE_TEST_LIB_JOB.clear()
        return jsonify(success=True, active=False)

    return jsonify(
        success=True,
        active=True,
        job_id=job_id,
        started_at=ACTIVE_TEST_LIB_JOB.get("started_at"),
        progress=info,
    )


@app.route("/clone-test-libraries", methods=["POST"])
def clone_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, tmp_root, _, _ = _resolve_test_libraries_paths(quickstart_root)

    resolved_path = os.path.abspath(target_path)
    if _paths_overlap(tmp_root, target_path):
        return jsonify(success=False, message="Temp and final paths must be different and cannot be nested.")
    if not _safe_to_replace_test_libraries(target_path):
        return jsonify(
            success=False,
            message="Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.",
        )

    try:
        # If already exists
        if os.path.exists(target_path) and _test_libraries_present(target_path):
            return jsonify(success=True, message="Test libraries already present (ZIP install).", target_path=resolved_path)

        # ZIP fallback if git not found or Download failed
        zip_url = "https://github.com/chazlarson/plex-test-libraries/archive/refs/heads/main.zip"
        commit_sha = None
        try:
            commit_info = requests.get("https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main", timeout=5).json()
            commit_sha = commit_info.get("sha", "")[:7]
        except Exception:
            commit_sha = None

        ok, msg = _ensure_rw_dir(tmp_root)
        if not ok:
            return jsonify(success=False, message=msg)
        try:
            for entry in os.listdir(tmp_root):
                if entry.startswith("qs_test_libs_"):
                    shutil.rmtree(os.path.join(tmp_root, entry), ignore_errors=True)
        except Exception:
            pass

        with tempfile.TemporaryDirectory(prefix="qs_test_libs_", dir=tmp_root) as tmpdir:
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
                if not _safe_to_replace_test_libraries(target_path):
                    return jsonify(
                        success=False,
                        message="Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.",
                    )
                shutil.rmtree(target_path, onerror=helpers.handle_remove_readonly)
            shutil.move(extracted_dir, target_path)

            if commit_sha:
                try:
                    with open(os.path.join(target_path, ".test_libraries_version"), "w") as f:
                        f.write(commit_sha)
                except Exception as e:
                    helpers.ts_log(f"Warning: Failed to write SHA version file: {e}", level="WARNING")

        if platform.system() in ["Linux", "Darwin"]:
            subprocess.run(["chmod", "-R", "777", target_path], check=False)

        return jsonify(success=True, message="Test libraries installed successfully.", target_path=resolved_path)

    except Exception as e:
        return jsonify(success=False, message=f"Unexpected error: {str(e)}")


@app.route("/purge-test-libraries", methods=["POST"])
def purge_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, _, _, _ = _resolve_test_libraries_paths(quickstart_root)

    resolved_path = os.path.abspath(target_path)

    try:
        if not os.path.exists(resolved_path):
            return jsonify(success=False, message="Test libraries folder does not exist.")
        if not _test_libraries_present(resolved_path):
            return jsonify(
                success=False,
                message="Target path does not look like test libraries. Refusing to delete.",
            )

        shutil.rmtree(resolved_path, onerror=helpers.handle_remove_readonly)
        return jsonify(success=True, message=f"Test libraries deleted at: {resolved_path}")

    except Exception as e:
        return jsonify(success=False, message=f"Failed to delete folder:\n{str(e)}")


@app.route("/restart", methods=["POST"])
def restart_quickstart():
    data = request.get_json(silent=True) or {}
    reason = data.get("reason")
    if reason == "update":
        helpers.set_restart_notice(
            "update",
            "Update complete. Quickstart restarted.",
        )

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

        helpers.ts_log(
            f"Port and Debug Settings can be amended via the Settings cog in the UI or by editing your {DOTENV} file",
            level="INFO",
        )
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
                helpers.ts_log(
                    f"Port and Debug Settings can be amended via the Settings cog in the UI, " f"right-clicking the system tray icon, or by editing your {DOTENV} file",
                    level="INFO",
                )
                if app.config.get("QS_SKIP_AUTO_OPEN"):
                    helpers.ts_log("Skipping auto-open after update restart.", level="INFO")
                else:
                    # Open the browser automatically
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
