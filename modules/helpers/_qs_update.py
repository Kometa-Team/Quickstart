"""Quickstart version and update detection utilities extracted from the original helpers.py monolith."""

import copy
import os
import re
import subprocess
import sys
import time

from pathlib import Path

from modules.helpers._constants import BUILDNUM_FILE, QS_UPDATE_CACHE_TTL_SECONDS, VERSION_FILE, _QS_UPDATE_CACHE


def _run_git_remote(qs_root):
    qs_root = Path(qs_root or ".").resolve()
    is_windows = sys.platform.startswith("win")
    return subprocess.run(
        ["git", "remote"],
        cwd=qs_root,
        capture_output=True,
        text=True,
        shell=is_windows,
    )


def get_quickstart_update_remote(qs_root=None):
    try:
        remotes_out = _run_git_remote(qs_root or ".")
        remotes = (remotes_out.stdout or "").split()
    except Exception:
        remotes = []
    return "kometa-team" if "kometa-team" in remotes else "origin"


def build_quickstart_update_command(branch="master", qs_root=None, remote=None):
    branch = str(branch or "master").strip() or "master"
    remote = str(remote or get_quickstart_update_remote(qs_root)).strip() or "origin"
    remote_ref = f"{remote}/{branch}"
    return (
        f"git fetch {remote} --prune && "
        f"git switch -C {branch} --track {remote_ref} && "
        f"git reset --hard {remote_ref} && "
        "python -m pip install --upgrade pip && "
        "python -m pip install --no-cache-dir --upgrade -r requirements.txt"
    )


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


def _parse_quickstart_version(value):
    match = re.fullmatch(r"v?(\d+(?:\.\d+)*)(?:-build(\d+))?", str(value or "").strip(), re.IGNORECASE)
    if not match:
        return None
    base = tuple(int(part) for part in match.group(1).split("."))
    return base, int(match.group(2) or 0), bool(match.group(2))


def _is_remote_quickstart_version_newer(local_version, remote_version):
    if not remote_version:
        return False
    if str(local_version or "").strip().lower() in {"", "unknown"}:
        return True

    local = _parse_quickstart_version(local_version)
    remote = _parse_quickstart_version(remote_version)
    if not local or not remote:
        return str(remote_version).strip() != str(local_version or "").strip()

    local_base, local_build, local_has_build = local
    remote_base, remote_build, remote_has_build = remote
    max_len = max(len(local_base), len(remote_base))
    padded_local_base = local_base + (0,) * (max_len - len(local_base))
    padded_remote_base = remote_base + (0,) * (max_len - len(remote_base))
    if padded_remote_base != padded_local_base:
        return padded_remote_base > padded_local_base
    if local_has_build or remote_has_build:
        return remote_build > local_build
    return False


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

    update_available = _is_remote_quickstart_version_newer(local_version, remote_version)
    update_remote = get_quickstart_update_remote()

    # Determine Kometa branch
    kometa_branch = "nightly"

    os_name, os_ext = get_running_os()

    payload = {
        "local_version": local_version,
        "remote_version": remote_version,
        "branch": branch,
        "kometa_branch": kometa_branch,
        "update_available": update_available,
        "update_remote": update_remote,
        "update_command": build_quickstart_update_command(branch, remote=update_remote),
        "running_on": os_name,
        "file_ext": os_ext,
    }

    _QS_UPDATE_CACHE[cache_key] = {
        "created_at": time.monotonic(),
        "payload": copy.deepcopy(payload),
    }
    return payload


def perform_quickstart_update(qs_root, branch="master"):
    """
    Deterministic Quickstart update (mirrors Kometa updater):
        - Choose upstream remote: prefer 'kometa-team', else 'origin'
        - git fetch <upstream> --prune
        - git switch -C <branch> --track <upstream>/<branch>  (fallback to checkout)
        - git reset --hard <upstream>/<branch>
        - python -m pip install --upgrade pip
        - python -m pip install --no-cache-dir --upgrade -r requirements.txt
    Returns: {"success": bool, "log": [str, ...]}
    """
    logs, success = [], True
    try:
        qs_root = Path(qs_root).resolve()
        is_windows = sys.platform.startswith("win")

        upstream = get_quickstart_update_remote(qs_root)
        logs.append(f"🔗 Using Quickstart remote: {upstream}")
        logs.append(f"⚙️ Target Quickstart branch: {branch}")

        def run(cmd, label=None):
            if label:
                logs.append(label)
            p = subprocess.run(cmd, cwd=qs_root, capture_output=True, text=True, shell=is_windows)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            if out:
                logs.append(out)
            if p.returncode != 0 and err:
                logs.append(err)
            return p

        # 1) fetch (ensure upstream/<branch> exists)
        p = run(["git", "fetch", upstream, "--prune"], f"📥 git fetch {upstream} --prune")
        success &= p.returncode == 0

        # 2) switch to branch (fallback to checkout)
        if success:
            p = run(
                ["git", "switch", "-C", branch, "--track", f"{upstream}/{branch}"],
                f"🔀 git switch -C {branch} --track {upstream}/{branch}",
            )
            if p.returncode != 0:
                p = run(
                    ["git", "checkout", "-B", branch, f"{upstream}/{branch}"],
                    f"🔁 fallback: git checkout -B {branch} {upstream}/{branch}",
                )
                success &= p.returncode == 0

        # 3) hard reset to upstream tip
        if success:
            p = run(
                ["git", "reset", "--hard", f"{upstream}/{branch}"],
                f"↩️ git reset --hard {upstream}/{branch}",
            )
            success &= p.returncode == 0

        # 4) upgrade pip for this interpreter (QS uses its own Python)
        if success:
            logs.append("\n⬆️ Upgrading pip...")
            p = subprocess.run(
                [str(Path(sys.executable)), "-m", "pip", "install", "--upgrade", "pip"],
                cwd=qs_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        # 5) install requirements
        if success:
            logs.append("\n📦 Installing requirements...")
            p = subprocess.run(
                [
                    str(Path(sys.executable)),
                    "-m",
                    "pip",
                    "install",
                    "--no-cache-dir",
                    "--upgrade",
                    "-r",
                    "requirements.txt",
                ],
                cwd=qs_root,
                capture_output=True,
                text=True,
                shell=is_windows,
            )
            logs.append((p.stdout or "").strip() or "(no output)")
            if p.returncode != 0:
                logs.append((p.stderr or "").strip())
                success = False

        logs.append("\n✅ Update completed." if success else "\n❌ Update failed.")
        return {"success": success, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}
