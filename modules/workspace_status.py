"""Workspace status derivation.

The workspace status menu in Quickstart's UI shows the user how complete
each setup step is for the active config. Computing the per-step status,
the dependency hints, and the final "ready to build" gate is all done
here.

The two main entry points are:

* ``_build_workspace_status_context(config_name, template_list, ...)`` —
  rolls up DB section rows and the menu template list into the dict the
  workspace endpoint serialises.
* ``_build_workspace_app_readiness(config_name, ...)`` — drives the
  Kometa/ImageMaid app-readiness cards on the workspace page.

Both are pure (the only side effects are DB reads via
``modules.database``). Tests exercise them via
``qs_module._build_workspace_status_context`` re-exports.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import has_request_context, url_for

from modules import database, helpers
from modules.dependency_reasons import (
    QS_ANIDB_REQUIRED_STEP_KEY,
    QS_MAL_REQUIRED_STEP_KEY,
    QS_MDBLIST_REQUIRED_STEP_KEY,
    QS_OMDB_REQUIRED_STEP_KEY,
    QS_RADARR_REQUIRED_STEP_KEY,
    QS_SONARR_REQUIRED_STEP_KEY,
    QS_TAUTULLI_REQUIRED_STEP_KEY,
    QS_TRAKT_REQUIRED_STEP_KEY,
    _config_anidb_dependency_reasons,
    _config_mal_dependency_reasons,
    _config_mdblist_dependency_reasons,
    _config_omdb_dependency_reasons,
    _config_radarr_dependency_reasons,
    _config_sonarr_dependency_reasons,
    _config_tautulli_dependency_reasons,
    _config_trakt_dependency_reasons,
    _normalize_status,
)
from modules.imagemaid import (
    get_imagemaid_settings_section as _get_imagemaid_settings_section,
    probe_imagemaid_root_state as _probe_imagemaid_root_state,
    validate_imagemaid_settings as _validate_imagemaid_settings,
)
from modules.kometa_install import (
    KOMETA_INSTALL_MODE_MANAGED,
    build_kometa_install_context as _build_kometa_install_context,
    canonicalize_kometa_section as _canonicalize_kometa_section,
    validate_saved_kometa_selection as _validate_saved_kometa_selection,
)

utc_now_iso = helpers.utc_now_iso


# --- workspace constants ---------------------------------------------------

QS_REQUIRED_STEP_KEYS = ["001-start", "010-plex", "020-tmdb", "025-libraries", "150-settings"]
QS_REVIEW_STEP_KEYS = ["900-kometa", "905-analytics", "910-sponsor", "915-imagemaid"]
QS_VALIDATION_STEP_KEYS = {
    "010-plex",
    "020-tmdb",
    "025-libraries",
    "030-tautulli",
    "040-github",
    "050-omdb",
    "060-mdblist",
    "070-notifiarr",
    "080-gotify",
    "085-ntfy",
    "087-apprise",
    "090-webhooks",
    "100-anidb",
    "110-radarr",
    "120-sonarr",
    "130-trakt",
    "140-mal",
    "150-settings",
}
QS_STATUS_ORDER = {"unknown": 0, "ok": 1, "warn": 2, "error": 3}
QS_WARN_REASONS = {
    "missing_credentials",
    "missing_tokens",
    "no_libraries",
    "missing_settings",
    "disabled",
    "no_webhooks",
}
QS_ERROR_REASONS = {
    "missing_plex_validation",
    "missing_location",
    "token_invalid",
    "account_locked",
    "validation_error",
    "invalid_paths",
    "invalid_arr_overrides",
    "invalid_collection_files",
    "invalid_overlay_files",
    "invalid_fields",
    "invalid_metadata_files",
    "missing_library_defaults",
    "missing_separator_placeholder",
}
QS_FINAL_VALIDATION_TTL_HOURS = 12


# --- status rollup helpers -------------------------------------------------


def _worst_status(statuses):
    worst = "ok"
    for status in statuses:
        normalized = _normalize_status(status)
        if QS_STATUS_ORDER.get(normalized, 1) > QS_STATUS_ORDER.get(worst, 1):
            worst = normalized
    return worst


def _derive_live_final_validation_status(step_statuses, template_keys):
    validation_states = []
    for key in template_keys:
        if key not in QS_VALIDATION_STEP_KEYS:
            continue
        if key not in step_statuses:
            continue
        validation_states.append(_normalize_status(step_statuses.get(key)))

    if not validation_states:
        return "warn"
    if any(state == "error" for state in validation_states):
        return "error"
    if any(state == "warn" for state in validation_states):
        return "warn"
    if any(state == "ok" for state in validation_states):
        return "ok"
    return "warn"


def _build_live_validation_rollup(step_statuses, template_keys):
    counts = {"validated": 0, "failed": 0, "skipped": 0, "unknown": 0}
    for key in template_keys:
        if key not in QS_VALIDATION_STEP_KEYS:
            continue
        state = _normalize_status(step_statuses.get(key))
        if state == "ok":
            counts["validated"] += 1
        elif state == "error":
            counts["failed"] += 1
        elif state == "warn":
            counts["skipped"] += 1
        else:
            counts["unknown"] += 1

    if counts["failed"] > 0:
        state = "error"
    elif counts["skipped"] > 0:
        state = "warn"
    elif counts["validated"] > 0:
        state = "ok"
    else:
        state = "unknown"

    summary_text = f"Current. Validated: {counts['validated']} \u2022 " f"Failed: {counts['failed']} \u2022 " f"Pending: {counts['skipped']}"
    if counts["unknown"] > 0:
        summary_text += f" \u2022 Not checked: {counts['unknown']}"
    summary_text += "."

    return {"counts": counts, "state": state, "summary_text": summary_text}


# --- timestamp helpers -----------------------------------------------------


def _latest_iso_timestamp(values):
    latest_dt = None
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if latest_dt is None or parsed > latest_dt:
            latest_dt = parsed
    return latest_dt.isoformat().replace("+00:00", "Z") if latest_dt else None


def _format_validation_age(iso_text):
    text = str(iso_text or "").strip()
    if not text:
        return "Never", "never"
    try:
        dt_value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "Unknown", "never"
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=timezone.utc)
    now_utc = datetime.now(timezone.utc)
    delta = now_utc - dt_value.astimezone(timezone.utc)
    if delta.total_seconds() < 0:
        delta = timedelta(0)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now", "fresh"
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago", "fresh"
    if seconds < 86400:
        hours = max(1, seconds // 3600)
        return f"{hours}h ago", "stale"
    days = max(1, seconds // 86400)
    return f"{days}d ago", "stale"


def _parse_iso_datetime(iso_text):
    text = str(iso_text or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bulk_validation_is_fresh(iso_text, ttl_hours=QS_FINAL_VALIDATION_TTL_HOURS):
    parsed = _parse_iso_datetime(iso_text)
    if parsed is None:
        return False
    return datetime.now(timezone.utc) - parsed <= timedelta(hours=ttl_hours)


# --- final gate / step navigation ------------------------------------------


def _build_final_gate(workspace_status, template_list, validation_bulk_rollup_at):
    label_map = {file.rsplit(".", 1)[0]: display_name for file, display_name in template_list or []}
    step_statuses = workspace_status.get("step_statuses", {}) if isinstance(workspace_status, dict) else {}
    required_keys = workspace_status.get("required_keys", []) if isinstance(workspace_status, dict) else []
    optional_keys = workspace_status.get("optional_keys", []) if isinstance(workspace_status, dict) else []

    blockers = []
    seen = set()
    for key in required_keys:
        state = step_statuses.get(key, "warn")
        if state == "ok":
            continue
        blockers.append({"key": key, "label": label_map.get(key, key), "state": state, "group": "required"})
        seen.add(key)

    for key in optional_keys:
        state = step_statuses.get(key, "unknown")
        if state not in {"warn", "error"} or key in seen:
            continue
        blockers.append({"key": key, "label": label_map.get(key, key), "state": state, "group": "optional"})
        seen.add(key)

    dependency_defs = [
        ("tautulli", QS_TAUTULLI_REQUIRED_STEP_KEY, "Tautulli", "tautulli_requirement_reasons", "qs-tautulli-required-hint"),
        ("omdb", QS_OMDB_REQUIRED_STEP_KEY, "OMDb", "omdb_requirement_reasons", "qs-omdb-required-hint"),
        ("mdblist", QS_MDBLIST_REQUIRED_STEP_KEY, "MDBList", "mdblist_requirement_reasons", "qs-mdblist-required-hint"),
        ("anidb", QS_ANIDB_REQUIRED_STEP_KEY, "AniDB", "anidb_requirement_reasons", "qs-anidb-required-hint"),
        ("radarr", QS_RADARR_REQUIRED_STEP_KEY, "Radarr", "radarr_requirement_reasons", "qs-radarr-required-hint"),
        ("sonarr", QS_SONARR_REQUIRED_STEP_KEY, "Sonarr", "sonarr_requirement_reasons", "qs-sonarr-required-hint"),
        ("trakt", QS_TRAKT_REQUIRED_STEP_KEY, "Trakt", "trakt_requirement_reasons", "qs-trakt-required-hint"),
        ("mal", QS_MAL_REQUIRED_STEP_KEY, "MyAnimeList", "mal_requirement_reasons", "qs-mal-required-hint"),
    ]
    dependency_cards = []
    for provider, step_key, label, reasons_key, css_class in dependency_defs:
        reasons = workspace_status.get(reasons_key, []) if isinstance(workspace_status, dict) else []
        if not reasons or step_statuses.get(step_key) == "ok":
            continue
        dependency_cards.append(
            {
                "provider": provider,
                "key": step_key,
                "label": label,
                "title": f"{label} required by",
                "reasons": reasons,
                "state": step_statuses.get(step_key, "warn"),
                "css_class": css_class,
            }
        )
    dependency_keys = {card["key"] for card in dependency_cards}
    setup_blockers = [blocker for blocker in blockers if blocker.get("key") not in dependency_keys]

    bulk_fresh = _bulk_validation_is_fresh(validation_bulk_rollup_at)
    if blockers:
        stage = "todo"
    elif not bulk_fresh:
        stage = "freshness"
    else:
        stage = "config"

    return {
        "stage": stage,
        "todo_count": len(blockers),
        "todo_blockers": blockers,
        "dependency_cards": dependency_cards,
        "setup_blockers": setup_blockers,
        "bulk_validation_fresh": bulk_fresh,
        "bulk_validation_at": validation_bulk_rollup_at or "",
        "validation_ttl_hours": QS_FINAL_VALIDATION_TTL_HOURS,
        "can_build_config": not blockers and bulk_fresh,
        "config_valid": False,
    }


def _step_href(step_key):
    target = str(step_key or "").strip()
    if not target:
        target = "001-start"
    if has_request_context():
        try:
            return url_for("step", name=target)
        except Exception:
            return f"/step/{target}"
    return f"/step/{target}"


def _latest_bulk_validation_timestamp(config_name):
    if not config_name:
        return ""
    try:
        stored_validation = database.retrieve_section_data(config_name, "validation_summary")
        stored_payload = stored_validation[2] if stored_validation else None
        if isinstance(stored_payload, dict):
            return str(stored_payload.get("updated_at") or "").strip()
    except Exception:
        return ""
    return ""


# --- app-readiness cards ---------------------------------------------------


def _workspace_step_status_from_app_readiness(state):
    normalized = str(state or "").strip().lower()
    if normalized in {"ready", "review", "running", "queued"}:
        return "ok"
    if normalized == "needs_validation":
        return "warn"
    if normalized in {"needs_prepare", "needs_setup", "blocked", "error"}:
        return "error"
    return "unknown"


def _build_workspace_app_readiness_from_status(config_name, workspace_status, template_list=None):
    template_list = template_list or helpers.get_menu_list()
    final_gate = _build_final_gate(
        workspace_status,
        template_list,
        _latest_bulk_validation_timestamp(config_name),
    )
    install_context = _build_kometa_install_context(config_name)

    first_blocker = {}
    todo_blockers = final_gate.get("todo_blockers") or []
    if todo_blockers:
        first_blocker = todo_blockers[0] if isinstance(todo_blockers[0], dict) else {}
    blocker_key = first_blocker.get("key") or "001-start"
    blocker_label = first_blocker.get("label") or "setup"
    todo_count = int(final_gate.get("todo_count") or 0)

    kometa = {
        "name": "Kometa",
        "href": _step_href("900-kometa"),
        "action_label": "Open Kometa",
        "state": "review",
        "summary": "Open Kometa",
        "detail": "Use the Kometa page to review build status, prepare the runtime, and run this config.",
        "target_step": "900-kometa",
        "final_gate_stage": final_gate.get("stage") or "todo",
        "todo_count": todo_count,
        "install_mode": install_context.get("kometa_install_mode") or "",
        "mode_label": install_context.get("kometa_mode_label") or "",
        "can_launch": bool(install_context.get("kometa_can_launch")),
        "can_sync_config": bool(install_context.get("kometa_can_sync_config")),
    }

    if final_gate.get("stage") == "todo":
        noun = "item" if todo_count == 1 else "items"
        kometa.update(
            state="needs_setup",
            summary=f"{todo_count} setup {noun} left" if todo_count else "Finish setup first",
            detail=f"Finish {blocker_label} before Kometa is ready to review in Quickstart.",
            action_label="Finish setup",
            href=_step_href(blocker_key),
            target_step=blocker_key,
        )
    elif final_gate.get("stage") == "freshness":
        kometa.update(
            state="review",
            summary="Validation refresh recommended",
            detail=f"Open Kometa to refresh bulk validation before running. Quickstart expects validation within the last {QS_FINAL_VALIDATION_TTL_HOURS} hours, but the app itself is still available.",
            action_label="Open Kometa",
            href=_step_href("900-kometa"),
            target_step="900-kometa",
        )
    elif install_context.get("kometa_can_launch"):
        kometa.update(
            state="ready",
            summary="Ready in Quickstart",
            detail="Open Kometa to prepare the runtime if needed, then review or run this config.",
        )
    elif install_context.get("kometa_can_sync_config"):
        detail = "Open Kometa to review and sync this config."
        if install_context.get("kometa_is_external_install"):
            detail = "Open Kometa to review and sync this config for your external Kometa install."
        kometa.update(
            state="review",
            summary="Config ready",
            detail=detail,
        )

    imagemaid_settings, imagemaid_section = _get_imagemaid_settings_section(config_name)
    imagemaid_state = _probe_imagemaid_root_state(helpers.get_imagemaid_root_path())
    imagemaid_row = database.retrieve_section_data(config_name, "imagemaid") if config_name else None
    imagemaid_validated = helpers.booler(imagemaid_row[0]) if imagemaid_row else helpers.booler(imagemaid_settings.get("validated", False))
    imagemaid_is_valid, imagemaid_reason, imagemaid_details = _validate_imagemaid_settings(imagemaid_section, config_name=config_name)

    imagemaid = {
        "name": "ImageMaid",
        "href": _step_href("915-imagemaid"),
        "action_label": "Open ImageMaid",
        "state": "needs_prepare",
        "summary": "Prepare ImageMaid",
        "detail": "Install or prepare ImageMaid before validating and running it in Quickstart.",
        "target_step": "915-imagemaid",
        "validated": bool(imagemaid_validated),
        "settings_valid": bool(imagemaid_is_valid),
        "installed": bool(imagemaid_state.get("imagemaid_installed")),
        "venv_ready": bool(imagemaid_state.get("venv_python_exists")),
    }

    if imagemaid_state.get("imagemaid_installed") and imagemaid_state.get("venv_python_exists"):
        if imagemaid_is_valid and imagemaid_validated:
            imagemaid.update(
                state="ready",
                summary="Ready to run",
                detail="Open ImageMaid to review the command preview and run it.",
            )
        elif imagemaid_is_valid:
            imagemaid.update(
                state="needs_validation",
                summary="Ready to validate",
                detail="Open ImageMaid and validate the saved settings to unlock run controls.",
            )
        else:
            summary_map = {
                "missing_plex_validation": "Plex validation required",
                "missing_credentials": "Saved Plex credentials required",
                "invalid_path": "Plex path needs attention",
            }
            imagemaid.update(
                state="needs_setup",
                summary=summary_map.get(imagemaid_reason, "ImageMaid needs attention"),
                detail=str(imagemaid_details or "Open ImageMaid to finish setup.").strip(),
            )
            if imagemaid_reason == "missing_plex_validation":
                imagemaid.update(
                    href=_step_href("010-plex"),
                    action_label="Open Plex",
                    target_step="010-plex",
                )

    return {
        "generated_at": utc_now_iso(),
        "kometa": kometa,
        "imagemaid": imagemaid,
    }


def _build_workspace_app_readiness(config_name, template_list=None, available_configs=None):
    template_list = template_list or helpers.get_menu_list()
    available_configs = available_configs or database.get_unique_config_names() or []
    workspace_status = _build_workspace_status_context(
        config_name,
        template_list,
        available_configs=available_configs,
        include_app_readiness_overrides=False,
    )
    return _build_workspace_app_readiness_from_status(config_name, workspace_status, template_list=template_list)


# --- optional-input "meaningful" probes ------------------------------------


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
        return any(
            _is_meaningful_optional_status_input(value)
            for value in (
                trakt.get("client_id"),
                trakt.get("client_secret"),
                trakt.get("pin"),
                auth.get("access_token"),
                auth.get("refresh_token"),
            )
        )

    if template_key == "140-mal":
        mal = payload.get("mal", {})
        if not isinstance(mal, dict):
            return False
        auth = mal.get("authorization", {}) if isinstance(mal.get("authorization"), dict) else {}
        return any(
            _is_meaningful_optional_status_input(value)
            for value in (
                mal.get("client_id"),
                mal.get("client_secret"),
                mal.get("localhost_url"),
                auth.get("access_token"),
                auth.get("refresh_token"),
            )
        )

    # For unknown validation-backed optional steps, keep prior behavior.
    return True


# --- per-step status derivation --------------------------------------------


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


# --- the main workspace status context builder -----------------------------


def _build_workspace_status_context(config_name, template_list, available_configs=None, include_app_readiness_overrides=True):
    template_keys = []
    for file_entry, _ in template_list or []:
        template_key = file_entry.rsplit(".", 1)[0]
        template_keys.append(template_key)

    section_rows = {}
    if config_name:
        try:
            for row in database.retrieve_config_sections(config_name):
                section_name = row.get("section")
                if section_name:
                    section_rows[section_name] = row
        except Exception:
            section_rows = {}

    available_set = set(available_configs or [])
    config_exists = bool(config_name) and (config_name in available_set or bool(section_rows))

    required_seed = set(QS_REQUIRED_STEP_KEYS)
    tautulli_requirement_reasons = _config_tautulli_dependency_reasons(section_rows) if QS_TAUTULLI_REQUIRED_STEP_KEY in template_keys else []
    omdb_requirement_reasons = _config_omdb_dependency_reasons(section_rows) if QS_OMDB_REQUIRED_STEP_KEY in template_keys else []
    mdblist_requirement_reasons = _config_mdblist_dependency_reasons(section_rows) if QS_MDBLIST_REQUIRED_STEP_KEY in template_keys else []
    anidb_requirement_reasons = _config_anidb_dependency_reasons(section_rows) if QS_ANIDB_REQUIRED_STEP_KEY in template_keys else []
    radarr_requirement_reasons = _config_radarr_dependency_reasons(section_rows) if QS_RADARR_REQUIRED_STEP_KEY in template_keys else []
    sonarr_requirement_reasons = _config_sonarr_dependency_reasons(section_rows) if QS_SONARR_REQUIRED_STEP_KEY in template_keys else []
    trakt_requirement_reasons = _config_trakt_dependency_reasons(section_rows) if QS_TRAKT_REQUIRED_STEP_KEY in template_keys else []
    mal_requirement_reasons = _config_mal_dependency_reasons(section_rows) if QS_MAL_REQUIRED_STEP_KEY in template_keys else []
    if QS_TAUTULLI_REQUIRED_STEP_KEY in template_keys and tautulli_requirement_reasons:
        required_seed.add(QS_TAUTULLI_REQUIRED_STEP_KEY)
    if QS_OMDB_REQUIRED_STEP_KEY in template_keys and omdb_requirement_reasons:
        required_seed.add(QS_OMDB_REQUIRED_STEP_KEY)
    if QS_MDBLIST_REQUIRED_STEP_KEY in template_keys and mdblist_requirement_reasons:
        required_seed.add(QS_MDBLIST_REQUIRED_STEP_KEY)
    if QS_ANIDB_REQUIRED_STEP_KEY in template_keys and anidb_requirement_reasons:
        required_seed.add(QS_ANIDB_REQUIRED_STEP_KEY)
    if QS_RADARR_REQUIRED_STEP_KEY in template_keys and radarr_requirement_reasons:
        required_seed.add(QS_RADARR_REQUIRED_STEP_KEY)
    if QS_SONARR_REQUIRED_STEP_KEY in template_keys and sonarr_requirement_reasons:
        required_seed.add(QS_SONARR_REQUIRED_STEP_KEY)
    if QS_TRAKT_REQUIRED_STEP_KEY in template_keys and trakt_requirement_reasons:
        required_seed.add(QS_TRAKT_REQUIRED_STEP_KEY)
    if QS_MAL_REQUIRED_STEP_KEY in template_keys and mal_requirement_reasons:
        required_seed.add(QS_MAL_REQUIRED_STEP_KEY)
    review_seed = set(QS_REVIEW_STEP_KEYS)

    required_keys = [key for key in template_keys if key in required_seed]
    review_keys = [key for key in template_keys if key in review_seed]
    optional_keys = [key for key in template_keys if key not in required_seed and key not in review_seed]

    step_statuses = {}
    for template_key in template_keys:
        if template_key == "900-kometa":
            continue
        if template_key in required_keys:
            group = "required"
        elif template_key in optional_keys:
            group = "optional"
        else:
            group = "review"
        step_statuses[template_key] = _derive_step_status(template_key, group, section_rows, config_exists)
    if "900-kometa" in template_keys:
        step_statuses["900-kometa"] = _derive_live_final_validation_status(step_statuses, template_keys)

    if include_app_readiness_overrides and config_name:
        provisional_status = {
            "step_statuses": dict(step_statuses),
            "required_keys": list(required_keys),
            "optional_keys": list(optional_keys),
            "review_keys": list(review_keys),
            "tautulli_requirement_reasons": tautulli_requirement_reasons,
            "omdb_requirement_reasons": omdb_requirement_reasons,
            "mdblist_requirement_reasons": mdblist_requirement_reasons,
            "anidb_requirement_reasons": anidb_requirement_reasons,
            "radarr_requirement_reasons": radarr_requirement_reasons,
            "sonarr_requirement_reasons": sonarr_requirement_reasons,
            "trakt_requirement_reasons": trakt_requirement_reasons,
            "mal_requirement_reasons": mal_requirement_reasons,
        }
        app_readiness = _build_workspace_app_readiness_from_status(config_name, provisional_status, template_list=template_list)
        kometa_readiness = app_readiness.get("kometa") if isinstance(app_readiness, dict) else None
        imagemaid_readiness = app_readiness.get("imagemaid") if isinstance(app_readiness, dict) else None
        if "900-kometa" in step_statuses and isinstance(kometa_readiness, dict):
            step_statuses["900-kometa"] = _workspace_step_status_from_app_readiness(kometa_readiness.get("state"))
        if "915-imagemaid" in step_statuses and isinstance(imagemaid_readiness, dict):
            step_statuses["915-imagemaid"] = _workspace_step_status_from_app_readiness(imagemaid_readiness.get("state"))

    required_rollup = _worst_status(step_statuses.get(key, "warn") for key in required_keys) if required_keys else "ok"
    review_rollup = _worst_status(step_statuses.get(key, "ok") for key in review_keys) if review_keys else "ok"

    optional_status_values = [step_statuses.get(key, "unknown") for key in optional_keys]
    if not optional_status_values:
        optional_rollup = "ok"
    elif any(status == "error" for status in optional_status_values):
        optional_rollup = "error"
    elif any(status == "warn" for status in optional_status_values):
        optional_rollup = "warn"
    elif any(status == "unknown" for status in optional_status_values):
        optional_rollup = "unknown"
    else:
        optional_rollup = "ok"

    section_statuses = {
        "required": required_rollup,
        "optional": optional_rollup,
        "review": review_rollup,
    }

    jump_to_validations = {}
    for key in QS_VALIDATION_STEP_KEYS:
        if key in step_statuses:
            jump_to_validations[key] = step_statuses.get(key) == "ok"

    required_total = len(required_keys)
    required_ready = sum(1 for key in required_keys if step_statuses.get(key) == "ok")
    required_percent = round((required_ready / required_total) * 100) if required_total else 0

    optional_total = len(optional_keys)
    optional_configured = sum(1 for key in optional_keys if step_statuses.get(key) != "unknown")
    optional_issue_count = sum(1 for key in optional_keys if step_statuses.get(key) in {"warn", "error"})

    optional_summary = f"Optional {optional_configured}/{optional_total} configured" if optional_total else "No optional pages"
    if optional_issue_count > 0:
        optional_summary += f" \u2022 {optional_issue_count} issue{'s' if optional_issue_count != 1 else ''}"

    validation_timestamps = []
    for row in section_rows.values():
        if not isinstance(row, dict):
            continue
        data = row.get("data")
        if not isinstance(data, dict):
            continue
        for key in ("validation_updated_at", "validated_at"):
            value = data.get(key)
            if value:
                validation_timestamps.append(value)
        if row.get("section") == "validation_summary":
            summary_updated = data.get("updated_at")
            if summary_updated:
                validation_timestamps.append(summary_updated)
    latest_validation_at = _latest_iso_timestamp(validation_timestamps)
    validation_age_label, validation_freshness = _format_validation_age(latest_validation_at)

    readiness = {
        "required_total": required_total,
        "required_ready": required_ready,
        "required_percent": required_percent,
        "required_state": required_rollup,
        "optional_total": optional_total,
        "optional_configured": optional_configured,
        "optional_issue_count": optional_issue_count,
        "optional_summary": optional_summary,
        "latest_validation_at": latest_validation_at,
        "validation_age_label": validation_age_label,
        "validation_freshness": validation_freshness,
    }

    return {
        "step_statuses": step_statuses,
        "section_statuses": section_statuses,
        "jump_to_validations": jump_to_validations,
        "required_keys": required_keys,
        "optional_keys": optional_keys,
        "review_keys": review_keys,
        "tautulli_requirement_reasons": tautulli_requirement_reasons,
        "omdb_requirement_reasons": omdb_requirement_reasons,
        "mdblist_requirement_reasons": mdblist_requirement_reasons,
        "anidb_requirement_reasons": anidb_requirement_reasons,
        "radarr_requirement_reasons": radarr_requirement_reasons,
        "sonarr_requirement_reasons": sonarr_requirement_reasons,
        "trakt_requirement_reasons": trakt_requirement_reasons,
        "mal_requirement_reasons": mal_requirement_reasons,
        "readiness": readiness,
    }
