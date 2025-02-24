import webbrowser

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
from flask_session import Session
from cachelib.file import FileSystemCache

import argparse
import io
import os
import requests
import pystray
import shutil
import signal
import stat
import sys
import threading
from threading import Thread
from dotenv import load_dotenv
import namesgenerator
from io import BytesIO
from werkzeug.utils import secure_filename
from waitress import serve


from modules.validations import (
    validate_plex_server,
    validate_tautulli_server,
    validate_trakt_server,
    validate_mal_server,
    validate_anidb_server,
    validate_gotify_server,
    validate_ntfy_server,
    validate_webhook_server,
    validate_radarr_server,
    validate_sonarr_server,
    validate_omdb_server,
    validate_github_server,
    validate_tmdb_server,
    validate_mdblist_server,
    validate_notifiarr_server,
)
from modules.output import build_config
from modules.helpers import (
    get_template_list,
    get_bits,
    get_menu_list,
    redact_sensitive_data,
    check_for_update,
    update_checker_loop,
    booler,
    ensure_json_schema,
    get_pyfiglet_fonts,
)
from modules.persistence import (
    save_settings,
    retrieve_settings,
    check_minimum_settings,
    flush_session_storage,
    notification_systems_available,
)
from modules.database import reset_data, get_unique_config_names

from PIL import Image, ImageDraw

# Determine the base directory (where Quickstart.exe is located)
if getattr(sys, "frozen", False):  # Running as PyInstaller EXE
    BASE_DIR = os.path.dirname(sys.executable)  # D:\QS\
    MEIPASS_DIR = sys._MEIPASS  # PyInstaller's temp directory
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Running as a script
    MEIPASS_DIR = BASE_DIR  # Use local directory when running normally

# Ensure config directory exists
CONFIG_DIR = os.path.join(BASE_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)

# Files to copy from _MEIPASS to correct locations
files_to_copy = {
    "VERSION": BASE_DIR,  # Copy to the same directory as Quickstart.exe
    ".env.example": CONFIG_DIR,  # Copy to config/ next to Quickstart.exe
}

# Copy files before _MEIPASS disappears
for filename, dest_dir in files_to_copy.items():
    src_path = os.path.join(MEIPASS_DIR, filename)  # File location in _MEIPASS
    dest_path = os.path.join(dest_dir, filename)  # Target location

    # Copy only if the file exists in _MEIPASS and does not already exist in the destination
    if os.path.exists(src_path) and not os.path.exists(dest_path):
        try:
            print(f"[INFO] Extracting {filename} to {dest_dir}")
            shutil.copyfile(src_path, dest_path)
        except Exception as e:
            print(f"[ERROR] Failed to copy {filename}: {e}")


load_dotenv("config/.env")

UPLOAD_FOLDER = "config/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

UPLOAD_FOLDER_MOVIE = "config/uploads/movies"
UPLOAD_FOLDER_SHOW = "config/uploads/shows"
os.makedirs(UPLOAD_FOLDER_MOVIE, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_SHOW, exist_ok=True)
IMAGES_FOLDER = "static/images"
OVERLAY_FOLDER = "static/images/overlays"
PREVIEW_FOLDER = "config/previews"
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

VERSION_FILE = "VERSION"
GITHUB_MASTER_VERSION_URL = (
    "https://raw.githubusercontent.com/Kometa-Team/Quickstart/master/VERSION"
)
GITHUB_DEVELOP_VERSION_URL = (
    "https://raw.githubusercontent.com/Kometa-Team/Quickstart/develop/VERSION"
)

basedir = os.path.abspath

app = Flask(__name__)

# Run version check at startup
app.config["VERSION_CHECK"] = check_for_update()


def start_update_thread():
    """Ensure update_checker_loop runs inside the Flask app context."""
    with app.app_context():
        update_checker_loop(app)


# Start the background version checker safely
threading.Thread(target=start_update_thread, daemon=True).start()


@app.context_processor
def inject_version_info():
    """Ensure latest version info is injected dynamically in templates."""
    return {"version_info": check_for_update()}


# Use booler() for FLASK_DEBUG conversion
app.config["QS_DEBUG"] = booler(os.getenv("QS_DEBUG", "0"))

app.config["SESSION_TYPE"] = "cachelib"
app.config["SESSION_CACHELIB"] = FileSystemCache(
    cache_dir="flask_session", threshold=500
)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = False

server_session = Session(app)

# Ensure json-schema files are up to date at startup
ensure_json_schema()

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

parser = argparse.ArgumentParser(description="Run Quickstart Flask App")
parser.add_argument("--port", type=int, help="Specify the port number to run the server")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
args = parser.parse_args()

port = args.port if args.port else int(os.getenv("QS_PORT", "5000"))
debug_mode = args.debug if args.debug else booler(os.getenv("QS_DEBUG", "0"))

print(f"[INFO] Running on port: {port} | Debug Mode: {'Enabled' if debug_mode else 'Disabled'}")


def allowed_file(filename):
    """Check if the file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def is_valid_aspect_ratio(image):
    """Check if the image has an aspect ratio of approximately 1:1.5."""
    width, height = image.size
    return abs((width / height) - (2 / 3)) < 0.01  # Ensure it's approximately 1000x1500


@app.route("/rename_library_image", methods=["POST"])
def rename_library_image():
    data = request.json
    old_name = data.get("old_name")
    new_name = data.get("new_name")
    image_type = data.get("type")  # "movie" or "show"

    if not old_name or not new_name or image_type not in ["movie", "show"]:
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    save_folder = UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW
    old_path = os.path.join(save_folder, old_name)
    new_path = os.path.join(save_folder, new_name)

    if not os.path.exists(old_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    if os.path.exists(new_path):
        return (
            jsonify(
                {"status": "error", "message": "File with new name already exists"}
            ),
            400,
        )

    try:
        os.rename(old_path, new_path)
        return jsonify({"status": "success", "message": "File renamed successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/config/uploads/<path:filename>")
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/config/previews/<path:filename>")
def serve_previews(filename):
    return send_from_directory("config/previews", filename)


@app.route("/generate_preview", methods=["POST"])
def generate_preview():
    data = request.json
    overlays = data.get("overlays", [])
    img_type = data.get("type", "movie")
    selected_image = data.get("selected_image")

    upload_folder = UPLOAD_FOLDER_MOVIE if img_type == "movie" else UPLOAD_FOLDER_SHOW
    preview_folder = "config/previews"
    preview_filename = f"{img_type}_preview.png"
    preview_path = os.path.join(preview_folder, preview_filename)

    # Ensure preview folder exists
    os.makedirs(preview_folder, exist_ok=True)

    # ✅ First, check if `default.png` exists in `IMAGES_FOLDER`
    default_image_path = os.path.join(IMAGES_FOLDER, "default.png")

    if not selected_image or selected_image == "default":
        if os.path.exists(default_image_path):
            base_image_path = default_image_path  # ✅ Use existing `default.png`
        else:
            base_image_path = os.path.join(preview_folder, "default.png")

            # ✅ Only create grey image if both locations are missing
            if not os.path.exists(base_image_path):
                if app.config["QS_DEBUG"]:
                    print(
                        "[DEBUG] default.png not found in IMAGES_FOLDER or previews, creating grey placeholder image..."
                    )

                # Create grey image
                base_img = Image.new("RGBA", (1000, 1500), (128, 128, 128, 255))  # grey
                base_img.save(base_image_path)
    else:
        base_image_path = os.path.join(upload_folder, selected_image)

    if not os.path.exists(base_image_path):
        return jsonify({"status": "error", "message": "Selected image not found."}), 400

    base_img = Image.open(base_image_path).convert("RGBA")

    # Ensure base image is 1000x1500
    base_img = base_img.resize((1000, 1500), Image.LANCZOS)

    # Apply overlays
    for overlay in overlays:
        overlay_path = f"static/images/overlays/{overlay}.png"
        if os.path.exists(overlay_path):
            overlay_img = Image.open(overlay_path).convert("RGBA")
            base_img.paste(overlay_img, (0, 0), overlay_img)

    # Save the generated preview
    base_img.save(preview_path)

    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Preview saved at {preview_path}")

    return jsonify({"status": "success", "preview_url": f"/{preview_path}"})


@app.route("/get_preview_image/<img_type>", methods=["GET"])
def get_preview_image(img_type):
    preview_folder = "config/previews"
    preview_filename = f"{img_type}_preview.png"
    preview_path = os.path.join(preview_folder, preview_filename)

    # Generate preview if it doesn't exist
    if not os.path.exists(preview_path):
        print(f"[WARNING] Preview not found for {img_type}. Generating...")
        generate_preview()

    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype="image/png")

    return jsonify({"status": "error", "message": "Preview image not found"}), 40


@app.route("/list_uploaded_images", methods=["GET"])
def list_uploaded_images():
    image_type = request.args.get("type")  # Expecting "movie" or "show"

    if image_type not in ["movie", "show"]:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    # Ensure the correct directory is used
    uploads_dir = UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW

    if not os.path.exists(uploads_dir):
        return jsonify({"images": []})  # Return empty list if folder doesn't exist

    images = [
        img
        for img in os.listdir(uploads_dir)
        if img.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    return jsonify({"images": images})


@app.route("/upload_library_image", methods=["POST"])
def upload_library_image():
    if "image" not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400

    image = request.files["image"]
    image_type = request.form.get("type")  # "movie" or "show"

    if not image or not image_type or image_type not in ["movie", "show"]:
        return (
            jsonify({"status": "error", "message": "Invalid request parameters"}),
            400,
        )

    # Validate file extension
    filename = secure_filename(image.filename)
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Invalid file type. Allowed: png, jpg, jpeg, webp",
                }
            ),
            400,
        )

    # Open and validate image
    img = Image.open(image)
    if not is_valid_aspect_ratio(img):
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Image must have a 1:1.5 aspect ratio (e.g., 1000x1500).",
                }
            ),
            400,
        )

    # Resize if needed
    img = img.resize((1000, 1500), Image.LANCZOS)

    # Set save directory
    save_folder = UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW
    os.makedirs(save_folder, exist_ok=True)

    # Set initial save path **before the loop**
    save_path = os.path.join(save_folder, filename)

    # Prevent overwriting existing files
    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(os.path.join(save_folder, filename)):
        filename = f"{base}_{counter}{ext}"
        save_path = os.path.join(save_folder, filename)
        counter += 1

    # Save the validated and resized image
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
    image_type = data.get("type")  # "movie" or "show"

    if not image_url or not image_type or image_type not in ["movie", "show"]:
        return (
            jsonify({"status": "error", "message": "Invalid request parameters"}),
            400,
        )

    try:
        response = requests.get(image_url, stream=True, timeout=5)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))

        # Validate file extension
        file_extension = img.format.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Invalid file type. Allowed: png, jpg, jpeg, webp",
                    }
                ),
                400,
            )

        # Ensure the correct aspect ratio
        if not is_valid_aspect_ratio(img):
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Image must have a 1:1.5 aspect ratio (e.g., 1000x1500).",
                    }
                ),
                400,
            )

        # Resize if necessary
        img = img.resize((1000, 1500), Image.LANCZOS)

        # Set save directory
        save_folder = (
            UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW
        )
        os.makedirs(save_folder, exist_ok=True)

        # Generate a safe filename from URL
        filename = secure_filename(os.path.basename(image_url))
        if (
            "." not in filename
            or filename.split(".")[-1].lower() not in ALLOWED_EXTENSIONS
        ):
            filename += ".png"  # Default to PNG if no valid extension is found

        # Set initial save path **before the loop**
        save_path = os.path.join(save_folder, filename)

        # Prevent overwriting existing files
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(save_folder, filename)
            counter += 1

        # Save the validated and resized image
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
        return jsonify({"status": "error", "message": f"Processing error: {str(e)}"}), 4


@app.route("/delete_library_image/<filename>", methods=["DELETE"])
def delete_library_image(filename):
    image_type = request.args.get("type")  # "movie" or "show"

    if image_type not in ["movie", "show"]:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    uploads_dir = UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW
    file_path = os.path.join(uploads_dir, filename)

    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    try:
        os.remove(file_path)
        return jsonify({"status": "success", "message": f"Deleted {filename}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/update_libraries", methods=["POST"])
def update_libraries():
    try:
        data = request.get_json()
        app.logger.info("Received data: %s", data)  # Log the received data

        return jsonify({"status": "success"})

    except Exception as e:
        app.logger.error("Error updating libraries: %s", str(e))
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

    flush_session_storage(config_name)

    # Send message to toast
    return jsonify(
        {
            "status": "success",
            "message": f"Session storage cleared for '{config_name}'.",
        }
    )


@app.route("/clear_data/<name>/<section>")
def clear_data_section(name, section):
    reset_data(name, section)
    flash("SQLite storage cleared successfully.", "success")
    return redirect(url_for("start"))


@app.route("/clear_data/<name>")
def clear_data(name):
    reset_data(name)
    flash("SQLite storage cleared successfully.", "success")
    return redirect(url_for("start"))


@app.route("/step/<name>", methods=["GET", "POST"])
def step(name):
    page_info = {}
    header_style = "standard"  # Default to 'standard' font

    if request.method == "POST":
        save_settings(request.referrer, request.form)
        header_style = request.form.get("header_style", "standard")

    # Retrieve available fonts (ensuring "none" and "single line" are always included)
    available_fonts = get_pyfiglet_fonts()

    page_info["available_fonts"] = available_fonts

    # Ensure session["config_name"] always exists
    if "config_name" not in session:
        session["config_name"] = namesgenerator.get_random_name()
        app.logger.info(f"Assigned new config_name: {session['config_name']}")

    # Retrieve stored settings from DB
    saved_settings = retrieve_settings(name)  # Retrieve from DB

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

    # Generate a placeholder name for "Add Config"
    page_info["new_config_name"] = namesgenerator.get_random_name()

    # Fetch available configurations from the database
    available_configs = get_unique_config_names() or []

    # Ensure the selected config is either in the dropdown or newly created
    if selected_config not in available_configs:
        page_info["new_config_name"] = selected_config  # Use the new config name

    file_list = get_menu_list()
    template_list = get_template_list()
    total_steps = len(template_list)

    stem, num, b = get_bits(name)

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
        # Extract numeric part (e.g., "020" from "020-tmdb")
        next_num = page_info["next_page"].split("-")[0]
        prev_num = page_info["prev_page"].split("-")[0]

        # Lookup name from template_list
        page_info["next_page_name"] = template_list.get(next_num, {}).get(
            "name", "Next"
        )
        page_info["prev_page_name"] = template_list.get(prev_num, {}).get(
            "name", "Previous"
        )

    except Exception as e:
        print(f"[ERROR] Failed to get page names: {e}")
        page_info["next_page_name"] = "Next"
        page_info["prev_page_name"] = "Previous"

    # Retrieve data from storage
    data = retrieve_settings(name)
    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Raw data retrieved for {name}: {data}")

    plex_data = retrieve_settings("010-plex")

    # Ensure `libraries` dictionary exists
    if "libraries" not in data:
        data["libraries"] = {}

    # Ensure `mov-template_variables` and `sho-template_variables` exist inside `libraries`
    if "mov-template_variables" not in data["libraries"]:
        data["libraries"]["mov-template_variables"] = {}

    if "sho-template_variables" not in data["libraries"]:
        data["libraries"]["sho-template_variables"] = {}

    if app.config["QS_DEBUG"]:
        print(
            f"[DEBUG] ************************************************************************"
        )
        print(f"[DEBUG] Data retrieved for {name}")

    (
        page_info["plex_valid"],
        page_info["tmdb_valid"],
        page_info["libs_valid"],
        page_info["sett_valid"],
    ) = check_minimum_settings()

    (
        page_info["notifiarr_available"],
        page_info["gotify_available"],
        page_info["ntfy_available"],
    ) = notification_systems_available()

    # Ensure template variables exist
    if "mov-template_variables" not in data:
        data["mov-template_variables"] = {}
    if "sho-template_variables" not in data:
        data["sho-template_variables"] = {}

    # Ensure correct rendering for the final validation page
    config_name = session.get("config_name") or page_info.get("config_name", "default")
    if name == "900-final":
        validated, validation_error, config_data, yaml_content = build_config(
            header_style, config_name=config_name
        )

        page_info["yaml_valid"] = validated
        session["yaml_content"] = yaml_content

        return render_template(
            "900-final.html",
            page_info=page_info,
            data=data,
            yaml_content=yaml_content,
            validation_error=validation_error,
            template_list=file_list,
            available_configs=available_configs,
        )

    else:
        return render_template(
            name + ".html",
            page_info=page_info,
            data=data,
            plex_data=plex_data,
            template_list=file_list,
            available_configs=available_configs,
        )


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
        redacted_content = redact_sensitive_data(yaml_content)

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
    return validate_gotify_server(data)


@app.route("/validate_ntfy", methods=["POST"])
def validate_ntfy():
    data = request.json
    return validate_ntfy_server(data)


@app.route("/validate_plex", methods=["POST"])
def validate_plex():
    data = request.json
    return validate_plex_server(data)


@app.route("/validate_tautulli", methods=["POST"])
def validate_tautulli():
    data = request.json
    return validate_tautulli_server(data)


@app.route("/validate_trakt", methods=["POST"])
def validate_trakt():
    data = request.json
    return validate_trakt_server(data)


@app.route("/validate_mal", methods=["POST"])
def validate_mal():
    data = request.json
    return validate_mal_server(data)


@app.route("/validate_anidb", methods=["POST"])
def validate_anidb():
    data = request.json
    return validate_anidb_server(data)


@app.route("/validate_webhook", methods=["POST"])
def validate_webhook():
    data = request.json
    return validate_webhook_server(data)


@app.route("/validate_radarr", methods=["POST"])
def validate_radarr():
    data = request.json
    result = validate_radarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_sonarr", methods=["POST"])
def validate_sonarr():
    data = request.json
    result = validate_sonarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_omdb", methods=["POST"])
def validate_omdb():
    data = request.json
    result = validate_omdb_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_github", methods=["POST"])
def validate_github():
    data = request.json
    result = validate_github_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_tmdb", methods=["POST"])
def validate_tmdb():
    data = request.json
    result = validate_tmdb_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_mdblist", methods=["POST"])
def validate_mdblist():
    data = request.json
    result = validate_mdblist_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400


@app.route("/validate_notifiarr", methods=["POST"])
def validate_notifiarr():
    data = request.json
    result = validate_notifiarr_server(data)

    if result.get_json().get("valid"):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400

server_thread = None

def start_flask_app():
    global server_thread
    if debug_mode:
        app.run(host="0.0.0.0", port=port, debug=debug_mode)
    else:
        serve(app, host="0.0.0.0", port=port)

def open_github(icon):
    webbrowser.open("https://github.com/Kometa-Team/Quickstart/")


def exit_action(icon):
    global server_thread
    icon.stop()
    os.kill(os.getpid(), signal.SIGINT)
    if server_thread and server_thread.is_alive():
        server_thread.join()

if __name__ == "__main__":
    icon = pystray.Icon("Flask App", Image.open("static/favicon.ico"), menu=pystray.Menu(
        pystray.MenuItem("Quickstart GitHub", open_github),
        pystray.MenuItem("Exit", exit_action),
    ))

    server_thread = Thread(target=start_flask_app)
    server_thread.daemon = True
    server_thread.start()
    icon.run()
