from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session, send_file
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

from modules.validations import validate_iso3166_1, validate_iso639_1, validate_plex_server, validate_tautulli_server, validate_trakt_server, validate_mal_server, validate_anidb_server, validate_gotify_server
from modules.output import build_config
from modules.helpers import get_template_list, get_bits, get_menu_list
from modules.persistence import save_settings, retrieve_settings, check_minimum_settings, flush_session_storage, notification_systems_available

# Load JSON Schema
yaml = YAML(typ='safe', pure=True)

# URL to the JSON schema
url = 'https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json'

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

app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# SESSION_TYPE = 'cachelib'
# SESSION_SERIALIZATION_FORMAT = 'json'
# SESSION_CACHELIB = FileSystemCache(threshold=500, cache_dir="sessions"),
# app.config.from_object(__name__)
# Session(app)

# Create the Flask application
# app = Flask(__name__)

# Details on the Secret Key: https://flask.palletsprojects.com/en/3.0.x/config/#SECRET_KEY
# NOTE: The secret key is used to cryptographically-sign the cookies used for storing
#       the session identifier.
# app.secret_key = os.getenv('SECRET_KEY', default='BAD_SECRET_KEY')

# Configure Redis for storing the session data on the server-side
app.config['SESSION_TYPE'] = 'cachelib'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = False
# app.config['SESSION_REDIS'] = redis.from_url('redis://127.0.0.1:6379')

# Create and initialize the Flask-Session object AFTER `app` has been configured
server_session = Session(app)

@app.route('/')
def start():
    return render_template('001-start.html')


@app.route('/clear_session', methods=['POST'])
def clear_session():
    flush_session_storage()
    flash('Session storage cleared successfully.', 'success')
    return redirect(url_for('start'))


@app.route('/step/<name>', methods=['GET', 'POST'])
def step(name):

    page_info = {}
    header_style = 'ascii'  # Default to ASCII art
    if request.method == 'POST':
        save_settings(request.referrer, request.form)
        header_style = request.form.get('header_style', 'ascii')
    
    page_info['header_style'] = header_style

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
        return redirect(url_for('start'))
    
    page_info['progress'] = round((current_index + 1) / total_steps * 100)
    
    page_info['title'] = item['name']
    page_info['next_page'] = item['next']
    page_info['prev_page'] = item['prev']
        
    data = retrieve_settings(name)

    print(f"data retrieved for {name}: {data}")

    page_info['plex_valid'], page_info['tmdb_valid'] = check_minimum_settings()
    
    page_info['notifiarr_available'], page_info['gotify_available'] = notification_systems_available()
    # notifiarr_available = False
    # gotify_available = False
    
    # This should not be based on name; maybe next being empty
    if name == '900-final':
        validated, config_data, yaml_content = build_config(header_style)
        validation_error = None

        try:
            jsonschema.validate(instance=config_data, schema=schema)
        except jsonschema.exceptions.ValidationError as e:
            flash(f'Validation error: {e.message}', 'danger')
            validation_error = e
        
        return render_template('900-final.html', page_info=page_info, data=data, yaml_content=yaml_content, validation_error=validation_error, template_list=file_list)

    else:
        return render_template(name + '.html', page_info=page_info, data=data, template_list=file_list)

@app.route('/download')
def download():
    yaml_content = session.get('yaml_content', '')
    if yaml_content:
        return send_file(
            io.BytesIO(yaml_content.encode('utf-8')),
            mimetype='text/yaml',
            as_attachment=True,
            download_name='config.yml'
        )
    flash('No configuration to download', 'danger')
    return redirect(url_for('final_step'))


@app.route('/validate_gotify', methods=['POST'])
def validate_gotify():
    data = request.json
    return validate_gotify_server(data)


@app.route('/validate_plex', methods=['POST'])
def validate_plex():
    data = request.json
    return validate_plex_server(data)


@app.route('/validate_tautulli', methods=['POST'])
def validate_tautulli():
    data = request.json
    return validate_tautulli_server(data)


@app.route('/validate_trakt', methods=['POST'])
def validate_trakt():
    data = request.json
    return validate_trakt_server(data)

@app.route('/validate_mal', methods=['POST'])
def validate_mal():
    data = request.json
    return validate_mal_server(data)

@app.route('/validate_anidb', methods=['POST'])
def validate_anidb():
    data = request.json
    return validate_anidb_server(data)

@app.route('/test_webhook', methods=['POST'])
def test_webhook():
    webhook_url = request.json.get('webhook_url')
    message = request.json.get('message')
    print(f"message: {message}")
    
    if not webhook_url:
        return jsonify({"error": "Webhook URL is required"}), 400

    message = {
        "content": message
    }

    response = requests.post(webhook_url, json=message)

    if response.status_code == 204:
        return jsonify({"success": "Test message sent successfully!"}), 200
    else:
        return jsonify({"error": f"Failed to send message: {response.status_code}, {response.text}"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
