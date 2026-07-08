#!/usr/bin/env python3
"""Pre-commit wrapper that runs pyspelling on the repo's markdown files.

Why a wrapper (instead of `entry: pyspelling -c .spellcheck.yml ...`):

  1. `aspell` is a SYSTEM binary that pre-commit's Python venv cannot
     install. If it's missing, pyspelling emits an unhelpful traceback.
     This wrapper checks up-front and prints a friendly "install aspell
     via <pkg manager>" message before bailing.

  2. Keeps the pre-commit YAML tidy (no long multi-line shell entry).

  3. Gives one clear place to tweak the config path or task name if
     the .spellcheck.yml layout ever changes.

The script runs unconditionally when triggered by pre-commit's
`files: '\\.md$'` filter -- pyspelling reads .spellcheck.yml for its
own file list (currently just top-level *.md), so we don't try to
second-guess it with per-file args.

Exit codes:
  0  -- spellcheck passed OR aspell is missing (we skip with a warning
        rather than blocking the commit; devs on machines without
        aspell can still commit, they just don't get local checking
        -- CI will still catch spelling problems)
  1  -- spellcheck ran and found misspellings
  2  -- unexpected error (bad config, pyspelling crash, etc.)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".spellcheck.yml"
TASK_NAME = "Markdown"


def _install_hint_for_platform() -> str:
    """Best-effort per-OS aspell install command. Same detection
    approach as modules/_preflight.py to keep the two consistent."""
    if sys.platform == "darwin":
        return "brew install aspell"
    if sys.platform.startswith("linux"):
        try:
            content = Path("/etc/os-release").read_text(encoding="utf-8").lower()
        except OSError:
            return "install the 'aspell' package for your distribution"
        if "id=debian" in content or "id_like=debian" in content or "ubuntu" in content:
            return "sudo apt install aspell aspell-en"
        if "id=fedora" in content or "rhel" in content or "centos" in content:
            return "sudo dnf install aspell aspell-en"
        return "install the 'aspell' package for your distribution"
    if sys.platform.startswith("win"):
        return "install aspell via Chocolatey (choco install aspell) " "or use WSL / skip this hook on Windows"
    return "install the 'aspell' package for your platform"


def main() -> int:
    if shutil.which("aspell") is None:
        sys.stderr.write(
            "\n"
            "  [spellcheck] skipping: 'aspell' binary not found on PATH.\n"
            f"  [spellcheck] to enable local spellcheck: {_install_hint_for_platform()}\n"
            "  [spellcheck] (CI will still catch spelling issues on push.)\n"
            "\n"
        )
        return 0

    if not CONFIG.exists():
        sys.stderr.write(f"[spellcheck] config not found: {CONFIG}\n")
        return 2

    # Delegate to pyspelling. It picks up file patterns from .spellcheck.yml.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pyspelling", "-c", str(CONFIG), "--name", TASK_NAME],
            cwd=str(REPO_ROOT),
            check=False,
        )
    except FileNotFoundError:
        sys.stderr.write(
            "[spellcheck] pyspelling module not importable. "
            "This should have been auto-installed by pre-commit; "
            "try `pre-commit clean && pre-commit install --install-hooks`.\n"
        )
        return 2

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
