"""Path and filesystem safety utilities extracted from helpers.py."""

from __future__ import annotations

import os
from pathlib import Path


def utc_now_iso():
    """Return current UTC time as ISO 8601 string."""
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def safe_rel_path(raw_path: str | None, allow_subdirs: bool = False) -> str | None:
    """Sanitize a user-supplied relative path. Returns None if path is unsafe."""
    if not raw_path or not isinstance(raw_path, str):
        return None
    stripped = raw_path.strip()
    if not stripped or stripped.startswith(("/", "\\")):
        return None
    if ".." in stripped.split(os.sep) or ".." in stripped.split("/"):
        return None
    if not allow_subdirs and ("/" in stripped or "\\" in stripped):
        return None
    return stripped


def safe_join(base_dir: str | Path, raw_path: str | None, allow_subdirs: bool = False) -> Path | None:
    """Join a sanitized path to base_dir safely. Returns None if unsafe."""
    if raw_path is None:
        return None
    safe = safe_rel_path(raw_path, allow_subdirs=allow_subdirs)
    if safe is None:
        return None
    resolved = (Path(base_dir) / safe).resolve()
    base_resolved = Path(base_dir).resolve()
    if not str(resolved).startswith(str(base_resolved)):
        return None
    return resolved


def resolve_user_dir(raw_path: str | None) -> Path | None:
    """Resolve a user-supplied path, expanding ~ and env vars."""
    if not raw_path or not raw_path.strip():
        return None
    expanded = os.path.expandvars(os.path.expanduser(raw_path.strip()))
    p = Path(expanded).resolve()
    if not p.exists():
        return None
    return p


def is_logscan_gzip_path(path):
    """Check if a logscan path is a gzip file."""
    return bool(path and str(path).endswith(".gz"))


def _read_optional_text(path, encoding="utf-8", errors="replace"):
    try:
        candidate = Path(path)
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding=encoding, errors=errors).strip()
    except Exception:
        pass
    return ""


def read_logscan_text(path, encoding="utf-8", errors="replace"):
    """Read text from a logscan file, handling gzip and Quickstart marker journals."""
    import gzip

    path = Path(path)
    if is_logscan_gzip_path(path):
        with gzip.open(path, "rt", encoding=encoding, errors=errors) as handle:
            return handle.read()
    content = path.read_text(encoding=encoding, errors=errors)
    try:
        if path.name.lower() == "meta.log":
            from modules import helpers
            from modules.process_markers import flush_quickstart_pending_markers

            kometa_root = path.parent.parent.parent
            if not helpers.is_kometa_running():
                flush_quickstart_pending_markers(kometa_root, require_process_stopped=True)
                content = path.read_text(encoding=encoding, errors=errors)
            aux_content = []
            for aux_path in (
                path.parent / "meta.quickstart-pending.log",
                path.parent / "meta.quickstart-maintenance.log",
            ):
                text = _read_optional_text(aux_path, encoding=encoding, errors=errors)
                if text:
                    aux_content.append(text)
            if aux_content:
                content = f"{content.rstrip()}\n" + "\n".join(aux_content) + "\n"
        elif path.suffix.lower() == ".log" and path.name.lower().startswith("imagemaid"):
            from modules import helpers
            from modules.process_markers import flush_imagemaid_pending_markers

            imagemaid_root = path.parent.parent.parent
            if not helpers.is_imagemaid_running():
                flush_imagemaid_pending_markers(imagemaid_root, log_path=path, require_process_stopped=True)
                content = path.read_text(encoding=encoding, errors=errors)
            aux_content = []
            for aux_path in (
                path.parent / "imagemaid.quickstart-pending.log",
                path.parent / "imagemaid.quickstart-maintenance.log",
            ):
                text = _read_optional_text(aux_path, encoding=encoding, errors=errors)
                if text:
                    aux_content.append(text)
            if aux_content:
                content = f"{content.rstrip()}\n" + "\n".join(aux_content) + "\n"
    except Exception:
        pass
    return content
