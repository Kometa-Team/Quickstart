"""Exercise release history and transactions against real temporary Git remotes."""

import argparse
import json
from pathlib import Path

import pytest

from scripts import release


@pytest.fixture
def repo(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    local = tmp_path / "checkout"
    release.run("git", "init", "--bare", str(remote))
    release.run("git", "init", "--initial-branch=develop", str(local))
    monkeypatch.chdir(local)
    release.git("config", "user.name", "Release Test")
    release.git("config", "user.email", "release@example.com")
    release.git("config", "core.autocrlf", "false")
    # Never inherit user hooks or signing settings in temporary repositories.
    release.git("config", "core.hooksPath", str(local / ".git" / "hooks"))
    release.git("config", "commit.gpgsign", "false")
    Path("VERSION").write_text("1.2.3\n")
    Path("BUILDNUM").write_text("0\n")
    Path("dependency.txt").write_text("old\n")
    release.git("add", ".")
    release.git("commit", "-m", "Existing release")
    for branch in ("master", "hotfix"):
        release.git("branch", branch)
    release.git("remote", "add", "origin", str(remote))
    release.git("push", "origin", *release.BRANCHES)
    args = argparse.Namespace(remote="origin", base_version="1.2.3", release_type="patch", state=str(tmp_path / "state.json"))
    return args, remote


def state(args):
    return json.loads(Path(args.state).read_text())


def commit_file(name, text):
    Path(name).write_text(text)
    release.git("add", name)
    release.git("commit", "-m", f"Update {name}")
    return release.git("rev-parse", "HEAD")


def ready(args):
    release.prepare(args)
    plan = state(args)
    release.finalize(plan)
    release.publish(plan)
    return plan


def test_divergent_history_preserves_both_trees_and_parents(repo):
    args, _ = repo
    release.git("checkout", "master")
    production = commit_file("security-fix.txt", "dependency fix\n")
    release.git("push", "origin", "master")
    release.git("checkout", "develop")
    integration = commit_file("feature.txt", "production feature\n")
    release.git("push", "origin", "develop")
    plan = ready(args)
    assert release.ancestor(production, plan["candidate"])
    assert release.ancestor(integration, plan["candidate"])
    assert Path("security-fix.txt").read_text() == "dependency fix\n"
    assert Path("feature.txt").exists()
    assert release.metadata(plan["candidate"]) == ("1.2.4", "0")
    assert release.snapshot("origin") == plan["heads"]


@pytest.mark.parametrize("promoted", [(), ("develop",), ("develop", "master"), release.BRANCHES])
def test_reruns_and_partial_promotions_reuse_exact_candidate(repo, monkeypatch, promoted):
    args, _ = repo
    plan = ready(args)
    for branch in promoted:
        release.git("push", "origin", f"{plan['candidate']}:refs/heads/{branch}")
    rerun = ready(args)
    assert rerun["candidate"] == plan["candidate"]
    assert release.metadata("HEAD") == ("1.2.4", "0")
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    release.promote(rerun, rerun["candidate"], "example/repo")
    assert set(release.snapshot("origin").values()) == {plan["candidate"]}


def test_legacy_interrupted_release_resumes_without_increment(repo):
    args, _ = repo
    release.prepare(args)
    plan = state(args)
    release.finalize(plan)
    release.git("push", "origin", f"{plan['candidate']}:develop")
    # Legacy failure: no durable candidate ref exists, only develop advanced.
    args.base_version = "1.2.4"
    args.release_type = "resume"
    resumed = ready(args)
    assert resumed["candidate"] == plan["candidate"]
    assert release.metadata("HEAD") == ("1.2.4", "0")


def test_competing_release_runs_cannot_replace_candidate(repo, monkeypatch):
    args, _ = repo
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-01T00:00:00Z")
    release.prepare(args)
    first = state(args)
    release.finalize(first)
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-01T00:00:01Z")
    release.prepare(args)
    second = state(args)
    release.finalize(second)
    assert first["candidate"] != second["candidate"]
    release.publish(first)
    with pytest.raises(RuntimeError, match="Candidate changed"):
        release.publish(second)
    assert release.remote_refs("origin", first["ref"])[first["ref"]] == first["candidate"]
    assert release.snapshot("origin") == first["heads"]


def test_new_dispatch_cannot_skip_incomplete_release(repo):
    args, _ = repo
    plan = ready(args)
    release.git("push", "origin", f"{plan['candidate']}:develop")
    args.base_version = "1.2.4"
    with pytest.raises(RuntimeError, match="earlier release is incomplete"):
        release.prepare(args)


def test_conflict_aborts_without_changing_remote(repo):
    args, _ = repo
    release.git("checkout", "master")
    commit_file("dependency.txt", "master-version\n")
    release.git("push", "origin", "master")
    release.git("checkout", "develop")
    commit_file("dependency.txt", "develop-version\n")
    release.git("push", "origin", "develop")
    before = release.snapshot("origin")
    with pytest.raises(RuntimeError, match="CONFLICT"):
        release.prepare(args)
    assert release.snapshot("origin") == before


def test_concurrent_update_aborts_all_promotion(repo, monkeypatch):
    args, remote = repo
    plan = ready(args)
    other = Path(args.state).parent / "other"
    release.run("git", "clone", "--branch", "develop", str(remote), str(other))
    release.run("git", "-C", str(other), "config", "user.name", "Other")
    release.run("git", "-C", str(other), "config", "user.email", "other@example.com")
    (other / "concurrent.txt").write_text("concurrent update\n")
    release.run("git", "-C", str(other), "add", ".")
    release.run("git", "-C", str(other), "-c", "core.hooksPath=", "-c", "commit.gpgsign=false", "commit", "-m", "Concurrent update")
    release.run("git", "-C", str(other), "push", "origin", "develop")
    before = release.snapshot("origin")
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    with pytest.raises(RuntimeError, match="Remote heads changed"):
        release.promote(plan, plan["candidate"], "example/repo")
    assert release.snapshot("origin") == before


def test_server_rejection_is_atomic(repo, monkeypatch):
    args, remote = repo
    plan = ready(args)
    hook = remote / "hooks" / "update"
    hook.write_text('#!/bin/sh\nif [ "$1" = "refs/heads/master" ]; then exit 1; fi\nexit 0\n', newline="\n")
    hook.chmod(0o755)
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    with pytest.raises(RuntimeError, match="failed"):
        release.promote(plan, plan["candidate"], "example/repo")
    assert release.snapshot("origin") == plan["heads"]


def test_update_between_preflight_and_push_advertisement_aborts(repo, monkeypatch):
    args, remote = repo
    integration = commit_file("feature.txt", "integration change\n")
    release.git("push", "origin", "develop")
    plan = ready(args)
    original_unchanged = release.unchanged

    def update_after_preflight(remote_name, heads):
        original_unchanged(remote_name, heads)
        # This concurrent update is an ancestor of our candidate, so a plain
        # fast-forward push would accept it despite the stale review snapshot.
        release.run("git", "--git-dir", str(remote), "update-ref", "refs/heads/master", integration)

    monkeypatch.setattr(release, "unchanged", update_after_preflight)
    monkeypatch.setattr(release, "check_protection", lambda *args: None)
    with pytest.raises(RuntimeError, match="Remote advertisement changed"):
        release.promote(plan, plan["candidate"], "example/repo")
    heads = release.snapshot("origin")
    assert heads["develop"] == plan["heads"]["develop"]
    assert heads["hotfix"] == plan["heads"]["hotfix"]
    assert heads["master"] == integration


def test_changed_heads_during_fetch_abort(monkeypatch):
    expected = {f"refs/heads/{branch}": "a" * 40 for branch in release.BRANCHES}
    changed = {**expected, "refs/heads/master": "b" * 40}
    snapshots = iter([expected, changed])
    monkeypatch.setattr(release, "remote_refs", lambda *args: next(snapshots))
    monkeypatch.setattr(release, "git", lambda *args: "")
    with pytest.raises(RuntimeError, match="changed during fetch"):
        release.snapshot("origin")


def test_wrong_approval_and_missing_checks_block_promotion(repo, monkeypatch):
    args, _ = repo
    plan = ready(args)
    with pytest.raises(RuntimeError, match="exact reviewed"):
        release.promote(plan, "0" * 40, "example/repo")
    monkeypatch.setattr(release, "api", lambda path: [{"check_runs": []}] if "check-runs" in path else [[]])
    with pytest.raises(RuntimeError, match="not green"):
        release.promote(plan, plan["candidate"], "example/repo")
    assert release.snapshot("origin") == plan["heads"]


def test_latest_failed_check_cannot_be_hidden_by_older_success(monkeypatch):
    checks = [{"id": n, "name": "ci-status", "app": {"id": 15368}, "status": "completed", "conclusion": result} for n, result in [(1, "success"), (2, "failure")]]
    monkeypatch.setattr(release, "api", lambda path: [{"check_runs": checks}] if "check-runs" in path else [[]])
    with pytest.raises(RuntimeError, match="not green"):
        release.check_protection("example/repo", "a" * 40)


def test_required_pr_rule_is_reported_without_bypass(monkeypatch):
    monkeypatch.setattr(release, "api", lambda path: [{"check_runs": []}] if "check-runs" in path else [[{"type": "pull_request", "ruleset_id": 123}]])
    with pytest.raises(RuntimeError, match="rule pull_request.*approved PR path.*123"):
        release.check_protection("example/repo", "a" * 40)


def test_validation_mutations_block_release_commit(repo):
    args, _ = repo
    release.prepare(args)
    Path("dependency.txt").write_text("changed by validator\n")
    with pytest.raises(RuntimeError):
        release.finalize(state(args))


@pytest.mark.parametrize("kind,expected", [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0"), ("resume", "1.2.3")])
def test_fixed_version_calculation(kind, expected):
    assert release.target_version("1.2.3", kind) == expected


def test_workflow_concurrency_and_integration_contract():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflows = root / ".github" / "workflows"
    for name in ("release-master.yml", "increment-build.yml", "copyright.yml"):
        workflow = yaml.safe_load((workflows / name).read_text(encoding="utf-8-sig"))
        assert workflow["concurrency"] == {"group": "quickstart-release-writer", "cancel-in-progress": False}
    for name in ("release-master.yml", "release-hotfix.yml"):
        text = (workflows / name).read_text(encoding="utf-8-sig")
        assert "--force" not in text and "git rebase" not in text and "reconcile_0_10_9" not in text
    dependabot = yaml.safe_load((root / ".github" / "dependabot.yml").read_text())
    assert all(update["target-branch"] == "develop" for update in dependabot["updates"])
    increment = yaml.safe_load((workflows / "increment-build.yml").read_text())
    assert "!startsWith(github.event.pull_request.head.ref, 'release-candidates/')" in increment["jobs"]["verify-changes"]["if"]
    routing = yaml.safe_load((workflows / "dependency-integration.yml").read_text())
    assert all("checkout" not in step.get("uses", "") for step in routing["jobs"]["route"]["steps"])
    for name in ("ci.yml", "lint.yml"):
        workflow = yaml.safe_load((workflows / name).read_text())
        events = workflow.get("on", workflow.get(True))  # PyYAML's YAML 1.1 boolean key.
        assert "edited" in events["pull_request"]["types"]  # Retargeting must rerun integration checks.
