from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session, send_file
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
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

from modules.validations import validate_iso3166_1, validate_iso639_1, validate_plex_server, validate_tautulli_server, validate_trakt_server, validate_mal_server, validate_anidb_server, validate_gotify_server, validate_webhook_server, validate_radarr_server, validate_sonarr_server, validate_omdb_server, validate_github_server, validate_tmdb_server, validate_mdblist_server, validate_notifiarr_server
from modules.output import build_config
from modules.helpers import get_template_list, get_bits, get_menu_list
from modules.persistence import save_settings, retrieve_settings, check_minimum_settings, flush_session_storage, notification_systems_available
from modules.database import reset_data

basedir = os.path.abspath

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

app.config['SESSION_TYPE'] = 'cachelib'
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = False

server_session = Session(app)

@app.route('/')
def start():
    return redirect(url_for('step', name='001-start'))

@app.route('/clear_session', methods=['POST'])
def clear_session():
    flush_session_storage()
    flash('Session storage cleared successfully.', 'success')
    return redirect(url_for('start'))

@app.route('/clear_data/<name>/<section>')
def clear_data_section(name, section):
    reset_data(name, section)
    flash('SQLite storage cleared successfully.', 'success')
    return redirect(url_for('start'))

@app.route('/clear_data/<name>')
def clear_data(name):
    reset_data(name)
    flash('SQLite storage cleared successfully.', 'success')
    return redirect(url_for('start'))

@app.route('/step/<name>', methods=['GET', 'POST'])
def step(name):

    page_info = {}
    header_style = 'ascii'  # Default to ASCII art
    if request.method == 'POST':
        save_settings(request.referrer, request.form)
        header_style = request.form.get('header_style', 'ascii')
    
    try:
        if not session['config_name']:
            session['config_name'] = namesgenerator.get_random_name()
        else:
            print(f"There's a config name in the session")
    except:
        session['config_name'] = namesgenerator.get_random_name()

    print(f"using config name: {session['config_name']}")

    page_info['config_name'] = session['config_name']
    page_info['header_style'] = header_style
    page_info['template_name'] = name

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
    
    page_info['progress'] = round((current_index + 1) / total_steps * 100)
    
    page_info['title'] = item['name']
    page_info['next_page'] = item['next']
    page_info['prev_page'] = item['prev']
        
    data = retrieve_settings(name)
    plex_data = retrieve_settings('010-plex')

    print(f"data retrieved for {name}")

    page_info['plex_valid'], page_info['tmdb_valid'] = check_minimum_settings()
    
    page_info['notifiarr_available'], page_info['gotify_available'] = notification_systems_available()
    
    # This should not be based on name; maybe next being empty
    if name == '900-final':
        validated, validation_error, config_data, yaml_content = build_config(header_style)
        
        page_info['yaml_valid'] = validated
                
        return render_template('900-final.html', page_info=page_info, data=data, yaml_content=yaml_content, validation_error=validation_error, template_list=file_list)

    else:
        return render_template(name + '.html', page_info=page_info, data=data, plex_data=plex_data, template_list=file_list)

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

@app.route('/validate_webhook', methods=['POST'])
def validate_webhook():
    data = request.json
    return validate_webhook_server(data)

@app.route('/validate_radarr', methods=['POST'])
def validate_radarr():
    data = request.json
    result = validate_radarr_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400

@app.route('/validate_sonarr', methods=['POST'])
def validate_sonarr():
    data = request.json
    result = validate_sonarr_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400

@app.route('/validate_omdb', methods=['POST'])
def validate_omdb():
    data = request.json
    result = validate_omdb_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400

@app.route('/validate_github', methods=['POST'])
def validate_github():
    data = request.json
    result = validate_github_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400

@app.route('/validate_tmdb', methods=['POST'])
def validate_tmdb():
    data = request.json
    result = validate_tmdb_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400
    
@app.route('/validate_mdblist', methods=['POST'])
def validate_mdblist():
    data = request.json
    result = validate_mdblist_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400

@app.route('/validate_notifiarr', methods=['POST'])
def validate_notifiarr():
    data = request.json
    result = validate_notifiarr_server(data)

    if result.get_json().get('valid'):
        return jsonify(result.get_json())
    else:
        return jsonify(result.get_json()), 400
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
