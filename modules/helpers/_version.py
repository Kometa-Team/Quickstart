"""Version/branch detection utilities extracted from the original helpers.py monolith."""

import os

try:
    from git import Repo
except ImportError:
    Repo = None  # Prevents errors if GitPython is missing


import requests


def get_remote_version(branch):
    """Fetch the latest VERSION file from the correct GitHub branch."""

    try:
        response = requests.get(
            f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/VERSION",
            timeout=5,
        )
        response.raise_for_status()
        version = response.text.strip()
    except requests.RequestException:
        return None  # If request fails, return None
    if branch == "master":
        return version

    try:
        response = requests.get(
            f"https://raw.githubusercontent.com/Kometa-Team/Quickstart/{branch}/BUILDNUM",
            timeout=5,
        )
        response.raise_for_status()
        build_num = response.text.strip()
    except requests.RequestException:
        return None

    if not build_num or not build_num.isdigit():
        return None
    return f"{version}-build{build_num}"


def get_branch():
    # First priority: environment variable (Docker and CI use this)
    branch = os.getenv("BRANCH_NAME")
    if branch:
        return branch

    # Otherwise, try GitPython (if available)
    if Repo:
        try:
            return Repo(path=".").head.ref.name  # noqa
        except Exception:  # noqa
            pass  # Ignore errors if GitPython fails

    # Fallback: Use BRANCH_NAME from the environment (for non-Docker cases)
    return os.getenv("BRANCH_NAME", "master")
