"""Workspace status derivation.

The workspace status menu in Quickstart's UI shows the user how complete
each setup step is for the active config. Computing the per-step status,
the dependency hints, and the final "ready to build" gate is all done
here.

The two main entry points that still LIVE in this module are:

* ``_build_workspace_status_context(config_name, template_list, ...)`` --
  rolls up DB section rows and the menu template list into the dict the
  workspace endpoint serialises.
* ``_build_workspace_app_readiness(config_name, ...)`` /
  ``_build_workspace_app_readiness_from_status(...)`` -- drives the
  Kometa/ImageMaid app-readiness cards on the workspace page.

All the leaf helpers moved out:

* ``modules.workspace_status_constants`` -- ``QS_*`` module constants
  (step-key lists, status order, warn/error reason sets, freshness TTL).
* ``modules.workspace_rollups`` -- ``_worst_status``, the two
  ``*_live_final_validation_*`` rollups, the four timestamp helpers,
  ``_build_final_gate``, ``_step_href``, ``_latest_bulk_validation_timestamp``,
  and ``_workspace_step_status_from_app_readiness``.
* ``modules.workspace_step_status`` -- ``_is_nonblank_setting``,
  ``_is_meaningful_optional_status_input``, ``_has_meaningful_optional_input``,
  and the 100-line ``_derive_step_status`` dispatch.

All re-exported below so ``qs_module.<name>`` (via ``quickstart.py``'s
big ``from modules.workspace_status import ...`` block) keeps working.
"""

from __future__ import annotations

from flask import has_request_context, url_for  # noqa: F401 (kept for parity with prior module surface)

from modules import database, helpers
from modules.dependency_reasons import (
    QS_ANIDB_REQUIRED_STEP_KEY,
    QS_FLOPPY_REQUIRED_STEP_KEY,
    QS_MAL_REQUIRED_STEP_KEY,
    QS_MDBLIST_REQUIRED_STEP_KEY,
    QS_OMDB_REQUIRED_STEP_KEY,
    QS_RADARR_REQUIRED_STEP_KEY,
    QS_SONARR_REQUIRED_STEP_KEY,
    QS_TAUTULLI_REQUIRED_STEP_KEY,
    QS_TRACEARR_REQUIRED_STEP_KEY,
    QS_TRAKT_REQUIRED_STEP_KEY,
    _config_anidb_dependency_reasons,
    _config_floppy_dependency_reasons,
    _config_mal_dependency_reasons,
    _config_mdblist_dependency_reasons,
    _config_omdb_dependency_reasons,
    _config_radarr_dependency_reasons,
    _config_sonarr_dependency_reasons,
    _config_tautulli_dependency_reasons,
    _config_tracearr_dependency_reasons,
    _config_trakt_dependency_reasons,
)
from modules.imagemaid import (
    get_imagemaid_settings_section as _get_imagemaid_settings_section,
    probe_imagemaid_root_state as _probe_imagemaid_root_state,
    validate_imagemaid_settings as _validate_imagemaid_settings,
)
from modules.kometa_install import (
    build_kometa_install_context as _build_kometa_install_context,
    probe_kometa_root_state as _probe_kometa_root_state,
)

# Constants extracted to modules.workspace_status_constants. Re-exported here.
from modules.workspace_status_constants import (  # noqa: F401
    QS_ERROR_REASONS,
    QS_FINAL_VALIDATION_TTL_HOURS,
    QS_REQUIRED_STEP_KEYS,
    QS_REVIEW_STEP_KEYS,
    QS_STATUS_ORDER,
    QS_VALIDATION_STEP_KEYS,
    QS_WARN_REASONS,
)

# Rollup helpers (status/timestamp/final-gate/nav) extracted to
# modules.workspace_rollups. Re-exported here.
from modules.workspace_rollups import (  # noqa: F401
    _build_final_gate,
    _build_live_validation_rollup,
    _bulk_validation_is_fresh,
    _derive_live_final_validation_status,
    _format_validation_age,
    _latest_bulk_validation_timestamp,
    _latest_iso_timestamp,
    _parse_iso_datetime,
    _step_href,
    _workspace_step_status_from_app_readiness,
    _worst_status,
)

# Per-step status derivation extracted to modules.workspace_step_status.
# Re-exported here.
from modules.workspace_step_status import (  # noqa: F401
    _derive_step_status,
    _has_meaningful_optional_input,
    _is_meaningful_optional_status_input,
    _is_nonblank_setting,
)

utc_now_iso = helpers.utc_now_iso


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
    else:
        detail = "Open Kometa to validate, review, download, prepare, or run this config."
        if install_context.get("kometa_is_external_install"):
            detail = "Open Kometa to validate, review, download, and sync this config for your external Kometa install."
            kometa.update(
                state="review",
                summary="Sync config",
                detail=detail,
                action_label="Open Kometa",
                href=_step_href("900-kometa"),
                target_step="900-kometa",
                installed=False,
                prepared=False,
            )
        else:
            root_path = install_context.get("kometa_selected_root") or install_context.get("kometa_primary_path")
            runtime_state = {}
            if root_path:
                try:
                    runtime_state = _probe_kometa_root_state(root_path)
                except Exception:
                    runtime_state = {}
            installed = bool(runtime_state.get("kometa_installed"))
            prepared = bool(runtime_state.get("venv_python_exists"))
            kometa.update(
                state="ready" if installed and prepared else "needs_prepare",
                summary="Ready to run" if installed and prepared else ("Prepare Kometa" if installed else "Install Kometa"),
                detail=(
                    "Open Kometa to review the command preview and run this config."
                    if installed and prepared
                    else (
                        "Open Kometa to prepare the Python environment before running this config."
                        if installed
                        else "Open Kometa to download/install Kometa before running this config."
                    )
                ),
                action_label="Open Kometa",
                href=_step_href("900-kometa"),
                target_step="900-kometa",
                installed=installed,
                prepared=prepared,
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
    tracearr_requirement_reasons = _config_tracearr_dependency_reasons(section_rows) if QS_TRACEARR_REQUIRED_STEP_KEY in template_keys else []
    omdb_requirement_reasons = _config_omdb_dependency_reasons(section_rows) if QS_OMDB_REQUIRED_STEP_KEY in template_keys else []
    mdblist_requirement_reasons = _config_mdblist_dependency_reasons(section_rows) if QS_MDBLIST_REQUIRED_STEP_KEY in template_keys else []
    floppy_requirement_reasons = _config_floppy_dependency_reasons(section_rows) if QS_FLOPPY_REQUIRED_STEP_KEY in template_keys else []
    anidb_requirement_reasons = _config_anidb_dependency_reasons(section_rows) if QS_ANIDB_REQUIRED_STEP_KEY in template_keys else []
    radarr_requirement_reasons = _config_radarr_dependency_reasons(section_rows) if QS_RADARR_REQUIRED_STEP_KEY in template_keys else []
    sonarr_requirement_reasons = _config_sonarr_dependency_reasons(section_rows) if QS_SONARR_REQUIRED_STEP_KEY in template_keys else []
    trakt_requirement_reasons = _config_trakt_dependency_reasons(section_rows) if QS_TRAKT_REQUIRED_STEP_KEY in template_keys else []
    mal_requirement_reasons = _config_mal_dependency_reasons(section_rows) if QS_MAL_REQUIRED_STEP_KEY in template_keys else []
    if QS_TAUTULLI_REQUIRED_STEP_KEY in template_keys and tautulli_requirement_reasons:
        required_seed.add(QS_TAUTULLI_REQUIRED_STEP_KEY)
    if QS_TRACEARR_REQUIRED_STEP_KEY in template_keys and tracearr_requirement_reasons:
        required_seed.add(QS_TRACEARR_REQUIRED_STEP_KEY)
    if QS_OMDB_REQUIRED_STEP_KEY in template_keys and omdb_requirement_reasons:
        required_seed.add(QS_OMDB_REQUIRED_STEP_KEY)
    if QS_MDBLIST_REQUIRED_STEP_KEY in template_keys and mdblist_requirement_reasons:
        required_seed.add(QS_MDBLIST_REQUIRED_STEP_KEY)
    if QS_FLOPPY_REQUIRED_STEP_KEY in template_keys and floppy_requirement_reasons:
        required_seed.add(QS_FLOPPY_REQUIRED_STEP_KEY)
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
            "tracearr_requirement_reasons": tracearr_requirement_reasons,
            "omdb_requirement_reasons": omdb_requirement_reasons,
            "mdblist_requirement_reasons": mdblist_requirement_reasons,
            "floppy_requirement_reasons": floppy_requirement_reasons,
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
        "tracearr_requirement_reasons": tracearr_requirement_reasons,
        "omdb_requirement_reasons": omdb_requirement_reasons,
        "mdblist_requirement_reasons": mdblist_requirement_reasons,
        "floppy_requirement_reasons": floppy_requirement_reasons,
        "anidb_requirement_reasons": anidb_requirement_reasons,
        "radarr_requirement_reasons": radarr_requirement_reasons,
        "sonarr_requirement_reasons": sonarr_requirement_reasons,
        "trakt_requirement_reasons": trakt_requirement_reasons,
        "mal_requirement_reasons": mal_requirement_reasons,
        "readiness": readiness,
    }
