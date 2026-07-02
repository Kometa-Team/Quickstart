"""Kometa/ImageMaid ZIP-based update primitives extracted from _legacy.py.

Small, composable helpers used by the ``perform_kometa_update_zip_only``,
``perform_kometa_update_zip_only_at_root`` and ``perform_imagemaid_update_zip_only``
flows in ``_legacy.py``. Also consumed directly by ``_kometa_version.py`` for
SHA/branch discovery.
"""

from __future__ import annotations

import datetime
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from pathlib import Path

import requests

from modules.helpers._legacy import CONFIG_DIR

GITHUB_API_BRANCH = "https://api.github.com/repos/kometa-team/Kometa/branches/{branch}"
GITHUB_ZIP_URL = "https://codeload.github.com/kometa-team/Kometa/zip/refs/heads/{branch}"
IMAGEMAID_GITHUB_API_BRANCH = "https://api.github.com/repos/kometa-team/ImageMaid/branches/{branch}"
IMAGEMAID_GITHUB_ZIP_URL = "https://codeload.github.com/kometa-team/ImageMaid/zip/refs/heads/{branch}"


def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _read_text(p: Path):
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _write_text(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _get_upstream_sha(branch: str, logs: list[str], api_url_template: str = GITHUB_API_BRANCH, label: str = "Kometa") -> str | None:
    try:
        url = api_url_template.format(branch=branch)
        if label == "Kometa":
            logs.append(f"🔎 Resolving upstream SHA from: {url}")
        else:
            logs.append(f"🔎 Resolving upstream {label} SHA from: {url}")
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            logs.append(f"❌ GitHub API {r.status_code} for {url}")
            return None
        sha = (r.json().get("commit") or {}).get("sha")
        if sha:
            logs.append(f"🔎 Upstream {branch} SHA: {sha[:12]}")
        else:
            logs.append("❌ Unable to parse upstream SHA.")
        return sha
    except Exception as e:
        logs.append(f"❌ Exception fetching SHA: {e}")
        return None


def _download_zip(branch: str, logs: list[str], zip_url_template: str = GITHUB_ZIP_URL, label: str = "Kometa") -> bytes | None:
    try:
        url = zip_url_template.format(branch=branch)
        if label == "Kometa":
            logs.append(f"📥 Downloading {branch}.zip from: {url}")
        else:
            logs.append(f"📥 Downloading {label} {branch}.zip from: {url}")
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            logs.append(f"❌ ZIP download failed ({r.status_code})")
            return None
        return r.content
    except Exception as e:
        logs.append(f"❌ Exception during ZIP download: {e}")
        return None


def _backup_kometa_runtime_assets(kometa_dir: Path, logs: list[str]) -> Path | None:
    config_dir = kometa_dir / "config"
    if not config_dir.exists():
        return None

    logs_dir = config_dir / "logs"
    cache_files = list(config_dir.glob("*.cache"))
    if not logs_dir.is_dir() and not cache_files:
        return None

    backup_root = Path(CONFIG_DIR) / "kometa-backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"kometa-config-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        if logs_dir.is_dir():
            shutil.copytree(logs_dir, backup_dir / "logs", dirs_exist_ok=True)
        if cache_files:
            cache_dir = backup_dir / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            for cache_file in cache_files:
                shutil.copy2(cache_file, cache_dir / cache_file.name)
        logs.append(f"?? Backed up Kometa logs/cache to {backup_dir}")
        return backup_dir
    except Exception as e:
        logs.append(f"? Failed to back up Kometa logs/cache: {e}")
        return None


def _restore_kometa_runtime_assets(kometa_dir: Path, backup_dir: Path, logs: list[str]) -> bool:
    if not backup_dir or not backup_dir.exists():
        return False

    restored = False
    try:
        config_dir = kometa_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        logs_backup = backup_dir / "logs"
        if logs_backup.is_dir():
            target_logs = config_dir / "logs"
            if target_logs.exists():
                shutil.rmtree(target_logs, ignore_errors=True)
            shutil.copytree(logs_backup, target_logs, dirs_exist_ok=True)
            restored = True

        cache_backup = backup_dir / "cache"
        if cache_backup.is_dir():
            for cache_file in cache_backup.glob("*.cache"):
                shutil.copy2(cache_file, config_dir / cache_file.name)
            restored = True

        if restored:
            logs.append(f"?? Restored Kometa logs/cache from {backup_dir}")
        return restored
    except Exception as e:
        logs.append(f"? Failed to restore Kometa logs/cache: {e}")
        return False


def _cleanup_kometa_backup(backup_dir: Path, logs: list[str]):
    try:
        shutil.rmtree(backup_dir, ignore_errors=True)
    except Exception as e:
        logs.append(f"? Failed to remove Kometa backup: {e}")


def _clear_directory_contents(dest_dir: Path, logs: list[str], label: str = "Kometa") -> bool:
    logs.append(f"🧹 Removing existing {label} contents from: {dest_dir}")
    removed_count = 0
    failed_paths = []

    for child in list(dest_dir.iterdir()):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink()
            else:
                shutil.rmtree(child)
            removed_count += 1
        except Exception as e:
            failed_paths.append((child, e))
            logs.append(f"❌ Failed to remove existing path: {child} ({e})")

    leftovers = list(dest_dir.iterdir())
    if leftovers:
        for leftover in leftovers:
            if all(str(leftover) != str(path) for path, _err in failed_paths):
                logs.append(f"❌ Existing path still present after cleanup: {leftover}")
        logs.append(f"❌ Aborting extraction because the {label} directory is not empty after cleanup.")
        return False

    logs.append(f"🧹 Removed {removed_count} existing entr{'y' if removed_count == 1 else 'ies'}.")
    return True


def _extract_zip_bytes(zip_bytes: bytes, dest_dir: Path, logs: list[str], label: str = "Kometa") -> bool:
    try:
        _ensure_dir(dest_dir)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            root_name = zf.namelist()[0].split("/")[0]  # e.g., Kometa-nightly
            # Use a stable tmp under CONFIG_DIR to avoid /tmp RAM constraints
            tmp_base = Path(CONFIG_DIR) / "tmp"
            if tmp_base.is_dir():
                for entry in tmp_base.iterdir():
                    shutil.rmtree(entry, ignore_errors=True)
            tmp_base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=tmp_base) as td:
                tmp_root = Path(td) / root_name
                zf.extractall(Path(td))
                if not _clear_directory_contents(dest_dir, logs, label=label):
                    return False
                # Copy over
                for item in tmp_root.iterdir():
                    target = dest_dir / item.name
                    if item.is_dir():
                        shutil.copytree(item, target, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, target)
        version_file = dest_dir / "VERSION"
        if version_file.exists():
            version_value = _read_text(version_file)
            if version_value:
                logs.append(f"📦 Extracted VERSION file: {version_value}")
        logs.append(f"📦 Extracted to: {dest_dir}")
        return True
    except Exception as e:
        logs.append(f"❌ Extraction failed: {e}")
        return False


def _ensure_venv(kometa_dir: Path, logs: list[str], venv_name: str = "kometa-venv") -> tuple[Path, Path] | None:
    """
    Create (if missing) and validate a venv at <kometa_dir>/kometa-venv.
    Returns (python_bin, pip_bin) or None on failure.
    """

    is_windows = os.name == "nt"
    venv_dir = kometa_dir / venv_name

    def _venv_ok() -> bool:
        # A valid venv should have pyvenv.cfg and a python binary
        cfg_ok = (venv_dir / "pyvenv.cfg").exists()
        bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
        py = bin_dir / ("python.exe" if is_windows else "python3")
        if not py.exists():
            # allow 'python' as a fallback name on some platforms
            py = bin_dir / ("python.exe" if is_windows else "python")
        return cfg_ok and py.exists()

    # Build command to create venv
    cmd: list[str] | None = None
    if getattr(sys, "frozen", False):
        # Prefer a *real* system Python when running frozen
        if is_windows and shutil.which("py"):
            cmd = ["py", "-3", "-m", "venv", str(venv_dir)]
        else:
            for cand in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):
                if shutil.which(cand):
                    cmd = [cand, "-m", "venv", str(venv_dir)]
                    break
        if cmd is None:
            logs.append("❌ Could not find a system Python 3 (3.10+) to create a virtualenv. " "Please install Python and ensure it is on PATH.")
            return None
    else:
        # Non-frozen: current interpreter is fine
        cmd = [sys.executable, "-m", "venv", str(venv_dir)]

    # Create venv if needed
    if not venv_dir.exists() or not _venv_ok():
        if venv_dir.exists() and not _venv_ok():
            logs.append(f"⚠️ Existing {venv_name} looks invalid; recreating...")
            try:
                shutil.rmtree(venv_dir, ignore_errors=True)
            except Exception as e:
                logs.append(f"❌ Failed to remove invalid venv: {e}")
                return None

        logs.append(f"🐍 Creating virtual environment with: {' '.join(cmd)}")
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(kometa_dir),
            shell=False,
        )
        if p.stdout.strip():
            logs.append(p.stdout.strip())
        if p.returncode != 0:
            logs.append((p.stderr or "").strip() or "venv creation failed")
            return None

        # Some AV tools on Windows can delay file appearance; give it a moment
        for _ in range(10):
            if _venv_ok():
                break
            time.sleep(0.2)

    # Validate venv structure
    if not _venv_ok():
        cfg_present = (venv_dir / "pyvenv.cfg").exists()
        logs.append(f"❌ Invalid venv: pyvenv.cfg present? {cfg_present}; " f"bin/Scripts present? {(venv_dir / ('Scripts' if is_windows else 'bin')).exists()}")
        return None

    bin_dir = venv_dir / ("Scripts" if is_windows else "bin")
    python_bin = bin_dir / ("python.exe" if is_windows else "python3")
    if not python_bin.exists():
        alt = bin_dir / ("python.exe" if is_windows else "python")
        if alt.exists():
            python_bin = alt

    pip_bin = bin_dir / ("pip.exe" if is_windows else "pip")

    # Extra sanity: print interpreter identity
    try:
        p = subprocess.run(
            [str(python_bin), "-c", "import sys; print(sys.executable); import sysconfig; print(sysconfig.get_platform())"], capture_output=True, text=True, shell=False
        )
        diag = (p.stdout or "").strip().replace("\n", " | ")
        if diag:
            logs.append(f"🔎 venv python: {diag}")
    except Exception:
        pass

    # Final guard: ensure pyvenv.cfg really exists, else pip will emit “No pyvenv.cfg file”
    if not (venv_dir / "pyvenv.cfg").exists():
        logs.append("❌ No pyvenv.cfg file after venv creation; aborting.")
        return None

    return python_bin, pip_bin


def _pip_install(python_bin: Path, kometa_dir: Path, logs: list[str], requirements_file: str = "requirements.txt") -> bool:
    is_windows = os.name == "nt"

    logs.append("⬆️ Upgrading pip...")
    p = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True,
        text=True,
        cwd=str(kometa_dir),
        shell=is_windows,
    )
    if p.stdout.strip():
        logs.append(p.stdout.strip())
    if p.returncode != 0:
        logs.append((p.stderr or p.stdout or "").strip() or "pip upgrade failed")
        return False

    logs.append("📦 Installing requirements...")
    p = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--no-cache-dir", "--upgrade", "-r", requirements_file],
        capture_output=True,
        text=True,
        cwd=str(kometa_dir),
        shell=is_windows,
    )
    if p.stdout.strip():
        logs.append(p.stdout.strip())
    if p.returncode != 0:
        logs.append((p.stderr or p.stdout or "").strip() or "requirements install failed")
        return False

    return True


def perform_kometa_update_zip_only(config_root: str | Path, branch: str = "nightly", force: bool = False, logs=None):
    """
    Update Kometa by downloading/extracting the branch ZIP into:
        {config_root}/kometa
    Uses upstream commit SHA to skip when up-to-date unless force is True.
    Works identically for local, PyInstaller, and Docker installs.
    """
    logs = logs if logs is not None else []
    try:
        config_root = Path(config_root).resolve()
        kometa_dir = config_root / "kometa"
        sha_file = kometa_dir / ".kometa_sha"
        branch_file = kometa_dir / ".kometa_branch"

        logs.append(f"⚙️ ZIP updater → branch '{branch}'")
        _ensure_dir(kometa_dir)

        upstream_sha = _get_upstream_sha(branch, logs)
        if not upstream_sha:
            return {"success": False, "log": logs}

        local_sha = _read_text(sha_file)
        if local_sha == upstream_sha and not force:
            logs.append("✅ Up to date (SHA matches). Skipping download.")
            return {"success": True, "log": logs, "up_to_date": True, "skipped": True}
        if force:
            logs.append("Force update requested; proceeding without SHA match check.")

        zip_bytes = _download_zip(branch, logs)
        if not zip_bytes:
            return {"success": False, "log": logs}

        backup_dir = _backup_kometa_runtime_assets(kometa_dir, logs)

        if not _extract_zip_bytes(zip_bytes, kometa_dir, logs):
            if backup_dir:
                restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
                if restored:
                    _cleanup_kometa_backup(backup_dir, logs)
            return {"success": False, "log": logs}

        if backup_dir:
            restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
            if restored:
                _cleanup_kometa_backup(backup_dir, logs)

        res = _ensure_venv(kometa_dir, logs)
        if not res:
            return {"success": False, "log": logs}
        python_bin, _pip_bin_unused = res
        if not _pip_install(python_bin, kometa_dir, logs):
            return {"success": False, "log": logs}

        _write_text(sha_file, upstream_sha)
        _write_text(branch_file, branch)
        logs.append("✅ Kometa updated via ZIP.")
        return {"success": True, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}


def perform_kometa_update_zip_only_at_root(kometa_root: str | Path, branch: str = "nightly", force: bool = False, logs=None):
    """
    Update Kometa by downloading/extracting the branch ZIP into an explicit Kometa root.
    """
    logs = logs if logs is not None else []
    try:
        kometa_dir = Path(kometa_root).resolve()
        sha_file = kometa_dir / ".kometa_sha"
        branch_file = kometa_dir / ".kometa_branch"

        logs.append(f"⚙️ ZIP updater → branch '{branch}'")
        _ensure_dir(kometa_dir)

        upstream_sha = _get_upstream_sha(branch, logs)
        if not upstream_sha:
            return {"success": False, "log": logs}

        local_sha = _read_text(sha_file)
        if local_sha == upstream_sha and not force:
            logs.append("✅ Up to date (SHA matches). Skipping download.")
            return {"success": True, "log": logs, "up_to_date": True, "skipped": True}
        if force:
            logs.append("Force update requested; proceeding without SHA match check.")

        zip_bytes = _download_zip(branch, logs)
        if not zip_bytes:
            return {"success": False, "log": logs}

        backup_dir = _backup_kometa_runtime_assets(kometa_dir, logs)

        if not _extract_zip_bytes(zip_bytes, kometa_dir, logs):
            if backup_dir:
                restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
                if restored:
                    _cleanup_kometa_backup(backup_dir, logs)
            return {"success": False, "log": logs}

        if backup_dir:
            restored = _restore_kometa_runtime_assets(kometa_dir, backup_dir, logs)
            if restored:
                _cleanup_kometa_backup(backup_dir, logs)

        res = _ensure_venv(kometa_dir, logs, venv_name="kometa-venv")
        if not res:
            return {"success": False, "log": logs}
        python_bin, _pip_bin_unused = res
        if not _pip_install(python_bin, kometa_dir, logs):
            return {"success": False, "log": logs}

        _write_text(sha_file, upstream_sha)
        _write_text(branch_file, branch)
        logs.append("✅ Kometa updated via ZIP.")
        return {"success": True, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}


def perform_imagemaid_update_zip_only(config_root: str | Path, branch: str = "develop", force: bool = False, logs=None):
    """
    Update ImageMaid by downloading/extracting the branch ZIP into:
        {config_root}/imagemaid
    Uses upstream commit SHA to skip when up-to-date unless force is True.
    """
    logs = logs if logs is not None else []
    try:
        config_root = Path(config_root).resolve()
        imagemaid_dir = config_root / "imagemaid"
        sha_file = imagemaid_dir / ".imagemaid_sha"
        branch_file = imagemaid_dir / ".imagemaid_branch"

        logs.append(f"⚙️ ZIP updater → ImageMaid branch '{branch}'")
        _ensure_dir(imagemaid_dir)

        upstream_sha = _get_upstream_sha(branch, logs, api_url_template=IMAGEMAID_GITHUB_API_BRANCH, label="ImageMaid")
        if not upstream_sha:
            return {"success": False, "log": logs}

        local_sha = _read_text(sha_file)
        if local_sha == upstream_sha and not force:
            logs.append("✅ ImageMaid is up to date (SHA matches). Skipping download.")
            return {"success": True, "log": logs, "up_to_date": True, "skipped": True}
        if force:
            logs.append("Force update requested; proceeding without SHA match check.")

        zip_bytes = _download_zip(branch, logs, zip_url_template=IMAGEMAID_GITHUB_ZIP_URL, label="ImageMaid")
        if not zip_bytes:
            return {"success": False, "log": logs}

        if not _extract_zip_bytes(zip_bytes, imagemaid_dir, logs, label="ImageMaid"):
            return {"success": False, "log": logs}

        res = _ensure_venv(imagemaid_dir, logs, venv_name="imagemaid-venv")
        if not res:
            return {"success": False, "log": logs}
        python_bin, _pip_bin_unused = res
        if not _pip_install(python_bin, imagemaid_dir, logs):
            return {"success": False, "log": logs}

        _write_text(sha_file, upstream_sha)
        _write_text(branch_file, branch)
        logs.append("✅ ImageMaid updated via ZIP.")
        return {"success": True, "log": logs}

    except Exception as e:
        logs.append(f"❌ Exception: {e}")
        return {"success": False, "log": logs}
