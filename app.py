from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session, send_file
from flask_session import Session
from cachelib.file import FileSystemCache

import jsonschema
import requests
import io
from ruamel.yaml import YAML
import os
from dotenv import load_dotenv
from plexapi.server import PlexServer
import pyfiglet
import secrets

from modules.validations import validate_iso3166_1, validate_iso639_1, validate_plex_server, validate_tautulli_server, validate_trakt_server, validate_mal_server, validate_anidb_server, validate_gotify_server
from modules.output import add_border_to_ascii_art
from modules.helpers import build_config_dict, get_template_list
from modules.persistence import save_settings, retrieve_settings, check_minimum_settings, flush_session_storage

# Load JSON Schema
# probably ought to load this from github
yaml = YAML(typ='safe', pure=True)
with open('json-schema/config-schema.json', 'r') as file:
    schema = yaml.load(file)

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
    return render_template('start.html')


@app.route('/clear_session', methods=['POST'])
def clear_session():
    flush_session_storage()
    flash('Session storage cleared successfully.', 'success')
    return redirect(url_for('start'))


@app.route('/step/<name>', methods=['GET', 'POST'])
def step(name):
    template_list = get_template_list(app)
    special_cases = {'start': 'Start', '999-final': 'Final', '999-danger': 'Danger'}
    
    if name in special_cases:
        curr_page = special_cases[name]
        title = special_cases[name]
        if name == 'start':
            prev_page = ""
            next_page = template_list[0][0].rsplit('.html', 1)[0]
            progress = 0
        elif name == '999-final':
            prev_page = template_list[-1][0].rsplit('.html', 1)[0]
            next_page = ""
            progress = 100
        elif name == '999-danger':
            prev_page = template_list[-1][0].rsplit('.html', 1)[0]
            next_page = "999-final"
            progress = 100
    else:
        current_index = next((index for index, (file, _) in enumerate(template_list) if file.startswith(name)), None)
        
        if current_index is None:
            return redirect(url_for('step', name='start'))
        
        curr_page = template_list[current_index][0].rsplit('.html', 1)[0].split('-', 1)[1].capitalize()
        title = curr_page
        next_page = template_list[current_index + 1][0].rsplit('.html', 1)[0] if current_index + 1 < len(template_list) else "999-final"
        prev_page = template_list[current_index - 1][0].rsplit('.html', 1)[0] if current_index > 0 else "start"
        
        # Calculate progress
        total_steps = len([file for file, _ in template_list if not file.startswith('999-')]) + 1  # Exclude 999-*.html but count as one step
        progress = round((current_index + 1) / total_steps * 100)
    
    if request.method == 'POST':
        save_settings(request.referrer, request.form)

    data = retrieve_settings(name)

    print(f"data retrieved for {name}: {data}")

    plex_valid, tmdb_valid = check_minimum_settings()
    
    if name == '999-final' or name == '999-danger':
        return build_config(title=title, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)
    else:
        return render_template(name + '.html', title=title, data=data, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress, plex_valid=plex_valid, tmdb_valid=tmdb_valid)


def build_config(title, template_list, next_page, prev_page, curr_page, progress):
    sections = get_template_list(app)
    section_names = [section[0].rsplit('.html', 1)[0] for section in sections]

    config_data = {}
    for index, section in enumerate(section_names):
        section_data = retrieve_settings(section)

        if section in section_data:
            config_data[section] = section_data[section]
        else:
            config_data[section] = section_data

    # Generate ASCII art
    ascii_arts = {
        'kometa': add_border_to_ascii_art(pyfiglet.figlet_format('KOMETA')),
        'settings': add_border_to_ascii_art(pyfiglet.figlet_format('GlobalSettings')),
        'webhooks': add_border_to_ascii_art(pyfiglet.figlet_format('Webhooks')),
        'plex': add_border_to_ascii_art(pyfiglet.figlet_format('Plex')),
        'tmdb': add_border_to_ascii_art(pyfiglet.figlet_format('TMDb')),
        'tautulli': add_border_to_ascii_art(pyfiglet.figlet_format('Tautulli')),
        'github': add_border_to_ascii_art(pyfiglet.figlet_format('Github')),
        'omdb': add_border_to_ascii_art(pyfiglet.figlet_format('OMDb')),
        'mdblist': add_border_to_ascii_art(pyfiglet.figlet_format('MDBList')),
        'notifiarr': add_border_to_ascii_art(pyfiglet.figlet_format('Notifiarr')),
        'gotify': add_border_to_ascii_art(pyfiglet.figlet_format('Gotify')),
        'anidb': add_border_to_ascii_art(pyfiglet.figlet_format('AniDb')),
        'radarr': add_border_to_ascii_art(pyfiglet.figlet_format('Radarr')),
        'sonarr': add_border_to_ascii_art(pyfiglet.figlet_format('Sonarr')),
        'trakt': add_border_to_ascii_art(pyfiglet.figlet_format('Trakt')),
        'mal': add_border_to_ascii_art(pyfiglet.figlet_format('MAL'))
    }

    header_comment = (
        "### We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. VSC will also leverage the above link to enhance Kometa yml edits."
    )

    # Configure the YAML instance
    yaml.default_flow_style = False
    yaml.sort_keys = False

    # Prepare the final YAML content
    yaml_content = (
        '# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json\n\n'
        f"{ascii_arts['kometa']}\n\n"
        f"{header_comment}\n\n"
        "libraries:\n\n"
    )

    def dump_section(title, data):
        # Convert 'true' and 'false' strings to boolean values
        for key, value in data.items():
            if value == 'true':
                data[key] = True
            elif value == 'false':
                data[key] = False
        
        # Remove 'valid' key if present
        data = {k: v for k, v in data.items() if k != 'valid'}

        with io.StringIO() as stream:
            yaml.dump(data, stream)
            return f"{title}\n{stream.getvalue().strip()}\n\n"

    ordered_sections = [
        ('settings', '150-settings'),
        ('webhooks', '140-webhooks'),
        ('plex', '010-plex'),
        ('tmdb', '020-tmdb'),
        ('tautulli', '030-tautulli'),
        ('github', '040-github'),
        ('omdb', '050-omdb'),
        ('mdblist', '060-mdblist'),
        ('notifiarr', '070-notifiarr'),
        ('gotify', '080-gotify'),
        ('anidb', '090-anidb'),
        ('radarr', '100-radarr'),
        ('sonarr', '110-sonarr'),
        ('trakt', '120-trakt'),
        ('mal', '130-mal')
    ]

    for section_name, section_key in ordered_sections:
        section_art = ascii_arts.get(section_name)
        if section_art:
            yaml_content += dump_section(section_art, config_data[section_key])

    # Store the final YAML content in the session
    yaml_content = yaml_content.replace("'true'", "true")
    yaml_content = yaml_content.replace("'false'", "false")
    
    print(f"config_data:{config_data}")
    print("==================================================\n")
    print(f"yaml_content:{yaml_content}")
    print("==================================================\n")

    try:
        jsonschema.validate(instance=config_data, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        flash(f'Validation error: {e.message}', 'danger')
        return render_template('999-danger.html', title=title, yaml_content=yaml_content, validation_error=e, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)

    # Render the final step template with the YAML content
    return render_template('999-final.html', title=title, yaml_content=yaml_content, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)


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


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
