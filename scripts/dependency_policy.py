"""Master-specific dependency gate. Inspect Git objects; never execute PR code."""

import json
import os
import re
import subprocess

try:
    from scripts import release
except ModuleNotFoundError:
    import release

MESSAGE = "Dependency updates must first merge into develop. Perform a Master Release to propagate approved dependency changes to master."
CHECK = "master-dependency-policy"


def dependency_path(path):
    return bool(
        re.search(
            r"(^|/)(requirements[^/]*\.txt|package(?:-lock)?\.json|npm-shrinkwrap\.json|uv\.lock|pyproject\.toml|Pipfile(?:\.lock)?|poetry\.lock|yarn\.lock|pnpm-lock\.yaml)$", path
        )
    )


def dependency_change(author, paths):
    return author == "dependabot[bot]" or any(dependency_path(path) for path in paths)


def main():
    event = json.loads(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8").read())
    repository = os.environ["GITHUB_REPOSITORY"]
    pr = event.get("pull_request")
    candidate = not pr
    if pr:
        if pr["base"]["ref"] != "master":
            return  # Never create a successful master gate on a develop PR.
        approved = pr["head"]["sha"]
    else:
        approved = event.get("after") or os.environ["GITHUB_SHA"]
        event.setdefault("ref", os.environ.get("GITHUB_REF", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", approved):
        raise RuntimeError("Unexpected commit identity")
    # Create a failing check first; a crash or retarget can never leave success.
    body = {"name": CHECK, "head_sha": approved, "status": "completed", "conclusion": "failure", "output": {"title": "Dependency integration policy", "summary": MESSAGE}}
    result = subprocess.run(["gh", "api", f"repos/{repository}/check-runs", "--method", "POST", "--input", "-"], input=json.dumps(body), text=True, capture_output=True, check=True)
    check_id = json.loads(result.stdout)["id"]
    master = release.snapshot("origin")["master"]
    if pr:
        release.git("fetch", "--no-tags", "origin", f"refs/pull/{pr['number']}/head")
        if release.git("rev-parse", "FETCH_HEAD") != approved:
            raise RuntimeError("PR changed; policy remains blocked")
        # Inspect every unique commit, including net-zero dependency changes.
        paths = release.git("log", "--format=", "--name-only", f"{master}..{approved}").splitlines()
        if dependency_change(pr["user"]["login"], paths):
            return
        latest = json.loads(release.run("gh", "api", f"repos/{repository}/pulls/{pr['number']}"))
        if latest["head"]["sha"] != approved or latest["base"]["ref"] != "master":
            return
    if candidate:
        target, build = release.metadata(approved)
        release.version(target)
        ref = f"refs/heads/release-candidates/{target}"
        if event["ref"] != ref or release.remote_refs("origin", ref).get(ref) != approved or build != "0":
            return
        release.require_fast_forwards(release.snapshot("origin"), approved)
    if release.remote_refs("origin", "refs/heads/master").get("refs/heads/master") != master:
        return
    body["conclusion"] = "success"
    body.pop("head_sha")
    body["output"]["summary"] = "Reviewed release candidate preserves all branch history." if candidate else "No dependency changes are introduced by this PR."
    subprocess.run(
        ["gh", "api", f"repos/{repository}/check-runs/{check_id}", "--method", "PATCH", "--input", "-"], input=json.dumps(body), text=True, capture_output=True, check=True
    )


if __name__ == "__main__":
    main()
