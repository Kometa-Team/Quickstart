"""Manual and opt-in automatic uploads of runtime logs to Logscan."""

import os
import copy
import gzip
import hashlib
import json
import logging
import math
import re
import secrets
import tempfile
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

from modules.logscan_cache import get_logscan_cache_dir

PORTAL_URL = "https://logscan.kometa.team"
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_BATCH_LOGS = 500
UPLOAD_RESPONSE_TIMEOUT = 900
SCAN_JOB_TIMEOUT = 900
MAX_STATUS_FAILURES = 5
UPLOAD_CHUNK_BYTES = 64 * 1024


class UploadError(ValueError):
    def __init__(self, message, *, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class MultipartLog:
    """Sized iterable multipart body; requests never reads the whole file."""

    def __init__(self, snapshot, size, filename="qs-default-meta.gz"):
        self.snapshot = snapshot
        self.boundary = secrets.token_hex(24)
        self.prefix = (f'--{self.boundary}\r\nContent-Disposition: form-data; name="log"; filename="{filename}"\r\n' "Content-Type: application/gzip\r\n\r\n").encode()
        self.suffix = f"\r\n--{self.boundary}--\r\n".encode()
        self.size = size

    def __len__(self):
        return len(self.prefix) + self.size + len(self.suffix)

    def __iter__(self):
        yield self.prefix
        self.snapshot.seek(0)
        while chunk := self.snapshot.read(UPLOAD_CHUNK_BYTES):
            yield chunk
        yield self.suffix


def compress_source(source, size, digest=None):
    """Gzip a fixed byte count without retaining uncompressed data in memory."""
    snapshot = tempfile.TemporaryFile(mode="w+b")
    try:
        validate_size(size)
        remaining = size
        with gzip.GzipFile(fileobj=snapshot, mode="wb", filename="", mtime=0) as compressed:
            while remaining:
                chunk = source.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise UploadError("The log changed while preparing the upload. Try again.")
                compressed.write(chunk)
                if digest is not None:
                    digest.update(chunk)
                remaining -= len(chunk)
        size = snapshot.tell()
        if size > MAX_UPLOAD_BYTES:
            raise UploadError("The compressed log exceeds Logscan's 1 GiB upload limit.")
        snapshot.seek(0)
        return snapshot, size
    except Exception:
        snapshot.close()
        raise


def validate_size(size):
    if not size:
        raise UploadError("The selected log is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise UploadError("The selected log exceeds Logscan's 1 GiB upload limit.")


def snapshot_gzip(source, size, digest=None):
    """Copy an archive unchanged, checking its decoded size and integrity."""
    snapshot = tempfile.TemporaryFile(mode="w+b")
    try:
        validate_size(size)
        remaining = size
        while remaining:
            chunk = source.read(min(remaining, 1024 * 1024))
            if not chunk:
                raise UploadError("The archived log changed while preparing the upload.")
            snapshot.write(chunk)
            remaining -= len(chunk)
        snapshot.seek(0)
        decoded_size = 0
        with gzip.GzipFile(fileobj=snapshot, mode="rb") as decoded:
            while chunk := decoded.read(min(1024 * 1024, MAX_UPLOAD_BYTES - decoded_size + 1)):
                decoded_size += len(chunk)
                validate_size(decoded_size)
                if digest is not None:
                    digest.update(chunk)
        validate_size(decoded_size)
        snapshot.seek(0)
        return snapshot, size
    except Exception:
        snapshot.close()
        raise


def snapshot_log(path):
    with open(path, "rb") as source:
        return compress_source(source, os.fstat(source.fileno()).st_size)


def upload_filename(config_name=None):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(config_name or "default")).strip("_-")[:80] or "default"
    return f"qs-{name}-meta.gz"


def result_links(payload):
    url = payload.get("result_url", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "logscan.kometa.team" or not re.fullmatch(r"/scan/[A-Za-z0-9_-]+", parsed.path):
        raise UploadError("Logscan returned an unexpected result link.")
    public_url = PORTAL_URL + parsed.path
    token = payload.get("delete_token", "")
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,128}", token):
        raise UploadError("Logscan did not return a valid upload management token.")
    return {
        "result_url": public_url,
        "management_url": f"{public_url}#delete={token}",
        "expires_at": payload.get("expires_at"),
    }


class LogscanUploader:
    def __init__(self, receipt_path=None):
        self.lock = threading.Lock()
        self.jobs = {}
        self.batches = {}
        self.active = False
        self.receipt_path = receipt_path
        self.receipts = {}
        self.receipts_loaded = False
        self.receipt_lock = threading.RLock()
        self.automatic = {}
        self.auto_queue = {}
        self.auto_thread = None
        self.restore_queue = {}
        self.restore_checked = set()
        self.restore_thread = None
        self.capabilities = None
        self.capabilities_checked_at = 0

    def supports_tool(self, tool_name):
        if tool_name == "kometa":
            return True
        if tool_name != "imagemaid":
            return False
        with self.lock:
            if self.capabilities is not None and time.monotonic() - self.capabilities_checked_at < (300 if tool_name in self.capabilities else 30):
                return tool_name in self.capabilities
        tools = []
        try:
            response = requests.get(PORTAL_URL + "/api/capabilities", timeout=(10, 15), allow_redirects=False)
            try:
                payload = response.json() if response.status_code == 200 else None
            finally:
                response.close()
            advertised = payload.get("tools") if isinstance(payload, dict) else None
            if isinstance(advertised, list) and all(isinstance(tool, str) for tool in advertised):
                tools = advertised
        except (requests.RequestException, ValueError):
            pass
        with self.lock:
            self.capabilities = set(tools)
            self.capabilities_checked_at = time.monotonic()
        return tool_name in tools

    def _receipt_file(self):
        value = self.receipt_path() if callable(self.receipt_path) else self.receipt_path
        return Path(value) if value is not None else None

    def _load_receipts(self):
        if self.receipts_loaded:
            return
        self.receipts_loaded = True
        try:
            path = self._receipt_file()
            if path is None:
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            receipts = data.get("receipts", {}) if isinstance(data, dict) else {}
            automatic = data.get("automatic", {}) if isinstance(data, dict) else {}
            if isinstance(automatic, dict):
                for key, value in automatic.items():
                    if not isinstance(key, str) or not 0 < len(key) <= 256 or not isinstance(value, dict):
                        continue
                    if value.get("phase") not in {"complete", "failed", "not_uploaded"}:
                        value = {"phase": "failed", "error": "Automatic upload was interrupted. Check Logscan before uploading manually.", "uncertain": True}
                    self.automatic[key] = {**value, "run_key": key}
            if isinstance(receipts, dict):
                for key, value in receipts.items():
                    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key) or not isinstance(value, dict):
                        continue
                    try:
                        uploaded_at = float(value.get("uploaded_at", 0))
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(uploaded_at) and uploaded_at > 0:
                        self.receipts[key] = value
        except (OSError, ValueError):
            self.receipts = {}

    def _existing_receipt(self, fingerprint):
        with self.receipt_lock:
            self._load_receipts()
            return self._receipt_links(self.receipts.get(fingerprint))

    def _confirmed_receipt(self, fingerprint):
        existing = self._existing_receipt(fingerprint)
        if existing is None:
            return None
        try:
            with requests.Session() as connection:
                response = connection.head(existing["result_url"], timeout=(10, 30), allow_redirects=False)
                try:
                    status = response.status_code
                finally:
                    response.close()
        except requests.RequestException as exc:
            raise UploadError(
                "The previous upload could not be checked. Nothing new was uploaded. Try again when Logscan is available.",
                uncertain=True,
            ) from exc
        if status == 200:
            return existing
        if status in (404, 410):
            with self.receipt_lock:
                self.receipts.pop(fingerprint, None)
                self._save_receipts()
            return None
        raise UploadError(
            "The previous upload could not be checked. Nothing new was uploaded. Try again when Logscan is available.",
            uncertain=True,
        )

    def _receipt_links(self, receipt):
        if receipt is None:
            return None
        try:
            expires = receipt.get("expires_at")
            if expires is None:
                expires = float(receipt["uploaded_at"]) + 86400
            elif isinstance(expires, str):
                date = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                expires = date.replace(tzinfo=timezone.utc).timestamp() if date.tzinfo is None else date.timestamp()
            if not math.isfinite(float(expires)) or float(expires) <= time.time():
                return None
            return result_links(receipt)
        except (
            UploadError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            OverflowError,
        ):
            return None

    def _remember_receipt(self, fingerprint, payload, run_key=None):
        with self.receipt_lock:
            self._load_receipts()
            run_keys = self._receipt_run_keys(self.receipts.get(fingerprint, {}))
            if run_key:
                run_keys.add(run_key)
            self.receipts[fingerprint] = {
                "result_url": payload["result_url"],
                "delete_token": payload["delete_token"],
                "expires_at": payload.get("expires_at"),
                "uploaded_at": time.time(),
                "run_keys": sorted(run_keys),
            }
            self._save_receipts()

    @staticmethod
    def _receipt_run_keys(receipt):
        keys = receipt.get("run_keys", [])
        return {key for key in keys if isinstance(key, str) and 0 < len(key) <= 256} if isinstance(keys, list) else set()

    def _bind_receipt(self, fingerprint, run_key):
        if not run_key:
            return
        with self.receipt_lock:
            self._load_receipts()
            receipt = self.receipts.get(fingerprint)
            if not self._receipt_links(receipt):
                return
            run_keys = self._receipt_run_keys(receipt)
            if run_key not in run_keys:
                receipt["run_keys"] = sorted(run_keys | {run_key})
                self._save_receipts()

    def saved_run_results(self):
        with self.receipt_lock:
            self._load_receipts()
            results = {}
            for receipt in sorted(self.receipts.values(), key=lambda item: float(item["uploaded_at"])):
                links = self._receipt_links(receipt)
                if links:
                    for run_key in self._receipt_run_keys(receipt):
                        results[run_key] = {
                            "phase": "complete",
                            "run_key": run_key,
                            "uploaded_at": receipt["uploaded_at"],
                            **links,
                        }
            return results

    def automatic_results(self):
        with self.receipt_lock:
            self._load_receipts()
            results = copy.deepcopy(self.automatic)
            saved = self.saved_run_results()
            for key, value in results.items():
                if key in saved:
                    results[key] = saved[key]
                elif value.get("phase") == "complete":
                    results[key] = {"run_key": key, "phase": "expired"}
            return results

    def automatic_pending(self):
        with self.receipt_lock:
            return self.auto_thread is not None

    def enqueue_auto(self, path, *, config_name, run_key, tool_name, enabled):
        if not isinstance(run_key, str) or not 0 < len(run_key) <= 256 or tool_name not in {"kometa", "imagemaid"}:
            return False
        with self.receipt_lock:
            self._load_receipts()
            if run_key in self.automatic or run_key in self.saved_run_results():
                return False
            self.automatic[run_key] = {"run_key": run_key, "phase": "waiting"}
            self.auto_queue[run_key] = (path, config_name, tool_name, enabled)
            self._save_receipts()
            if self.auto_thread is None:
                self.auto_thread = threading.Thread(target=self._run_automatic, daemon=True, name="logscan-auto-upload")
                try:
                    self.auto_thread.start()
                except Exception:
                    self.auto_thread = None
                    self.auto_queue.pop(run_key, None)
                    self.automatic[run_key] = {"run_key": run_key, "phase": "failed", "error": "Automatic upload could not start. Nothing was uploaded."}
                    self._save_receipts()
                    raise
            return True

    def _set_automatic_result(self, run_key, data):
        with self.receipt_lock:
            self.automatic[run_key] = {key: value for key, value in data.items() if key in {"phase", "error", "uncertain", "already_uploaded"}}
            self.automatic[run_key]["run_key"] = run_key
            self._save_receipts()

    def _run_automatic(self):
        while True:
            with self.receipt_lock:
                if not self.auto_queue:
                    self.auto_thread = None
                    return
                run_key = next(iter(self.auto_queue))
                path, config_name, tool_name, enabled = self.auto_queue.pop(run_key)
            try:
                while True:
                    if not enabled():
                        self._set_automatic_result(run_key, {"phase": "not_uploaded"})
                        break
                    with self.lock:
                        active = self.active
                    if active:
                        time.sleep(0.25)
                        continue
                    if not self.supports_tool(tool_name):
                        raise UploadError("Online Logscan does not currently accept this log type. Nothing was uploaded.")
                    if not enabled():
                        continue
                    try:
                        job_id = self.start(path, config_name=config_name, run_key=run_key)
                    except UploadError:
                        with self.lock:
                            if self.active:
                                continue
                        raise
                    previous_phase = None
                    while True:
                        status = self.status(job_id)
                        if status["phase"] != previous_phase:
                            self._set_automatic_result(run_key, status)
                            previous_phase = status["phase"]
                        if status["phase"] in {"complete", "failed"}:
                            break
                        time.sleep(0.25)
                    break
            except (OSError, UploadError) as exc:
                error = str(exc) if isinstance(exc, UploadError) else "The local log could not be read. Nothing was uploaded."
                self._set_automatic_result(run_key, {"phase": "failed", "error": error})
            except Exception:
                self._set_automatic_result(
                    run_key, {"phase": "failed", "uncertain": True, "error": "Automatic upload could not be confirmed. Check Logscan before uploading manually."}
                )

    def restore_run_result(self, run_key, path):
        """Recover pre-association receipts locally, without delaying Analytics."""
        if not isinstance(run_key, str) or not 0 < len(run_key) <= 256:
            return False
        with self.receipt_lock:
            self._load_receipts()
            if not any(not self._receipt_run_keys(item) and self._receipt_links(item) for item in self.receipts.values()):
                return False
            try:
                path = Path(path)
                stat = path.stat()
                validate_size(stat.st_size)
            except (OSError, UploadError):
                return False
            key = (run_key, str(path), stat.st_size, stat.st_mtime_ns)
            if key in self.restore_checked:
                return self.restoring_results()
            self.restore_checked.add(key)
            self.restore_queue[key] = path
            if self.restore_thread is None:
                self.restore_thread = threading.Thread(
                    target=self._restore_run_results,
                    daemon=True,
                    name="logscan-receipt-restore",
                )
                self.restore_thread.start()
            return True

    def restoring_results(self):
        with self.receipt_lock:
            return self.restore_thread is not None

    def _restore_run_results(self):
        while True:
            with self.receipt_lock:
                if not self.restore_queue or not any(not self._receipt_run_keys(item) and self._receipt_links(item) for item in self.receipts.values()):
                    self.restore_queue.clear()
                    self.restore_thread = None
                    return
                key, path = self.restore_queue.popitem()
            try:
                digest = hashlib.sha256()
                total = 0
                opener = gzip.open if path.suffix.lower() == ".gz" else open
                with opener(path, "rb") as source:
                    while chunk := source.read(min(1024 * 1024, MAX_UPLOAD_BYTES - total + 1)):
                        total += len(chunk)
                        validate_size(total)
                        digest.update(chunk)
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) == key[2:]:
                    self._bind_receipt(digest.hexdigest(), key[0])
            except (OSError, EOFError, zlib.error, UploadError):
                continue

    def _save_receipts(self):
        self.receipts = dict(
            sorted(
                self.receipts.items(),
                key=lambda entry: float(entry[1].get("uploaded_at", 0)),
                reverse=True,
            )[:500]
        )
        temporary = None
        try:
            path = self._receipt_file()
            if path is None:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({"version": 3, "receipts": self.receipts, "automatic": dict(list(self.automatic.items())[-500:])}, handle)
            temporary.replace(path)
        except OSError:
            logging.getLogger(__name__).warning("Could not save the local Logscan upload receipt.")
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    logging.getLogger(__name__).warning("Could not remove the temporary Logscan upload receipt.")

    def status(self, job_id):
        with self.lock:
            job = self.batches.get(job_id) or self.jobs.get(job_id)
            return copy.deepcopy(job) if job else None

    def _update(self, job_id, **values):
        with self.lock:
            self.jobs[job_id].update(values)
            job = self.jobs[job_id]
            if job.get("batch_id") in self.batches:
                self.batches[job["batch_id"]]["items"][job["batch_index"]].update(values)

    def start_batch(self, run_keys, resolve_run):
        keys = list(dict.fromkeys(run_keys))
        if not keys or len(keys) > MAX_BATCH_LOGS:
            raise UploadError(f"Select between 1 and {MAX_BATCH_LOGS} logs.")
        with self.lock:
            if self.active:
                raise UploadError("An upload is already in progress. Wait for it to finish.")
            self.active = True
            batch_id = secrets.token_urlsafe(24)
            self.batches = {key: value for key, value in self.batches.items() if time.time() - value["created_at"] < 3600}
            if len(self.batches) >= 20:
                self.batches.pop(next(iter(self.batches)))
            self.batches[batch_id] = {
                "kind": "batch",
                "phase": "uploading",
                "created_at": time.time(),
                "cancel_requested": False,
                "items": [{"run_key": key, "phase": "waiting"} for key in keys],
            }
        try:
            threading.Thread(
                target=self._run_batch,
                args=(batch_id, resolve_run),
                daemon=True,
                name="logscan-upload-batch",
            ).start()
        except Exception:
            with self.lock:
                self.active = False
                self.batches.pop(batch_id, None)
            raise
        return batch_id

    def cancel_batch(self, batch_id):
        with self.lock:
            batch = self.batches.get(batch_id)
            if batch and batch["phase"] == "uploading":
                batch["cancel_requested"] = True
            return bool(batch)

    def _run_batch(self, batch_id, resolve_run):
        try:
            total = len(self.status(batch_id)["items"])
            for index in range(total):
                with self.lock:
                    batch = self.batches[batch_id]
                    if batch["cancel_requested"]:
                        break
                    run_key = batch["items"][index]["run_key"]
                    batch["items"][index]["phase"] = "preparing"
                job_id = secrets.token_urlsafe(24)
                source = None
                try:
                    path, config_name = resolve_run(run_key)
                    source = open(path, "rb")
                    size = os.fstat(source.fileno()).st_size
                    validate_size(size)
                    with self.lock:
                        self.jobs[job_id] = {
                            "phase": "preparing",
                            "run_key": run_key,
                            "batch_id": batch_id,
                            "batch_index": index,
                        }
                    self._prepare_and_run(
                        job_id,
                        source,
                        size,
                        upload_filename(config_name),
                        Path(path).suffix.lower() == ".gz",
                        release_active=False,
                    )
                    item = self.status(job_id)
                    if item.get("uncertain"):
                        with self.lock:
                            self.batches[batch_id].update(
                                phase="failed",
                                error="Queue paused: an upload could not be confirmed. Check Logscan before retrying. Remaining logs were not uploaded.",
                            )
                        break
                except (UploadError, OSError) as exc:
                    error = str(exc) if isinstance(exc, UploadError) else "The selected log could not be read. Nothing was uploaded."
                    with self.lock:
                        self.batches[batch_id]["items"][index].update(phase="failed", error=error)
                finally:
                    if source is not None:
                        source.close()
                    with self.lock:
                        self.jobs.pop(job_id, None)
            with self.lock:
                batch = self.batches[batch_id]
                for item in batch["items"]:
                    if item["phase"] == "waiting":
                        item["phase"] = "not_uploaded"
                if batch["phase"] != "failed":
                    batch["phase"] = "complete"
        except Exception:
            with self.lock:
                batch = self.batches[batch_id]
                batch.update(
                    phase="failed",
                    error="The upload queue stopped. Check the per-run results before retrying.",
                )
                for item in batch["items"]:
                    if item["phase"] not in ("complete", "failed"):
                        item["phase"] = "not_uploaded"
        finally:
            with self.lock:
                self.active = False

    def start(self, path, config_name=None, run_key=None):
        with self.lock:
            if self.active:
                raise UploadError("An upload is already in progress. Wait for it to finish.")
            self.active = True
        source = None
        try:
            source = open(path, "rb")
            size = os.fstat(source.fileno()).st_size
            validate_size(size)
            job_id = secrets.token_urlsafe(24)
            with self.lock:
                self.jobs = {key: job for key, job in self.jobs.items() if time.time() - job["created_at"] < 3600}
                if len(self.jobs) >= 20:
                    self.jobs.pop(next(iter(self.jobs)))
                self.jobs[job_id] = {
                    "phase": ("preparing" if Path(path).suffix.lower() == ".gz" else "compressing"),
                    "created_at": time.time(),
                    "filename": upload_filename(config_name),
                    "run_key": run_key,
                }
            threading.Thread(
                target=self._prepare_and_run,
                args=(
                    job_id,
                    source,
                    size,
                    upload_filename(config_name),
                    Path(path).suffix.lower() == ".gz",
                ),
                daemon=True,
                name="logscan-upload",
            ).start()
            return job_id
        except Exception:
            if source is not None:
                source.close()
            with self.lock:
                self.active = False
            raise

    def _prepare_and_run(self, job_id, source, size, filename, compressed=False, *, release_active=True):
        snapshot = None
        try:
            digest = hashlib.sha256()
            with source:
                prepare = snapshot_gzip if compressed else compress_source
                snapshot, compressed_size = prepare(source, size, digest)
            fingerprint = digest.hexdigest()
            self._update(job_id, phase="checking", content_sha256=fingerprint)
            existing = self._confirmed_receipt(fingerprint)
            if existing:
                self._bind_receipt(fingerprint, self.status(job_id).get("run_key"))
                self._update(job_id, phase="complete", already_uploaded=True, **existing)
                return
            self._update(job_id, phase="uploading")
            self._run(job_id, snapshot, compressed_size, filename)
        except UploadError as exc:
            self._update(job_id, phase="failed", error=str(exc), uncertain=exc.uncertain)
        except (OSError, EOFError):
            self._update(
                job_id,
                phase="failed",
                error="The log could not be prepared. Nothing was uploaded.",
            )
        except Exception:
            self._update(
                job_id,
                phase="failed",
                error="The upload could not be confirmed. Check Logscan before retrying.",
                uncertain=True,
            )
        finally:
            try:
                if snapshot is not None:
                    snapshot.close()
            finally:
                if release_active:
                    with self.lock:
                        self.active = False

    def _wait_for_remote_job(self, connection, job_id, *, recovery_error=None):
        deadline = time.monotonic() + SCAN_JOB_TIMEOUT
        failures = 0
        last_error = recovery_error or "Logscan upload status is unavailable."
        if recovery_error:
            self._update(job_id, phase="checking_status")
        while time.monotonic() < deadline:
            time.sleep(2)
            if time.monotonic() >= deadline:
                break
            try:
                poll = connection.get(
                    PORTAL_URL + f"/api/scan-jobs/{job_id}",
                    timeout=(10, min(30, max(1, deadline - time.monotonic()))),
                    allow_redirects=False,
                )
                try:
                    if poll.status_code != 200:
                        last_error = f"Logscan status request returned HTTP {poll.status_code}."
                        if poll.status_code not in {404, 408, 429, 500, 502, 503, 504}:
                            raise UploadError(last_error + " The upload may still be processing; check Logscan before retrying.", uncertain=True)
                        payload = None
                    else:
                        payload = poll.json()
                        if not isinstance(payload, dict) or payload.get("phase") not in {"uploading", "queued", "validating", "scanning", "saving", "complete", "failed"}:
                            last_error = "Logscan returned an unexpected upload status."
                            payload = None
                finally:
                    poll.close()
            except requests.Timeout:
                last_error = "A Logscan status request timed out."
                payload = None
            except requests.RequestException:
                last_error = "The connection was interrupted while checking Logscan upload status."
                payload = None
            except ValueError as exc:
                if isinstance(exc, UploadError):
                    raise
                last_error = "Logscan returned an unreadable upload status."
                payload = None
            if payload is None:
                failures += 1
                self._update(job_id, phase="checking_status", status_retry_count=failures)
                if failures >= MAX_STATUS_FAILURES:
                    reason = f"{recovery_error} {last_error}" if recovery_error and recovery_error != last_error else last_error
                    raise UploadError(reason + " The upload could not be confirmed. Check Logscan before retrying; the file was not resent.", uncertain=True)
                continue
            failures = 0
            self._update(job_id, phase=payload["phase"], status_retry_count=0)
            if payload["phase"] == "failed":
                raise UploadError("Logscan reported that the uploaded log could not be scanned.")
            if payload["phase"] == "complete":
                return payload.get("result") or {}
        raise UploadError("Logscan has not finished within 15 minutes. Check Logscan before retrying; the file was not resent.", uncertain=True)

    def _run(self, job_id, snapshot, size, filename="qs-default-meta.gz"):
        try:
            with snapshot, requests.Session() as connection:
                body = MultipartLog(snapshot, size, filename)
                recovery_error = None
                accepted_async = False
                try:
                    response = connection.post(
                        PORTAL_URL + "/api/scan",
                        data=body,
                        headers={
                            "Content-Type": f"multipart/form-data; boundary={body.boundary}",
                            "X-Scan-Job-ID": job_id,
                        },
                        timeout=(10, UPLOAD_RESPONSE_TIMEOUT),
                        allow_redirects=False,
                    )
                    try:
                        if response.status_code == 408 or 500 <= response.status_code < 600:
                            recovery_error = f"Logscan's upload response returned HTTP {response.status_code}."
                        elif response.status_code not in (200, 202):
                            raise UploadError(f"Logscan rejected the upload (HTTP {response.status_code}).", uncertain=300 <= response.status_code < 400)
                        else:
                            try:
                                payload = response.json()
                            except ValueError:
                                recovery_error = "Logscan's upload response was unreadable."
                            else:
                                if response.status_code == 202:
                                    if not isinstance(payload, dict) or payload.get("job_id") != job_id:
                                        raise UploadError("Logscan returned an unexpected upload job.", uncertain=True)
                                    self._update(job_id, phase=payload.get("phase", "queued"))
                                    accepted_async = True
                    finally:
                        response.close()
                except requests.ConnectTimeout:
                    raise UploadError("Quickstart could not connect to Logscan within 10 seconds. Nothing was uploaded.") from None
                except requests.Timeout:
                    recovery_error = "Quickstart timed out waiting for Logscan's upload response."
                except requests.RequestException:
                    recovery_error = "Quickstart lost its connection to Logscan during the upload."
                if recovery_error:
                    logging.getLogger(__name__).warning("%s Checking the existing upload job without resending the file.", recovery_error)
                    payload = self._wait_for_remote_job(connection, job_id, recovery_error=recovery_error)
                elif accepted_async:
                    payload = self._wait_for_remote_job(connection, job_id)
                try:
                    links = result_links(payload)
                except UploadError as exc:
                    raise UploadError(str(exc), uncertain=True) from exc
                fingerprint = self.status(job_id).get("content_sha256")
                if fingerprint:
                    self._remember_receipt(fingerprint, payload, self.status(job_id).get("run_key"))
                self._update(job_id, phase="complete", already_uploaded=payload.get("already_uploaded") is True, **links)
        except UploadError as exc:
            self._update(job_id, phase="failed", error=str(exc), uncertain=exc.uncertain)
        except (
            requests.RequestException,
            ValueError,
            TypeError,
            AttributeError,
            OSError,
        ):
            self._update(
                job_id,
                phase="failed",
                error="The upload could not be confirmed. It may have reached Logscan; retrying could create a duplicate.",
                uncertain=True,
            )


portal_uploader = LogscanUploader(receipt_path=lambda: get_logscan_cache_dir() / "upload_receipts.json")
