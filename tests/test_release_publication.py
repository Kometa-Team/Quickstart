"""Real local Git transactions; registry, release and executable effects are mocked."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
import test_release

from scripts import dependency_policy, pr_artifacts, release, release_publication as publication
from test_release import commit_file, ready


@pytest.fixture
def repo(tmp_path, monkeypatch):
    return test_release.repo.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def promoted(repo, monkeypatch):
    args, remote = repo
    plan = ready(args)
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    release.promote(plan, plan["candidate"], "example/repo")
    return plan, remote


class Registry:
    image = "example/quickstart"

    def __init__(self):
        self.tags = {}
        self.writes = []
        self.fail_alias = None

    def inspect(self, tag):
        return self.tags.get(tag)

    def assemble(self, tag, sources, approved):
        if tag == self.fail_alias:
            raise RuntimeError("Interrupted registry publication")
        self.writes.append((tag, sources))
        self.tags[tag] = {
            "annotations": {publication.REVISION: approved},
            "digest": "sha256:" + "a" * 64,
            "manifests": [{"platform": {"os": "linux", "architecture": arch, **({"variant": "v7"} if arch == "arm" else {})}} for arch in ("amd64", "arm64", "arm")],
        }


@pytest.fixture
def external(tmp_path, monkeypatch):
    directory = tmp_path / "artifacts"
    directory.mkdir()
    approved = "a" * 40
    for arch in publication.ARCHES:
        (directory / f"image-{arch}.tar").write_bytes(b"test OCI artifact")
    calls = []

    def run(*args):
        calls.append(args)
        return approved if args[:3] == ("docker", "image", "inspect") else ""

    monkeypatch.setattr(release, "run", run)
    return Registry(), directory, approved, calls


def test_normal_atomic_release_includes_tag_and_all_branches(promoted):
    plan, _ = promoted
    assert set(release.snapshot("origin").values()) == {plan["candidate"]}
    assert release.release_tag("origin", "1.2.4", plan["candidate"])[1] == plan["candidate"]
    assert publication.verify("example/repo", "origin", plan["candidate"]) == "v1.2.4"


def test_missing_tag_after_version_and_tooling_commits_is_repaired(promoted):
    plan, remote = promoted
    # Reproduce recovery: parent and candidate both already say the new version.
    release.git("checkout", "--detach", plan["candidate"])
    candidate = commit_file("tooling.txt", "release safety\n")
    release.git("push", "origin", f"{candidate}:{plan['ref']}")
    release.git("push", "--atomic", "origin", *(f"{candidate}:refs/heads/{b}" for b in release.BRANCHES))
    release.run("git", "--git-dir", str(remote), "update-ref", "-d", "refs/tags/v1.2.4")
    assert release.metadata(candidate) == release.metadata(candidate + "^")
    assert publication.ensure_tag("example/repo", "origin", candidate) == "v1.2.4"
    assert release.release_tag("origin", "1.2.4", candidate)[1] == candidate


def test_existing_correct_tag_and_complete_promotion_retry_are_noops(promoted):
    plan, _ = promoted
    release.promote(plan, plan["candidate"], "example/repo")
    publication.ensure_tag("example/repo", "origin", plan["candidate"])
    assert release.metadata("HEAD") == ("1.2.4", "0")


def test_candidate_revision_requires_explicit_previous_sha_approval(repo):
    args, _ = repo
    plan = ready(args)
    previous = plan["candidate"]
    plan["candidate"] = commit_file("tooling.txt", "reviewed correction\n")
    plan["tree"] = release.git("rev-parse", "HEAD^{tree}")
    with pytest.raises(RuntimeError, match="explicit approval"):
        release.publish(plan)
    release.publish(plan, previous)
    assert release.remote_refs("origin", plan["ref"])[plan["ref"]] == plan["candidate"]
    assert release.snapshot("origin") == plan["heads"]


def test_untrusted_recovery_state_cannot_supply_git_options(repo):
    args, _ = repo
    plan = ready(args)
    plan["remote"] = "--upload-pack=unexpected-command"
    with pytest.raises(RuntimeError, match="configured Git remote"):
        release.publish(plan)


def test_conflicting_tag_prevents_all_branch_updates(repo, monkeypatch):
    args, _ = repo
    plan = ready(args)
    release.git("push", "origin", f"{plan['heads']['master']}:refs/tags/v1.2.4")
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    with pytest.raises(RuntimeError, match="conflicts"):
        release.promote(plan, plan["candidate"], "example/repo")
    assert release.snapshot("origin") == plan["heads"]


def test_failed_prepare_never_publishes_candidate_or_tag(repo):
    args, _ = repo
    release.git("checkout", "master")
    commit_file("dependency.txt", "production\n")
    release.git("push", "origin", "master")
    release.git("checkout", "develop")
    commit_file("dependency.txt", "integration\n")
    release.git("push", "origin", "develop")
    with pytest.raises(RuntimeError, match="CONFLICT"):
        release.prepare(args)
    assert release.remote_refs("origin", "refs/tags/*", "refs/heads/release-candidates/*") == {}


def test_failed_promotion_prevents_tag_creation(repo, monkeypatch):
    args, remote = repo
    plan = ready(args)
    hook = remote / "hooks" / "update"
    hook.write_text('#!/bin/sh\n[ "$1" != "refs/heads/master" ]\n', newline="\n")
    hook.chmod(0o755)
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    with pytest.raises(RuntimeError):
        release.promote(plan, plan["candidate"], "example/repo")
    assert release.snapshot("origin") == plan["heads"]
    assert release.remote_refs("origin", "refs/tags/*") == {}


def test_stale_candidate_or_incomplete_promotion_never_tags(repo, monkeypatch):
    args, _ = repo
    plan = ready(args)
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    with pytest.raises(RuntimeError, match="Incomplete"):
        publication.ensure_tag("example/repo", "origin", plan["candidate"])
    with pytest.raises(RuntimeError, match="exact reviewed"):
        release.promote(plan, "0" * 40, "example/repo")
    assert release.remote_refs("origin", "refs/tags/*") == {}


def test_successful_images_and_retry_reuse_immutable_manifest(external):
    registry, directory, approved, calls = external
    publication.publish_images(registry, "v1.2.4", approved, directory, "10-1", lambda *_: True)
    assert [tag for tag, _ in registry.writes] == ["v1.2.4", "latest", "develop"]
    pushed = [args[-1] for args in calls if args[:2] == ("docker", "push")]
    assert all(f"release-{approved}-10-1-" in ref for ref in pushed)
    assert len(pushed) == 3
    calls.clear()
    registry.writes.clear()
    publication.publish_images(registry, "v1.2.4", approved, directory, "10-2", lambda *_: True)
    assert not calls and not registry.writes


def test_partial_docker_alias_failure_recovers_without_rebuilding(external):
    registry, directory, approved, calls = external
    registry.fail_alias = "latest"
    with pytest.raises(RuntimeError, match="Interrupted"):
        publication.publish_images(registry, "v1.2.4", approved, directory, "11-1", lambda *_: True)
    assert "v1.2.4" in registry.tags and "latest" not in registry.tags
    calls.clear()
    registry.fail_alias = None
    publication.publish_images(registry, "v1.2.4", approved, directory, "11-2", lambda *_: True)
    assert not calls
    assert set(registry.tags) == {"v1.2.4", "latest", "develop"}


def test_concurrent_version_appearance_and_stale_publication_stop(external):
    registry, directory, approved, _ = external

    def competing(*_):
        registry.tags["v1.2.4"] = {"annotations": {publication.REVISION: "b" * 40}}

    with pytest.raises(RuntimeError, match="conflicts"):
        publication.publish_images(registry, "v1.2.4", approved, directory, "12-1", competing)
    assert not registry.writes

    def stale(*_):
        raise RuntimeError("Superseded release")

    with pytest.raises(RuntimeError, match="Superseded"):
        publication.publish_images(registry, "v1.2.4", approved, directory, "12-2", stale)


def test_competing_publisher_after_component_push_never_gets_overwritten(external):
    registry, directory, approved, _ = external
    checks = 0

    def competing(*_):
        nonlocal checks
        checks += 1
        if checks == 2:
            registry.tags["v1.2.4"] = {"annotations": {publication.REVISION: "b" * 40}}

    with pytest.raises(RuntimeError, match="appeared during publication"):
        publication.publish_images(registry, "v1.2.4", approved, directory, "15-1", competing)
    assert registry.tags["v1.2.4"]["annotations"][publication.REVISION] == "b" * 40
    assert not registry.writes


def test_component_failure_has_no_public_version_or_alias(external, monkeypatch):
    registry, directory, approved, _ = external
    original = release.run

    def interrupted(*args):
        if args[:2] == ("docker", "push") and args[-1].endswith("arm64"):
            raise RuntimeError("Partial component push")
        return original(*args)

    monkeypatch.setattr(release, "run", interrupted)
    with pytest.raises(RuntimeError, match="Partial component"):
        publication.publish_images(registry, "v1.2.4", approved, directory, "13-1", lambda *_: True)
    assert not registry.tags
    monkeypatch.setattr(release, "run", original)
    publication.publish_images(registry, "v1.2.4", approved, directory, "13-2", lambda *_: True)
    assert "latest" in registry.tags


def test_advanced_develop_is_not_overwritten_by_release_image(external):
    registry, directory, approved, _ = external
    publication.publish_images(registry, "v1.2.4", approved, directory, "14-1", lambda alias=None: alias != "develop")
    assert set(registry.tags) == {"v1.2.4", "latest"}


@pytest.fixture
def assets(tmp_path, monkeypatch):
    tag = "v1.2.4"
    files = []
    for suffix in ("Windows.exe", "Linux", "macOS-x86_64", "macOS-arm64"):
        file = tmp_path / f"Quickstart-{tag}-{suffix}"
        file.write_bytes(b"immutable executable " + suffix.encode())
        files.append(file)
    records = []
    uploads = []

    def api(*args, **kwargs):
        return records

    def upload(*args):
        file = Path(args[4])
        uploads.append(file.name)
        records.append({"name": file.name, "state": "uploaded", "digest": "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest(), "size": file.stat().st_size})
        return ""

    monkeypatch.setattr(publication, "gh_json", api)
    monkeypatch.setattr(release, "run", upload)
    return {"id": 1, "tag_name": tag, "draft": True}, files, records, uploads


def test_interrupted_upload_and_retry_preserve_existing_bytes(assets, monkeypatch):
    info, files, records, uploads = assets
    original = release.run

    def disconnect(*args):
        original(*args)
        raise RuntimeError("Client disconnected after successful upload")

    monkeypatch.setattr(release, "run", disconnect)
    with pytest.raises(RuntimeError, match="disconnected"):
        publication.upload_assets("example/repo", info, files[0].parent)
    assert len(records) == 1
    monkeypatch.setattr(release, "run", original)
    publication.upload_assets("example/repo", info, files[0].parent)
    assert len(records) == len(uploads) == 4
    publication.upload_assets("example/repo", {**info, "draft": False}, files[0].parent)
    assert len(uploads) == 4
    files[0].write_bytes(b"rebuilt differing bytes")
    with pytest.raises(RuntimeError, match="never overwrite"):
        publication.upload_assets("example/repo", info, files[0].parent)


def test_existing_stable_release_is_not_deleted_or_recreated(monkeypatch):
    record = {"id": 7, "tag_name": "v1.2.4", "target_commitish": "a" * 40, "draft": False, "prerelease": False}
    calls = []

    def api(*args):
        calls.append(args)
        return record

    monkeypatch.setattr(publication, "gh_json", api)
    assert publication.ensure_release("example/repo", "v1.2.4", "a" * 40) == record
    assert len(calls) == 1
    record["target_commitish"] = "b" * 40
    with pytest.raises(RuntimeError, match="conflicts"):
        publication.ensure_release("example/repo", "v1.2.4", "a" * 40)
    assert all(len(call) == 2 for call in calls)


@pytest.mark.parametrize("branch", ["x$(touch hacked)", "x`touch hacked`", 'x";touch hacked;#', "x\ny", "../latest", "x//y", "-latest"])
def test_malicious_pr_branch_names_fail_closed(branch):
    with pytest.raises(ValueError):
        pr_artifacts.artifact_name(12, "a" * 40, branch)


@pytest.mark.parametrize("branch", ["latest", "latest-amd64", "v0.10.15", "release-0.10.15", "develop", "feature/fix"])
def test_reserved_tags_cannot_be_cleanup_targets(branch):
    assert pr_artifacts.artifact_name(12, "a" * 40, branch) == "pr-12-" + "a" * 40
    with pytest.raises(RuntimeError, match="disabled"):
        pr_artifacts.cleanup_target(branch)


def test_publication_credentials_triggers_and_hotfix_contracts():
    root = Path(__file__).resolve().parents[1]
    workflows = {file.name: yaml.safe_load(file.read_text(encoding="utf-8-sig")) for file in (root / ".github/workflows").glob("*.yml")}
    publish = workflows["docker-version.yml"]
    assert set(publish.get("on", publish.get(True))) == {"workflow_dispatch"}
    assert publish["concurrency"] == {"group": "quickstart-release-writer", "cancel-in-progress": False}
    assert publish["jobs"]["publish-release"]["permissions"]["contents"] == "write"
    for name in ("docker-develop.yml", "docker-latest.yml", "tag-new-version.yml", "release-notification.yml", "validate-pull.yml"):
        text = (root / ".github/workflows" / name).read_text()
        assert "secrets." not in text and "workflow_run" not in text and "contents: write" not in text
    for name in ("release-validation.yml", "test.yml", "docker-build.yml", "release-executables.yml"):
        text = (root / ".github/workflows" / name).read_text()
        assert workflows[name]["permissions"] == {"contents": "read"}
        assert "secrets." not in text and "persist-credentials: false" in text
    master = workflows["release-master.yml"]
    assert master["permissions"] == {"contents": "read"}
    assert "secrets." not in json.dumps(master["jobs"]["validate"])
    assert master["jobs"]["promote"]["environment"]["name"] == "release-promotion"
    assert publish["jobs"]["tag"]["environment"] == "release-publication"
    hotfix = release.run("git", "-C", str(root), "show", "80e7b95531aad71ac8fdaa5cd47342ebaa6cd811:.github/workflows/release-hotfix.yml")
    assert hotfix == (root / ".github/workflows/release-hotfix.yml").read_text().strip()


@pytest.mark.parametrize(
    "results,passes",
    [
        (("success", "success", "success"), True),
        (("skipped", "success", "success"), False),
        (("success", "skipped", "success"), False),
        (("success", "success", "skipped"), False),
        (("skipped", "skipped", "skipped"), False),
        (("failure", "success", "success"), False),
        (("cancelled", "success", "success"), False),
    ],
)
def test_actual_ci_aggregator_cannot_mask_skipped_guard_or_tests(results, passes):
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/ci.yml").read_text())
    gate = workflow["jobs"]["ci-status"]
    assert set(gate["needs"]) == {"guard", "tests", "quality"}
    assert "if" not in workflow["jobs"]["guard"]  # Label events must still run it.
    script = gate["steps"][0]["run"]
    bash = str(Path(os.environ["ProgramFiles"]) / "Git/usr/bin/bash.exe") if os.name == "nt" else shutil.which("bash")
    assert bash and shutil.which("jq"), "The real CI-gate regression requires Bash and jq."
    environment = {**os.environ, "RESULTS": json.dumps({name: {"result": result} for name, result in zip(("guard", "tests", "quality"), results)})}
    completed = subprocess.run([bash, "-e", "-c", script], env=environment, capture_output=True)
    assert (completed.returncode == 0) is passes


def test_environment_without_independent_review_or_with_bypass_is_rejected(monkeypatch):
    good = {"can_admins_bypass": False, "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "Team"}], "prevent_self_review": True}]}
    monkeypatch.setattr(release, "api", lambda _: [good])
    publication.environment_gate("example/repo", "release-promotion")
    bad = copy.deepcopy(good)
    bad["can_admins_bypass"] = True
    monkeypatch.setattr(release, "api", lambda _: [bad])
    with pytest.raises(RuntimeError, match="Administrator"):
        publication.environment_gate("example/repo", "release-promotion")


def test_check_preflight_verifies_exact_sha_classic_rules_and_identity(monkeypatch):
    approved = "a" * 40
    checks = [
        {"id": i, "head_sha": approved, "name": name, "app": {"id": 15368}, "status": "completed", "conclusion": "success", "completed_at": datetime.now(timezone.utc).isoformat()}
        for i, name in enumerate(("ci-status", "master-dependency-policy"), 1)
    ]
    details = {"current_user_can_bypass": "never"}

    def api(path):
        if "check-runs" in path:
            return [{"check_runs": checks}]
        if "/rules/branches/" in path:
            return [[]]
        if "/rulesets?" in path:
            return [[{"id": 7, "enforcement": "active"}]]
        return [details]

    monkeypatch.setattr(release, "api", api)
    monkeypatch.setattr(release, "run", lambda *_: json.dumps({"data": {"repository": {"branchProtectionRules": {"totalCount": 0}}}}))
    release.check_protection("example/repo", approved)
    details["current_user_can_bypass"] = "always"
    with pytest.raises(RuntimeError, match="bypass"):
        release.check_protection("example/repo", approved)
    details["current_user_can_bypass"] = "never"
    monkeypatch.setattr(release, "run", lambda *_: json.dumps({"data": {"repository": {"branchProtectionRules": {"totalCount": 1}}}}))
    with pytest.raises(RuntimeError, match="Classic"):
        release.check_protection("example/repo", approved)


def test_complete_chain_with_local_git_and_mocked_publication(promoted, tmp_path, monkeypatch):
    plan, _ = promoted
    approved = plan["candidate"]
    assert publication.ensure_tag("example/repo", "origin", approved) == "v1.2.4"
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    for arch in publication.ARCHES:
        (image_dir / f"image-{arch}.tar").write_bytes(b"image")
    registry = Registry()
    assets_dir = tmp_path / "executables"
    assets_dir.mkdir()
    for suffix in ("Windows.exe", "Linux", "macOS-x86_64", "macOS-arm64"):
        (assets_dir / f"Quickstart-v1.2.4-{suffix}").write_bytes(b"original executable")
    record, asset_records, mutations = {}, [], []

    def api(repository, path, method="GET", body=None):
        if path.startswith("releases/tags/"):
            return record or None
        if method == "POST":
            record.update(body, id=1)
            mutations.append("create draft")
        elif path.endswith("assets?per_page=100"):
            return asset_records
        elif method == "PATCH":
            record.update(body)
            mutations.append("publish once")
        return record

    def external(*args):
        if args[:3] == ("docker", "image", "inspect"):
            return approved
        if args[:3] == ("gh", "release", "upload"):
            file = Path(args[4])
            asset_records.append({"name": file.name, "state": "uploaded", "size": file.stat().st_size, "digest": "sha256:" + hashlib.sha256(file.read_bytes()).hexdigest()})
        return ""

    monkeypatch.setattr(release, "run", external)
    monkeypatch.setattr(publication, "gh_json", api)
    publication.publish_images(registry, "v1.2.4", approved, image_dir, "200-1", lambda *_: True)
    info = publication.ensure_release("example/repo", "v1.2.4", approved)
    publication.upload_assets("example/repo", info, assets_dir)
    api("example/repo", "releases/1", "PATCH", {"draft": False})
    publication.ensure_release("example/repo", "v1.2.4", approved)
    publication.upload_assets("example/repo", info, assets_dir)
    assert record["target_commitish"] == approved and record["draft"] is False
    assert len(asset_records) == 4 and mutations == ["create draft", "publish once"]
    assert all(image["annotations"][publication.REVISION] == approved for image in registry.tags.values())


@pytest.mark.parametrize(
    "author,paths,blocked",
    [("dependabot[bot]", [], True), ("user", ["package-lock.json"], True), ("user", ["requirements.txt"], True), ("user", ["modules/application.py"], False)],
)
def test_dependency_policy_is_specific_and_develop_first(author, paths, blocked):
    assert dependency_policy.dependency_change(author, paths) is blocked
