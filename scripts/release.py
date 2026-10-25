#!/usr/bin/env python3
"""Prepare reviewed release candidates and promote them without rewriting history."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BRANCHES = ("develop", "master", "hotfix")


def run(*args: str) -> str:
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def git(*args: str) -> str:
    return run("git", *args)


def ancestor(old: str, new: str) -> bool:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", old, new], capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode())
    return result.returncode == 0


def version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", value):
        raise ValueError(f"Invalid version: {value!r}")
    return tuple(map(int, value.split(".")))


def target_version(base: str, kind: str) -> str:
    parts = list(version(base))
    if kind == "resume":
        return base
    index = {"major": 0, "minor": 1, "patch": 2}[kind]
    parts[index] += 1
    parts[index + 1 :] = [0] * (2 - index)
    return ".".join(map(str, parts))


def remote_refs(remote: str, *refs: str) -> dict[str, str]:
    output = git("ls-remote", "--refs", remote, *refs)
    return dict(line.split()[::-1] for line in output.splitlines())


def snapshot(remote: str) -> dict[str, str]:
    refs = remote_refs(remote, *(f"refs/heads/{branch}" for branch in BRANCHES))
    heads = {branch: refs[f"refs/heads/{branch}"] for branch in BRANCHES}
    git("fetch", "--no-tags", remote, *(f"refs/heads/{branch}" for branch in BRANCHES))
    if remote_refs(remote, *refs) != refs:
        raise RuntimeError("Remote heads changed during fetch; start a fresh review.")
    return heads


def unchanged(remote: str, heads: dict[str, str]) -> None:
    expected = {f"refs/heads/{branch}": sha for branch, sha in heads.items()}
    if remote_refs(remote, *expected) != expected:
        raise RuntimeError("Remote heads changed since preparation; no promotion attempted. Start a fresh review.")


def guarded_push(remote: str, expected: dict[str, str], targets: dict[str, str]) -> None:
    """Compare advertised old IDs, then let Git atomically compare and swap them.

    A preflight ls-remote alone leaves a race before push advertisement. The
    pre-push hook closes it without enabling force updates or using force leases.
    """
    with tempfile.TemporaryDirectory(prefix="quickstart-release-") as directory:
        hooks = Path(directory)
        guard = hooks / "guard.py"
        guard.write_text(
            "import sys\n"
            f"expected = {expected!r}\n"
            f"targets = {targets!r}\n"
            "seen = set()\n"
            "for line in sys.stdin:\n"
            "    local_ref, local_sha, remote_ref, remote_sha = line.split()\n"
            "    if remote_ref not in expected or expected[remote_ref] != remote_sha or targets[remote_ref] != local_sha:\n"
            "        sys.exit('Remote advertisement changed; promotion aborted: ' + remote_ref)\n"
            "    seen.add(remote_ref)\n"
            "missing = {ref for ref in expected if expected[ref] != targets[ref]} - seen\n"
            "if missing:\n"
            "    sys.exit('Remote advertisement changed; expected updates missing: ' + repr(missing))\n",
            encoding="utf-8",
        )
        hook = hooks / "pre-push"
        executable = shlex.quote(sys.executable.replace("\\", "/"))
        script = shlex.quote(guard.as_posix())
        hook.write_text(f"#!/bin/sh\nexec {executable} {script}\n", encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        credentials = ("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential") if os.environ.get("GH_TOKEN") else ()
        git(*credentials, "-c", f"core.hooksPath={hooks.as_posix()}", "push", "--atomic", remote, *(f"{sha}:{ref}" for ref, sha in targets.items()))


def metadata(commit: str) -> tuple[str, str]:
    return git("show", f"{commit}:VERSION"), git("show", f"{commit}:BUILDNUM")


def require_fast_forwards(heads: dict[str, str], candidate: str) -> None:
    for branch, sha in heads.items():
        if not ancestor(sha, candidate):
            raise RuntimeError(f"{branch} has commits outside the candidate; reconcile and validate again.")


def validate_state(state: dict) -> None:
    version(state["target"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", state["remote"]):
        raise RuntimeError("Recovery state must name a configured Git remote, not a URL or Git option.")
    if set(state["heads"]) != set(BRANCHES) or any(not re.fullmatch(r"[0-9a-f]{40}", value) for value in (*state["heads"].values(), state["tree"], state["candidate"])):
        raise RuntimeError("Recovery state contains invalid object IDs or branch names.")
    if state["ref"] != f"refs/heads/release-candidates/{state['target']}":
        raise RuntimeError("Recovery state is not a versioned candidate ref.")


def prepare(args: argparse.Namespace) -> None:
    if git("status", "--porcelain"):
        raise RuntimeError("Preparation requires a clean checkout.")
    target = target_version(args.base_version, args.release_type)
    heads = snapshot(args.remote)
    ref = f"refs/heads/release-candidates/{target}"
    candidates = remote_refs(args.remote, ref)
    if ref in candidates:
        candidate = candidates[ref]
        git("fetch", args.remote, ref)
        require_fast_forwards(heads, candidate)
        git("checkout", "--detach", candidate)
        if metadata(candidate) != (target, "0"):
            raise RuntimeError("Existing candidate has inconsistent release metadata.")
    else:
        git("checkout", "--detach", heads["develop"])
        current, build = metadata("HEAD")
        # A fixed base version is the retry key. Never derive a new version from
        # the current branch on a rerun, including a legacy partial promotion.
        if current != args.base_version and (current, build) != (target, "0"):
            raise RuntimeError("Develop does not match the requested base or pending release.")
        if args.release_type == "resume" and (current, build) != (target, "0"):
            raise RuntimeError("Resume requires the existing release with BUILDNUM=0.")
        if args.release_type != "resume":
            for branch in ("master", "hotfix"):
                released, _ = metadata(heads[branch])
                if version(released) > version(args.base_version) and released != target:
                    raise RuntimeError(f"{branch} has a newer release; review the requested version.")
                # Do not step over an interrupted release with a new dispatch.
                if version(released) < version(args.base_version):
                    raise RuntimeError("An earlier release is incomplete. Resume that version first.")
        for branch in ("master", "hotfix"):
            if not ancestor(heads[branch], "HEAD"):
                print(f"Reconciling unique {branch} commits with a normal merge.", flush=True)
                git("merge", "--no-ff", "--no-edit", heads[branch], "-m", f"Reconcile {branch} before release {target}")
        # Merge conflicts stop above. No automatic ours/theirs resolution.
        require_fast_forwards(heads, "HEAD")
        if metadata("HEAD")[0] not in (args.base_version, target):
            raise RuntimeError("Reconciliation changed the release version unexpectedly.")
        Path("VERSION").write_text(target + "\n", encoding="utf-8")
        Path("BUILDNUM").write_text("0\n", encoding="utf-8")
        git("add", "VERSION", "BUILDNUM")
    state = {"target": target, "heads": heads, "ref": ref, "tree": git("write-tree"), "remote": args.remote}
    Path(args.state).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))


def finalize(state: dict) -> None:
    # Validation tools must not silently change the reviewed tree.
    git("diff", "--exit-code")
    if git("write-tree") != state["tree"]:
        raise RuntimeError("Validation changed the prepared tree; review it again.")
    if git("diff", "--cached", "--name-only"):
        git("commit", "-m", f"Quickstart Release {state['target']}")
    if metadata("HEAD") != (state["target"], "0"):
        raise RuntimeError("Release metadata changed during validation.")
    state["candidate"] = git("rev-parse", "HEAD")


def publish(state: dict, approved_previous: str = "") -> None:
    validate_state(state)
    version(state["target"])
    if state["ref"] != f"refs/heads/release-candidates/{state['target']}" or metadata(state["candidate"]) != (state["target"], "0"):
        raise RuntimeError("Invalid candidate publication identity or metadata.")
    if git("rev-parse", state["candidate"] + "^{tree}") != state["tree"]:
        raise RuntimeError("Candidate publication tree differs from validation.")
    unchanged(state["remote"], state["heads"])
    require_fast_forwards(state["heads"], state["candidate"])
    existing = remote_refs(state["remote"], state["ref"])
    if existing and existing[state["ref"]] != state["candidate"]:
        old = existing[state["ref"]]
        if old != approved_previous or not ancestor(old, state["candidate"]):
            raise RuntimeError("Candidate changed; review the new candidate instead. A reviewed descendant requires explicit approval of the previous SHA.")
        guarded_push(state["remote"], {state["ref"]: old}, {state["ref"]: state["candidate"]})
    if not existing:
        guarded_push(state["remote"], {state["ref"]: "0" * 40}, {state["ref"]: state["candidate"]})
    print(f"Review candidate {state['candidate']} for {state['target']}; production branches were not updated.")


def api(path: str) -> object:
    return json.loads(run("gh", "api", "--paginate", "--slurp", path))


def check_protection(repository: str, candidate: str) -> None:
    checks = [check for page in api(f"repos/{repository}/commits/{candidate}/check-runs?per_page=100") for check in page["check_runs"]]
    # Always require our complete CI, even if a repository rule is removed.
    required = {("ci-status", 15368), ("master-dependency-policy", 15368)}
    for branch in BRANCHES:
        rules = [rule for page in api(f"repos/{repository}/rules/branches/{branch}?per_page=100") for rule in page]
        for rule in rules:
            kind = rule["type"]
            if kind == "required_status_checks":
                for check in rule["parameters"]["required_status_checks"]:
                    required.add((check["context"], check.get("integration_id")))
            elif kind not in ("non_fast_forward", "deletion"):
                raise RuntimeError(f"{branch}: rule {kind} requires the approved PR path or manual review: {json.dumps(rule)}")
    for name, integration in required:
        matching = [check for check in checks if check["name"] == name and (not integration or check["app"]["id"] == integration)]
        latest = max(matching, key=lambda check: check["id"], default=None)
        if not latest or latest["status"] != "completed" or latest["conclusion"] != "success":
            raise RuntimeError(f"Required check {name} (integration {integration}) is not green on {candidate}. Use the candidate PR; do not bypass.")
        if latest.get("head_sha") != candidate:
            raise RuntimeError("Required check belongs to a different candidate.")
        finished = datetime.fromisoformat(latest["completed_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - finished).total_seconds()
        if not -300 <= age <= 7 * 86400:
            raise RuntimeError("Required check is stale; validate the same candidate again before promotion.")
    # Do not infer absence from REST 404 (which can also mean no permission).
    owner, name = repository.split("/")
    query = "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){branchProtectionRules(first:1){totalCount}}}"
    classic = json.loads(run("gh", "api", "graphql", "-f", f"query={query}", "-f", f"owner={owner}", "-f", f"name={name}"))
    if classic["data"]["repository"]["branchProtectionRules"]["totalCount"]:
        raise RuntimeError("Classic branch protection requires manual review and the approved PR path.")
    # Fail closed even for an unrelated bypass grant. Never use the old release App.
    for page in api(f"repos/{repository}/rulesets?includes_parents=true&per_page=100"):
        for ruleset in page:
            if ruleset["enforcement"] != "active":
                continue
            detail = api(f"repos/{repository}/rulesets/{ruleset['id']}")[0]
            if detail.get("current_user_can_bypass") != "never":
                raise RuntimeError("Promotion identity may bypass protections or bypass permissions could not be verified.")


def release_tag(remote: str, target: str, approved: str) -> tuple[str, str]:
    version(target)
    ref = f"refs/tags/v{target}"
    refs = dict(line.split()[::-1] for line in git("ls-remote", remote, ref, ref + "^{}").splitlines())
    if refs and refs.get(ref + "^{}", refs.get(ref)) != approved:
        raise RuntimeError(f"Existing release tag {ref} conflicts with approved SHA; never move it.")
    return ref, refs.get(ref, "0" * 40)


def verify_remote(repository: str, remote: str) -> None:
    url = git("remote", "get-url", "--push", remote)
    if url.removesuffix(".git").lower() != f"https://github.com/{repository}".lower():
        raise RuntimeError("Promotion requires the expected HTTPS repository and the same GH_TOKEN identity used for protection inspection.")
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("Set GH_TOKEN to a non-bypassing identity; Git and protection API must use the same credential.")
    headers = subprocess.run(["git", "config", "--get-regexp", r"^http\..*extraheader$"], capture_output=True)
    if headers.returncode not in (0, 1) or headers.stdout.strip():
        raise RuntimeError("Remove persisted Git HTTP authentication headers before promotion; only GH_TOKEN may authenticate this transaction.")
    if os.environ.get("GH_HOST", "github.com") != "github.com":
        raise RuntimeError("Promotion must authenticate to github.com.")


def promote(state: dict, approved: str, repository: str) -> None:
    validate_state(state)
    if not re.fullmatch(r"[0-9a-f]{40}", approved) or approved != state["candidate"]:
        raise RuntimeError("Promotion requires the exact reviewed candidate SHA.")
    if git("status", "--porcelain"):
        raise RuntimeError("Promotion requires the validated clean tree.")
    if git("rev-parse", "HEAD") != approved or git("rev-parse", "HEAD^{tree}") != state["tree"] or metadata(approved) != (state["target"], "0"):
        raise RuntimeError("The checkout does not match the validated candidate tree and metadata.")
    if remote_refs(state["remote"], state["ref"]).get(state["ref"]) != approved:
        raise RuntimeError("The published candidate changed or is missing.")
    require_fast_forwards(state["heads"], approved)
    check_protection(repository, approved)
    verify_remote(repository, state["remote"])
    tag, existing_tag = release_tag(state["remote"], state["target"], approved)
    actual = remote_refs(state["remote"], *(f"refs/heads/{branch}" for branch in BRANCHES))
    already_promoted = actual == {f"refs/heads/{branch}": approved for branch in BRANCHES}
    if not already_promoted and approved in actual.values():
        raise RuntimeError("Partial promotion requires a newly reviewed descendant candidate so every branch participates in the atomic transaction.")
    if not already_promoted:
        unchanged(state["remote"], state["heads"])
    # One transaction: protection or concurrent non-FF rejection leaves ALL
    # three refs unchanged. Never fall back to sequential or forced pushes.
    expected = actual if already_promoted else {f"refs/heads/{branch}": sha for branch, sha in state["heads"].items()}
    targets = {ref: approved for ref in expected}
    if existing_tag == "0" * 40:
        expected[tag] = existing_tag
        targets[tag] = approved
    guarded_push(state["remote"], expected, targets)
    actual = remote_refs(state["remote"], *(f"refs/heads/{branch}" for branch in BRANCHES))
    if set(actual.values()) != {approved}:
        raise RuntimeError("Post-promotion heads differ; inspect remote state before retrying.")
    if release_tag(state["remote"], state["target"], approved)[1] == "0" * 40:
        raise RuntimeError("Promotion tag is missing; inspect remote state before retrying.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "finalize", "publish", "promote"))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base-version")
    parser.add_argument("--release-type", choices=("major", "minor", "patch", "resume"), default="patch")
    parser.add_argument("--state", required=True)
    parser.add_argument("--approved-sha", default="")
    parser.add_argument("--approved-previous-sha", default="", help="Explicitly authorize a reviewed fast-forward candidate revision; never a production update.")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
        return
    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    if args.command == "finalize":
        finalize(state)
        Path(args.state).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    elif args.command == "publish":
        publish(state, args.approved_previous_sha)
    else:
        promote(state, args.approved_sha, args.repository)


if __name__ == "__main__":
    main()
