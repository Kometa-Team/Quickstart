"""Kometa and ImageMaid version/update check utilities extracted from _legacy.py."""

import os

from pathlib import Path

from flask import current_app as app
from flask import has_app_context, has_request_context, session

from modules.helpers._legacy import CONFIG_DIR, IMAGEMAID_GITHUB_API_BRANCH, IMAGEMAID_GITHUB_BASE_URL


def get_kometa_remote_version(branch="nightly"):
    import requests

    url = f"https://raw.githubusercontent.com/Kometa-Team/Kometa/{branch}/VERSION"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        return None


def get_kometa_local_version(kometa_root=None):
    if kometa_root is None:
        kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    else:
        kometa_root = Path(kometa_root)

    version_path = kometa_root / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "unknown"


def get_kometa_local_sha(kometa_root=None):
    from modules.helpers._legacy import _read_text

    if kometa_root is None:
        kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    else:
        kometa_root = Path(kometa_root)

    return _read_text(kometa_root / ".kometa_sha")


def get_kometa_local_branch(kometa_root=None):
    from modules.helpers._legacy import _read_text
    from modules.helpers._update_cache import normalize_kometa_branch_override

    if kometa_root is None:
        kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    else:
        kometa_root = Path(kometa_root)

    return normalize_kometa_branch_override(_read_text(kometa_root / ".kometa_branch"))


def get_kometa_remote_sha(branch="nightly"):
    from modules.helpers._legacy import _get_upstream_sha

    return _get_upstream_sha(branch, [])


def get_imagemaid_root_path() -> Path:
    base = None
    if has_app_context():
        base = app.config.get("IMAGEMAID_ROOT")
    if not base and has_request_context():
        base = session.get("imagemaid_root")
    if not base:
        base = os.path.join(CONFIG_DIR, "imagemaid")
    return Path(os.path.normpath(base)).resolve()


def get_imagemaid_local_sha(imagemaid_root=None):
    from modules.helpers._legacy import _read_text

    if imagemaid_root is None:
        imagemaid_root = get_imagemaid_root_path()
    else:
        imagemaid_root = Path(imagemaid_root)
    return _read_text(imagemaid_root / ".imagemaid_sha")


def get_imagemaid_local_version(imagemaid_root=None):
    if imagemaid_root is None:
        imagemaid_root = get_imagemaid_root_path()
    else:
        imagemaid_root = Path(imagemaid_root)
    version_path = imagemaid_root / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return "unknown"


def get_imagemaid_local_branch(imagemaid_root=None):
    from modules.helpers._legacy import _read_text
    from modules.helpers._update_cache import normalize_imagemaid_branch_override

    if imagemaid_root is None:
        imagemaid_root = get_imagemaid_root_path()
    else:
        imagemaid_root = Path(imagemaid_root)
    return normalize_imagemaid_branch_override(_read_text(imagemaid_root / ".imagemaid_branch"))


def get_imagemaid_remote_sha(branch="develop"):
    from modules.helpers._legacy import _get_upstream_sha

    return _get_upstream_sha(branch, [], api_url_template=IMAGEMAID_GITHUB_API_BRANCH, label="ImageMaid")


def get_imagemaid_remote_version(branch="develop"):
    import requests

    url = f"{IMAGEMAID_GITHUB_BASE_URL}/{branch}/VERSION"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return response.text.strip()
    except requests.RequestException:
        return None


def check_imagemaid_update(imagemaid_root=None, branch_override=None):
    from modules.helpers._update_cache import resolve_imagemaid_update_branch

    branch = resolve_imagemaid_update_branch(branch_override)
    local_version = get_imagemaid_local_version(imagemaid_root)
    local_sha = get_imagemaid_local_sha(imagemaid_root)
    local_branch = get_imagemaid_local_branch(imagemaid_root)
    remote_version = get_imagemaid_remote_version(branch)
    remote_sha = get_imagemaid_remote_sha(branch)
    branch_mismatch = bool(local_branch and local_branch != branch)

    if local_sha and remote_sha:
        update_available = branch_mismatch or (local_sha != remote_sha)
        comparison_basis = "sha"
    else:
        update_available = branch_mismatch or bool(remote_version and remote_version != local_version)
        comparison_basis = "version"

    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": remote_version,
        "remote_sha": remote_sha,
        "branch": branch,
        "branch_mismatch": branch_mismatch,
        "comparison_basis": comparison_basis,
        "update_available": update_available,
    }


def check_kometa_update(kometa_root=None, branch_override=None):
    from modules.helpers._update_cache import resolve_kometa_update_branch

    branch = resolve_kometa_update_branch(branch_override)
    local_version = get_kometa_local_version(kometa_root)
    local_sha = get_kometa_local_sha(kometa_root)
    local_branch = get_kometa_local_branch(kometa_root)
    remote_version = get_kometa_remote_version(branch)
    remote_sha = get_kometa_remote_sha(branch)
    branch_mismatch = bool(local_branch and local_branch != branch)

    if local_sha and remote_sha:
        update_available = branch_mismatch or (local_sha != remote_sha)
        comparison_basis = "sha"
    else:
        update_available = branch_mismatch or bool(remote_version and remote_version != local_version)
        comparison_basis = "version"

    return {
        "local_version": local_version,
        "local_sha": local_sha,
        "local_branch": local_branch,
        "remote_version": remote_version,
        "remote_sha": remote_sha,
        "branch": branch,
        "branch_mismatch": branch_mismatch,
        "comparison_basis": comparison_basis,
        "update_available": update_available,
    }
