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
        source : {}
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

    return(data)

def build_config_dict(source, form_data):
    if (source == 'trakt') or (source == 'mal') :
        return build_oauth_dict(source, form_data)
    else:
        return build_simple_dict(source, form_data)
