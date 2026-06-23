import os
import platform
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile

import requests
from flask import Blueprint, current_app as app, jsonify, request

from modules import helpers, path_validation, test_libraries
from modules.background_jobs import (
    JOB_TARGET_PAGES,
    clear_active_background_job,
    complete_background_job,
    create_background_job,
    fail_background_job,
    get_active_background_job,
    get_background_job,
    update_background_job,
)

bp = Blueprint("test_libraries_routes", __name__)


@bp.route("/check-test-libraries", methods=["POST"])
def check_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, _, _, _ = test_libraries.resolve_test_libraries_paths(quickstart_root)
    resolved_path = os.path.abspath(target_path)

    found = test_libraries.test_libraries_present(target_path)
    target_exists = os.path.exists(target_path)
    unrecognized = bool(target_exists and not found)

    local_sha = ""
    remote_sha = ""
    is_outdated = False

    if found:
        sha_path = os.path.join(target_path, ".test_libraries_version")
        if os.path.exists(sha_path):
            try:
                with open(sha_path, "r") as f:
                    local_sha = f.read().strip()
            except Exception:
                local_sha = ""
            try:
                commit_info = requests.get(
                    "https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main",
                    timeout=5,
                ).json()
                remote_sha = commit_info.get("sha", "")[:7]
            except Exception:
                remote_sha = ""
            if local_sha and remote_sha and local_sha != remote_sha:
                is_outdated = True

    return jsonify(
        {
            "found": bool(found),
            "target_path": resolved_path,
            "is_outdated": is_outdated,
            "local_sha": local_sha,
            "remote_sha": remote_sha,
            "target_exists": target_exists,
            "unrecognized": unrecognized,
        }
    )


@bp.route("/test-libraries-settings", methods=["POST"])
def update_test_libraries_settings():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")
    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    temp_raw = data.get("temp_path", "")
    final_raw = data.get("final_path", "")
    confirm = helpers.booler(str(data.get("confirm", "")))

    path_errors = path_validation.validate_payload(
        {
            "temp_path": temp_raw,
            "final_path": final_raw,
        }
    )
    if path_errors:
        return jsonify(success=False, message="Invalid path values: " + " ".join(path_errors)), 400

    base_config_dir, _, _, default_final, default_tmp = test_libraries.resolve_test_libraries_paths(quickstart_root)
    temp_path = test_libraries.normalize_test_libraries_path(temp_raw or default_tmp, base_config_dir)
    final_path = test_libraries.normalize_test_libraries_path(final_raw or default_final, base_config_dir)

    if not temp_path or not final_path:
        return jsonify(success=False, message="Temp and final paths are required."), 400

    if test_libraries.paths_overlap(temp_path, final_path):
        return jsonify(success=False, message="Temp and final paths must be different and cannot be nested."), 400

    ok, msg = test_libraries.ensure_rw_dir(temp_path)
    if not ok:
        return jsonify(success=False, message=msg), 400
    ok, msg = test_libraries.ensure_rw_dir(final_path)
    if not ok:
        return jsonify(success=False, message=msg), 400

    old_final = test_libraries.normalize_test_libraries_path(app.config.get("QS_TEST_LIBS_PATH") or default_final, base_config_dir)
    old_has_libs = test_libraries.test_libraries_present(old_final)
    if old_final and final_path != old_final and old_has_libs and not confirm:
        return (
            jsonify(
                success=False,
                needs_confirm=True,
                message="Test libraries exist at the previous configured path. Quickstart will not move them.",
            ),
            409,
        )

    final_has_content = False
    if os.path.isdir(final_path):
        try:
            final_has_content = any(os.scandir(final_path))
        except Exception:
            final_has_content = True
    final_is_test_libs = test_libraries.test_libraries_present(final_path)
    if final_has_content and not final_is_test_libs and not confirm:
        return (
            jsonify(
                success=False,
                needs_confirm=True,
                message="The final path is not empty and does not look like test libraries. Quickstart will replace this folder during install/update.",
            ),
            409,
        )

    helpers.update_env_variable("QS_TEST_LIBS_TMP", temp_path)
    helpers.update_env_variable("QS_TEST_LIBS_PATH", final_path)
    os.environ["QS_TEST_LIBS_TMP"] = temp_path
    os.environ["QS_TEST_LIBS_PATH"] = final_path
    app.config["QS_TEST_LIBS_TMP"] = temp_path
    app.config["QS_TEST_LIBS_PATH"] = final_path

    return jsonify(
        success=True,
        message="Test library paths saved.",
        temp_path=temp_path,
        final_path=final_path,
        old_path=old_final if old_final and final_path != old_final else "",
    )


@bp.route("/clone-test-libraries-start", methods=["POST"])
def clone_test_libraries_start():
    """
    Starts a background job to download and install plex_test_libraries.

    Progress payload shapes by phase:
      download: {"phase":"download","pct":<int|None>,"text":str,"downloaded":int,"total":int}
      extract : {"phase":"extract","pct":int,"text":str,"files_done":int,"files_total":int}
      finalize: {"phase":"finalize","pct":int,"text":str}
      done    : {"phase":"done","pct":100,"text":str,"target_path":str}
      error   : {"phase":"error","pct":0,"text":str}
    """
    import quickstart

    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, tmp_root, _, _ = quickstart._resolve_test_libraries_paths(quickstart_root)
    resolved_path = os.path.abspath(target_path)
    if quickstart._paths_overlap(tmp_root, target_path):
        return jsonify(success=False, message="Temp and final paths must be different and cannot be nested.")
    if not quickstart._safe_to_replace_test_libraries(target_path):
        return jsonify(
            success=False,
            message="Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.",
        )

    active = get_active_background_job("test_library_install")
    if active:
        phase = active.get("phase")
        if phase and phase not in ["done", "error"]:
            return jsonify(success=True, job_id=active.get("job_id"), existing_job=True, started_at=active.get("started_epoch"))
        clear_active_background_job("test_library_install", job_id=active.get("job_id"))
    job = create_background_job(
        "test_library_install",
        trigger="manual",
        phase="queued",
        status="running",
        target_page=JOB_TARGET_PAGES.get("test_library_install"),
        pct=0,
        text="Queued...",
        started_epoch=time.time(),
    )
    job_id = job["job_id"]

    def worker():
        zip_url = "https://github.com/chazlarson/plex-test-libraries/archive/refs/heads/main.zip"
        commit_sha = ""
        estimated_total = 0
        estimated = False
        estimated_note = ""
        fallback_total = 5 * 1024 * 1024 * 1024  # 5 GiB

        def set_job_progress(**state):
            update_background_job(job_id, status="running", **state)

        try:
            # Best-effort SHA for UI banner
            try:
                commit_info = requests.get(
                    "https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main",
                    timeout=5,
                ).json()
                commit_sha = commit_info.get("sha", "")[:7]
            except Exception:
                commit_sha = ""

            # Try to get total size first (lets UI show determination early)
            total_size = 0
            try:
                head = requests.head(zip_url, allow_redirects=True, timeout=10)
                total_size = int(head.headers.get("Content-Length", "0") or 0)
            except Exception:
                total_size = 0
            if not total_size:
                try:
                    release_info = requests.get(
                        "https://api.github.com/repos/chazlarson/plex-test-libraries/releases/latest",
                        timeout=5,
                    ).json()
                    assets = release_info.get("assets") or []
                    release_zip = next(
                        (a for a in assets if str(a.get("name", "")).lower().endswith(".zip")),
                        None,
                    )
                    if release_zip and int(release_zip.get("size", 0) or 0) > 0:
                        estimated_total = int(release_zip.get("size", 0) or 0)
                        total_size = estimated_total
                        estimated = True
                        estimated_note = "release"
                except Exception:
                    estimated_total = 0
                    estimated = False
            if not total_size:
                try:
                    repo_info = requests.get(
                        "https://api.github.com/repos/chazlarson/plex-test-libraries",
                        timeout=5,
                    ).json()
                    size_kb = int(repo_info.get("size", 0) or 0)
                    if size_kb > 0:
                        estimated_total = size_kb * 1024
                        total_size = estimated_total
                        estimated = True
                        estimated_note = "repo"
                except Exception:
                    estimated_total = 0
                    estimated = False
            if not total_size or (estimated and total_size < fallback_total):
                total_size = fallback_total
                estimated = True
                estimated_note = "fallback"

            set_job_progress(
                phase="download",
                pct=0 if total_size else None,  # None => indeterminate until we know size
                text="Downloading zip...",
                downloaded=0,
                total=total_size,
                estimated=estimated,
                estimated_note=estimated_note,
            )

            ok, msg = test_libraries.ensure_rw_dir(tmp_root)
            if not ok:
                raise RuntimeError(msg)
            # Clean only our own stale temp folders
            try:
                for entry in os.listdir(tmp_root):
                    if entry.startswith("qs_test_libs_"):
                        shutil.rmtree(os.path.join(tmp_root, entry), ignore_errors=True)
            except Exception:
                pass

            with tempfile.TemporaryDirectory(prefix="qs_test_libs_", dir=tmp_root) as tmpdir:
                zip_path = os.path.join(tmpdir, "main.zip")

                # Stream download with throttled progress updates
                downloaded = 0
                last_push = 0.0
                with requests.get(zip_url, stream=True, timeout=(30, 300)) as r:
                    r.raise_for_status()

                    # If HEAD failed, try to get size from GET
                    if not total_size:
                        try:
                            total_size = int(r.headers.get("Content-Length", "0") or 0)
                            if total_size:
                                estimated = False
                                estimated_note = ""
                            set_job_progress(total=total_size, estimated=estimated, estimated_note=estimated_note)
                        except Exception:
                            total_size = 0

                    chunk = 1024 * 1024  # 1 MiB
                    with open(zip_path, "wb") as f:
                        for part in r.iter_content(chunk_size=chunk):
                            if not part:
                                continue
                            f.write(part)
                            downloaded += len(part)

                            now = time.time()
                            if (now - last_push) > 0.5 or (total_size and downloaded >= total_size):
                                pct = None
                                if total_size:
                                    pct = int(downloaded * 100 / total_size)
                                set_job_progress(
                                    phase="download",
                                    pct=pct,
                                    text="Downloading zip...",
                                    downloaded=downloaded,
                                    total=total_size,
                                    estimated=estimated,
                                    estimated_note=estimated_note,
                                )
                                last_push = now

                # Extract with per-file progress
                set_job_progress(
                    phase="extract",
                    pct=0,
                    text="Extracting...",
                    files_done=0,
                    files_total=0,
                )
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    members = zip_ref.infolist()
                    total_files = len(members) or 1
                    files_done = 0
                    last_push = 0.0

                    for info in members:
                        zip_ref.extract(info, tmpdir)
                        files_done += 1

                        now = time.time()
                        if (now - last_push) > 0.2 or files_done == total_files:
                            pct = int(files_done * 100 / total_files)
                            set_job_progress(
                                phase="extract",
                                pct=pct,
                                text=f"Extracting... {files_done}/{total_files} files",
                                files_done=files_done,
                                files_total=total_files,
                            )
                            last_push = now

                extracted_dir = os.path.join(tmpdir, "plex-test-libraries-main")

                # Finalize (replace folder)
                set_job_progress(phase="finalize", pct=95, text="Finalizing...")
                if os.path.exists(target_path):
                    if not test_libraries.safe_to_replace_test_libraries(target_path):
                        raise RuntimeError("Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.")
                    shutil.rmtree(target_path, onerror=helpers.handle_remove_readonly)
                shutil.move(extracted_dir, target_path)

                # Write version marker (best effort)
                if commit_sha:
                    try:
                        with open(os.path.join(target_path, ".test_libraries_version"), "w") as f:
                            f.write(commit_sha)
                    except Exception as e:
                        helpers.ts_log(f"Warning: Failed to write SHA version file: {e}", level="WARNING")

                # Permissions for non-Windows
                if platform.system() in ["Linux", "Darwin"]:
                    subprocess.run(["chmod", "-R", "777", target_path], check=False)

                complete_background_job(
                    job_id,
                    phase="done",
                    success=True,
                    pct=100,
                    text="Installed/updated successfully.",
                    target_path=resolved_path,
                )

        except Exception as e:
            fail_background_job(
                job_id,
                e,
                phase="error",
                success=False,
                pct=0,
                text=f"Error: {str(e)}",
            )

    threading.Thread(target=worker, daemon=True).start()
    return jsonify(success=True, job_id=job_id, started_at=job.get("started_epoch"))


@bp.route("/clone-test-libraries-progress", methods=["GET"])
def clone_test_libraries_progress():
    job_id = request.args.get("job_id", "")
    info = get_background_job(job_id)
    if not info:
        return jsonify(success=False, message="Unknown job_id"), 404

    # avoid duplicate kwarg: remove job's 'success' if present
    info_no_flag = dict(info)
    info_no_flag.pop("success", None)

    return jsonify(success=True, **info_no_flag)


@bp.route("/clone-test-libraries-active", methods=["GET"])
def clone_test_libraries_active():
    active = get_active_background_job("test_library_install")
    if not active:
        return jsonify(success=True, active=False)

    job_id = active.get("job_id")
    info = get_background_job(job_id) or {}
    phase = info.get("phase")
    if phase in ["done", "error"]:
        clear_active_background_job("test_library_install", job_id=job_id)
        return jsonify(success=True, active=False)

    return jsonify(
        success=True,
        active=True,
        job_id=job_id,
        started_at=info.get("started_epoch"),
        progress=info,
    )


@bp.route("/clone-test-libraries", methods=["POST"])
def clone_test_libraries():
    import quickstart

    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, tmp_root, _, _ = quickstart._resolve_test_libraries_paths(quickstart_root)

    resolved_path = os.path.abspath(target_path)
    if quickstart._paths_overlap(tmp_root, target_path):
        return jsonify(success=False, message="Temp and final paths must be different and cannot be nested.")
    if not quickstart._safe_to_replace_test_libraries(target_path):
        return jsonify(
            success=False,
            message="Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.",
        )

    try:
        # If already exists
        if os.path.exists(target_path) and test_libraries.test_libraries_present(target_path):
            return jsonify(success=True, message="Test libraries already present (ZIP install).", target_path=resolved_path)

        # ZIP fallback if git not found or Download failed
        zip_url = "https://github.com/chazlarson/plex-test-libraries/archive/refs/heads/main.zip"
        commit_sha = None
        try:
            commit_info = requests.get("https://api.github.com/repos/chazlarson/plex-test-libraries/commits/main", timeout=5).json()
            commit_sha = commit_info.get("sha", "")[:7]
        except Exception:
            commit_sha = None

        ok, msg = test_libraries.ensure_rw_dir(tmp_root)
        if not ok:
            return jsonify(success=False, message=msg)
        try:
            for entry in os.listdir(tmp_root):
                if entry.startswith("qs_test_libs_"):
                    shutil.rmtree(os.path.join(tmp_root, entry), ignore_errors=True)
        except Exception:
            pass

        with tempfile.TemporaryDirectory(prefix="qs_test_libs_", dir=tmp_root) as tmpdir:
            zip_path = os.path.join(tmpdir, "main.zip")

            with requests.get(zip_url, stream=True, timeout=(30, 300)) as r:
                if r.status_code != 200:
                    return jsonify(success=False, message="Failed to download ZIP fallback from GitHub.")
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            extracted_dir = os.path.join(tmpdir, "plex-test-libraries-main")
            if os.path.exists(target_path):
                if not test_libraries.safe_to_replace_test_libraries(target_path):
                    return jsonify(
                        success=False,
                        message="Target path exists but does not look like test libraries. Choose an empty folder or one containing test libraries.",
                    )
                shutil.rmtree(target_path, onerror=helpers.handle_remove_readonly)
            shutil.move(extracted_dir, target_path)

            if commit_sha:
                try:
                    with open(os.path.join(target_path, ".test_libraries_version"), "w") as f:
                        f.write(commit_sha)
                except Exception as e:
                    helpers.ts_log(f"Warning: Failed to write SHA version file: {e}", level="WARNING")

        if platform.system() in ["Linux", "Darwin"]:
            subprocess.run(["chmod", "-R", "777", target_path], check=False)

        return jsonify(success=True, message="Test libraries installed successfully.", target_path=resolved_path)

    except Exception as e:
        helpers.ts_log(f"Test library install failed: {e}", level="ERROR")
        return jsonify(success=False, message="Unexpected error.")


@bp.route("/purge-test-libraries", methods=["POST"])
def purge_test_libraries():
    data = request.get_json(silent=True) or {}
    quickstart_root = data.get("quickstart_root", "")

    if not quickstart_root:
        return jsonify(success=False, message="Quickstart root path not provided.")

    _, target_path, _, _, _ = test_libraries.resolve_test_libraries_paths(quickstart_root)

    resolved_path = os.path.abspath(target_path)

    try:
        if not os.path.exists(resolved_path):
            return jsonify(success=False, message="Test libraries folder does not exist.")
        if not test_libraries.test_libraries_present(resolved_path):
            return jsonify(
                success=False,
                message="Target path does not look like test libraries. Refusing to delete.",
            )

        shutil.rmtree(resolved_path, onerror=helpers.handle_remove_readonly)
        return jsonify(success=True, message=f"Test libraries deleted at: {resolved_path}")

    except Exception as e:
        return jsonify(success=False, message=f"Failed to delete folder:\n{str(e)}")
