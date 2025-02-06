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
)
from flask_session import Session
from cachelib.file import FileSystemCache

import io
import os
from dotenv import load_dotenv
import namesgenerator

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
)
from modules.persistence import (
    save_settings,
    retrieve_settings,
    check_minimum_settings,
    flush_session_storage,
    notification_systems_available,
)
from modules.database import reset_data
from modules.database import get_unique_config_names
from modules.helpers import booler

basedir = os.path.abspath

load_dotenv()

app = Flask(__name__)

# Use booler() for FLASK_DEBUG conversion
app.config["QS_DEBUG"] = booler(os.getenv("QS_DEBUG", "0"))

app.config["SESSION_TYPE"] = "cachelib"
app.config["SESSION_CACHELIB"] = FileSystemCache(
    cache_dir="flask_session", threshold=500
)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = False

server_session = Session(app)


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
    header_style = "ascii"  # Default to ASCII art

    if request.method == "POST":
        save_settings(request.referrer, request.form)
        header_style = request.form.get("header_style", "ascii")

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
    if name == "900-final":
        validated, validation_error, config_data, yaml_content = build_config(
            header_style
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Quickstart Flask App")
    parser.add_argument(
        "--port", type=int, help="Specify the port number to run the server"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    # Load port and debug settings from `.env`
    env_port = os.getenv("QS_PORT", "5000")
    env_debug = booler(
        os.getenv("QS_DEBUG", "0")
    )  # Use booler() to handle boolean conversion

    # Determine final settings with precedence: CLI > .env > default
    port = args.port if args.port else int(env_port)
    debug_mode = args.debug if args.debug else env_debug

    print(
        f"[INFO] Running on port {port} | Debug Mode: {'Enabled' if debug_mode else 'Disabled'}"
    )

    app.run(host="0.0.0.0", port=port, debug=debug_mode)
