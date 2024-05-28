from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, session, send_file
import jsonschema
import requests
import io
import yaml
import os
from dotenv import load_dotenv
from plexapi.server import PlexServer
import pyfiglet
import secrets

from modules.validations import validate_iso3166_1, validate_iso639_1, validate_plex_server, validate_tautulli_server, validate_trakt_server, validate_mal_server, validate_anidb_server, validate_gotify_server
from modules.output import add_border_to_ascii_art
from modules.helpers import build_config_dict, get_template_list

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


@app.route('/clear_session', methods=['POST'])
def clear_session():
    session.clear()
    flash('Session cleared successfully.', 'success')
    return redirect(url_for('start'))


@app.route('/step/<name>', methods=['GET', 'POST'])
def step(name):
    template_list = get_template_list(app)
    special_cases = {'start': 'Start', '999-final': 'Final', '999-danger': 'Danger'}
    
    if name in special_cases:
        curr_page = special_cases[name]
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
        next_page = template_list[current_index + 1][0].rsplit('.html', 1)[0] if current_index + 1 < len(template_list) else "999-final"
        prev_page = template_list[current_index - 1][0].rsplit('.html', 1)[0] if current_index > 0 else "start"
        
        # Calculate progress
        total_steps = len([file for file, _ in template_list if not file.startswith('999-')]) + 1  # Exclude 999-*.html but count as one step
        progress = (current_index + 1) / total_steps * 100
    
    if request.method == 'POST':
        source = request.referrer.split("/")[-1]
        source = source.split("?")[0]
        source = source.split('-')[-1]

        data = build_config_dict(source, request.form)

        session[source] = data[source]

    code_verifier = secrets.token_urlsafe(100)[:128]

    if name == '999-final' or name == '999-danger':
        return build_config(code_verifier=code_verifier, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)
    else:
        return render_template(name + '.html', code_verifier=code_verifier, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)


def build_config(code_verifier, template_list, next_page, prev_page, curr_page, progress):

    # Combine data from all steps (retrieve from session or other storage)
    config_data = {
        'settings': session.get('settings'),
        'webhooks': session.get('webhooks'),
        'plex': session.get('plex'),
        'tmdb': session.get('tmdb'),
        'tautulli': session.get('tautulli'),
        'github': session.get('github'),
        'omdb': session.get('omdb'),
        'mdblist': session.get('mdblist'),
        'notifiarr': session.get('notifiarr'),
        'gotify': session.get('gotify'),
        'anidb': session.get('anidb'),
        'radarr': session.get('radarr'),
        'sonarr': session.get('sonarr'),
        'trakt': session.get('trakt'),
        'mal': session.get('mal'),
        # Add other sections as needed
    }

    # Generate ASCII art
    kometa_art = add_border_to_ascii_art(pyfiglet.figlet_format('KOMETA'))
    settings_art = add_border_to_ascii_art(pyfiglet.figlet_format('GlobalSettings'))
    webhooks_art = add_border_to_ascii_art(pyfiglet.figlet_format('Webhooks'))
    plex_art = add_border_to_ascii_art(pyfiglet.figlet_format('Plex'))
    tmdb_art = add_border_to_ascii_art(pyfiglet.figlet_format('TMDb'))
    tautulli_art = add_border_to_ascii_art(pyfiglet.figlet_format('Tautulli'))
    github_art = add_border_to_ascii_art(pyfiglet.figlet_format('Github'))
    omdb_art = add_border_to_ascii_art(pyfiglet.figlet_format('OMDb'))
    mdblist_art = add_border_to_ascii_art(pyfiglet.figlet_format('MDBList'))
    notifiarr_art = add_border_to_ascii_art(pyfiglet.figlet_format('Notifiarr'))
    gotify_art = add_border_to_ascii_art(pyfiglet.figlet_format('Gotify'))
    anidb_art = add_border_to_ascii_art(pyfiglet.figlet_format('AniDb'))
    radarr_art = add_border_to_ascii_art(pyfiglet.figlet_format('Radarr'))
    sonarr_art = add_border_to_ascii_art(pyfiglet.figlet_format('Sonarr'))
    trakt_art = add_border_to_ascii_art(pyfiglet.figlet_format('Trakt'))
    mal_art = add_border_to_ascii_art(pyfiglet.figlet_format('MAL'))
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
        f"{settings_art}\n"
        f"{yaml.dump({'settings': config_data['settings']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{webhooks_art}\n"
        f"{yaml.dump({'webhooks': config_data['webhooks']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{plex_art}\n"
        f"{yaml.dump({'plex': config_data['plex']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{tmdb_art}\n"
        f"{yaml.dump({'tmdb': config_data['tmdb']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{tautulli_art}\n"
        f"{yaml.dump({'tautulli': config_data['tautulli']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{github_art}\n"
        f"{yaml.dump({'github': config_data['github']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{omdb_art}\n"
        f"{yaml.dump({'omdb': config_data['omdb']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{mdblist_art}\n"
        f"{yaml.dump({'mdblist': config_data['mdblist']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{notifiarr_art}\n"
        f"{yaml.dump({'notifiarr': config_data['notifiarr']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{gotify_art}\n"
        f"{yaml.dump({'gotify': config_data['gotify']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{anidb_art}\n"
        f"{yaml.dump({'anidb': config_data['anidb']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{radarr_art}\n"
        f"{yaml.dump({'radarr': config_data['radarr']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{sonarr_art}\n"
        f"{yaml.dump({'sonarr': config_data['sonarr']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{trakt_art}\n"
        f"{yaml.dump({'trakt': config_data['trakt']}, default_flow_style=False, sort_keys=False)}\n\n"
        f"{mal_art}\n"
        f"{yaml.dump({'mal': config_data['mal']}, default_flow_style=False, sort_keys=False)}\n\n"
    )

    # Store the final YAML content in the session
    session['yaml_content'] = yaml_content
    try:
        jsonschema.validate(instance=config_data, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        print(config_data)
        flash(f'Validation error: {e.message}', 'danger')
        return render_template('999-danger.html', yaml_content=yaml_content, validation_error=e, code_verifier=code_verifier, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)

    # Render the final step template with the YAML content
    return render_template('999-final.html', yaml_content=yaml_content, code_verifier=code_verifier, template_list=template_list, next_page=next_page, prev_page=prev_page, curr_page=curr_page, progress=progress)


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
