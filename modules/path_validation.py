import os
import re
import sys

from flask import current_app as app

from modules import helpers

WINDOWS_INVALID_CHARS = set('<>:"|?*')
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def get_platform_key():
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def _is_absolute_path(path, platform_key):
    if platform_key == "windows":
        return bool(re.match(r"^[A-Za-z]:[\\/]", path)) or path.startswith("\\\\") or path.startswith("//")
    return path.startswith("/")


def _has_control_chars(path):
    return any(ord(ch) < 32 for ch in path)


def _has_invalid_windows_chars(path):
    for idx, ch in enumerate(path):
        if ch in WINDOWS_INVALID_CHARS:
            if ch == ":" and idx == 1 and re.match(r"^[A-Za-z]:", path):
                continue
            return True
    return False


def _windows_segment_invalid(segment):
    if not segment:
        return False
    if segment in {".", ".."}:
        return True
    if segment.endswith(" ") or segment.endswith("."):
        return True
    base = segment.split(".")[0].upper()
    return base in WINDOWS_RESERVED_NAMES


def _validate_windows(path):
    if _has_control_chars(path):
        return False, "Contains control characters."
    if _has_invalid_windows_chars(path):
        return False, "Contains invalid characters for Windows paths."
    segments = re.split(r"[\\/]+", path)
    for segment in segments:
        if _windows_segment_invalid(segment):
            return False, "Contains a reserved or invalid Windows path segment."
    return True, None


def _validate_posix(path):
    if _has_control_chars(path):
        return False, "Contains control characters."
    if "\x00" in path:
        return False, "Contains null characters."
    return True, None


def validate_path(value, rule, platform_key=None):
    if value is None:
        return True, None
    if isinstance(value, (bool, int, float)):
        return True, None

    value = str(value).strip()
    if value == "":
        return True, None
    if value.lower() in ("none", "null"):
        return True, None

    platform_key = platform_key or get_platform_key()

    if not rule.get("allow_relative", False) and not _is_absolute_path(value, platform_key):
        return False, "Path must be absolute."

    if platform_key == "windows":
        valid, message = _validate_windows(value)
    else:
        valid, message = _validate_posix(value)
    if not valid:
        return False, message

    if rule.get("must_exist"):
        exists = os.path.exists(value)
        if not exists:
            return False, "Path does not exist."

        mode = rule.get("mode")
        if mode == "input_file" and not os.path.isfile(value):
            return False, "Path must point to an existing file."
        if mode == "input_dir" and not os.path.isdir(value):
            return False, "Path must point to an existing directory."

    return True, None


def load_rules():
    try:
        rules_data = helpers.load_quickstart_config("path_validation.json")
        return rules_data.get("rules", []) if isinstance(rules_data, dict) else []
    except Exception as e:
        if app and app.config.get("QS_DEBUG"):
            helpers.ts_log(f"Failed to load path_validation.json: {e}", level="ERROR")
    return []


def _iter_payload_items(payload):
    if hasattr(payload, "getlist"):
        for key in payload.keys():
            values = payload.getlist(key)
            if not values:
                yield key, ""
            elif len(values) == 1:
                yield key, values[0]
            else:
                for item in values:
                    yield key, item
        return

    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key, value


def _match_rule_for_key(key, rules):
    for rule in rules:
        rule_id = rule.get("id")
        if not rule_id:
            continue
        if key == rule_id or str(key).endswith(f"-{rule_id}"):
            return rule
    return None


def validate_payload(payload, platform_key=None):
    errors = []
    rules = load_rules()
    if not rules:
        return errors

    platform_key = platform_key or get_platform_key()

    for key, value in _iter_payload_items(payload):
        rule = _match_rule_for_key(key, rules)
        if not rule:
            continue
        valid, message = validate_path(value, rule, platform_key)
        if not valid:
            label = rule.get("label") or rule.get("id", "Path")
            errors.append(f"{label}: {message}")

    return errors
