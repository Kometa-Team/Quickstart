import argparse
import io
import os
import signal
import threading
import time
import webbrowser
from io import BytesIO
from threading import Thread

import namesgenerator
import requests
from PIL import Image
from cachelib.file import FileSystemCache
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
from werkzeug.utils import secure_filename

from flask_session import Session
from modules import validations, output, persistence, helpers, database

load_dotenv(os.path.join(helpers.CONFIG_DIR, ".env"))

UPLOAD_FOLDER = os.path.join(helpers.CONFIG_DIR, "uploads")
UPLOAD_FOLDER_MOVIE = os.path.join(UPLOAD_FOLDER, "movies")
UPLOAD_FOLDER_SHOW = os.path.join(UPLOAD_FOLDER, "shows")
os.makedirs(UPLOAD_FOLDER_MOVIE, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_SHOW, exist_ok=True)
IMAGES_FOLDER = os.path.join(helpers.MEIPASS_DIR, "static", "images")
OVERLAY_FOLDER = os.path.join(IMAGES_FOLDER, "overlays")
PREVIEW_FOLDER = os.path.join(helpers.CONFIG_DIR, "previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)

GITHUB_MASTER_VERSION_URL = "https://raw.githubusercontent.com/Kometa-Team/Quickstart/master/VERSION"
GITHUB_DEVELOP_VERSION_URL = "https://raw.githubusercontent.com/Kometa-Team/Quickstart/develop/VERSION"

basedir = os.path.abspath

app = Flask(__name__)

# Run version check at startup
app.config["VERSION_CHECK"] = helpers.check_for_update()


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
    """Ensure latest version info is injected dynamically in templates."""
    return {"version_info": helpers.check_for_update()}


# Use booler() for FLASK_DEBUG conversion
app.config["QS_DEBUG"] = helpers.booler(os.getenv("QS_DEBUG", "0"))
app.config["QUICKSTART_DOCKER"] = helpers.booler(os.getenv("QUICKSTART_DOCKER", "0"))

app.config["SESSION_TYPE"] = "cachelib"
app.config["SESSION_CACHELIB"] = FileSystemCache(cache_dir="flask_session", threshold=500)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = False

server_session = Session(app)
server_thread = None

# Ensure json-schema files are up to date at startup
helpers.ensure_json_schema()

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}

parser = argparse.ArgumentParser(description="Run Quickstart Flask App")
parser.add_argument("--port", type=int, help="Specify the port number to run the server")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
args = parser.parse_args()

port = args.port if args.port else int(os.getenv("QS_PORT", "7171"))
running_port = port
debug_mode = args.debug if args.debug else helpers.booler(os.getenv("QS_DEBUG", "0"))

print(f"[INFO] Running on port: {port} | Debug Mode: {'Enabled' if debug_mode else 'Disabled'}")


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

    # Ensure old file exists
    if not os.path.exists(old_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    # Extract original extension
    old_ext = os.path.splitext(old_name)[1]  # e.g., ".jpg"

    # Ensure new name has correct extension
    if "." not in new_name:  # No extension provided
        new_name += old_ext  # Append original extension
    elif not new_name.endswith(old_ext):  # Wrong extension provided
        new_name += old_ext  # Append original extension

    new_path = os.path.join(save_folder, new_name)

    # Check if the new file name already exists
    if os.path.exists(new_path):
        return jsonify({"status": "error", "message": "File with new name already exists"}), 400

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
    return send_from_directory(PREVIEW_FOLDER, filename)


@app.route("/generate_preview", methods=["POST"])
def generate_preview():
    data = request.json
    overlays = data.get("overlays", [])
    img_type = data.get("type", "movie")  # "movie" or "show"
    selected_image = data.get("selected_image", "default.png")
    library_id = data.get("library_id", "default-library")  # Unique identifier for each library
    upload_folder = UPLOAD_FOLDER_MOVIE if img_type == "movie" else UPLOAD_FOLDER_SHOW

    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Generating preview for {library_id}, Type: {img_type}, Overlays: {overlays}")

    # Ensure preview directory exists
    if not os.path.exists(PREVIEW_FOLDER):
        os.makedirs(PREVIEW_FOLDER)

    # Generate a unique preview filename per library
    preview_filename = f"{library_id}-{img_type}_preview.png"
    preview_filepath = os.path.join(PREVIEW_FOLDER, preview_filename)

    # First, check if `default.png` exists in `IMAGES_FOLDER`
    default_image_path = os.path.join(IMAGES_FOLDER, "default.png")

    if not selected_image or selected_image == "default":
        if os.path.exists(default_image_path):
            base_image_path = default_image_path  # ✅ Use existing `default.png`
        else:
            base_image_path = os.path.join(PREVIEW_FOLDER, "default.png")

            # Only create grey image if both locations are missing.
            if not os.path.exists(base_image_path):
                if app.config["QS_DEBUG"]:
                    print("[DEBUG] default.png not found in IMAGES_FOLDER or previews, creating grey placeholder image...")

                base_img = Image.new("RGBA", (1000, 1500), (128, 128, 128, 255))  # grey
                base_img.save(base_image_path)
    else:
        base_image_path = os.path.join(upload_folder, selected_image)

    if not os.path.exists(base_image_path):
        return jsonify({"status": "error", "message": "Selected image not found."}), 400

    base_img = Image.open(base_image_path).convert("RGBA")

    # Ensure base image is 1000x1500
    base_img = base_img.resize((1000, 1500), Image.LANCZOS)  # noqa

    # Apply overlays
    for overlay in overlays:
        overlay_path = os.path.join(OVERLAY_FOLDER, f"{overlay}.png")
        if os.path.exists(overlay_path):
            overlay_img = Image.open(overlay_path).convert("RGBA")
            base_img.paste(overlay_img, (0, 0), overlay_img)

    # Save the generated preview
    base_img.save(preview_filepath)

    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Preview saved at {preview_filepath}")

    return jsonify({"status": "success", "preview_url": f"/{preview_filepath}"})


@app.route("/config/previews/<filename>")
def serve_preview_image(filename):
    """
    Serves the requested preview image. If not found, returns a default placeholder.
    """
    filepath = os.path.join(PREVIEW_FOLDER, filename)

    if os.path.exists(filepath):
        return send_file(filepath, mimetype="image/png")
    else:
        print(f"[WARNING] Requested preview image '{filename}' not found. Returning default.")
        return send_file(os.path.join(IMAGES_FOLDER, "default.png"), mimetype="image/png")


@app.route("/get_preview_image/<img_type>", methods=["GET"])
def get_preview_image(img_type):
    preview_filename = f"{img_type}_preview.png"
    preview_path = os.path.join(PREVIEW_FOLDER, preview_filename)

    # Generate preview if it doesn't exist
    if not os.path.exists(preview_path):
        print(f"[WARNING] Preview not found for {img_type}. Generating...")
        generate_preview()

    if os.path.exists(preview_path):
        return send_file(preview_path, mimetype="image/png")

    return jsonify({"status": "error", "message": "Preview image not found"}), 400


@app.route("/list_uploaded_images", methods=["GET"])
def list_uploaded_images():
    image_type = request.args.get("type")  # Expecting "movie" or "show"

    if image_type not in ["movie", "show"]:
        return jsonify({"status": "error", "message": "Invalid image type"}), 400

    # Ensure the correct directory is used
    uploads_dir = UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW

    if not os.path.exists(uploads_dir):
        return jsonify({"images": []})  # Return empty list if folder doesn't exist

    images = [img for img in os.listdir(uploads_dir) if img.lower().endswith((".png", ".jpg", ".jpeg"))]

    return jsonify({"images": images})


@app.route("/upload_library_image", methods=["POST"])
def upload_library_image():
    if "image" not in request.files:
        return jsonify({"status": "error", "message": "No image uploaded"}), 400
    image = request.files["image"]

    image_type = request.form.get("type")  # "movie" or "show"

    if not image or not image_type or image_type not in ["movie", "show"]:
        return jsonify({"status": "error", "message": "Invalid request parameters"}), 400

    # Validate file extension
    filename = secure_filename(image.filename)
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"status": "error", "message": "Invalid file type. Allowed: png, jpg, jpeg, webp"}), 400

    # Open and validate image
    img = Image.open(image)  # noqa
    if not helpers.is_valid_aspect_ratio(img):
        return jsonify({"status": "error", "message": "Image must have a 1:1.5 aspect ratio (e.g., 1000x1500)."}), 400

    # Resize if needed
    img = img.resize((1000, 1500), Image.LANCZOS)  # noqa

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

    return jsonify({"status": "success", "message": f"Image uploaded and saved as {filename}", "filename": filename})


@app.route("/fetch_library_image", methods=["POST"])
def fetch_library_image():
    data = request.json
    image_url = data.get("url")
    image_type = data.get("type")  # "movie" or "show"

    if not image_url or not image_type or image_type not in ["movie", "show"]:
        return jsonify({"status": "error", "message": "Invalid request parameters"}), 400

    try:
        response = requests.get(image_url, stream=True, timeout=5)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))

        # Validate file extension
        file_extension = img.format.lower()
        if file_extension not in ALLOWED_EXTENSIONS:
            return jsonify({"status": "error", "message": "Invalid file type. Allowed: png, jpg, jpeg, webp"}), 400

        # Ensure the correct aspect ratio
        if not helpers.is_valid_aspect_ratio(img):
            return jsonify({"status": "error", "message": "Image must have a 1:1.5 aspect ratio (e.g., 1000x1500)."}), 400

        # Resize if necessary
        img = img.resize((1000, 1500), Image.LANCZOS)  # noqa

        # Set save directory
        save_folder = UPLOAD_FOLDER_MOVIE if image_type == "movie" else UPLOAD_FOLDER_SHOW
        os.makedirs(save_folder, exist_ok=True)

        # Generate a safe filename from URL
        filename = secure_filename(os.path.basename(image_url))
        if "." not in filename or filename.split(".")[-1].lower() not in ALLOWED_EXTENSIONS:
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

        return jsonify({"status": "success", "message": f"Image fetched and saved as {filename}", "filename": filename})

    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"Failed to fetch image: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Processing error: {str(e)}"}), 400


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

    persistence.flush_session_storage(config_name)

    # Send message to toast
    return jsonify({"status": "success", "message": f"Session storage cleared for '{config_name}'."})


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


@app.route("/step/<name>", methods=["GET", "POST"])
def step(name):
    page_info = {}
    header_style = "standard"  # Default to 'standard' font

    if request.method == "POST":
        persistence.save_settings(request.referrer, request.form)
        header_style = request.form.get("header_style", "standard")

    # ✅ Call `refresh_plex_libraries()` BEFORE retrieving Plex settings
    refresh_plex_libraries()

    # Retrieve available fonts (ensuring "none" and "single line" are always included)
    available_fonts = helpers.get_pyfiglet_fonts()

    page_info["available_fonts"] = available_fonts

    # Ensure session["config_name"] always exists
    if "config_name" not in session:
        session["config_name"] = namesgenerator.get_random_name()
        app.logger.info(f"Assigned new config_name: {session['config_name']}")

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
        # Extract numeric part (e.g., "020" from "020-tmdb")
        next_num = page_info["next_page"].split("-")[0]
        prev_num = page_info["prev_page"].split("-")[0]

        # Lookup name from template_list
        page_info["next_page_name"] = template_list.get(next_num, {}).get("name", "Next")
        page_info["prev_page_name"] = template_list.get(prev_num, {}).get("name", "Previous")

    except Exception as e:
        print(f"[ERROR] Failed to get page names: {e}")
        page_info["next_page_name"] = "Next"
        page_info["prev_page_name"] = "Previous"

    # Retrieve data from storage
    data = persistence.retrieve_settings(name)
    if app.config["QS_DEBUG"]:
        print(f"[DEBUG] Raw data retrieved for {name}: {data}")

    # Fetch Plex settings
    all_libraries = persistence.retrieve_settings("010-plex")

    # Debug: Print entire structure
    if app.config["QS_DEBUG"]:
        print("[DEBUG] all_libraries content:", all_libraries)

    # Ensure 'plex' key exists before accessing sub-keys
    plex_data = all_libraries.get("plex", {})

    # Extract the movie and show libraries
    movie_libraries_raw = plex_data.get("tmp_movie_libraries", "")
    show_libraries_raw = plex_data.get("tmp_show_libraries", "")

    # Debugging extracted values
    if app.config["QS_DEBUG"]:
        print("[DEBUG] Extracted movie libraries:", movie_libraries_raw)
        print("[DEBUG] Extracted show libraries:", show_libraries_raw)

    # Ensure it's a string before splitting
    if not isinstance(movie_libraries_raw, str):
        print("[ERROR] tmp_movie_libraries is not a string!")
        movie_libraries_raw = ""

    if not isinstance(show_libraries_raw, str):
        print("[ERROR] tmp_show_libraries is not a string!")
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
        print(f"[DEBUG] ************************************************************************")
        print(f"[DEBUG] Data retrieved for {name}")

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
    if name == "900-final":
        validated, validation_error, config_data, yaml_content = output.build_config(header_style, config_name=config_name)

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
            movie_libraries=movie_libraries,
            show_libraries=show_libraries,
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
        # ✅ Get stored Plex credentials from DB
        config_name = session.get("config_name")  # Ensure the session has config_name
        if not config_name:
            return jsonify({"valid": False, "error": "Missing config_name"}), 400

        plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")  # Fetch from DB

        # ✅ Load default values from config.yml.template
        dummy_plex_config = persistence.get_dummy_data("plex")  # Retrieves {"url": "...", "token": "..."}
        default_plex_url = dummy_plex_config.get("url", "")
        default_plex_token = dummy_plex_config.get("token", "")

        # ✅ Exit early if the Plex credentials are still using default placeholder values
        if not plex_url or not plex_token or plex_url == default_plex_url or plex_token == default_plex_token:
            return jsonify({"valid": False, "error": "Plex credentials are using default placeholder values"}), 400

        # ✅ Fetch latest libraries from Plex
        plex_response = validations.validate_plex_server({"plex_url": plex_url, "plex_token": plex_token})

        # ✅ Fix: Convert Flask response object to JSON before accessing data
        if isinstance(plex_response, Flask.response_class):
            plex_data = plex_response.get_json()  # ✅ Extract JSON data correctly
        else:
            plex_data = plex_response  # If already a dict, use as-is

        if not plex_data.get("validated"):
            return jsonify({"valid": False, "error": "Plex validation failed"}), 500

        # ✅ Extract new library data
        updated_movie_libraries = plex_data.get("movie_libraries", [])
        updated_show_libraries = plex_data.get("show_libraries", [])
        updated_music_libraries = plex_data.get("music_libraries", [])

        # ✅ Update the DB with the latest libraries
        persistence.update_stored_plex_libraries(
            "010-plex",
            updated_movie_libraries,
            updated_show_libraries,
            updated_music_libraries,
        )

        return jsonify(plex_data)  # Return refreshed data

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


server_thread = None


def start_flask_app():
    global server_thread
    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":

    def start_update_thread(app_in):
        with app_in.app_context():
            while True:
                app_in.config["VERSION_CHECK"] = helpers.check_for_update()
                print("[INFO] Checked for updates.")
                time.sleep(86400)

    update_thread = threading.Thread(target=start_update_thread, args=(app,), daemon=True)
    update_thread.start()

    if app.config["QUICKSTART_DOCKER"]:
        start_flask_app()
    else:
        import pystray
        import tkinter
        from tkinter.messagebox import showinfo

        class QSApp(tkinter.Tk):
            def __init__(self):
                super().__init__()
                global port

                def validate_input(new_text):
                    if not new_text:
                        return True
                    try:
                        value = int(new_text)
                        return 0 <= value <= 65535
                    except ValueError:
                        return False

                def get_value():
                    global port
                    value = entry.get()
                    if value:
                        port = int(value)
                        helpers.update_env_variable("QS_PORT", port)
                        showinfo("Port Number", f"Port Number Set to {port}. Please restart server to use new port.")
                        self.minimize_to_tray()

                def enter_pressed(event):  # noqa
                    get_value()

                self.title("Change Port Number")
                self.geometry("200x100")
                self.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

                label = tkinter.Label(self, text=f"Current Port Number: {port}")
                label.pack(pady=5)

                entry = tkinter.Entry(self, validate="key", validatecommand=(self.register(validate_input), "%P"))
                entry.pack(pady=5)
                entry.bind("<Return>", enter_pressed)

                button = tkinter.Button(self, text="Save Port Number", command=get_value)
                button.pack(pady=5)

                self.minimize_to_tray()

            def minimize_to_tray(self):
                self.withdraw()

                icon_image = Image.open(os.path.join(helpers.MEIPASS_DIR, "static", "favicon.ico"))
                pystray_icon = pystray.Icon(
                    "Quickstart",
                    icon_image,
                    menu=self.get_menu(),
                    title=f"Quickstart (Port: {running_port})",
                )
                pystray_icon.run()

            def get_menu(self):
                return pystray.Menu(
                    pystray.MenuItem(f"Open Quickstart (Port: {running_port})", self.open_quickstart, default=True),
                    pystray.MenuItem("Quickstart GitHub", self.open_github),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem(f"{'Disable' if debug_mode else 'Enable'} Debug", self.toggle_debug),
                    pystray.MenuItem(f"Change Port (Current: {port})", self.show_window),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Exit", self.exit_action),
                )

            def show_window(self, icon):
                icon.stop()
                self.after(0, self.deiconify)

            def open_quickstart(self, icon):  # noqa
                webbrowser.open(f"http://localhost:{running_port}")

            def open_github(self, icon):  # noqa
                webbrowser.open("https://github.com/Kometa-Team/Quickstart/")

            def toggle_debug(self, icon):
                global debug_mode
                debug_mode = not debug_mode
                helpers.update_env_variable("QS_DEBUG", "1" if debug_mode else "0")
                app.config["QS_DEBUG"] = debug_mode
                icon.menu = self.get_menu()
                icon.update_menu()

            def exit_action(self, icon):  # noqa
                global server_thread
                icon.stop()
                os.kill(os.getpid(), signal.SIGINT)
                if server_thread and server_thread.is_alive():
                    server_thread.join()

        server_thread = Thread(target=start_flask_app)
        server_thread.daemon = True
        server_thread.start()

        main_app = QSApp()
        main_app.mainloop()
