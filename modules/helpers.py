import os

def build_oauth_dict(source, form_data):
    data = {
        source : {
            'authentication' : {}
        }
    }
    for key in form_data:
        final_key = key.replace(source + '_', '', 1)
        value = form_data[key]

        if (final_key == 'client_id') or (final_key == 'client_secret') or (final_key == 'pin'):
            data[source][final_key] = value
        else:
            if (final_key != 'url'):
                data[source]['authentication'][final_key] = value

    return(data)


def build_simple_dict(source, form_data):
    data = {
        source: {}
    }
    for key in form_data:
        final_key = key.replace(source + '_', '', 1)
        value = form_data[key]

        try:
            value = int(value)
        except ValueError:
            try:
                if value.lower() == 'on':
                    value = bool(value)
            except ValueError:
                value = value

        data[source][final_key] = value

    # Special handling for run_order to split and clean it into a list
    if 'run_order' in data[source]:
        run_order = data[source]['run_order']
        run_order = [item.strip() for item in run_order.split() if item.strip()]
        data[source]['run_order'] = run_order

    return data



def build_config_dict(source, form_data):
    if (source == 'trakt') or (source == 'mal') :
        return build_oauth_dict(source, form_data)
    else:
        return build_simple_dict(source, form_data)


def get_template_list(app):
    templates_dir = os.path.join(app.root_path, 'templates')
    templates = []
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if (
                file.endswith('.html')
                and file != '000-base.html'
                and file[:3].isdigit()
                and file[3] == '-'
                and not file.startswith('999-')
            ):  # Ensure it starts with ###- and does not start with 999-
                # Remove the leading numbers, dash, and '.html' extension
                formatted_name = file.split('-', 1)[1].rsplit('.', 1)[0]
                # Capitalize the first letter
                formatted_name = formatted_name.capitalize()
                templates.append((file, formatted_name))
    # Sort the templates based on the numeric prefix
    templates.sort(key=lambda x: int(x[0].split('-')[0]))
    return templates