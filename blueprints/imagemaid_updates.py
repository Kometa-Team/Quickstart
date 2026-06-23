import sys
import threading
import time
from pathlib import Path

from flask import Blueprint, current_app as app, jsonify, request, session

from modules import helpers, imagemaid
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

bp = Blueprint("imagemaid_updates", __name__)


@bp.route("/probe-imagemaid-root", methods=["POST"])
def probe_imagemaid_root():
    payload = request.get_json(silent=True) or {}
    root_path = str(payload.get("path", "")).strip()
    branch_override = helpers.normalize_imagemaid_branch_override(payload.get("branch_override"))
    logs = []

    def log(msg):
        print(msg, file=sys.stderr)
        logs.append(msg)

    if not root_path:
        root_path = str(helpers.get_imagemaid_root_path())

    p = helpers.resolve_user_dir(root_path)
    if not p:
        log("❌ Invalid path provided.")
        return jsonify(success=False, error="Invalid path provided.", log=logs), 400

    session["imagemaid_root"] = p.as_posix()
    app.config["IMAGEMAID_ROOT"] = str(p)

    state = imagemaid.probe_imagemaid_root_state(p)
    effective_branch = helpers.resolve_imagemaid_update_branch(branch_override)
    log(f"🔍 Probing ImageMaid path: {state['imagemaid_root_display']}")
    if not state["root_exists"]:
        log("ℹ️ ImageMaid root does not exist yet. Install required.")
    elif not state["imagemaid_installed"]:
        log("ℹ️ ImageMaid files not found yet. Install required.")
    else:
        log("✅ ImageMaid files detected locally.")
        if state["local_branch"]:
            log(f"🌿 Local ImageMaid branch metadata: {state['local_branch']}")
        if state["local_sha"]:
            log(f"🔎 Local ImageMaid SHA: {state['local_sha'][:12]}")
        if state["venv_python_exists"]:
            log(f"🐍 ImageMaid venv python detected at: {state['venv_python_display']}")
        else:
            log("ℹ️ ImageMaid venv python not present yet. Prepare step still needed.")
    if state["imagemaid_running"]:
        log("ℹ️ ImageMaid is currently running.")

    return (
        jsonify(
            success=True,
            log=logs,
            effective_branch=effective_branch,
            branch_source_url=f"{helpers.IMAGEMAID_GITHUB_BASE_URL}/{effective_branch}",
            zip_source_url=helpers.IMAGEMAID_GITHUB_ZIP_URL.format(branch=effective_branch),
            **state,
        ),
        200,
    )


@bp.route("/check-imagemaid-update", methods=["POST"])
def check_imagemaid_update():
    payload = request.get_json(silent=True) or {}
    root_path = str(payload.get("path", "")).strip()
    branch_override_raw = payload.get("branch_override")
    branch_override = helpers.normalize_imagemaid_branch_override(branch_override_raw)
    branch = helpers.resolve_imagemaid_update_branch(branch_override)
    logs = []

    def log(msg):
        print(msg, file=sys.stderr)
        logs.append(msg)

    if not root_path:
        root_path = str(helpers.get_imagemaid_root_path())

    if branch_override_raw and not branch_override:
        log(f"❌ Invalid ImageMaid branch override: {branch_override_raw}")
        return jsonify(success=False, error="Invalid ImageMaid branch override.", log=logs), 400

    p = helpers.resolve_user_dir(root_path)
    if not p:
        log("❌ Invalid path provided.")
        return jsonify(success=False, error="Invalid path provided.", log=logs), 400

    session["imagemaid_root"] = p.as_posix()
    app.config["IMAGEMAID_ROOT"] = str(p)

    state = imagemaid.probe_imagemaid_root_state(p)
    if not state["imagemaid_installed"]:
        log("ℹ️ ImageMaid is not installed yet; update check skipped.")
        response = dict(state)
        response.update(
            success=True,
            log=logs,
            update_check_completed=False,
            imagemaid_update_available=False,
            imagemaid_update_check_skipped=False,
            cached=False,
            effective_branch=branch,
            remote_version="",
            remote_sha="",
            branch_mismatch=False,
            branch_source_url=f"{helpers.IMAGEMAID_GITHUB_BASE_URL}/{branch}",
            zip_source_url=helpers.IMAGEMAID_GITHUB_ZIP_URL.format(branch=branch),
        )
        return jsonify(response), 200

    if state["imagemaid_running"]:
        log("ℹ️ ImageMaid is currently running; update check skipped.")
        response = dict(state)
        response.update(
            success=True,
            log=logs,
            update_check_completed=True,
            imagemaid_update_check_skipped=True,
            imagemaid_update_available=False,
            cached=False,
            effective_branch=branch,
            remote_version="",
            remote_sha="",
            branch_mismatch=False,
            branch_source_url=f"{helpers.IMAGEMAID_GITHUB_BASE_URL}/{branch}",
            zip_source_url=helpers.IMAGEMAID_GITHUB_ZIP_URL.format(branch=branch),
        )
        return jsonify(response), 200

    if branch_override:
        log(f"⚠️ ImageMaid branch override selected: {branch_override}")
    else:
        log("ℹ️ ImageMaid branch selection: auto")

    update_info = helpers.get_cached_imagemaid_update(
        p,
        force_refresh=helpers.booler(payload.get("force", False)),
        branch_override=branch_override,
    )
    remote_branch = update_info.get("branch") or "develop"
    local_version = update_info.get("local_version") or state.get("local_version") or "unknown"
    local_branch = update_info.get("local_branch") or "unknown"
    local_sha = update_info.get("local_sha") or ""
    remote_version = update_info.get("remote_version") or ""
    remote_sha = update_info.get("remote_sha") or ""
    log(f"🌐 Remote ImageMaid branch source: {helpers.IMAGEMAID_GITHUB_BASE_URL}/{remote_branch}")
    if local_version:
        log(f"ℹ️ Installed ImageMaid version: {local_version}")
    if remote_version:
        log(f"🌐 Remote ImageMaid version: {remote_version}")
    log(f"ℹ️ Installed ImageMaid branch metadata: {local_branch}")
    if local_sha:
        log(f"🔎 Local ImageMaid SHA: {local_sha[:12]}")
    if remote_sha:
        log(f"🔎 Remote ImageMaid SHA: {remote_sha[:12]}")
    if update_info.get("cached"):
        log("ℹ️ Using cached ImageMaid update lookup.")
    if update_info.get("update_available"):
        if update_info.get("branch_mismatch"):
            log(f"⚠️ Installed branch '{local_branch}' differs from selected branch '{remote_branch}'.")
        log("⬆️ ImageMaid update available.")
    else:
        log("✅ ImageMaid is up to date.")

    response = dict(state)
    response.update(
        success=True,
        log=logs,
        update_check_completed=True,
        imagemaid_update_check_skipped=False,
        imagemaid_update_available=bool(update_info.get("update_available")),
        cached=bool(update_info.get("cached")),
        effective_branch=remote_branch,
        local_version=local_version,
        local_branch=local_branch,
        local_sha=local_sha,
        remote_version=remote_version,
        remote_sha=remote_sha,
        branch_mismatch=bool(update_info.get("branch_mismatch")),
        branch_source_url=f"{helpers.IMAGEMAID_GITHUB_BASE_URL}/{remote_branch}",
        zip_source_url=helpers.IMAGEMAID_GITHUB_ZIP_URL.format(branch=remote_branch),
    )
    return jsonify(response), 200


@bp.route("/update-imagemaid", methods=["POST"])
def update_imagemaid():
    import quickstart

    blocker = quickstart._get_active_work_blocker("imagemaid_update")
    if blocker:
        return (
            jsonify(
                {
                    "success": False,
                    "error": blocker.get("message") or "ImageMaid is currently running.",
                    "blocked_by": blocker.get("blocked_by"),
                    "pid": blocker.get("pid"),
                    "target_page": blocker.get("target_page"),
                }
            ),
            409,
        )

    try:
        cfg_dir = helpers.CONFIG_DIR
        data = request.get_json(silent=True) or {}
        branch_override_raw = data.get("branch_override")
        branch_override = helpers.normalize_imagemaid_branch_override(branch_override_raw)
        if branch_override_raw and not branch_override:
            return jsonify({"success": False, "error": "Invalid ImageMaid branch override.", "log": ["❌ Invalid ImageMaid branch override."]}), 400

        imagemaid_branch = branch_override or helpers.resolve_imagemaid_update_branch()
        force_update = helpers.booler(data.get("force", False))
        background = data.get("background") is True

        if background:
            active = get_active_background_job("imagemaid_update")
            if active:
                phase = active.get("phase")
                if phase and phase not in ["done", "error"]:
                    return jsonify(success=True, active=True, existing_job=True, job_id=active.get("job_id"), phase=phase), 200
                clear_active_background_job("imagemaid_update", job_id=active.get("job_id"))

            job = create_background_job(
                "imagemaid_update",
                trigger="manual",
                phase="queued",
                status="running",
                target_page=JOB_TARGET_PAGES.get("imagemaid_update"),
                logs=[],
                done=False,
                success=False,
                up_to_date=False,
                skipped=False,
                force=force_update,
                imagemaid_branch=imagemaid_branch,
                started_epoch=time.time(),
            )
            job_id = job["job_id"]

            def worker():
                class _ProgressLog(list):
                    def append(self_inner, item):
                        super().append(item)
                        current = get_background_job(job_id) or {}
                        lines = list(current.get("logs") or [])
                        lines.append(item)
                        update_background_job(job_id, logs=lines)

                logs = _ProgressLog()
                update_background_job(job_id, phase="running", status="running")
                if branch_override:
                    logs.append(f"⚠️ ImageMaid branch override selected: {branch_override}")
                else:
                    logs.append("ℹ️ ImageMaid branch selection: auto")
                logs.append(f"⚙️ ImageMaid branch selected: {imagemaid_branch} (ZIP mode)")
                if force_update:
                    logs.append("Force update enabled.")

                try:
                    result = helpers.perform_imagemaid_update_zip_only(cfg_dir, branch=imagemaid_branch, force=force_update, logs=logs)
                    try:
                        helpers.invalidate_cached_imagemaid_update(Path(cfg_dir) / "imagemaid")
                    except Exception:
                        pass
                    if result.get("success", False):
                        complete_background_job(
                            job_id, phase="done", success=True, done=True, up_to_date=bool(result.get("up_to_date", False)), skipped=bool(result.get("skipped", False))
                        )
                    else:
                        fail_background_job(
                            job_id,
                            "ImageMaid update failed.",
                            done=True,
                            success=False,
                            up_to_date=bool(result.get("up_to_date", False)),
                            skipped=bool(result.get("skipped", False)),
                        )
                except Exception as e:
                    logs.append("Exception during ImageMaid update.")
                    helpers.ts_log(f"ImageMaid update failed: {e}", level="ERROR")
                    fail_background_job(job_id, e, done=True, success=False)
                finally:
                    clear_active_background_job("imagemaid_update", job_id=job_id)

            threading.Thread(target=worker, daemon=True).start()
            return jsonify(success=True, active=True, job_id=job_id, phase="queued"), 200

        logs = []
        if branch_override:
            logs.append(f"⚠️ ImageMaid branch override selected: {branch_override}")
        else:
            logs.append("ℹ️ ImageMaid branch selection: auto")
        logs.append(f"⚙️ ImageMaid branch selected: {imagemaid_branch} (ZIP mode)")
        if force_update:
            logs.append("Force update enabled.")

        result = helpers.perform_imagemaid_update_zip_only(cfg_dir, branch=imagemaid_branch, force=force_update, logs=logs)
        try:
            helpers.invalidate_cached_imagemaid_update(Path(cfg_dir) / "imagemaid")
        except Exception:
            pass
        status = 200 if result.get("success") else 500

        return (
            jsonify(
                {
                    "success": result.get("success", False),
                    "log": list(logs),
                    "imagemaid_branch": imagemaid_branch,
                    "up_to_date": result.get("up_to_date", False),
                    "skipped": result.get("skipped", False),
                    "force": force_update,
                }
            ),
            status,
        )
    except Exception as e:
        helpers.ts_log(f"ImageMaid update failed: {e}", level="ERROR")
        return jsonify({"success": False, "log": ["Exception during ImageMaid update."]}), 500


@bp.route("/update-imagemaid-progress", methods=["GET"])
def update_imagemaid_progress():
    job_id = request.args.get("job_id", "").strip()
    since = request.args.get("since", "0").strip()
    if not job_id:
        return jsonify(success=False, error="Missing job_id."), 400
    info = get_background_job(job_id)
    if not info:
        return jsonify(success=False, error="Unknown job_id."), 404
    try:
        start_idx = max(int(since or "0"), 0)
    except ValueError:
        start_idx = 0
    lines = list(info.get("logs") or [])
    return jsonify(
        success=True,
        job_id=job_id,
        phase=info.get("phase"),
        done=bool(info.get("done")) or info.get("status") in {"complete", "error"},
        update_success=bool(info.get("success")),
        up_to_date=bool(info.get("up_to_date")),
        skipped=bool(info.get("skipped")),
        force=bool(info.get("force")),
        imagemaid_branch=info.get("imagemaid_branch"),
        lines=lines[start_idx:],
        next_index=len(lines),
    )


@bp.route("/tail-imagemaid-log", methods=["GET"])
def tail_imagemaid_log():
    latest_log = imagemaid.get_latest_imagemaid_log_path()
    path = latest_log if latest_log and Path(latest_log).exists() else None
    try:
        lines_param = str(request.args.get("lines", "2000")).strip().lower()
        max_lines = None
        if lines_param not in ("all", "full"):
            max_lines = max(1, min(int(lines_param), 20000))
    except Exception:
        max_lines = 2000

    if not path or not Path(path).exists():
        return jsonify({"error": "No ImageMaid log found."}), 404
    try:
        payload = imagemaid.read_text_tail_payload(path, max_lines=max_lines)
        text = imagemaid.sanitize_imagemaid_log_tail(payload.get("text"))
        return jsonify(
            {
                "success": True,
                "path": str(path),
                "text": text,
                "total_lines": payload.get("total_lines"),
                "log_age_seconds": payload.get("log_age_seconds"),
                "requested_lines": "all" if max_lines is None else max_lines,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Failed to read ImageMaid log: {e}"}), 500
