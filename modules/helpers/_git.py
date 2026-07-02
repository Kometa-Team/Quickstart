"""Git branch detection utility extracted from _legacy.py."""

import shutil
import subprocess

from pathlib import Path

try:
    from git import Repo
except ImportError:
    Repo = None


def detect_git_branch(repo_root=None, default="develop"):
    from modules.helpers._pid import get_app_root

    root = Path(repo_root or get_app_root()).resolve()

    if Repo is not None:
        try:
            repo = Repo(root, search_parent_directories=True)
            branch_name = str(repo.active_branch.name or "").strip()
            if branch_name:
                return branch_name
        except Exception:
            pass

    git_bin = shutil.which("git")
    if git_bin:
        try:
            result = subprocess.run(
                [git_bin, "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                shell=False,
            )
            branch_name = (result.stdout or "").strip()
            if result.returncode == 0 and branch_name:
                return branch_name
        except Exception:
            pass

    return default
