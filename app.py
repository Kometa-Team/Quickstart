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

import jsonschema
import requests
import io
from ruamel.yaml import YAML
import os
from dotenv import load_dotenv
from pathlib import Path
from plexapi.server import PlexServer
import pyfiglet
import secrets
import namesgenerator

import string
import random

from modules.validations import (
    validate_iso3166_1,
    validate_iso639_1,
    validate_plex_server,
    validate_tautulli_server,
    validate_trakt_server,
    validate_mal_server,
    validate_anidb_server,
    validate_gotify_server,
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
from modules.helpers import get_template_list, get_bits, get_menu_list
from modules.persistence import (
    save_settings,
    retrieve_settings,
    check_minimum_settings,
    flush_session_storage,
    notification_systems_available,
)
from modules.database import reset_data

basedir = os.path.abspath

# Load JSON Schema
yaml = YAML(typ="safe", pure=True)

# URL to the JSON schema
url = "https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json"

try:
    # Fetch the schema
    response = requests.get(url)
    response.raise_for_status()  # Ensure we notice bad responses

    # Load the schema
    schema = yaml.load(response.text)
except requests.RequestException as e:
    print(f"Error fetching the JSON schema: {e}")
    schema = None  # or handle the error appropriately

load_dotenv()

app = Flask(__name__)

app.config["SESSION_TYPE"] = "cachelib"
app.config["SESSION_CACHELIB"] = FileSystemCache(
    cache_dir="flask_session", threshold=500
)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_USE_SIGNER"] = False

server_session = Session(app)

TEMPLATES_DIR = "templates"


# Function to create a template file
def create_template_file(library_name, prefix):
    template_filename = f"{prefix}-{library_name.replace(' ', '_')}.html"
    template_path = os.path.join(TEMPLATES_DIR, template_filename)
    if not os.path.exists(template_path):
        with open(template_path, "w") as f:
            f.write(f"<!-- Template for {library_name} -->\n")
            f.write(f"<h1>{library_name} Library</h1>")
    return template_filename


# Function to delete a template file
def delete_template_file(library_name, prefix):
    template_filename = f"{prefix}-{library_name.replace(' ', '_')}.html"
    template_path = os.path.join(TEMPLATES_DIR, template_filename)
    if os.path.exists(template_path):
        os.remove(template_path)


@app.route("/update_libraries", methods=["POST"])
def update_libraries():
    try:
        data = request.get_json()
        app.logger.info("Received data: %s", data)  # Log the received data

        selected_libraries = data.get("libraries", [])
        template_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), TEMPLATES_DIR
        )

        # Define the template content with required blocks
        template_content = "{% extends '000-library_template.html' %} {% block content %}{% endblock %}"
        template_content = """{% extends '000-base.html' %} {% block content %}
<form method="post" id="configForm" name="configForm">
<div id="{{page_info['title']}}Section">
    <div class="row">
        <div class="col align-self-center">
            <div class="input-group justify-content-start">
                <button type="submit" class="btn btn-secondary" onclick="loading('prev')" formaction="/step/{{ page_info['prev_page'] }}">
                    <i id="prev-spinner-icon" class="fa fa-arrow-left"></i>
                </button>
            </div>
        </div>
        <div class="col-6 align-self-center text-center">
            <h2>{{ page_info['title'] }}</h2>
        </div>
        <div class="col align-self-center">
            <div class="input-group justify-content-end jump-spinner-container">
                <button type="button" class="btn btn-success dropdown-toggle dropdown-toggle-split" data-bs-toggle="dropdown" aria-expanded="false">
                    <span id="jump-to-text">Jump To</span>
                    <i id="jump-spinner-icon" class=""></i>
                </button>
                <ul class="dropdown-menu dropdown-menu-end">
                    {% for file, name in template_list %}
                    {% if name == 'Final Validation' %}
                    <li>
                        <hr class="dropdown-divider">
                    </li>
                    {% endif %}
                    <li>
                        <a class="dropdown-item" href="javascript:void(0);" onclick="jumpTo('{{ file.rsplit('.', 1)[0] }}')">{{ name }}</a>
                    </li>
                    {% if name == 'Start' %}
                    <li>
                        <hr class="dropdown-divider">
                    </li>
                    {% endif %}
                    {% endfor %}
                </ul>
                <button type="submit" class="btn btn-success" onclick="loading('next')" formaction="/step/{{ page_info['next_page'] }}">
                    <i id="next-spinner-icon" class="fa fa-arrow-right"></i>
                </button>
            </div>
        </div>
    </div>
    <div class="container text-center">
        <div class="row">
            <div class="col"></div>
            <div class="col-8">
                <div class="col align-self-end">
                    <div class="progress" role="progressbar" aria-label="Example with label" aria-valuenow="25"
                        aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar bg-success" style="width: {{ page_info['progress'] }}%">
                            {{ page_info['progress'] }}%
                        </div>
                    </div>
                </div>
            </div>
            <div class="col"></div>
        </div>
    </div>
    <hr class="hr">
    {% include "modals/" + page_info['template_name'] + ".html" ignore missing %}
</div>
</form>
{% endblock %}
"""

        # Gather a list of existing template files that match the patterns
        existing_files = [
            filename
            for filename in os.listdir(template_dir)
            if filename.startswith("012")
            or filename.startswith("013")
            or filename.startswith("014")
        ]

        # Determine which files to delete
        files_to_delete = existing_files

        # Delete the files that are not in the selected libraries
        for filename in files_to_delete:
            os.remove(os.path.join(template_dir, filename))

        # Generate new template files based on the selected libraries
        counters = {"movie": 1, "show": 1, "music": 1}
        for library in selected_libraries:
            library_name = library["name"]
            library_type = library["type"]
            prefix = {"movie": "012", "show": "013", "music": "014"}.get(
                library_type, "012"
            )

            filename = f"{prefix}{counters[library_type]:02d}-{library_name.replace(' ', '_')}.html"
            counters[library_type] += 1

            filepath = os.path.join(template_dir, filename)
            if not os.path.exists(filepath):
                with open(filepath, "w") as f:
                    f.write(template_content)

        return jsonify({"status": "success"})

    except Exception as e:
        app.logger.error("Error updating libraries: %s", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/")
def start():
    return redirect(url_for("step", name="001-start"))


@app.route("/clear_session", methods=["POST"])
def clear_session():
    flush_session_storage()
    flash("Session storage cleared successfully.", "success")
    return redirect(url_for("start"))


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

    try:
        if not session["config_name"]:
            session["config_name"] = namesgenerator.get_random_name()
        else:
            print(f"There's a config name in the session")
    except:
        session["config_name"] = namesgenerator.get_random_name()

    print(f"using config name: {session['config_name']}")

    page_info["config_name"] = session["config_name"]
    page_info["header_style"] = header_style
    page_info["template_name"] = name

    file_list = get_menu_list()

    template_list = get_template_list()

    total_steps = len(template_list)

    stem, num, b = get_bits(name)

    current_index = -1
    item = None

    try:
        current_index = list(template_list).index(num)
        item = template_list[num]
    except:
        # not in there
        return f"ERROR WITH NAME {name}; stem, num, b: {stem}, {num}, {b}"

    page_info["progress"] = round((current_index + 1) / total_steps * 100)

    page_info["title"] = item["name"]
    page_info["next_page"] = item["next"]
    page_info["prev_page"] = item["prev"]

    data = retrieve_settings(name)
    plex_data = retrieve_settings("010-plex")

    print(f"data retrieved for {name}")

    page_info["plex_valid"], page_info["tmdb_valid"] = check_minimum_settings()

    page_info["notifiarr_available"], page_info["gotify_available"] = (
        notification_systems_available()
    )

    # This should not be based on name; maybe next being empty
    if name == "900-final":
        validated, validation_error, config_data, yaml_content = build_config(
            header_style
        )

        page_info["yaml_valid"] = validated

        return render_template(
            "900-final.html",
            page_info=page_info,
            data=data,
            yaml_content=yaml_content,
            validation_error=validation_error,
            template_list=file_list,
        )

    else:
        return render_template(
            name + ".html",
            page_info=page_info,
            data=data,
            plex_data=plex_data,
            template_list=file_list,
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
    return redirect(url_for("final_step"))


@app.route("/validate_gotify", methods=["POST"])
def validate_gotify():
    data = request.json
    return validate_gotify_server(data)


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
    app.run(host="0.0.0.0", debug=True)
