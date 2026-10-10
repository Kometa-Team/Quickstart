import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

from modules import kometa_integrity as integrity
from modules.helpers import _zip_update as updater

COMMIT = "a" * 40
NEW_COMMIT = "b" * 40
SHIPPED = {
    "kometa.py": b"# vanilla Kometa\n",
    "requirements.txt": b"requests\n",
    "VERSION": b"1.0.0\n",
    "modules/overlay.py": b"# vanilla overlay code\n",
    "defaults/overlays/ratings.yml": b"overlays: {}\n",
    "defaults/overlays/images/rating.png": b"vanilla image bytes",
    "fonts/example.ttf": b"vanilla font bytes",
    "config/config.yml.template": b"# upstream template\n",
}


def make_zip(files=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in (files or SHIPPED).items():
            entry = zipfile.ZipInfo()
            # Preserve deliberately invalid ZIP paths on Windows too.
            entry.filename = f"Kometa-test/{path}"
            archive.writestr(entry, content)
    return buffer.getvalue()


@pytest.fixture
def managed_root(tmp_path):
    root = tmp_path / "kometa"
    for name, content in SHIPPED.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / ".kometa_sha").write_text(COMMIT, encoding="utf-8")
    (root / ".kometa_branch").write_text("develop", encoding="utf-8")
    integrity.write_manifest(root, integrity.manifest_from_zip(make_zip(), COMMIT, "develop"))
    return root


def test_baseline_is_built_from_archive_not_installed_files(managed_root):
    image = "defaults/overlays/images/rating.png"
    (managed_root / image).write_bytes(b"custom image")
    manifest = integrity.manifest_from_zip(make_zip(), COMMIT, "develop")
    assert manifest["files"][image] == hashlib.sha256(SHIPPED[image]).hexdigest()
    assert not any(path.startswith("config/") for path in manifest["files"])
    assert integrity.check_integrity(managed_root)["state"] == "modified"


@pytest.mark.parametrize("path", [path for path in SHIPPED if not path.startswith("config/")])
def test_modifications_are_detected_across_repeated_checks(managed_root, path):
    before = (managed_root / integrity.MANIFEST_NAME).read_bytes()
    (managed_root / path).write_bytes(b"modified")
    for _ in range(2):
        report = integrity.check_integrity(managed_root)
        assert report["state"] == "modified"
        assert report["modified"] == [path]
    assert (managed_root / integrity.MANIFEST_NAME).read_bytes() == before


def test_missing_and_added_files_are_reported(managed_root):
    (managed_root / "fonts/example.ttf").unlink()
    (managed_root / "modules/custom.py").write_text("# extra", encoding="utf-8")
    report = integrity.check_integrity(managed_root)
    assert report["state"] == "modified"
    assert report["missing"] == ["fonts/example.ttf"]
    assert report["added"] == ["modules/custom.py"]


@pytest.mark.parametrize(
    "path",
    [
        "config/logs/meta.log",
        "config/test.cache",
        "config/test.cache-wal",
        "config/overlays/image.png",
        "config/fonts/custom.ttf",
        "kometa-venv/bin/python",
        "modules/__pycache__/overlay.pyc",
        "modules/overlay.pyc",
        ".git/HEAD",
    ],
)
def test_normal_runtime_changes_are_ignored(managed_root, path):
    target = managed_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"runtime data")
    assert integrity.check_integrity(managed_root)["state"] == "clean"


def test_missing_manifest_is_not_verified_and_never_rebuilt(managed_root):
    (managed_root / integrity.MANIFEST_NAME).unlink()
    (managed_root / "kometa.py").write_text("# custom", encoding="utf-8")
    assert integrity.check_integrity(managed_root)["state"] == "not_verified"
    assert not (managed_root / integrity.MANIFEST_NAME).exists()


@pytest.mark.parametrize("mode", ["existing", "external"])
def test_nonmanaged_installs_are_not_scanned(managed_root, monkeypatch, mode):
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: pytest.fail("must not read unmanaged files"))
    assert integrity.check_integrity(managed_root, mode)["state"] == "not_applicable"


@pytest.mark.parametrize("corruption", ["bad_json", "bad_version", "bad_hash", "unsafe_path", "wrong_commit", "missing_sha"])
def test_invalid_baseline_never_reports_clean(managed_root, corruption):
    path = managed_root / integrity.MANIFEST_NAME
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if corruption == "bad_json":
        path.write_text("not JSON", encoding="utf-8")
    elif corruption == "missing_sha":
        (managed_root / ".kometa_sha").unlink()
    else:
        if corruption == "bad_version":
            manifest["schema_version"] = 9
        elif corruption == "bad_hash":
            manifest["files"]["kometa.py"] = "bad"
        elif corruption == "unsafe_path":
            manifest["files"]["../outside"] = "a" * 64
        else:
            manifest["commit"] = NEW_COMMIT
        path.write_text(json.dumps(manifest), encoding="utf-8")
    assert integrity.check_integrity(managed_root)["state"] == "check_failed"


@pytest.mark.parametrize("name", ["../escape.py", "/absolute.py", "modules/../../escape.py", "modules\\escape.py", "C:/escape.py"])
def test_unsafe_archive_is_rejected_before_install(name):
    with pytest.raises(ValueError):
        integrity.manifest_from_zip(make_zip({**SHIPPED, name: b"bad"}), COMMIT, "develop")


def test_archive_symbolic_link_is_rejected():
    buffer = io.BytesIO(make_zip())
    with zipfile.ZipFile(buffer, "a") as archive:
        entry = zipfile.ZipInfo("Kometa-test/modules/link.py")
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        archive.writestr(entry, "../../outside")
    with pytest.raises(ValueError):
        integrity.manifest_from_zip(buffer.getvalue(), COMMIT, "develop")


def test_symbolic_link_does_not_read_outside_installation(managed_root, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("# secret", encoding="utf-8")
    target = managed_root / "modules/overlay.py"
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links unavailable")
    report = integrity.check_integrity(managed_root)
    assert report["modified"] == ["modules/overlay.py"]
    assert "secret" not in "\n".join(integrity.format_integrity(report))


def test_unreadable_file_is_check_failed(managed_root, monkeypatch):
    original = Path.open

    def open_path(path, *args, **kwargs):
        if path == managed_root / "kometa.py":
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    report = integrity.check_integrity(managed_root)
    assert report["state"] == "check_failed"
    assert report["errors"] == ["Unable to read kometa.py"]


def test_diagnostics_are_bounded_and_escape_filename_newlines(managed_root):
    report = integrity.check_integrity(managed_root)
    report.update(state="modified", added=["bad\n# injected"] + [f"modules/extra{index}.py" for index in range(30)])
    lines = integrity.format_integrity(report)
    assert "Added: bad\\n# injected" in lines
    assert "Added: 11 more" in lines
    assert all("\n" not in line for line in lines)
    assert any("Force update" in line for line in lines)


@pytest.fixture
def update_environment(managed_root, tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(updater, "_get_upstream_sha", lambda *_args: NEW_COMMIT)
    monkeypatch.setattr(updater, "_download_zip", lambda *_args, **_kwargs: make_zip())
    monkeypatch.setattr(updater, "_ensure_venv", lambda *_args, **_kwargs: (managed_root / "python", managed_root / "pip"))
    monkeypatch.setattr(updater, "_pip_install", lambda *_args: True)
    return managed_root


@pytest.mark.parametrize("explicit_root", [False, True])
@pytest.mark.parametrize("deployment", ["source", "exe", "docker"])
def test_update_preserves_entire_config_and_replaces_baseline(update_environment, monkeypatch, explicit_root, deployment):
    root = update_environment
    monkeypatch.setattr(sys, "frozen", deployment == "exe", raising=False)
    monkeypatch.setenv("QUICKSTART_DOCKER", "1" if deployment == "docker" else "0")
    original_rmtree = updater.shutil.rmtree

    def rmtree(path, *args, **kwargs):
        assert Path(path) != root / "config", "Runtime config must remain in place (it may be a Docker mount)"
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(updater.shutil, "rmtree", rmtree)
    paths = [
        "config.yml",
        ".env",
        "UUID",
        "logs/meta.log",
        "test.cache",
        "test.cache-wal",
        "fonts/custom.ttf",
        "overlays/Movies Original Posters/poster.jpg",
        "custom/metadata.yml",
    ]
    for path in paths:
        target = root / "config" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"user data: {path}".encode())
    before = {path: (root / "config" / path).read_bytes() for path in paths}
    (root / "modules/overlay.py").write_bytes(b"custom code")
    (root / "modules/extra.py").write_bytes(b"extra code")
    calls = []

    def download(branch, logs, commit=None):
        calls.append((branch, commit))
        return make_zip()

    monkeypatch.setattr(updater, "_download_zip", download)
    if explicit_root:
        result = updater.perform_kometa_update_zip_only_at_root(root)
    else:
        result = updater.perform_kometa_update_zip_only(root.parent)
    assert result["success"] is True
    assert calls == [("develop", NEW_COMMIT)]
    assert {path: (root / "config" / path).read_bytes() for path in paths} == before
    assert not (root / "modules/extra.py").exists()
    report = integrity.check_integrity(root)
    assert report["state"] == "clean"
    assert report["commit"] == NEW_COMMIT


@pytest.mark.parametrize("baseline_present", [True, False])
def test_force_update_restores_modified_images_even_when_sha_matches(update_environment, monkeypatch, baseline_present):
    root = update_environment
    if not baseline_present:
        (root / integrity.MANIFEST_NAME).unlink()
    monkeypatch.setattr(updater, "_get_upstream_sha", lambda *_args: COMMIT)
    (root / "defaults/overlays/images/rating.png").write_bytes(b"custom image")
    skipped = updater.perform_kometa_update_zip_only_at_root(root)
    assert skipped["skipped"] is True
    assert integrity.check_integrity(root)["state"] == ("modified" if baseline_present else "not_verified")
    result = updater.perform_kometa_update_zip_only_at_root(root, force=True)
    assert result["success"] is True
    assert integrity.check_integrity(root)["state"] == "clean"


@pytest.mark.parametrize("pip_success", [True, False])
def test_first_install_only_creates_baseline_after_success(update_environment, tmp_path, monkeypatch, pip_success):
    root = tmp_path / "fresh-install"
    monkeypatch.setattr(updater, "_pip_install", lambda *_args: pip_success)
    result = updater.perform_kometa_update_zip_only_at_root(root)
    assert result["success"] is pip_success
    assert (root / "config/config.yml.template").read_bytes() == SHIPPED["config/config.yml.template"]
    assert (root / integrity.MANIFEST_NAME).exists() is pip_success
    assert integrity.check_integrity(root)["state"] == ("clean" if pip_success else "not_verified")


def test_backup_failure_aborts_without_wiping_installation(update_environment, monkeypatch):
    root = update_environment
    before = (root / integrity.MANIFEST_NAME).read_bytes()
    original = updater.shutil.copytree

    def copytree(source, destination, *args, **kwargs):
        if Path(source) == root / "config":
            raise PermissionError("backup denied")
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(updater.shutil, "copytree", copytree)
    result = updater.perform_kometa_update_zip_only_at_root(root)
    assert result["success"] is False
    assert (root / "kometa.py").read_bytes() == SHIPPED["kometa.py"]
    assert (root / integrity.MANIFEST_NAME).read_bytes() == before


@pytest.mark.parametrize("failure", ["extract", "restore", "pip"])
def test_failed_update_does_not_publish_new_baseline_and_keeps_backup(update_environment, monkeypatch, failure):
    root = update_environment
    before = (root / integrity.MANIFEST_NAME).read_bytes()
    user_config = root / "config/config.yml"
    user_config.write_bytes(b"plex: user data")
    if failure == "extract":
        monkeypatch.setattr(updater, "_extract_zip_bytes", lambda *_args, **_kwargs: False)
    elif failure == "restore":

        def failed_extraction(_archive, destination, _logs, **_kwargs):
            updater.shutil.rmtree(destination / "config")
            return True

        monkeypatch.setattr(updater, "_extract_zip_bytes", failed_extraction)
        monkeypatch.setattr(updater, "_restore_kometa_runtime_assets", lambda *_args, **_kwargs: False)
    else:
        monkeypatch.setattr(updater, "_pip_install", lambda *_args: False)
    result = updater.perform_kometa_update_zip_only_at_root(root)
    assert result["success"] is False
    assert (root / integrity.MANIFEST_NAME).read_bytes() == before
    assert (root / ".kometa_sha").read_text(encoding="utf-8") == COMMIT
    backups = list((root.parent / "kometa-backup").glob("*/config/config.yml"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"plex: user data"
    if failure != "restore":
        assert user_config.read_bytes() == b"plex: user data"


def test_invalid_download_does_not_touch_existing_installation(update_environment, monkeypatch):
    before = (update_environment / integrity.MANIFEST_NAME).read_bytes()
    monkeypatch.setattr(updater, "_download_zip", lambda *_args, **_kwargs: make_zip({**SHIPPED, "../outside": b"bad"}))
    assert updater.perform_kometa_update_zip_only_at_root(update_environment)["success"] is False
    assert (update_environment / integrity.MANIFEST_NAME).read_bytes() == before


def test_download_uses_exact_commit(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        content = b"zip"

    monkeypatch.setattr(updater.requests, "get", lambda url, **_kwargs: calls.append(url) or Response())
    assert updater._download_zip("develop", [], commit=COMMIT) == b"zip"
    assert calls == [f"https://codeload.github.com/kometa-team/Kometa/zip/{COMMIT}"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_launch_stamp_replaces_stale_comments_without_changing_yaml(managed_root, newline):
    from ruamel.yaml import YAML

    path = managed_root / "config/config.yml"
    path.write_bytes(("# yaml-language-server: test" + newline + "plex:" + newline + "  token: secret" + newline).encode())
    assert integrity.stamp_integrity_comments(path, integrity.check_integrity(managed_root))
    (managed_root / "defaults/overlays/images/rating.png").write_bytes(b"modified")
    assert integrity.stamp_integrity_comments(path, integrity.check_integrity(managed_root))
    raw = path.read_bytes()
    assert raw.count(integrity.COMMENT_START.encode()) == 1
    assert b"Kometa Integrity: MODIFIED" in raw
    assert b"Kometa Integrity: CLEAN" not in raw
    assert YAML(typ="safe").load(raw.decode()) == {"plex": {"token": "secret"}}
    if newline == "\r\n":
        assert b"\n" not in raw.replace(b"\r\n", b"")


def test_support_and_header_use_same_diagnostics(client, managed_root, monkeypatch, qs_module):
    from modules import output_yaml_header

    (managed_root / "defaults/overlays/images/rating.png").write_bytes(b"modified")
    report = integrity.check_integrity(managed_root)
    monkeypatch.setattr(qs_module, "current_integrity", lambda: report)
    monkeypatch.setattr(output_yaml_header, "current_integrity", lambda: report)
    monkeypatch.setattr(qs_module.helpers, "get_plex_summary", lambda: "Plex test")
    monkeypatch.setattr(qs_module.helpers, "get_library_summaries", lambda *_args: "No libraries")
    monkeypatch.setattr(qs_module.helpers, "get_quickstart_settings_summary", lambda: [])
    with qs_module.app.test_request_context():
        header = output_yaml_header.render_yaml_header("none", "test", {}, {}, {})
    response = client.get("/support-info")
    assert response.status_code == 200
    comments = integrity.integrity_comments(report)
    assert comments in header
    assert comments in response.get_json()["text"]
    assert "defaults/overlays/images/rating.png" in comments


def test_integrity_endpoint_reports_modified_files_without_blocking(client, managed_root, monkeypatch):
    from blueprints import kometa_updates

    (managed_root / "modules/overlay.py").write_bytes(b"modified")
    monkeypatch.setattr(kometa_updates, "current_integrity", lambda: integrity.check_integrity(managed_root))
    response = client.get("/kometa-integrity")
    assert response.status_code == 200
    assert response.get_json()["integrity"]["state"] == "modified"


def test_run_marker_carries_snapshot_into_meta_log(managed_root, monkeypatch, qs_module):
    from modules import process_markers

    (managed_root / "defaults/overlays/images/rating.png").write_bytes(b"modified")
    report = integrity.check_integrity(managed_root)
    with qs_module.app.app_context():
        assert process_markers.write_quickstart_run_marker(managed_root, "test", integrity_report=report)
    log_path = process_markers.get_kometa_pending_marker_path(managed_root).parent / "meta.log"
    log_path.write_text("# [Quickstart] Run marker: config=test\nConfig File\n", encoding="utf-8")
    with qs_module.app.app_context():
        flushed = process_markers.flush_quickstart_pending_markers(managed_root, require_process_stopped=False)
    assert flushed["flushed"] is True
    text = log_path.read_text(encoding="utf-8")
    for line in integrity.format_integrity(report):
        assert f"[Quickstart] {line}" in text


@pytest.mark.parametrize("state", ["modified", "not_verified", "check_failed"])
def test_launch_refreshes_diagnostics_without_blocking(managed_root, monkeypatch, qs_module, state):
    from types import SimpleNamespace

    from modules import process_lifecycle

    config_path = managed_root / "config/config.yml"
    config_path.write_text(integrity.integrity_comments(integrity.check_integrity(managed_root)) + "\nplex: {}\n", encoding="utf-8")
    (managed_root / "defaults/overlays/images/rating.png").write_bytes(b"modified after config generation")
    if state == "not_verified":
        (managed_root / integrity.MANIFEST_NAME).unlink()
    elif state == "check_failed":
        (managed_root / integrity.MANIFEST_NAME).write_text("invalid JSON", encoding="utf-8")
    python = managed_root / "kometa-venv" / ("Scripts/python.exe" if sys.platform.startswith("win") else "bin/python3")
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(process_lifecycle.helpers, "get_kometa_root_path", lambda: managed_root)
    monkeypatch.setattr(process_lifecycle.helpers, "get_kometa_pid_file", lambda: managed_root / "config/kometa.pid")
    monkeypatch.setattr(process_lifecycle, "current_integrity", lambda root: integrity.check_integrity(root))
    monkeypatch.setattr(process_lifecycle, "extract_kometa_config_path", lambda *_args: config_path)
    launched = []
    markers = []

    def popen(*args, **kwargs):
        launched.append((args, kwargs))
        return SimpleNamespace(pid=4321)

    monkeypatch.setattr(process_lifecycle.subprocess, "Popen", popen)
    monkeypatch.setattr(process_lifecycle, "_track_launched_process", lambda _proc: None)
    monkeypatch.setattr(process_lifecycle, "schedule_quickstart_run_marker", lambda *_args, **kwargs: markers.append(kwargs))
    with qs_module.app.app_context():
        assert process_lifecycle.launch_kometa_command("python kometa.py", config_name="test") == (True, 4321)
    assert len(launched) == 1
    report = markers[0]["integrity_report"]
    assert report["state"] == state
    config = config_path.read_text(encoding="utf-8")
    assert integrity.integrity_comments(report) in config
    assert config.count(integrity.COMMENT_START) == 1
    assert "plex: {}" in config
    assert "Kometa Integrity: CLEAN" not in config
