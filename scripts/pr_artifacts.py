"""Names for read-only PR build artifacts; branch names never identify remote tags."""

import re


def artifact_name(number: int, sha: str, branch: str) -> str:
    # Reject rather than sanitize: different hostile names must never collide.
    if number <= 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid PR identity")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", branch) or ".." in branch or "//" in branch:
        raise ValueError("Unexpected PR branch name")
    return f"pr-{number}-{sha}"


def cleanup_target(*_args, **_kwargs):
    # PR images are now Actions artifacts with retention, never registry tags.
    # There is deliberately no branch-to-Docker-tag conversion or DELETE path.
    raise RuntimeError("Remote PR cleanup is disabled: no verified registry artifact exists")
