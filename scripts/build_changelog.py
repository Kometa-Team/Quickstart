#!/usr/bin/env python3
"""Build release notes without assuming the pending version has a stable tag."""

import argparse
import re
from pathlib import Path

try:
    from scripts import release
except ModuleNotFoundError:
    import release


def changelog(repository: str, target: str, source: str = "HEAD") -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected an owner/repository name")
    target_version = release.version(target)
    commit = release.git("rev-parse", "--verify", "--end-of-options", source + "^{commit}")
    # An unfinished release may already have VERSION updated without a matching
    # tag. Ignore prerelease tags and tags outside the source's ancestry.
    tags = release.git("tag", "--merged", commit, "--sort=-version:refname", "--list", "v*").splitlines()
    baseline = next((tag for tag in tags if re.fullmatch(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", tag) and release.version(tag[1:]) <= target_version), None)
    revision = f"{baseline}..{commit}" if baseline else commit
    url = f"https://github.com/{repository}"
    entries = release.git("log", revision, f"--pretty=format:* [`%h`]({url}/commit/%H): %s (@%an)", "--")
    history = f"{url}/compare/{baseline}...{commit}" if baseline else f"{url}/commits/{commit}"
    return f"## Commits\n\n{entries}\n\n[Full Code Changelog]({history})\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(changelog(args.repository, args.version, args.source), encoding="utf-8")


if __name__ == "__main__":
    main()
