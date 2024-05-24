from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session, send_file
import jsonschema
import yaml
import requests
import io
import yaml
import os
from dotenv import load_dotenv
from plexapi.server import PlexServer
import pyfiglet

from modules.validations import validate_iso3166_1, validate_iso639_1, validate_plex_server, validate_tautulli_server, validate_trakt_server, validate_gotify_server
from modules.output import add_border_to_ascii_art
from modules.helpers import build_config_dict

# Load JSON Schema
# probably ought to load this from github
with open('json-schema/config-schema.json', 'r') as file:
    schema = yaml.safe_load(file)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

@app.route('/')
def start():
    return render_template('start.html')

@app.route('/step-1')
def index():
    return render_template('index.html')

@app.route('/step/<name>', methods=['GET', 'POST'])
def step(name):
    if request.method == 'POST':
        # get source from referrer
        source = request.referrer.split("/")[-1]
        source = source.split("?")[0]
        source = source.split('-')[-1]

        data = build_config_dict(source, request.form)

        session[source] = data[source]

    template = name + '.html'

    return render_template(template)

@app.route('/999-final', methods=['GET', 'POST'])
def final_step():
    # Combine data from all steps (retrieve from session or other storage)
    config_data = {
        'plex': session.get('plex'),
        'tmdb': session.get('tmdb'),
        'tautulli': session.get('tautulli'),
        'github': session.get('github'),
        'omdb': session.get('omdb'),
        'mdblist': session.get('mdblist'),
        'notifiarr': session.get('notifiarr'),
        # 'gotify': session.get('gotify'),
        # 'anidb': session.get('anidb'),
        'radarr': session.get('radarr'),
        'sonarr': session.get('sonarr'),
        'trakt': session.get('trakt'),
        # 'mal': session.get('mal'),
        # Add other sections as needed
    }

    # Generate ASCII art
    kometa_art = add_border_to_ascii_art(pyfiglet.figlet_format('KOMETA'))
    plex_art = add_border_to_ascii_art(pyfiglet.figlet_format('Plex'))
    tmdb_art = add_border_to_ascii_art(pyfiglet.figlet_format('TMDb'))
    tautulli_art = add_border_to_ascii_art(pyfiglet.figlet_format('Tautulli'))
    github_art = add_border_to_ascii_art(pyfiglet.figlet_format('Github'))
    omdb_art = add_border_to_ascii_art(pyfiglet.figlet_format('OMDb'))
    mdblist_art = add_border_to_ascii_art(pyfiglet.figlet_format('MDBList'))
    notifiarr_art = add_border_to_ascii_art(pyfiglet.figlet_format('Notifiarr'))
    radarr_art = add_border_to_ascii_art(pyfiglet.figlet_format('Radarr'))
    sonarr_art = add_border_to_ascii_art(pyfiglet.figlet_format('Sonarr'))
    trakt_art = add_border_to_ascii_art(pyfiglet.figlet_format('Trakt'))

    header_comment = (
        "### We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension "
        "and YAML by Red Hat extension. VSC will also leverage the above link to enhance Kometa yml edits."
    )

    # Prepare the final YAML content
    yaml_content = (
        '# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json\n\n'
        f"{kometa_art}\n\n"
        f"{header_comment}\n\n"
        "libraries:\n\n"
        f"{plex_art}\n"
        f"{yaml.dump({'plex': config_data['plex']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{tmdb_art}\n"
        f"{yaml.dump({'tmdb': config_data['tmdb']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{tautulli_art}\n"
        f"{yaml.dump({'tautulli': config_data['tautulli']}, default_flow_style=False, sort_keys=False)}\n"
        f"{github_art}\n"
        f"{yaml.dump({'github': config_data['github']}, default_flow_style=False, sort_keys=False)}\n"
        f"{omdb_art}\n"
        f"{yaml.dump({'omdb': config_data['omdb']}, default_flow_style=False, sort_keys=False)}\n"
        f"{mdblist_art}\n"
        f"{yaml.dump({'mdblist': config_data['mdblist']}, default_flow_style=False, sort_keys=False)}\n"
        f"{notifiarr_art}\n"
        f"{yaml.dump({'notifiarr': config_data['notifiarr']}, default_flow_style=False, sort_keys=False)}\n"
        f"{radarr_art}\n"
        f"{yaml.dump({'radarr': config_data['radarr']}, default_flow_style=False, sort_keys=False)}\n"
        f"{sonarr_art}\n"
        f"{yaml.dump({'sonarr': config_data['sonarr']}, default_flow_style=False, sort_keys=False)}\n"
        f"{trakt_art}\n"
        f"{yaml.dump({'trakt': config_data['trakt']}, default_flow_style=False, sort_keys=False)}\n"
    )

    # Store the final YAML content in the session
    session['yaml_content'] = yaml_content
    try:
        jsonschema.validate(instance=config_data, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        print(config_data)
        flash(f'Validation error: {e.message}', 'danger')
        return render_template('999-danger.html', yaml_content=yaml_content, validation_error=e)
        
    # Render the final step template with the YAML content
    return render_template('999-final.html', yaml_content=yaml_content)

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

@app.route('/validate_anidb', methods=['POST'])
def validate_anidb():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    client = data.get('client')
    clientver = data.get('clientver')

    # AniDB API endpoint
    api_url = "http://api.anidb.net:9001/httpapi"
    
    # Prepare the request parameters
    params = {
        'request': 'hints',
        'user': username,
        'pass': password,
        'protover': '1',
        'client': client,
        'clientver': clientver,
        'type': '1',
    }

    try:
        # Construct the full URL with query parameters
        full_url = f"{api_url}?request=hints&user={username}&pass={password}&protover=1&client={client}&clientver={clientver}&type=1"
        print(f"Full URL: {full_url}")
        
        # Make a GET request to AniDB API
        response = requests.get(api_url, params=params)
        response_text = response.text
        print(f"Response text: {response_text}")
        print(f"Status code: {response.status_code}")

        # Check if the response contains 'hints'
        if 'hints' in response_text:
            print("Response contains 'hints'")
            print("Authentication successful")
            return jsonify({'valid': True})
        elif '<error code="302">' in response_text:
            print("Error: client version missing or invalid")
            return jsonify({'valid': False, 'error': 'Client version missing or invalid'})
        elif '<error code="303">' in response_text:
            print("Error: invalid username or password")
            return jsonify({'valid': False, 'error': 'Invalid username or password'})
        elif '<error code="500">' in response_text:
            print("Error: You have been banned")
            return jsonify({'valid': False, 'error': 'You have been banned(likely for 24 hours)'})
        else:
            print("Authentication failed")
            return jsonify({'valid': False, 'error': 'Authentication failed'})
    
    except requests.exceptions.RequestException as e:
        # Handle request exceptions (e.g., connection error)
        print(f"RequestException: {str(e)}")
        return jsonify({'valid': False, 'error': str(e)})

    return jsonify({'valid': False, 'error': 'Unknown error'})

@app.route('/submit', methods=['POST'])
def submit():
    try:
        # Plex settings
        plex_url = request.form['plex_url']
        plex_token = request.form['plex_token']
        plex_dbcache = int(request.form['plex_dbcache'])
        plex_timeout = int(request.form['plex_timeout'])
        plex_verify_ssl = 'plex_verify_ssl' in request.form
        plex_clean_bundles = 'plex_clean_bundles' in request.form
        plex_empty_trash = 'plex_empty_trash' in request.form
        plex_optimize = 'plex_optimize' in request.form

        # Validate Plex URL and token
        try:
            plex = PlexServer(plex_url, plex_token)
        except Exception as e:
            flash(f'Invalid Plex URL or Token: {str(e)}', 'error')
            return jsonify({'messages': [{'category': 'error', 'text': f'Invalid Plex URL or Token: {str(e)}'}]})

        # TMDb settings
        tmdb_apikey = request.form['tmdb_apikey']
        tmdb_language = request.form['tmdb_language']
        tmdb_region = request.form['tmdb_region']
        tmdb_cache_expiration = int(request.form['tmdb_cache_expiration'])

        # Validate TMDb settings
        valid_language = validate_iso639_1(tmdb_language)
        valid_region = validate_iso3166_1(tmdb_region)

        if not valid_language:
            flash('Invalid language code. Must be a valid ISO 639-1 code.', 'error')
            return jsonify({'messages': [{'category': 'error', 'text': 'Invalid language code. Must be a valid ISO 639-1 code.'}]})

        if not valid_region:
            flash('Invalid region code. Must be a valid ISO 3166-1 code.', 'error')
            return jsonify({'messages': [{'category': 'error', 'text': 'Invalid region code. Must be a valid ISO 3166-1 code.'}]})

        # Prepare configuration dictionary
        config = {
            'plex': {
                'url': plex_url,
                'token': plex_token,
                'timeout': plex_timeout,
                'clean_bundles': plex_clean_bundles,
                'empty_trash': plex_empty_trash,
                'optimize': plex_optimize,
                'db_cache': plex_dbcache,
                'verify_ssl': plex_verify_ssl,
            },
            'tmdb': {
                'apikey': tmdb_apikey,
                'language': valid_language,
                'region': valid_region,
                'cache_expiration': tmdb_cache_expiration
            }
        }

        # Generate ASCII art
        kometa_art = add_border_to_ascii_art(pyfiglet.figlet_format('KOMETA'))
        plex_art = add_border_to_ascii_art(pyfiglet.figlet_format('Plex'))
        tmdb_art = add_border_to_ascii_art(pyfiglet.figlet_format('TMDb'))
        header_comment = "### We highly recommend using Visual Studio Code with indent-rainbow by oderwat extension and YAML by Red Hat extension. VSC will also leverage the above link to enhance Kometa yml edits."

        # Write to config.yml
        with open('config.yml', 'w') as file:
            file.write('# yaml-language-server: $schema=https://raw.githubusercontent.com/Kometa-Team/Kometa/nightly/json-schema/config-schema.json\n\n')
            file.write(f"{kometa_art}\n\n")
            file.write(f"{header_comment}\n\n")
            file.write(f"libraries: \n\n")
            file.write(f"{plex_art}\n")
            yaml.dump({'plex': config['plex']}, file, default_flow_style=False, sort_keys=False)
            file.write("\n\n")
            file.write(f"{tmdb_art}\n")
            yaml.dump({'tmdb': config['tmdb']}, file, default_flow_style=False, sort_keys=False)

        flash('Configuration saved successfully!', 'success')
        return jsonify({'messages': [{'category': 'success', 'text': 'Configuration saved successfully!'}]})

    except Exception as e:
        flash(f'Error saving configuration: {str(e)}', 'error')
        return jsonify({'messages': [{'category': 'error', 'text': f'Error saving configuration: {str(e)}'}]})


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
    