from flask import Flask, render_template, request, flash, jsonify
import yaml
import os
from dotenv import load_dotenv
from plexapi.server import PlexServer
import pyfiglet
import iso639
import iso3166

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")


def add_border_to_ascii_art(art):
    lines = art.split('\n')
    width = max(len(line) for line in lines)
    border_line = "#" * (width + 4)
    bordered_art = [border_line] + [f"# {line.ljust(width)} #" for line in lines] + [border_line]
    return '\n'.join(bordered_art)


def validate_iso3166_1(code):
    try:
        country = iso3166.countries.get(code.upper())
        if country:
            return country.alpha2
        else:
            return None
    except KeyError:
        return None


def validate_iso639_1(code):
    if len(code) == 2 and iso639.languages.get(alpha2=code.lower()):
        return code.lower()
    return None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/validate_plex', methods=['POST'])
def validate_plex():
    data = request.json
    plex_url = data.get('plex_url')
    plex_token = data.get('plex_token')

    # Validate Plex URL and Token
    try:
        plex = PlexServer(plex_url, plex_token)

        # Fetch Plex settings
        srv_settings = plex.settings

        # Retrieve db_cache from Plex settings
        db_cache_setting = srv_settings.get("DatabaseCacheSize")

        # Get the value of db_cache
        db_cache = db_cache_setting.value

        # Log db_cache value
        app.logger.info(f"db_cache returned from Plex: {db_cache}")

        # If db_cache is None, treat it as invalid
        if db_cache is None:
            raise Exception("Unable to retrieve db_cache from Plex settings.")

    except Exception as e:
        app.logger.error(f'Error validating Plex server: {str(e)}')
        flash(f'Invalid Plex URL or Token: {str(e)}', 'error')
        return jsonify({'valid': False, 'error': f'Invalid Plex URL or Token: {str(e)}'})

    # If PlexServer instance is successfully created and db_cache is retrieved, return success response
    return jsonify({
        'valid': True,
        'db_cache': db_cache  # Send back the integer value of db_cache
    })

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
    