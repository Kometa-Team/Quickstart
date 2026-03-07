import ipaddress
import re
from urllib.parse import urlparse

URL_KEY_RE = re.compile(r"(^|[_-])url([_-]|$)")
BOOLEAN_TEXT_VALUES = {"true", "false", "on", "off", "yes", "no", "0", "1"}


def is_url_key(key):
    if not key:
        return False
    return bool(URL_KEY_RE.search(str(key)))


def is_placeholder(value):
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"http://", "https://"}


def is_boolean_value(value):
    if isinstance(value, bool):
        return True
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in BOOLEAN_TEXT_VALUES


def _is_local_address(hostname):
    host = str(hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def validate_url(value, allow_local=True):
    if value is None:
        return True, None
    text = str(value).strip()
    if text == "":
        return True, None
    if is_placeholder(text):
        return False, "URL is incomplete."
    parsed = urlparse(text)
    if not parsed.scheme or parsed.scheme not in {"http", "https"}:
        return False, "URL must start with http:// or https://."
    if not parsed.netloc:
        return False, "URL is missing a hostname."
    if parsed.netloc.endswith(":"):
        return False, "URL port is missing after ':'"
    try:
        if parsed.port is not None:
            if parsed.port < 1 or parsed.port > 65535:
                return False, "URL port must be between 1 and 65535."
    except ValueError:
        return False, "URL port must be between 1 and 65535."
    hostname = parsed.hostname
    if not hostname:
        return False, "URL is missing a hostname."
    if not is_valid_hostname(hostname):
        return False, "URL hostname is invalid."
    if not allow_local and _is_local_address(hostname):
        return False, "URL hostname must be a public address."
    return True, None


def is_valid_hostname(hostname):
    host = str(hostname).lower()
    if not host:
        return False
    if host == "localhost":
        return True
    if host.startswith(".") or host.endswith("."):
        return False
    if ".." in host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    labels = host.split(".")
    for label in labels:
        if not 1 <= len(label) <= 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not re.match(r"^[a-z0-9-]+$", label):
            return False
    if len(labels) > 1:
        tld = labels[-1]
        if len(tld) < 2 or len(tld) > 63:
            return False
        if not re.search(r"[a-z]", tld):
            return False
    return True


def validate_payload(payload):
    errors = []
    if payload is None:
        return errors

    items = payload.items() if isinstance(payload, dict) else []
    if hasattr(payload, "getlist"):
        items = []
        for key in payload.keys():
            values = payload.getlist(key)
            if not values:
                items.append((key, ""))
            elif len(values) == 1:
                items.append((key, values[0]))
            else:
                for val in values:
                    items.append((key, val))

    for key, value in items:
        if not is_url_key(key):
            continue
        if is_boolean_value(value):
            continue
        valid, message = validate_url(value)
        if not valid:
            errors.append(f"{key}: {message}")
    return errors
