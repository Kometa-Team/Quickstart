"""Constants for the workspace-status derivation stack.

Bottom-layer module -- imported by ``modules.workspace_status`` and its
extracted siblings (``workspace_rollups``, ``workspace_step_status``).

Nothing in this file imports from any sibling.  Keeping the constants
here breaks the circular-import problem that would otherwise appear:
``workspace_status`` re-exports names from its siblings for backward
compat, and if the siblings imported constants from
``workspace_status`` the loop would slam shut at module load.

## What's here

* ``QS_REQUIRED_STEP_KEYS`` / ``QS_REVIEW_STEP_KEYS`` -- the menu step
  keys grouped by whether they gate the "ready to build" action.
* ``QS_VALIDATION_STEP_KEYS`` -- the set of steps that can be validated
  (as opposed to purely informational ones like ``001-start``).
* ``QS_STATUS_ORDER`` -- severity ordering for
  ``_worst_status`` rollups: ``unknown < ok < warn < error``.
* ``QS_WARN_REASONS`` / ``QS_ERROR_REASONS`` -- classifiers used by
  ``_derive_step_status`` to convert a raw ``validation_reason`` value
  into a step status.
* ``QS_FINAL_VALIDATION_TTL_HOURS`` -- how long a validation rollup
  timestamp is considered fresh before the "revalidate" nudge appears.
"""

from __future__ import annotations

QS_REQUIRED_STEP_KEYS = ["001-start", "010-plex", "020-tmdb", "025-libraries", "150-settings"]
QS_REVIEW_STEP_KEYS = ["900-kometa", "905-analytics", "910-sponsor", "915-imagemaid"]
QS_VALIDATION_STEP_KEYS = {
    "010-plex",
    "020-tmdb",
    "025-libraries",
    "030-tautulli",
    "035-tracearr",
    "040-github",
    "050-omdb",
    "060-mdblist",
    "067-floppy",
    "070-notifiarr",
    "080-gotify",
    "085-ntfy",
    "087-apprise",
    "088-yamtrack",
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
