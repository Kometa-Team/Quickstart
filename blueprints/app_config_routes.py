"""Read-only endpoint exposing the app-level configuration to the front end.

Background
----------
Historically, every Quickstart page rendered an inline ``<script>`` block
in ``templates/000-base.html`` that copied 11 entries from Flask's
``app.config`` onto ``window.QS_*`` so the front-end JS could read them
back. That worked, but it meant every page reload re-serialized the same
unchanging values through Jinja, and it tightly coupled the template
output to the JS contract.

This module exposes those 11 keys via a single read endpoint:

    GET /api/app-config

The intent is for the front end to fetch this once on startup, keep the
result in a single module-scoped object, and let the existing settings
save handler in ``static/local-js/000-base.js`` mutate that object in
place when the user changes a setting (exactly as it already mutates
``window.QS_*`` today).

Scope of this PR
----------------
This blueprint is **additive**. The existing ``window.QS_*`` injections
in ``templates/000-base.html`` are left untouched so nothing in the
front end breaks. The follow-up PR migrates the JS readers to the new
namespace and removes the Jinja injections.

The 11 keys exposed
-------------------
Only the *app-level* (page-independent) keys are exposed here. Page-level
keys -- ``QS_REQUIRED_KEYS``, ``QS_OPTIONAL_KEYS``, ``QS_REVIEW_KEYS``,
``QS_CURRENT_TEMPLATE``, ``QS_SETTINGS_CUSTOM_REPO``,
``QS_SETTINGS_CUSTOM_REPO_BASE``, and the various
``QS_*_REQUIREMENT_REASONS`` -- are deliberately *not* exposed here.
They depend on the current page or active template and will be handled
when each page's component fetches its own initial state (roadmap Step 9
in #1334).

Why ``current_app`` and not the module-level import
---------------------------------------------------
Importing ``quickstart.app`` at module import time would create a
circular dependency, since ``quickstart.py`` imports this blueprint.
Flask's ``current_app`` proxy resolves at request time and is the right
tool here.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

bp = Blueprint("app_config_routes", __name__)


# The 11 app-level config keys exposed by /api/app-config, paired with
# the fallback value to use when the key is missing from app.config.
#
# Keep this list in sync with templates/000-base.html. The follow-up PR
# that removes those inline injections will delete the duplication.
APP_CONFIG_KEYS: tuple[tuple[str, object], ...] = (
    ("QS_DEBUG", False),
    ("QS_THEME", "kometa"),
    ("QS_OPTIMIZE_DEFAULTS", True),
    ("QS_CONFIG_HISTORY", 0),
    ("QS_KOMETA_LOG_KEEP", 0),
    ("QS_IMAGEMAID_LOG_KEEP", 0),
    ("QS_TEST_LIBS_PATH", ""),
    ("QS_TEST_LIBS_TMP", ""),
    ("QS_SESSION_LIFETIME_DAYS", 30),
    ("QS_FLASK_SESSION_DIR", ""),
    ("QS_RESTART_NOTICE", None),
)


def collect_app_config() -> dict[str, object]:
    """Return the app-level config as a JSON-serializable dict.

    Pulled out as a module-level function so tests can call it directly
    without spinning up a request context, and so future call sites
    (e.g. a server-rendered initial JSON blob, should we ever want one)
    don't have to duplicate the key list.
    """
    config = current_app.config
    return {key: config.get(key, default) for key, default in APP_CONFIG_KEYS}


@bp.route("/api/app-config", methods=["GET"])
def get_app_config():
    """Return the app-level config as JSON.

    Response shape::

        {
          "QS_DEBUG": false,
          "QS_THEME": "kometa",
          ... (9 more keys)
        }

    The keys mirror ``window.QS_*`` exactly so the front end can do::

        const config = await fetch('/api/app-config').then(r => r.json())
        // config.QS_DEBUG, config.QS_THEME, etc.

    No authentication is enforced here for the same reason none of the
    other Quickstart endpoints enforce it: this is a single-user local
    desktop wizard. The values returned are already visible in the
    rendered HTML today via the ``<script>`` injections in
    ``templates/000-base.html``.
    """
    return jsonify(collect_app_config())
