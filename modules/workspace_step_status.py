"""Per-step status derivation for the workspace menu.

Split out of ``modules.workspace_status`` -- this cluster owns the
"convert a DB section row into ok/warn/error/unknown for one menu step"
logic and its three input-presence helpers.

## What lives here

### Input-presence helpers
The workspace menu treats optional steps differently depending on
whether the user has actually put something into them.  These three
helpers form the presence ladder used by ``_derive_step_status``:

* ``_is_nonblank_setting(value)`` -- lowest level: value must be
  truthy, non-blank, and not the strings ``none`` / ``null`` /
  ``false``.
* ``_is_meaningful_optional_status_input(value)`` -- adds a filter to
  skip UI template placeholders (``"Enter your API key"`` etc.).
* ``_has_meaningful_optional_input(template_key, payload)`` --
  dispatch table by ``template_key``: each service has its own set of
  fields (Tautulli URL + apikey, Radarr URL + token, Trakt tokens
  under ``authorization``, etc.) and this function returns True iff
  any of them looks user-configured.

### The main derivation
* ``_derive_step_status(template_key, group, section_rows, config_exists)``
  -- 100-line dispatch that converts one DB row into a step status.
  Handles special cases for ``001-start`` (Kometa install-mode check),
  ``900-kometa`` (always ``warn`` -- it's the final review page),
  ``905-analytics`` / ``910-sponsor`` (always ``ok`` -- purely
  informational), ``027-playlist_files`` (visited-but-empty is OK
  because playlists are opt-in), and the general "validation step"
  path that inspects ``validated`` / ``validation_status`` /
  ``validation_reason`` on the payload.
"""

from __future__ import annotations

from modules import helpers
from modules.kometa_install import (
    KOMETA_INSTALL_MODE_MANAGED,
    canonicalize_kometa_section as _canonicalize_kometa_section,
    validate_saved_kometa_selection as _validate_saved_kometa_selection,
)
from modules.workspace_status_constants import (
    QS_ERROR_REASONS,
    QS_VALIDATION_STEP_KEYS,
    QS_WARN_REASONS,
)


def _is_nonblank_setting(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip()
    if not text:
        return False
    return text.lower() not in {"none", "null", "false"}


def _is_meaningful_optional_status_input(value):
    if not _is_nonblank_setting(value):
        return False
    text = str(value).strip().lower()
    # UI template placeholders can be persisted as defaults; they should not
    # make an optional page look user-configured in the workspace menu
    return not (text.startswith("enter ") and any(token in text for token in ("token", "api key", "url", "client")))


def _has_meaningful_optional_input(template_key, payload):
    if not isinstance(payload, dict):
        return False

    # Playlists intentionally treat pass-through differently (handled in its own branch).
    if template_key == "027-playlist_files":
        return True

    if template_key == "100-anidb":
        anidb = payload.get("anidb", {})
        return isinstance(anidb, dict) and helpers.booler(anidb.get("enable"))

    if template_key == "087-apprise":
        apprise = payload.get("apprise", {})
        if not isinstance(apprise, dict):
            return False
        return _is_meaningful_optional_status_input(apprise.get("location"))

    simple_key_requirements = {
        "030-tautulli": ("tautulli", ("url", "apikey")),
        "040-github": ("github", ("token",)),
        "050-omdb": ("omdb", ("apikey",)),
        "060-mdblist": ("mdblist", ("apikey",)),
        "070-notifiarr": ("notifiarr", ("apikey",)),
        "080-gotify": ("gotify", ("url", "token")),
        "085-ntfy": ("ntfy", ("url", "token", "topic")),
        "088-yamtrack": ("yamtrack", ("url", "username", "password")),
        "090-webhooks": ("webhooks", ("notifiarr", "gotify", "ntfy", "slack", "discord", "webhook", "url")),
        "110-radarr": ("radarr", ("url", "token")),
        "120-sonarr": ("sonarr", ("url", "token")),
    }

    req = simple_key_requirements.get(template_key)
    if req:
        section_name, keys = req
        section_data = payload.get(section_name, {})
        if isinstance(section_data, dict):
            if template_key == "090-webhooks":
                return any(_is_meaningful_optional_status_input(value) for value in section_data.values())
            return any(_is_meaningful_optional_status_input(section_data.get(key)) for key in keys)
        return False

    if template_key == "130-trakt":
        trakt = payload.get("trakt", {})
        if not isinstance(trakt, dict):
            return False
        auth = trakt.get("authorization", {}) if isinstance(trakt.get("authorization"), dict) else {}
        visible_inputs = (
            trakt.get("client_id"),
            trakt.get("client_secret"),
            trakt.get("pin"),
        )
        if any(_is_meaningful_optional_status_input(value) for value in visible_inputs):
            return True
        has_authorization_token = any(
            _is_meaningful_optional_status_input(value)
            for value in (
                auth.get("access_token"),
                auth.get("refresh_token"),
            )
        )
        has_client_identity = any(
            _is_meaningful_optional_status_input(value)
            for value in (
                trakt.get("client_id"),
                trakt.get("client_secret"),
                auth.get("client_id"),
                auth.get("client_secret"),
            )
        )
        return has_authorization_token and has_client_identity

    if template_key == "140-mal":
        mal = payload.get("mal", {})
        if not isinstance(mal, dict):
            return False
        auth = mal.get("authorization", {}) if isinstance(mal.get("authorization"), dict) else {}
        visible_inputs = (
            mal.get("client_id"),
            mal.get("client_secret"),
            mal.get("localhost_url"),
        )
        if any(_is_meaningful_optional_status_input(value) for value in visible_inputs):
            return True
        has_authorization_token = any(
            _is_meaningful_optional_status_input(value)
            for value in (
                auth.get("access_token"),
                auth.get("refresh_token"),
            )
        )
        has_client_identity = any(
            _is_meaningful_optional_status_input(value)
            for value in (
                mal.get("client_id"),
                mal.get("client_secret"),
                auth.get("client_id"),
                auth.get("client_secret"),
            )
        )
        return has_authorization_token and has_client_identity

    # For unknown validation-backed optional steps, keep prior behavior.
    return True


def _derive_step_status(template_key, group, section_rows, config_exists):
    if template_key == "001-start":
        if not config_exists:
            return "error"
        kometa_entry = section_rows.get("kometa") if isinstance(section_rows, dict) else None
        kometa_entry = kometa_entry if isinstance(kometa_entry, dict) else {}
        kometa_payload = kometa_entry.get("data")
        kometa_payload = kometa_payload if isinstance(kometa_payload, dict) else {}
        kometa_section = kometa_payload.get("kometa") if isinstance(kometa_payload.get("kometa"), dict) else {}
        kometa_selection = _canonicalize_kometa_section(kometa_section)
        if kometa_selection.get("install_mode") == KOMETA_INSTALL_MODE_MANAGED:
            return "ok"
        is_valid, _reason, _details = _validate_saved_kometa_selection(kometa_selection)
        return "ok" if is_valid else "error"

    if template_key == "900-kometa":
        return "warn"

    if template_key in {"905-analytics", "910-sponsor"}:
        return "ok"

    section_name = template_key.split("-", 1)[1] if "-" in template_key else template_key
    section_entry = section_rows.get(section_name) if isinstance(section_rows, dict) else None
    section_entry = section_entry if isinstance(section_entry, dict) else {}
    section_row_present = bool(section_entry)

    validated = helpers.booler(section_entry.get("validated", False))
    user_entered = helpers.booler(section_entry.get("user_entered", False))
    payload = section_entry.get("data")
    payload = payload if isinstance(payload, dict) else {}
    validation_status = str(payload.get("validation_status") or "").strip().lower()
    validation_reason = str(payload.get("validation_reason") or "").strip().lower()
    was_previously_validated = bool(payload.get("validated_at"))
    if template_key == "027-playlist_files":
        playlist_payload = payload.get("playlist_files", payload if isinstance(payload, dict) else {})
        if isinstance(playlist_payload, dict) and isinstance(playlist_payload.get("playlist_files"), dict):
            playlist_payload = playlist_payload.get("playlist_files", {})
        playlist_libraries = ""
        if isinstance(playlist_payload, dict):
            raw_libraries = playlist_payload.get("libraries")
            if isinstance(raw_libraries, list):
                selected_libraries = [str(item).strip() for item in raw_libraries if str(item).strip()]
            else:
                playlist_libraries = str(raw_libraries or "")
                selected_libraries = [item.strip() for item in playlist_libraries.split(",") if item.strip()]
        else:
            selected_libraries = []

        if validation_status == "failed":
            return "error"
        if selected_libraries:
            # Playlist selection itself is the completion signal for this optional page.
            return "ok"

        # If user has visited/passed-through this page (even with no libraries selected),
        # treat it as intentionally acknowledged/valid.
        was_visited = section_row_present and (user_entered or bool(validation_status) or bool(payload.get("validation_updated_at")) or bool(payload.get("validated_at")))
        if was_visited:
            return "ok"
        return "unknown"

    if template_key in QS_VALIDATION_STEP_KEYS:
        if group == "optional" and not _has_meaningful_optional_input(template_key, payload):
            return "unknown"

        if validated or validation_status == "validated":
            return "ok"

        if validation_status == "failed":
            return "error"

        if validation_status == "skipped":
            if template_key == "027-playlist_files" and validation_reason == "no_libraries":
                return "unknown"
            if validation_reason in QS_ERROR_REASONS:
                return "error"
            if group == "optional":
                # Optional sections should remain neutral when users simply pass through
                # or when validation is skipped due to missing optional inputs.
                return "unknown"
            if validation_reason in QS_WARN_REASONS:
                return "warn"
            return "warn" if group == "required" else ("warn" if user_entered else "ok")

        if group == "required":
            if not user_entered:
                return "error"
            if was_previously_validated:
                return "error"
            return "warn"

        if not user_entered and not was_previously_validated and not validation_status:
            return "unknown"
        if was_previously_validated:
            return "error"
        return "warn" if user_entered else "ok"

    if group == "required":
        return "warn" if user_entered else "error"
    if group == "optional":
        return "warn" if user_entered else "unknown"
    return "ok"
