"""Form-building utilities extracted from the original helpers.py monolith."""

from modules.helpers._constants import STRING_FIELDS


def enforce_string_fields(data, enforce=False):
    """Ensure specified fields in a dictionary are of type string."""
    if isinstance(data, dict):
        for k, v in data.items():
            data[k] = enforce_string_fields(v, enforce=k in STRING_FIELDS)
    elif isinstance(data, list):
        return [enforce_string_fields(v, enforce=enforce) for v in data]
    elif enforce:
        return str(data)
    return data


def build_oauth_dict(source, form_data):
    data = {source: {"authorization": {}}}
    for key in form_data:
        final_key = key.replace(source + "_", "", 1)
        value = form_data[key]

        if final_key in [
            "client_id",
            "client_secret",
            "pin",
            "force_refresh",
            "cache_expiration",
            "localhost_url",
        ]:
            data[source][final_key] = value  # Store outside authorization
        elif final_key in ["validated", "validated_at"]:
            data[final_key] = value
        else:
            if final_key != "url":
                data[source]["authorization"][final_key] = value  # Everything else goes into authorization

    return data


def build_simple_dict(source, form_data):
    data = {source: {}}
    for key in form_data:
        final_key = key.replace(source + "_", "", 1)  # Retain the original key transformation logic
        value = form_data[key]

        # Handle lists explicitly (e.g., asset_directory)
        if isinstance(value, list):
            data[source][final_key] = value
        elif isinstance(value, dict):
            # Keep valid nested dicts (like template_variables) untouched
            data[source][final_key] = value
        else:
            # Handle individual scalar values
            if value is not None and not isinstance(value, bool):
                if final_key.endswith("-library") or final_key == "libraries":
                    # Library display names from Plex — preserve exactly (leading/trailing spaces are significant)
                    pass
                elif final_key.endswith("_section"):
                    # Preserve as string to avoid stripping leading zeros
                    value = value.strip() if isinstance(value, str) else value
                else:
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        value = value.strip() if isinstance(value, str) else value

            # Assign the value to the appropriate key
            if final_key in ["validated", "validated_at"]:
                data[final_key] = value
            else:
                data[source][final_key] = value

    # Handle run_order specially
    if "run_order" in data[source]:
        run_order = data[source]["run_order"]
        if run_order is not None and isinstance(run_order, str):
            run_order = [item.strip() for item in run_order.split() if item.strip()]
        else:
            run_order = ["operations", "metadata", "collections", "overlays"]
        data[source]["run_order"] = run_order

    return data


def build_config_dict(source, form_data):
    if source in ["trakt", "mal"]:
        return build_oauth_dict(source, form_data)
    else:
        return build_simple_dict(source, form_data)
