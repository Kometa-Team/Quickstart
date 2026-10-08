"""Plex browser approval, with pending PINs kept in the server-side session."""

import time
import uuid
from urllib.parse import urlencode, urlparse

import requests
from flask import Blueprint, current_app, jsonify, request, session
from plexapi.myplex import MyPlexAccount

from modules import persistence

bp = Blueprint("plex_auth_routes", __name__)
PLEX_API_URL = "https://plex.tv/api/v2"
PRODUCT = "Kometa Quickstart"


@bp.after_request
def prevent_auth_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _headers():
    return {
        "X-Plex-Client-Identifier": session["plex_client_id"],
        "X-Plex-Product": PRODUCT,
        "X-Plex-Version": (current_app.config.get("VERSION_CHECK") or {}).get("local_version") or "1.0",
        "X-Plex-Platform": "Web",
        "X-Plex-Platform-Version": "1.0",
        "X-Plex-Device": "Web",
        "X-Plex-Device-Name": PRODUCT,
        "Accept": "application/json",
    }


def _error(message, status):
    return jsonify({"error": message}), status


def _attempt(data):
    attempt = session.get("plex_auth")
    if not attempt or data.get("attempt_id") != attempt["attempt_id"]:
        return None, _error("This Plex sign-in is no longer active. Please try again.", 409)
    if data.get("config_name") != attempt["config_name"] or session.get("config_name") != attempt["config_name"]:
        return None, _error("The selected configuration changed. Please start Plex sign-in again.", 409)
    if time.time() >= attempt["expires_at"]:
        session.pop("plex_auth", None)
        return None, _error("Plex sign-in expired. Please try again.", 410)
    return attempt, None


def _approved_attempt(data):
    attempt, error = _attempt(data)
    if error:
        return None, error
    if not attempt.get("result", {}).get("authenticated"):
        return None, _error("Complete Plex sign-in before selecting a server.", 409)
    return attempt, None


def _owned_servers(attempt):
    account = MyPlexAccount(token=attempt["result"]["token"], timeout=8)
    return sorted(
        (resource for resource in account.resources() if resource.owned and "server" in resource.provides and resource.clientIdentifier),
        key=lambda resource: (resource.name or "").casefold(),
    )


@bp.route("/plex-auth/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    config_name = session.get("config_name")
    if not config_name or data.get("config_name") != config_name:
        return _error("The selected configuration changed. Reload the Plex page and try again.", 409)

    session.pop("plex_auth", None)
    if "plex_client_id" not in session:
        session["plex_client_id"] = str(uuid.uuid4())
    try:
        response = requests.post(f"{PLEX_API_URL}/pins", headers=_headers(), params={"strong": "true"}, timeout=10, allow_redirects=False)
        response.raise_for_status()
        pin = response.json()
        pin_id = int(pin["id"])
        code = pin["code"]
        if not isinstance(code, str) or not code:
            raise ValueError("Missing PIN code")
        expires_in = max(1, min(int(pin.get("expiresIn", 600)), 3600))
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return _error("Unable to start Plex sign-in. Please try again.", 502)

    attempt_id = str(uuid.uuid4())
    session["plex_auth"] = {"attempt_id": attempt_id, "pin_id": pin_id, "config_name": config_name, "expires_at": time.time() + expires_in}
    # Polling does not require a callback URL reachable from Plex or the browser.
    headers = _headers()
    context_headers = {"product": "Product", "version": "Version", "platform": "Platform", "platformVersion": "Platform-Version", "device": "Device", "deviceName": "Device-Name"}
    auth_url = "https://app.plex.tv/auth#?" + urlencode(
        {"clientID": headers["X-Plex-Client-Identifier"], "code": code, **{f"context[device][{field}]": headers[f"X-Plex-{header}"] for field, header in context_headers.items()}}
    )
    return jsonify({"attempt_id": attempt_id, "auth_url": auth_url, "expires_in": expires_in})


@bp.route("/plex-auth/check", methods=["POST"])
def check():
    data = request.get_json(silent=True) or {}
    attempt, error = _attempt(data)
    if error:
        return error
    if "result" in attempt:
        return jsonify(attempt["result"])
    try:
        response = requests.get(f"{PLEX_API_URL}/pins/{attempt['pin_id']}", headers=_headers(), timeout=10, allow_redirects=False)
        if response.status_code in (404, 410):
            session.pop("plex_auth", None)
            return _error("Plex sign-in expired. Please try again.", 410)
        response.raise_for_status()
        token = response.json().get("authToken")
        if not token:
            return jsonify({"authenticated": False})
        if not isinstance(token, str):
            raise ValueError("Invalid token")
        user_response = requests.get(f"{PLEX_API_URL}/user", headers={**_headers(), "X-Plex-Token": token}, timeout=10, allow_redirects=False)
        user_response.raise_for_status()
        user = user_response.json()
        username = user.get("username") or user.get("title") or "Plex account"
    except (requests.RequestException, ValueError, AttributeError):
        return _error("Unable to check Plex approval. Retrying; you can also cancel and try again.", 502)

    try:
        persistence.update_stored_plex_token(attempt["config_name"], token)
    except Exception:
        return _error("Unable to save the Plex token. Please try again.", 500)

    result = {"authenticated": True, "token": token, "username": username}
    session["plex_auth"] = {**attempt, "result": result}
    return jsonify(result)


@bp.route("/plex-auth/servers", methods=["POST"])
def servers():
    attempt, error = _approved_attempt(request.get_json(silent=True) or {})
    if error:
        return error
    try:
        resources = _owned_servers(attempt)
        return jsonify({"servers": [{"id": resource.clientIdentifier, "name": resource.name or "Plex server"} for resource in resources]})
    except Exception:
        # Provider exceptions can include connection URLs and credentials.
        return _error("Unable to discover Plex servers. Enter your server URL, then validate.", 502)


@bp.route("/plex-auth/connect", methods=["POST"])
def connect():
    data = request.get_json(silent=True) or {}
    attempt, error = _approved_attempt(data)
    if error:
        return error
    server_id = data.get("server_id")
    if not isinstance(server_id, str) or not server_id:
        return _error("Select a Plex server.", 400)
    try:
        resource = next((resource for resource in _owned_servers(attempt) if resource.clientIdentifier == server_id), None)
        if resource is None:
            return _error("This server is not owned by the signed-in Plex account.", 404)
        # PlexAPI probes from QS, prefers local/HTTPS, and excludes relay URLs here.
        server = resource.connect(timeout=3, locations=["local", "remote"])
        url = server._baseurl
        parsed = urlparse(url)
        if (
            server.machineIdentifier != server_id
            or parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Unexpected Plex server connection")
        return jsonify({"url": url, "name": resource.name or "Plex server"})
    except Exception:
        return _error("Quickstart could not connect to this Plex server. Enter your server URL, then validate.", 502)


@bp.route("/plex-auth/cancel", methods=["POST"])
def cancel():
    data = request.get_json(silent=True) or {}
    attempt = session.get("plex_auth")
    if attempt and data.get("attempt_id") == attempt["attempt_id"]:
        session.pop("plex_auth", None)
    return jsonify({"cancelled": True})
