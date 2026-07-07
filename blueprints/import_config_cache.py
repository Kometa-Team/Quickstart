"""Import-preview session cache load helpers.

The four routes in :mod:`blueprints.import_config_routes` share a
common pattern for looking up the disk-backed preview cache written
by ``/import-config/preview``:

1. Validate the request token against the session token.
2. Read the cache path from the session.
3. Load the JSON blob at that path.

Three of the four routes had this pattern duplicated inline
(``import_config_report``, ``import_config_preview_mapped``,
``import_config_confirm``).  This module owns the shared load.

Each function returns ``(cached_dict, cache_path, None)`` on success or
``(None, None, error_response_tuple)`` on failure so the caller can:

.. code-block:: python

    cached, cache_path, err = load_preview_cache(token)
    if err:
        return err
    ...

``cache_path`` is returned so the two routes that need to write back
or remove the cache file (``preview_mapped`` and ``confirm``) don't
have to re-read the session key themselves.
"""

from __future__ import annotations

import json

from flask import jsonify, session


def load_preview_cache(token: str | None) -> tuple[dict | None, str | None, tuple | None]:
    """Validate the import-preview token and load the cached blob.

    :param token: the token from the incoming request.
    :returns: ``(cached_dict, cache_path, None)`` on success or
              ``(None, None, (jsonify_response, status_code))`` on
              failure.  ``cache_path`` is returned so callers that
              need to write-back the modified cache (preview_mapped)
              or remove it (confirm) don't have to re-read the
              session key.

    Three distinct failure modes, each with a byte-identical error
    message to the original inline code:

    * Missing / mismatched token -> "Import token is invalid."
    * Missing session cache path -> "Import preview not found."
    * File read or JSON parse fails -> "Import preview is unavailable."
    """
    if not token or token != session.get("import_preview_token"):
        return None, None, (jsonify(success=False, message="Import token is invalid."), 400)

    cache_path = session.get("import_preview_path")
    if not cache_path:
        return None, None, (jsonify(success=False, message="Import preview not found."), 400)

    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except Exception:
        return None, None, (jsonify(success=False, message="Import preview is unavailable."), 400)

    return cached, cache_path, None
