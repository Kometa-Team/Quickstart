import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "derive_tag.py"
WORKFLOWS = ROOT / ".github" / "workflows"
SANITISER = "[^a-zA-Z0-9._-]"

_spec = importlib.util.spec_from_file_location("derive_tag", SCRIPT)
derive_tag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(derive_tag)

OWNER_REPO = "Kometa-Team/Quickstart"


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("feature/new-thing", "feature-new-thing"),
        ("automation/fork-pr-5", "automation-fork-pr-5"),
        ("chore/remove-armv7", "chore-remove-armv7"),
        ("fix_x.y-z", "fix_x.y-z"),
        ("developer", "developer"),
    ],
)
def test_branch_names_are_sanitised(branch, expected):
    assert derive_tag.derive_tag(branch, OWNER_REPO) == expected


def test_shell_metacharacters_are_neutralised():
    tag = derive_tag.derive_tag("x$(id);a|b`c", OWNER_REPO)
    assert re.fullmatch(r"[A-Za-z0-9._-]+", tag)
    assert "$" not in tag and "(" not in tag and ";" not in tag


@pytest.mark.parametrize(("branch", "repo", "expected"), [("develop", OWNER_REPO, "Kometa-Team"), ("master", "badja-dev/Quickstart", "badja-dev")])
def test_master_and_develop_map_to_the_repo_owner(branch, repo, expected):
    assert derive_tag.derive_tag(branch, repo) == expected


@pytest.mark.parametrize("branch", ["$(id)", "-leading-dash", ".hidden", "a" * 129])
def test_branches_without_a_valid_docker_tag_raise(branch):
    with pytest.raises(ValueError):
        derive_tag.derive_tag(branch, OWNER_REPO)


def test_longest_valid_tag_is_accepted():
    assert derive_tag.derive_tag("a" * 128, OWNER_REPO) == "a" * 128


def test_main_writes_the_github_output_file(tmp_path, monkeypatch, capsys):
    output = tmp_path / "github_output"
    monkeypatch.setenv("HEAD_REF", "automation/fork-pr-5")
    monkeypatch.setenv("HEAD_REPO", OWNER_REPO)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert derive_tag.main() == 0
    assert output.read_text(encoding="utf-8") == "tag-name=automation-fork-pr-5\n"
    assert "tag-name=automation-fork-pr-5" in capsys.readouterr().out


@pytest.mark.parametrize(("head_ref", "head_repo"), [("", OWNER_REPO), ("main", ""), ("$(id)", OWNER_REPO)])
def test_main_fails_without_a_usable_tag(head_ref, head_repo, monkeypatch, tmp_path):
    output = tmp_path / "github_output"
    monkeypatch.setenv("HEAD_REF", head_ref)
    monkeypatch.setenv("HEAD_REPO", head_repo)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert derive_tag.main() == 1
    assert not output.exists()


def test_no_workflow_carries_its_own_copy_of_the_sanitiser():
    offenders = [path.name for path in sorted(WORKFLOWS.glob("*.yml")) if SANITISER in path.read_text(encoding="utf-8")]
    assert not offenders, f"derive the tag with .github/scripts/derive_tag.py instead of copying the sanitiser into: {offenders}"


@pytest.mark.parametrize("workflow", ["ci.yml", "tag-cleanup.yml"])
def test_tag_workflows_call_the_shared_script(workflow):
    assert "derive_tag.py" in (WORKFLOWS / workflow).read_text(encoding="utf-8")
