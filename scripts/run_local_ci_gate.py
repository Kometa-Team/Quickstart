#!/usr/bin/env python3
"""Run the repo-local checks that most closely mirror the GitHub CI gate.

This is intended to be run manually before pushing when developers want to catch
the same classes of issues that would fail the repo's lint and build jobs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], *, env: dict[str, str] | None = None) -> int:
    print(f"\n==> {' '.join(command)}")
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env)
    if completed.returncode != 0:
        return completed.returncode
    return 0


def main() -> int:
    env = os.environ.copy()
    env["SKIP"] = "repo-ci-gate"
    npm_command = "npm.cmd" if os.name == "nt" else "npm"

    # Mirror the repo's lint workflow exactly, but skip the current custom hook so
    # that the nested invocation does not recursively invoke itself. This keeps the
    # local gate aligned with the GitHub lint job while remaining safe as a hook.
    result = run([sys.executable, "-m", "pre_commit", "run", "--all-files", "--show-diff-on-failure", "--color=always"], env=env)
    if result != 0:
        return result

    result = run([sys.executable, "scripts/run_tests.py", "--setup", "--unit"], env=env)
    if result != 0:
        return result

    result = run([npm_command, "ci", "--no-fund", "--no-audit"], env=env)
    if result != 0:
        return result

    result = run([npm_command, "run", "build"], env=env)
    if result != 0:
        return result

    print("\nLocal CI gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
