"""Rollup helpers for the workspace-status stack.

Split out of ``modules.workspace_status`` -- this cluster owns the
"assemble derived values from step statuses" helpers that don't need
the full DB-row-inspection logic of ``_derive_step_status``.

## What lives here

### Status rollups
* ``_worst_status(statuses)`` -- picks the most severe entry using
  ``QS_STATUS_ORDER``.
* ``_derive_live_final_validation_status(step_statuses, template_keys)``
  -- ok / warn / error for the "all validation steps combined" indicator.
* ``_build_live_validation_rollup(step_statuses, template_keys)`` --
  returns counts + state + summary text for the workspace footer.

### Timestamp helpers
* ``_latest_iso_timestamp(values)`` -- pick the newest ISO timestamp
  from a list (used to roll up per-step ``validated_at`` values).
* ``_format_validation_age(iso_text)`` -- returns a "5m ago" / "3d ago"
  label plus a freshness bucket (``fresh`` / ``stale`` / ``never``).
* ``_parse_iso_datetime(iso_text)`` -- lenient ISO parser with UTC
  fallback for legacy naive timestamps.
* ``_bulk_validation_is_fresh(iso_text, ttl_hours)`` -- "is the
  bulk-validate rollup still valid?" boolean using
  ``QS_FINAL_VALIDATION_TTL_HOURS`` as the default.

### Final gate + navigation
* ``_build_final_gate(...)`` -- collects blockers + dependency cards
  and picks the ready-to-build stage (``todo`` / ``freshness`` /
  ``config``).
* ``_step_href(step_key)`` -- resolves a menu key to a URL (uses
  ``url_for`` when inside a request context, else a static path).
* ``_latest_bulk_validation_timestamp(config_name)`` -- reads the
  ``validation_summary`` DB row's ``updated_at`` field.
* ``_workspace_step_status_from_app_readiness(state)`` -- classifier
  that maps app-readiness states (ready / running / needs_setup / ...)
  to workspace step statuses (ok / warn / error).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import has_request_context, url_for

from modules import database
from modules.dependency_reasons import (
    QS_ANIDB_REQUIRED_STEP_KEY,
    QS_FLOPPY_REQUIRED_STEP_KEY,
    QS_MAL_REQUIRED_STEP_KEY,
    QS_MDBLIST_REQUIRED_STEP_KEY,
    QS_OMDB_REQUIRED_STEP_KEY,
    QS_RADARR_REQUIRED_STEP_KEY,
    QS_SONARR_REQUIRED_STEP_KEY,
    QS_TAUTULLI_REQUIRED_STEP_KEY,
    QS_TRAKT_REQUIRED_STEP_KEY,
    _normalize_status,
)
from modules.workspace_status_constants import (
    QS_FINAL_VALIDATION_TTL_HOURS,
    QS_STATUS_ORDER,
    QS_VALIDATION_STEP_KEYS,
)


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
        ("floppy", QS_FLOPPY_REQUIRED_STEP_KEY, "Floppy", "floppy_requirement_reasons", "qs-floppy-required-hint"),
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


def _workspace_step_status_from_app_readiness(state):
    normalized = str(state or "").strip().lower()
    if normalized in {"ready", "review", "running", "queued"}:
        return "ok"
    if normalized == "needs_validation":
        return "warn"
    if normalized in {"needs_prepare", "needs_setup", "blocked", "error"}:
        return "error"
    return "unknown"
