"""Plex discovery cache utilities extracted from the original helpers.py monolith."""

import copy
import hashlib
import time

from modules.helpers._constants import PLEX_DISCOVERY_CACHE_TTL_SECONDS

_PLEX_DISCOVERY_CACHE: dict = {}


def _plex_discovery_cache_key(kind, plex_url, plex_token):
    normalized_url = str(plex_url or "").strip().rstrip("/").lower()
    token_digest = hashlib.sha256(str(plex_token or "").encode("utf-8")).hexdigest()
    return kind, normalized_url, token_digest


def _get_plex_discovery_cache(kind, plex_url, plex_token):
    key = _plex_discovery_cache_key(kind, plex_url, plex_token)
    entry = _PLEX_DISCOVERY_CACHE.get(key)
    if not entry:
        return None
    age = time.monotonic() - entry.get("created_at", 0)
    if age > PLEX_DISCOVERY_CACHE_TTL_SECONDS:
        _PLEX_DISCOVERY_CACHE.pop(key, None)
        return None
    return copy.deepcopy(entry.get("payload"))


def _set_plex_discovery_cache(kind, plex_url, plex_token, payload):
    if not plex_url or not plex_token or not isinstance(payload, dict):
        return
    key = _plex_discovery_cache_key(kind, plex_url, plex_token)
    _PLEX_DISCOVERY_CACHE[key] = {
        "created_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }


def get_cached_plex_validation(plex_url, plex_token):
    return _get_plex_discovery_cache("validation", plex_url, plex_token)


def set_cached_plex_validation(plex_url, plex_token, payload):
    _set_plex_discovery_cache("validation", plex_url, plex_token, payload)


def get_cached_plex_metadata(plex_url, plex_token):
    return _get_plex_discovery_cache("metadata", plex_url, plex_token)


def set_cached_plex_metadata(plex_url, plex_token, payload):
    _set_plex_discovery_cache("metadata", plex_url, plex_token, payload)


def get_cached_plex_refresh(plex_url, plex_token):
    return _get_plex_discovery_cache("refresh", plex_url, plex_token)


def set_cached_plex_refresh(plex_url, plex_token, payload):
    _set_plex_discovery_cache("refresh", plex_url, plex_token, payload)


def clear_plex_discovery_cache():
    _PLEX_DISCOVERY_CACHE.clear()
