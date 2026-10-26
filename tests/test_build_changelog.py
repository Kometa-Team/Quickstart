"""Exercise changelog ranges against real Git history, including missing tags."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_changelog, release


@pytest.fixture
def history(tmp_path, monkeypatch):
    release.run("git", "init", "--initial-branch=develop", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    release.git("config", "user.name", "Changelog Test")
    release.git("config", "user.email", "changelog@example.com")
    release.git("config", "commit.gpgsign", "false")
    release.git("config", "core.hooksPath", str(tmp_path / ".git" / "hooks"))

    def commit(message):
        release.git("commit", "--allow-empty", "-m", message)
        return release.git("rev-parse", "HEAD")

    return commit


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("target", ["0.10.15", "0.10.16", "1.0.0"])
def test_prerelease_without_matching_stable_tag_uses_previous_release(history, annotated, target):
    history("Previous stable release")
    release.git("tag", *(("-a", "v0.10.14", "-m", "Stable release") if annotated else ("v0.10.14",)))
    history("Quickstart Release 0.10.15")
    source = history("TV separator correction")
    before = release.git("show-ref")
    legacy = subprocess.run(["git", "log", f"v{target}..HEAD"], capture_output=True)
    assert legacy.returncode != 0  # Reproduce the missing-tag failure before exercising the fix.
    notes = build_changelog.changelog("Kometa-Team/Quickstart", target)
    assert "TV separator correction" in notes
    assert "Quickstart Release 0.10.15" in notes
    assert "Previous stable release" not in notes
    assert f"compare/v0.10.14...{source}" in notes
    assert release.git("show-ref") == before  # Generating notes never creates or moves a tag.


def test_first_prerelease_without_any_tags_uses_complete_history(history):
    history("First application commit")
    source = history("First prerelease")
    notes = build_changelog.changelog("Kometa-Team/Quickstart", "0.1.0")
    assert "First application commit" in notes and "First prerelease" in notes
    assert f"/commits/{source}" in notes and "/compare/" not in notes
    assert release.git("tag", "--list") == ""


def test_existing_matching_stable_tag_remains_the_baseline(history):
    history("Stable release")
    release.git("tag", "v0.10.15")
    history("Development change")
    notes = build_changelog.changelog("Kometa-Team/Quickstart", "0.10.15")
    assert "compare/v0.10.15..." in notes
    assert "Development change" in notes and "Stable release" not in notes


def test_unrelated_future_and_prerelease_tags_are_not_baselines(history):
    history("Previous stable release")
    release.git("tag", "v0.10.14")
    history("Prerelease content")
    release.git("tag", "v0.10.15-rc1")
    release.git("tag", "v99.0.0")
    release.git("branch", "unrelated")
    source = history("Development change")
    release.git("checkout", "unrelated")
    history("Different release history")
    release.git("tag", "v0.10.15")
    release.git("checkout", "--detach", source)
    notes = build_changelog.changelog("Kometa-Team/Quickstart", "0.10.15")
    assert "compare/v0.10.14..." in notes
    assert "Prerelease content" in notes and "Different release history" not in notes


def test_cli_uses_the_pinned_source_and_does_not_include_later_commits(history, tmp_path):
    script = Path(build_changelog.__file__).resolve()
    source = history("Approved development source")
    history("Later competing change")
    output = tmp_path / "notes.md"
    subprocess.run([sys.executable, str(script), "--repository", "Kometa-Team/Quickstart", "--version", "0.10.15", "--source", source, "--output", str(output)], check=True)
    assert "Approved development source" in output.read_text()
    assert "Later competing change" not in output.read_text()


def test_build_workflow_generates_notes_before_the_privileged_review_job():
    import yaml

    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / ".github/workflows/increment-build.yml").read_text())
    prepare = workflow["jobs"]["verify-changes"]
    assert "contents" not in prepare.get("permissions", {})
    scripts = "\n".join(step.get("run", "") for step in prepare["steps"])
    assert "scripts/build_changelog.py" in scripts and '--source "$MERGED_SHA"' in scripts
    upload = next(step for step in prepare["steps"] if "upload-artifact" in step.get("uses", ""))
    assert "changelog.md" in upload["with"]["path"]
    review = workflow["jobs"]["review"]
    scripts = "\n".join(step.get("run", "") for step in review["steps"])
    assert '--body-file "$RUNNER_TEMP/changelog.md"' in scripts
    assert "scripts/build_changelog.py" not in scripts
