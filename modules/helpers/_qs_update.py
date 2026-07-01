"""Quickstart version and update detection utilities extracted from _legacy.py."""

import copy
import os
import time

from modules.helpers._legacy import BUILDNUM_FILE, QS_UPDATE_CACHE_TTL_SECONDS, VERSION_FILE, _QS_UPDATE_CACHE


def get_kometa_branch():
    """Fetch the correct branch (master or nightly)."""
    version_info = check_for_update()
    return version_info.get("kometa_branch", "nightly")  # Default to nightly branch


def get_version(branch):
    """Read the local VERSION file"""
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            version = f.read().strip()
            if branch == "master":
                return version
            build_num = "0"
            if os.path.exists(BUILDNUM_FILE):
                with open(BUILDNUM_FILE, "r", encoding="utf-8") as g:
                    build_num = g.read().strip()
            return f"{version}-build{build_num}"
    return "unknown"


def check_for_update():
    """Compare the local version with the remote version and determine Kometa branch."""
    from modules.helpers._version import get_branch, get_remote_version
    from modules.helpers._os import get_running_os

    branch = get_branch()
    local_version = get_version(branch)
    cache_key = (branch, local_version)
    cached = _QS_UPDATE_CACHE.get(cache_key)
    if cached:
        age = time.monotonic() - cached.get("created_at", 0)
        if age <= QS_UPDATE_CACHE_TTL_SECONDS:
            return copy.deepcopy(cached.get("payload") or {})

    remote_version = get_remote_version(branch)

    update_available = remote_version and remote_version != local_version

    # Determine Kometa branch
    kometa_branch = "nightly"

    os_name, os_ext = get_running_os()

    payload = {
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": branch,
        "kometa_branch": kometa_branch,
        "update_available": update_available,
        "running_on": os_name,
        "file_ext": os_ext,
    }

    _QS_UPDATE_CACHE[cache_key] = {
        "created_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }
    return payload
