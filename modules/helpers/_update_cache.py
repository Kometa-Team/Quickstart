"""Kometa and ImageMaid update caching utilities extracted from _legacy.py."""

import copy
import time

from pathlib import Path

from modules.helpers._legacy import (
    IMAGEMAID_BRANCH_OVERRIDES,
    IMAGEMAID_UPDATE_CACHE_TTL_SECONDS,
    KOMETA_BRANCH_OVERRIDES,
    KOMETA_UPDATE_CACHE_TTL_SECONDS,
    _IMAGEMAID_UPDATE_CACHE,
    _KOMETA_UPDATE_CACHE,
)


def _kometa_update_cache_key(kometa_root, branch, local_version, local_sha=None, local_branch=None):
    try:
        root = str(Path(kometa_root).resolve())
    except Exception:
        root = str(kometa_root or "")
    return root, str(branch or "").strip(), str(local_version or "").strip(), str(local_sha or "").strip(), str(local_branch or "").strip()


def normalize_kometa_branch_override(value):
    branch = str(value or "").strip().lower()
    return branch if branch in KOMETA_BRANCH_OVERRIDES else ""


def resolve_kometa_update_branch(branch_override=None):
    branch = normalize_kometa_branch_override(branch_override)
    from modules.helpers._qs_update import get_kometa_branch

    return branch or get_kometa_branch()


def get_cached_kometa_update(kometa_root=None, force_refresh=False, branch_override=None):
    from modules.helpers._kometa_version import check_kometa_update, get_kometa_local_branch, get_kometa_local_sha, get_kometa_local_version

    branch = resolve_kometa_update_branch(branch_override)
    local_version = get_kometa_local_version(kometa_root)
    local_sha = get_kometa_local_sha(kometa_root)
    local_branch = get_kometa_local_branch(kometa_root)
    key = _kometa_update_cache_key(kometa_root or ".", branch, local_version, local_sha=local_sha, local_branch=local_branch)

    if not force_refresh:
        entry = _KOMETA_UPDATE_CACHE.get(key)
        if entry:
            age = time.monotonic() - entry.get("created_at", 0)
            if age <= KOMETA_UPDATE_CACHE_TTL_SECONDS:
                payload = copy.deepcopy(entry.get("payload") or {})
                payload["cached"] = True
                return payload
            _KOMETA_UPDATE_CACHE.pop(key, None)

    payload = check_kometa_update(kometa_root, branch_override=branch_override)
    if isinstance(payload, dict):
        payload = copy.deepcopy(payload)
        payload["cached"] = False
        _KOMETA_UPDATE_CACHE[key] = {"created_at": time.monotonic(), "payload": copy.deepcopy(payload)}
        return payload
    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": None,
        "remote_sha": None,
        "branch": branch,
        "update_available": False,
        "cached": False,
    }


def invalidate_cached_kometa_update(kometa_root=None):
    if kometa_root is None:
        _KOMETA_UPDATE_CACHE.clear()
        return
    try:
        target_root = str(Path(kometa_root).resolve())
    except Exception:
        target_root = str(kometa_root or "")
    for key in list(_KOMETA_UPDATE_CACHE.keys()):
        if key[0] == target_root:
            _KOMETA_UPDATE_CACHE.pop(key, None)


def _imagemaid_update_cache_key(imagemaid_root, branch, local_version=None, local_sha=None, local_branch=None):
    try:
        root = str(Path(imagemaid_root).resolve())
    except Exception:
        root = str(imagemaid_root or "")
    return root, str(branch or "").strip(), str(local_version or "").strip(), str(local_sha or "").strip(), str(local_branch or "").strip()


def normalize_imagemaid_branch_override(value):
    branch = str(value or "").strip().lower()
    return branch if branch in IMAGEMAID_BRANCH_OVERRIDES else ""


def resolve_imagemaid_update_branch(branch_override=None):
    branch = normalize_imagemaid_branch_override(branch_override)
    if branch:
        return branch
    from modules.helpers._git import detect_git_branch
    from modules.helpers._pid import get_app_root

    qs_branch = detect_git_branch(get_app_root())
    return "master" if qs_branch == "master" else "develop"


def get_cached_imagemaid_update(imagemaid_root=None, force_refresh=False, branch_override=None):
    from modules.helpers._kometa_version import check_imagemaid_update, get_imagemaid_local_branch, get_imagemaid_local_sha, get_imagemaid_local_version

    branch = resolve_imagemaid_update_branch(branch_override)
    local_version = get_imagemaid_local_version(imagemaid_root)
    local_sha = get_imagemaid_local_sha(imagemaid_root)
    local_branch = get_imagemaid_local_branch(imagemaid_root)
    key = _imagemaid_update_cache_key(imagemaid_root or ".", branch, local_version=local_version, local_sha=local_sha, local_branch=local_branch)

    if not force_refresh:
        entry = _IMAGEMAID_UPDATE_CACHE.get(key)
        if entry:
            age = time.monotonic() - entry.get("created_at", 0)
            if age <= IMAGEMAID_UPDATE_CACHE_TTL_SECONDS:
                payload = copy.deepcopy(entry.get("payload") or {})
                payload["cached"] = True
                return payload
            _IMAGEMAID_UPDATE_CACHE.pop(key, None)

    payload = check_imagemaid_update(imagemaid_root, branch_override=branch_override)
    if isinstance(payload, dict):
        payload = copy.deepcopy(payload)
        payload["cached"] = False
        _IMAGEMAID_UPDATE_CACHE[key] = {"created_at": time.monotonic(), "payload": copy.deepcopy(payload)}
        return payload
    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": None,
        "remote_sha": None,
        "branch": branch,
        "update_available": False,
        "cached": False,
    }


def invalidate_cached_imagemaid_update(imagemaid_root=None):
    if imagemaid_root is None:
        _IMAGEMAID_UPDATE_CACHE.clear()
        return
    try:
        target_root = str(Path(imagemaid_root).resolve())
    except Exception:
        target_root = str(imagemaid_root or "")
    for key in list(_IMAGEMAID_UPDATE_CACHE.keys()):
        if key[0] == target_root:
            _IMAGEMAID_UPDATE_CACHE.pop(key, None)
