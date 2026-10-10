"""Nonblocking integrity diagnostics for Quickstart-managed Kometa installs."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

MANIFEST_NAME = ".kometa_integrity.json"
COMMENT_START = "# [Quickstart] Kometa integrity begin"
COMMENT_END = "# [Quickstart] Kometa integrity end"
_IGNORED_ROOTS = {"config", "kometa-venv", ".git"}
_METADATA = {MANIFEST_NAME, ".kometa_sha", ".kometa_branch"}


def _digest_stream(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(128 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError("Invalid integrity file path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("Invalid integrity file path")
    return path


def _ignored(path):
    parts = path.parts
    return (
        parts[0].lower() in _IGNORED_ROOTS
        or "__pycache__" in parts
        or path.suffix.lower() in {".pyc", ".pyo"}
        or (len(parts) == 1 and (parts[0] in _METADATA or parts[0].startswith(".kometa_integrity-")))
    )


def manifest_from_zip(zip_bytes, commit, branch):
    if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
        raise ValueError("A resolved GitHub commit is required for the integrity baseline")
    files = {}
    roots = set()
    seen = set()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for entry in archive.infolist():
            # ZipInfo normalizes separators on Windows; validate the original name.
            member = _safe_relative_path(entry.orig_filename.rstrip("/"))
            roots.add(member.parts[0])
            if len(roots) != 1 or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Unsupported Kometa archive layout")
            if entry.is_dir():
                continue
            if len(member.parts) < 2:
                raise ValueError("Unsupported Kometa archive layout")
            relative = PurePosixPath(*member.parts[1:])
            key = relative.as_posix()
            if key.casefold() in seen:
                raise ValueError("Duplicate Kometa archive file")
            seen.add(key.casefold())
            if not _ignored(relative):
                with archive.open(entry) as stream:
                    files[key] = _digest_stream(stream)
    if not {"kometa.py", "requirements.txt", "VERSION"}.issubset(files):
        raise ValueError("Kometa archive is missing required files")
    return {"schema_version": 1, "commit": commit, "branch": branch, "files": dict(sorted(files.items()))}


def write_manifest(root, manifest):
    root = Path(root)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".kometa_integrity-", suffix=".tmp", dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, root / MANIFEST_NAME)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def _report(state, detail=""):
    return {
        "state": state,
        "detail": detail,
        "commit": "",
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "modified": [],
        "missing": [],
        "added": [],
        "errors": [],
    }


def check_integrity(root, install_mode="managed"):
    if install_mode != "managed":
        return _report("not_applicable", "Integrity checking is limited to Quickstart-managed Kometa installs.")
    report = _report("not_verified", "No pristine baseline. Use Force update to establish one while preserving config/.")
    try:
        root = Path(root)
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.exists():
            return report
        if manifest_path.is_symlink():
            raise ValueError("Integrity manifest must not be a symbolic link")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("commit", ""))):
            raise ValueError("Invalid integrity manifest")
        files = manifest.get("files")
        if not isinstance(files, dict) or not {"kometa.py", "requirements.txt", "VERSION"}.issubset(files):
            raise ValueError("Invalid integrity manifest files")
        for key, digest in files.items():
            if _ignored(_safe_relative_path(key)) or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Invalid integrity manifest entry")
        report["commit"] = manifest["commit"]
        sha_path = root / ".kometa_sha"
        if sha_path.is_symlink() or sha_path.read_text(encoding="utf-8").strip() != manifest["commit"]:
            raise ValueError("Installed commit does not match the integrity baseline")

        for key, digest in files.items():
            relative = PurePosixPath(key)
            target = root.joinpath(*relative.parts)
            if any(root.joinpath(*relative.parts[:index]).is_symlink() for index in range(1, len(relative.parts) + 1)):
                report["modified"].append(key)
            elif not target.exists():
                report["missing"].append(key)
            elif not target.is_file():
                report["modified"].append(key)
            else:
                try:
                    with target.open("rb") as stream:
                        if _digest_stream(stream) != digest:
                            report["modified"].append(key)
                except OSError:
                    report["errors"].append(f"Unable to read {key}")

        def walk_error(_error):
            report["errors"].append("Unable to inspect an installation directory")

        for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
            base = Path(directory).relative_to(root)
            for name in dirs[:]:
                relative = PurePosixPath(*(base / name).parts)
                if _ignored(relative):
                    dirs.remove(name)
                elif (Path(directory) / name).is_symlink():
                    dirs.remove(name)
                    if relative.as_posix() not in files:
                        report["added"].append(relative.as_posix())
            for name in names:
                relative = PurePosixPath(*(base / name).parts)
                if not _ignored(relative) and relative.as_posix() not in files:
                    report["added"].append(relative.as_posix())
        for category in ("modified", "missing", "added", "errors"):
            report[category] = sorted(set(report[category]))
        report["state"] = "check_failed" if report["errors"] else ("modified" if any(report[key] for key in ("modified", "missing", "added")) else "clean")
        report["detail"] = ""
    except (OSError, ValueError, TypeError):
        report.update(state="check_failed", detail="Unable to verify the pristine baseline or installed files. Use Force update to restore managed Kometa.")
    return report


def current_integrity(root=None, install_mode=None):
    from modules import helpers

    try:
        mode = install_mode or helpers.get_kometa_install_mode()
        if mode != "managed":
            return check_integrity(None, mode)
        return check_integrity(root if root is not None else helpers.get_kometa_root_path(), mode)
    except (OSError, ValueError, TypeError):
        return _report("check_failed", "Unable to resolve the managed Kometa installation.")


def format_integrity(report, limit=20):
    state = report["state"].replace("_", " ").upper()
    lines = [f"Kometa Integrity: {state}", f"Checked At: {report['checked_at']}"]
    if report["commit"]:
        lines.insert(1, f"Installed Commit: {report['commit']}")
    if report["state"] in {"clean", "modified", "check_failed"}:
        lines.append("Changes: " + ", ".join(f"{len(report[key])} {key}" for key in ("modified", "missing", "added")))
    for category in ("modified", "missing", "added", "errors"):
        for value in report[category][:limit]:
            # Filenames may contain control characters; keep every diagnostic on one line.
            lines.append(f"{category.title()}: {json.dumps(value, ensure_ascii=True)[1:-1]}")
        if len(report[category]) > limit:
            lines.append(f"{category.title()}: {len(report[category]) - limit} more")
    if report["detail"]:
        lines.append(report["detail"])
    if report["state"] == "modified":
        lines.extend(
            [
                "WARNING: Installed Kometa files differ from the upstream baseline. Runs are not blocked.",
                "Use Force update to restore vanilla Kometa; the entire runtime config/ directory is preserved.",
            ]
        )
    return lines


def integrity_comments(report):
    return "\n".join([COMMENT_START, *(f"# {line}" for line in format_integrity(report)), COMMENT_END])


def stamp_integrity_comments(config_path, report):
    if not config_path or not Path(config_path).is_file():
        return False
    try:
        path = Path(config_path)
        with path.open("r", encoding="utf-8", newline="") as stream:
            content = stream.read()
        newline = "\r\n" if "\r\n" in content else "\n"
        pattern = rf"(?m)^{re.escape(COMMENT_START)}\r?\n(?:^#[^\r\n]*\r?\n)*?^{re.escape(COMMENT_END)}\r?\n?"
        content = re.sub(pattern, "", content)
        lines = content.splitlines()
        index = 1 if lines and lines[0].startswith("# yaml-language-server:") else 0
        lines[index:index] = integrity_comments(report).splitlines()
        with path.open("w", encoding="utf-8", newline="") as stream:
            stream.write(newline.join(lines) + newline)
        return True
    except (OSError, UnicodeError):
        return False
