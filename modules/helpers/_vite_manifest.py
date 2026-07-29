"""Vite manifest lookup for the ``asset_url`` Jinja helper.

Roadmap #1334 Step 4 (activation phase). This module reads the manifest
that ``vite build`` produces at ``static/dist/.vite/manifest.json`` and
resolves a source-file name (e.g. ``000-base``) to the hashed built
filename (e.g. ``000-base-DKccW2Od.js``).

The manifest is loaded once, at first lookup, and cached in module
scope. If Vite writes a new manifest (e.g. during a live development
loop with ``npm run build`` in a watch flow), ``reload_manifest()``
clears the cache. Production Flask processes never call
``reload_manifest`` -- the manifest is baked at container/binary
build time.

Two shipping-vector realities to know about:

- **Source checkout / dev**: ``static/dist/`` is gitignored. If nobody
  runs ``npm run build``, the manifest doesn't exist. ``asset_url()``
  falls back to ``/static/local-js/<name>.js`` so ``python quickstart.py``
  after a fresh clone still works.

- **Docker / PyInstaller / release binary**: a follow-up PR will run
  ``npm run build`` in the packaging step, producing a populated
  ``static/dist/`` inside the shipped image. The manifest resolves and
  clients get hashed, minified bundles.

The manifest schema (Vite 8.x) looks like::

    {
      "static/local-js/000-base.js": {
        "file": "000-base-DKccW2Od.js",
        "src":  "static/local-js/000-base.js",
        "isEntry": true,
        ...
      },
      "_validationPageBase-CfgGMyYr.js": {
        "file": "chunks/validationPageBase-CfgGMyYr.js",
        "name": "validationPageBase"
      }
    }

Entry files (the ones templates load via ``<script src=...>``) have
their source path as the key. Shared chunks have an ``_`` prefix and
are only referenced transitively via ``imports`` fields on entries;
this module doesn't need to look them up directly.
"""

from __future__ import annotations

import json
import os
import threading

# Repo root -> ``static/dist/.vite/manifest.json``.
_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "static",
    "dist",
    ".vite",
    "manifest.json",
)
_DIST_DIR = os.path.dirname(os.path.dirname(_MANIFEST_PATH))

# Thread-safe lazy load: read the manifest once, cache the dict.
_manifest_cache: dict | None = None
_manifest_lock = threading.Lock()

# Sentinel meaning "we've tried to load and there's no manifest on disk".
# Distinguishes "not yet loaded" (None) from "loaded and empty" ({}) so we
# don't hit the filesystem on every single request in the source-fallback path.
_MANIFEST_MISSING: dict = {}


def _load_manifest() -> dict:
    """Read the manifest from disk, returning an empty dict if absent.

    Not intended to be called directly -- ``asset_url()`` handles the
    caching. Extracted only so the tests can exercise the parsing path
    without going through the caching layer.
    """
    try:
        with open(_MANIFEST_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return _MANIFEST_MISSING
    except (OSError, json.JSONDecodeError):
        # A corrupt manifest is the shipping-vector equivalent of a build
        # bug. Rather than crash the app on every request, fall back to
        # serving source files -- the pages still work, just uncompressed.
        # A monitoring signal (500 vs 200 with weird JS behavior) would be
        # more useful long-term, but this keeps the fallback story clean.
        return _MANIFEST_MISSING
    return data


def _get_manifest() -> dict:
    """Return the cached manifest, loading it on first access."""
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    with _manifest_lock:
        if _manifest_cache is None:
            _manifest_cache = _load_manifest()
    return _manifest_cache


def reload_manifest() -> None:
    """Discard the cached manifest so the next ``asset_url()`` re-reads disk.

    Useful in tests and in local development if you're re-running
    ``npm run build`` in a loop. Production callers never need this.
    """
    global _manifest_cache
    with _manifest_lock:
        _manifest_cache = None


def asset_url(name: str) -> str:
    """Return the URL path a template should use for JS entry ``name``.

    ``name`` is the bare page/module name without extension, e.g.
    ``'000-base'``, ``'010-plex'``, ``'overlayHandler'``. It matches the
    filename in ``static/local-js/`` (also matches ``page_info['template_name']``).

    Resolution order:

    1. If the manifest is loaded and has an entry keyed
       ``static/local-js/<name>.js``, return ``/static/dist/<manifest['file']>``.
       This is the fast, hashed, cache-busted, minified path used in
       production.
    2. Otherwise, return ``/static/local-js/<name>.js`` -- the raw
       source file, still served by Flask via the ``static`` blueprint.
       This is the dev-mode / source-checkout path and preserves the
       ``python quickstart.py`` after a clone experience.

    The returned string is always absolute (starts with ``/static/``) so
    callers can drop it directly into ``<script src=...>`` without
    ``url_for``.
    """
    manifest = _get_manifest()
    key = f"static/local-js/{name}.js"
    entry = manifest.get(key)
    if entry and "file" in entry:
        built_file = str(entry["file"]).lstrip("/")
        built_path = os.path.join(_DIST_DIR, *built_file.split("/"))
        if os.path.exists(built_path):
            return f"/static/dist/{built_file}"
    return f"/static/local-js/{name}.js"


__all__ = ["asset_url", "reload_manifest"]
