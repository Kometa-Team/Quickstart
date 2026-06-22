import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

BACKGROUND_JOBS: Dict[str, Dict[str, Any]] = {}
ACTIVE_BACKGROUND_JOBS: Dict[str, str] = {}
BACKGROUND_JOBS_LOCK = threading.Lock()
JOB_TARGET_PAGES = {
    "logscan_reingest": "/logscan-trends",
    "kometa_update": "/step/900-kometa",
    "test_library_install": "/step/001-start",
    "imagemaid_update": "/step/915-imagemaid",
}


def copy_background_job(job):
    if not isinstance(job, dict):
        return None
    copied = dict(job)
    if isinstance(copied.get("summary"), dict):
        copied["summary"] = dict(copied["summary"])
    if isinstance(copied.get("meta"), dict):
        copied["meta"] = dict(copied["meta"])
    if isinstance(copied.get("logs"), list):
        copied["logs"] = list(copied["logs"])
    return copied


def create_background_job(job_type, job_id=None, trigger="manual", phase="queued", status="running", target_page=None, **extra):
    normalized_type = str(job_type or "").strip()
    if not normalized_type:
        raise ValueError("job_type is required")
    normalized_job_id = str(job_id or uuid.uuid4()).strip()
    payload = {
        "job_id": normalized_job_id,
        "job_type": normalized_type,
        "trigger": str(trigger or "manual").strip() or "manual",
        "status": str(status or "running").strip() or "running",
        "phase": str(phase or "").strip() or None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "target_page": target_page or JOB_TARGET_PAGES.get(normalized_type),
        "summary": {},
        "meta": {},
    }
    payload.update(extra)
    with BACKGROUND_JOBS_LOCK:
        BACKGROUND_JOBS[normalized_job_id] = payload
        if payload["status"] in {"queued", "running"}:
            ACTIVE_BACKGROUND_JOBS[normalized_type] = normalized_job_id
    return copy_background_job(payload)


def get_background_job(job_id):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    with BACKGROUND_JOBS_LOCK:
        payload = BACKGROUND_JOBS.get(normalized_job_id)
        return copy_background_job(payload)


def get_active_background_job(job_type):
    normalized_type = str(job_type or "").strip()
    if not normalized_type:
        return None
    with BACKGROUND_JOBS_LOCK:
        job_id = ACTIVE_BACKGROUND_JOBS.get(normalized_type)
        payload = BACKGROUND_JOBS.get(job_id) if job_id else None
        return copy_background_job(payload)


def get_active_background_jobs():
    with BACKGROUND_JOBS_LOCK:
        jobs = []
        for job_id in ACTIVE_BACKGROUND_JOBS.values():
            payload = BACKGROUND_JOBS.get(job_id)
            if payload:
                jobs.append(copy_background_job(payload))
        return jobs


def update_background_job(job_id, **updates):
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    with BACKGROUND_JOBS_LOCK:
        payload = BACKGROUND_JOBS.get(normalized_job_id)
        if not payload:
            return None
        payload.update(updates)
        job_type = payload.get("job_type")
        status = str(payload.get("status") or "").strip().lower()
        if job_type:
            if status in {"queued", "running"}:
                ACTIVE_BACKGROUND_JOBS[job_type] = normalized_job_id
            elif ACTIVE_BACKGROUND_JOBS.get(job_type) == normalized_job_id:
                ACTIVE_BACKGROUND_JOBS.pop(job_type, None)
        return copy_background_job(payload)


def clear_active_background_job(job_type, job_id=None):
    normalized_type = str(job_type or "").strip()
    normalized_job_id = str(job_id or "").strip() or None
    if not normalized_type:
        return
    with BACKGROUND_JOBS_LOCK:
        active_job_id = ACTIVE_BACKGROUND_JOBS.get(normalized_type)
        if normalized_job_id and active_job_id != normalized_job_id:
            return
        ACTIVE_BACKGROUND_JOBS.pop(normalized_type, None)


def ensure_background_job(job_type, job_id=None, create_if_missing=False, **defaults):
    normalized_type = str(job_type or "").strip()
    if not normalized_type:
        return None
    candidate_id = str(job_id or "").strip() or None
    if candidate_id:
        existing = get_background_job(candidate_id)
        if existing:
            return existing
    active = get_active_background_job(normalized_type)
    if active:
        return active
    if not create_if_missing:
        return None
    return create_background_job(normalized_type, job_id=candidate_id, **defaults)


def complete_background_job(job_id, phase="done", summary=None, **updates):
    payload = {"status": "complete", "phase": phase, "finished_at": datetime.now(timezone.utc).isoformat()}
    if summary is not None:
        payload["summary"] = summary
    payload.update(updates)
    return update_background_job(job_id, **payload)


def fail_background_job(job_id, error, phase="error", **updates):
    payload = {
        "status": "error",
        "phase": phase,
        "error": str(error or "Unknown error"),
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(updates)
    return update_background_job(job_id, **payload)
