import os
from flask import current_app as app
from pathlib import Path

def build_oauth_dict(source, form_data):
    data = {
        source : {
            'authorization' : {}
        }
    }
    for key in form_data:
        final_key = key.replace(source + '_', '', 1)
        value = form_data[key]

        if (final_key == 'client_id') or (final_key == 'client_secret') or (final_key == 'pin'):
            data[source][final_key] = value
        elif final_key == 'validated':
            data[final_key] = value
        else:
            if (final_key != 'url'):
                data[source]['authorization'][final_key] = value

    return(data)


def build_simple_dict(source, form_data):
    data = {
        source: {}
    }
    for key in form_data:
        final_key = key.replace(source + '_', '', 1)
        value = form_data[key]

        if value is not None and not isinstance(value, bool):
            try:
                value = int(value)
            except ValueError:
                value = value

        if final_key == 'validated':
            data[final_key] = value
        else:
            data[source][final_key] = value


    # Special handling for run_order to split and clean it into a list
    if 'run_order' in data[source]:
        run_order = data[source]['run_order']
        if run_order is not None:
            run_order = [item.strip() for item in run_order.split() if item.strip()]
        else:
            run_order = ['operations', 'metadata', 'collections', 'overlays']
        data[source]['run_order'] = run_order

    return data


def build_config_dict(source, form_data):
    if (source == 'trakt') or (source == 'mal') :
        return build_oauth_dict(source, form_data)
    else:
        return build_simple_dict(source, form_data)


def belongs_in_template_list(file):
    return (file.endswith('.html') 
            and file != '000-base.html'
            and file[:3].isdigit()
            and file[3] == '-'
            and not file.startswith('999-'))

def user_visible_name(raw_name):
    if raw_name == 'tmdb' or raw_name == 'omdb':
        # Capitalize the whole thing
        formatted_name = raw_name.upper()
    elif raw_name == 'mal':
        formatted_name = 'MyAnimeList'
    elif raw_name == 'mdblist':
        formatted_name = 'MDBList'
    elif raw_name == 'anidb':
        formatted_name = 'AniDB'
    elif raw_name == 'playlist_files':
        formatted_name = 'Playlist'
    elif raw_name == 'final':
        formatted_name = 'Final Validation'
    else:
        # Capitalize the first letter
        formatted_name = raw_name.capitalize()

    return formatted_name

def booler(thing):
    if type(thing) == str:
        thing = eval(thing)
    return bool(thing)

def get_bits(file):
    file_stem = Path(file).stem
    bits = file_stem.split('-')
    num = bits[0]
    raw_name = bits[1]

    return file_stem, num, raw_name

def get_next(file_list, file):
    stem, cmp_num, b = get_bits(file)
    cmp_num = int(cmp_num)
    if stem == '900-final':
        return ''

    for item in file_list:
        stem, this_num, b = get_bits(item)
        this_num = int(this_num)
        if this_num > cmp_num:
            return stem

    return '900-final'

def template_record(file, prev, next):
    rec = {}
    file_stem, num, raw_name = get_bits(file)
    rec['num'] = num
    rec['file'] = file
    rec['stem'] = file_stem
    rec['name'] = user_visible_name(raw_name)
    rec['raw_name'] = raw_name
    rec['next'] = next
    rec['prev'] = prev

    return rec

def get_menu_list():
    templates_dir = os.path.join(app.root_path, 'templates')
    file_list = sorted(item for item in os.listdir(templates_dir) if os.path.isfile(os.path.join(templates_dir, item)))
    final_list = []

    for file in file_list:
        if belongs_in_template_list(file):
            file_stem, num, raw_name = get_bits(file)
            final_list.append((file, user_visible_name(raw_name)))

    return final_list

def get_template_list():
    templates_dir = os.path.join(app.root_path, 'templates')
    file_list = sorted(item for item in os.listdir(templates_dir) if os.path.isfile(os.path.join(templates_dir, item)))

    templates = {}

    prev_item = '001-start'
    for file in file_list:
        if belongs_in_template_list(file):
            next = get_next(file_list, file)
            prev = prev_item
            rec = template_record(file, prev, next)
            templates[rec['num']] = rec
            prev_item = rec['stem']

    return templates

