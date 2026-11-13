"""Derive the Docker image tag for a pull request branch.

Single source of truth for ci.yml and tag-cleanup.yml: the tag an image is built under and the tag that gets deleted must come from the same rule.

Inputs (environment variables, never pasted into a shell line):
    HEAD_REF   the pull request's head branch name
    HEAD_REPO  the head repository as "owner/name"

Output: "tag-name=<tag>" appended to $GITHUB_OUTPUT (when set) and printed. Exits 1 if no valid Docker tag can be derived.
"""

import os
import re
import sys

DOCKER_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")


def derive_tag(head_ref, head_repo):
    branch = re.sub(r"[^a-zA-Z0-9._-]", "-", head_ref)
    owner = head_repo.split("/", 1)[0]
    tag = owner if branch in ("master", "develop") else branch
    if not DOCKER_TAG_RE.match(tag):
        raise ValueError(f"'{tag}' is not a valid Docker tag (derived from branch '{branch}' in '{owner}')")
    return tag


def main():
    head_ref = os.environ.get("HEAD_REF", "")
    head_repo = os.environ.get("HEAD_REPO", "")
    if not head_ref or not head_repo:
        print("::error::HEAD_REF and HEAD_REPO must both be set")
        return 1
    try:
        tag = derive_tag(head_ref, head_repo)
    except ValueError as exc:
        print(f"::error::{exc}")
        return 1
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"tag-name={tag}\n")
    print(f"tag-name={tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
