"""Upload current Kometa or resolved historical Kometa and ImageMaid logs."""

from flask import Blueprint, current_app, jsonify, request, session
from pathlib import Path

from modules import helpers
from modules.logscan_upload import MAX_BATCH_LOGS, UploadError, portal_uploader
from modules.logscan_auto_upload import AUTO_UPLOAD_KEYS

logscan_upload_bp = Blueprint("logscan_upload", __name__)


class RunLogError(UploadError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def resolve_run_log(run_key):
    import quickstart

    run = quickstart.database.get_log_run(run_key) or quickstart._get_logscan_incomplete_run(run_key)
    if not run:
        raise RunLogError("The selected run could not be found.", 404)
    tool_name = quickstart._normalize_logscan_tool_name(run.get("tool_name"))
    if tool_name not in ("kometa", "imagemaid"):
        raise RunLogError("The selected log type is not supported by online Logscan.")
    info = quickstart._resolve_logscan_run_log_info(run_key, run_record=run)
    if not info or not info.get("path"):
        raise RunLogError("The log for this run is no longer available.", 404)
    path = info["path"]
    if quickstart._classify_logscan_file_location(path) not in ("live", "archive"):
        raise RunLogError("The selected log is outside Quickstart's managed log locations.")
    if tool_name == "kometa" and Path(path).name.lower() == "meta.log" and quickstart._get_kometa_log_wait_payload(path):
        raise RunLogError("The current run's log is not ready yet.", 409)
    if not portal_uploader.supports_tool(tool_name):
        raise RunLogError("ImageMaid support is not yet available on online Logscan. Nothing was uploaded.")
    return path, run.get("config_name")


@logscan_upload_bp.post("/logscan/upload")
def upload_log():
    payload = request.get_json(silent=True)
    if not request.is_json or not isinstance(payload, dict) or payload.get("confirm") is not True:
        return jsonify(error="Confirm uploading the selected log to Logscan."), 400
    run_key = payload.get("run_key")
    if "run_key" in payload and (not isinstance(run_key, str) or not run_key.strip() or len(run_key) > 256):
        return jsonify(error="A valid run_key is required."), 400
    existing = portal_uploader.status(session.get("logscan_upload_job"))
    if existing and existing["phase"] not in ("complete", "failed"):
        if existing.get("kind") == "batch" or existing.get("run_key") != (run_key.strip() if run_key else None):
            return (
                jsonify(error="A different upload is already in progress. Wait for it to finish."),
                409,
            )
        return jsonify(existing), 202
    import quickstart

    path = helpers.get_kometa_log_dir() / "meta.log"
    config_name = session.get("config_name")
    if run_key:
        run_key = run_key.strip()
        try:
            path, config_name = resolve_run_log(run_key)
        except RunLogError as exc:
            return jsonify(error=str(exc)), exc.status
    # A new run may still be replacing the previous run's live meta.log.
    if not run_key and Path(path).name.lower() == "meta.log" and quickstart._get_kometa_log_wait_payload(path):
        return jsonify(error="The current run's log is not ready yet."), 409
    try:
        if run_key:
            job_id = portal_uploader.start(path, config_name=config_name, run_key=run_key)
        else:
            job_id = portal_uploader.start(path, config_name=config_name)
    except FileNotFoundError:
        return jsonify(error="The selected log is not available."), 404
    except UploadError as exc:
        return jsonify(error=str(exc)), 409
    except OSError:
        return jsonify(error="The selected log could not be read."), 500
    session["logscan_upload_job"] = job_id
    return jsonify(portal_uploader.status(job_id)), 202


@logscan_upload_bp.post("/logscan/upload/batch")
def upload_batch():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("confirm") is not True:
        return jsonify(error="Confirm uploading the selected logs to Logscan."), 400
    keys = payload.get("run_keys")
    if not isinstance(keys, list) or not 0 < len(keys) <= MAX_BATCH_LOGS or any(not isinstance(key, str) or not key.strip() or len(key) > 256 for key in keys):
        return (
            jsonify(error=f"Select between 1 and {MAX_BATCH_LOGS} valid run IDs."),
            400,
        )
    keys = list(dict.fromkeys(key.strip() for key in keys))
    existing = portal_uploader.status(session.get("logscan_upload_job"))
    if existing and existing["phase"] not in ("complete", "failed"):
        if existing.get("kind") != "batch" or [item["run_key"] for item in existing.get("items", [])] != keys:
            return (
                jsonify(error="A different upload is already in progress. Wait for it to finish."),
                409,
            )
        return jsonify(existing), 202
    app = current_app._get_current_object()

    def resolve(run_key):
        with app.app_context():
            return resolve_run_log(run_key)

    try:
        batch_id = portal_uploader.start_batch(keys, resolve)
    except UploadError as exc:
        return jsonify(error=str(exc)), 409
    session["logscan_upload_job"] = batch_id
    return jsonify(portal_uploader.status(batch_id)), 202


@logscan_upload_bp.post("/logscan/upload/batch/cancel")
def cancel_upload_batch():
    if not request.is_json:
        return jsonify(error="A JSON request is required."), 400
    batch_id = session.get("logscan_upload_job")
    if not portal_uploader.cancel_batch(batch_id):
        return jsonify(error="No upload queue is active in this session."), 404
    return jsonify(portal_uploader.status(batch_id))


@logscan_upload_bp.get("/logscan/upload/status")
def upload_status():
    status = portal_uploader.status(session.get("logscan_upload_job")) or {"phase": "idle"}
    if request.args.get("history") == "1":
        status["run_results"] = portal_uploader.saved_run_results()
        status["automatic_results"] = portal_uploader.automatic_results()
        status["automatic_pending"] = portal_uploader.automatic_pending()
        status["automatic_enabled"] = any(current_app.config.get(key, False) for key in AUTO_UPLOAD_KEYS.values())
        status["restoring"] = portal_uploader.restoring_results()
    response = jsonify(status)
    response.headers["Cache-Control"] = "no-store"
    return response
