import base64
import copy
import json
import subprocess
from pathlib import Path

import pytest
import test_release

from scripts import dependency_policy, release, security_notifications as security
from test_release import commit_file, ready


@pytest.fixture
def repo(tmp_path, monkeypatch):
    return test_release.repo.__wrapped__(tmp_path, monkeypatch)


@pytest.mark.parametrize("scenario", ["candidate", "bot-master", "bot-develop", "manual-dependency", "unrelated", "retarget-race", "net-zero-dependency"])
def test_actual_dependency_check_controller(repo, monkeypatch, scenario):
    args, remote = repo
    if scenario == "candidate":
        plan = ready(args)
        event = {"after": plan["candidate"], "ref": plan["ref"]}
    else:
        if scenario == "net-zero-dependency":
            commit_file("requirements.txt", "new==2.0\n")
            commit_file("requirements.txt", "")
        elif scenario == "manual-dependency":
            commit_file("requirements.txt", "new==2.0\n")
        else:
            commit_file("ordinary.txt", "unrelated app fix\n")
        head = release.git("rev-parse", "HEAD")
        release.git("push", "origin", f"{head}:refs/pull/1/head")
        event = {
            "pull_request": {
                "number": 1,
                "base": {"ref": "develop" if scenario == "bot-develop" else "master"},
                "head": {"sha": head},
                "user": {"login": "dependabot[bot]" if scenario.startswith("bot-") else "user"},
            }
        }
    path = Path(args.state).parent / "event.json"
    path.write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/repo")
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    original = subprocess.run
    writes = []

    def gh(command, **kwargs):
        if command[0] != "gh":
            return original(command, **kwargs)
        if "--input" in command:
            writes.append(json.loads(kwargs["input"]))
            data = {"id": 1}
        else:
            data = copy.deepcopy(event["pull_request"])
            if scenario == "retarget-race":
                data["base"]["ref"] = "develop"
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    monkeypatch.setattr(subprocess, "run", gh)
    dependency_policy.main()
    if scenario == "bot-develop":
        assert writes == []  # Never convert a blocked master check to success.
    else:
        assert writes[0]["conclusion"] == "failure"
        assert writes[-1]["conclusion"] == ("success" if scenario in ("candidate", "unrelated") else "failure")
        assert all(write["name"] == "master-dependency-policy" for write in writes)


@pytest.fixture
def alert():
    return {
        "number": 123,
        "html_url": "https://github.com/example/source/security/dependabot/123",
        "dependency": {"package": {"name": "undici", "ecosystem": "npm"}, "manifest_path": "package-lock.json"},
        "security_vulnerability": {"severity": "high", "vulnerable_version_range": ">= 8.0.0, < 8.12.3"},
        "security_advisory": {"ghsa_id": "GHSA-private-detail"},
    }


def test_security_pending_develop_unreleased_and_resolved(alert):
    pending = security.notification(alert, ["8.12.2"], ["8.12.2"], [])
    assert "fix pending" in pending["body"] and pending["state"] == "open"
    integrated = security.notification(alert, ["8.12.2"], ["8.12.3"], ["https://github.com/example/source/pull/1"])
    assert "NOT reached production" in integrated["body"] and integrated["state"] == "open"
    released = security.notification(alert, ["8.12.3"], ["8.12.3"], [])
    assert released["state"] == "closed" and "verified" in released["body"]
    unknown = security.notification(alert, None, ["8.12.3"], [])
    assert unknown["state"] == "open" and "manual review" in unknown["body"]


@pytest.mark.parametrize("installed,expected", [("8.12.2", True), ("8.12.3", False), ("9.0.0", False), ("8.12.3rc1", None)])
def test_advisory_ranges_are_conservative(installed, expected):
    assert security.vulnerable(installed, ">= 8.0.0, < 8.12.3") is expected
    assert security.vulnerable(installed, "unsupported || range") is None


def test_manifests_check_all_installed_versions_and_python_pins():
    lock = json.dumps({"packages": {"node_modules/undici": {"version": "8.12.3"}, "node_modules/a/node_modules/undici": {"version": "8.12.2"}}})
    installed = security.versions(lock, "package-lock.json", "npm", "undici")
    assert security.affected(installed, "< 8.12.3") is True
    assert security.versions("GitPython==3.2.1\nPillow==13.0.0", "requirements.txt", "pip", "gitpython") == ["3.2.1"]
    assert security.versions("other==1.0", "requirements.txt", "pip", "transitive") is None


class PrivateTracker:
    def __init__(self, visibility="private"):
        self.visibility = visibility
        self.issues = []
        self.writes = []

    def pages(self, path):
        return self.issues

    def request(self, path, method="GET", body=None):
        if method == "GET":
            return {"visibility": self.visibility}
        self.writes.append((method, copy.deepcopy(body)))
        if method == "POST":
            self.issues.append({"number": 1, "state": "open", **body})
        else:
            self.issues[0].update(body)


def test_private_notifications_deduplicate_update_and_resolve(alert):
    class Reader:
        production = "8.12.2"
        integration = "8.12.3"

        def pages(self, path):
            return [alert] if "state=open&" in path else []

        def request(self, path):
            if path.startswith("search/"):
                return {"items": [{"number": 12}]}
            if "/pulls/" in path:
                return {
                    "user": {"login": "dependabot[bot]"},
                    "head": {"sha": "develop-sha"},
                    "base": {"ref": "develop"},
                    "merged_at": "2026-10-25",
                    "html_url": "https://github.com/example/source/pull/12",
                }
            if "/contents/" in path:
                value = self.production if "ref=master-sha" in path else self.integration
                text = json.dumps({"packages": {"node_modules/undici": {"version": value}}})
                return {"content": base64.b64encode(text.encode()).decode()}
            if "/git/ref/" in path:
                return {"object": {"sha": path.split("/")[-1] + "-sha"}}
            return {"default_branch": "master"}

    reader, tracker = Reader(), PrivateTracker()
    security.synchronize(reader, tracker, "example/source", "example/private")
    assert len(tracker.writes) == 1 and "NOT reached production" in tracker.issues[0]["body"]
    assert "pull/12 (merged into develop)" in tracker.issues[0]["body"]
    security.synchronize(reader, tracker, "example/source", "example/private")
    assert len(tracker.writes) == 1
    reader.production = "8.12.3"
    security.synchronize(reader, tracker, "example/source", "example/private")
    assert tracker.issues[0]["state"] == "closed" and len(tracker.writes) == 2
    security.synchronize(reader, tracker, "example/source", "example/private")
    assert len(tracker.writes) == 2


def test_public_tracker_is_rejected_before_security_data_is_read():
    class Reader:
        def request(self, *_):
            pytest.fail("Private security data must not be read for a public tracker")

    tracker = PrivateTracker("public")
    with pytest.raises(RuntimeError, match="private"):
        security.synchronize(Reader(), tracker, "example/source", "example/public")
    assert tracker.writes == []
