import re
from pathlib import Path

from flask import current_app as app

from modules import helpers


def sanitize_config_name(raw_name: str | None) -> str:
    if not isinstance(raw_name, str):
        return ""
    return re.sub(r"[^a-z0-9_]", "", raw_name.strip().lower())


def normalize_config_filename(config_name: str | None) -> str:
    name = (config_name or "").strip().lower().replace(" ", "_")
    return name or "default"


def rename_config_files(old_name: str, new_name: str, dry_run: bool = False) -> dict:
    result = {"success": False, "renamed": [], "skipped": [], "errors": [], "rollback_errors": []}
    old_norm = normalize_config_filename(old_name)
    new_norm = normalize_config_filename(new_name)
    if old_norm == new_norm:
        result["skipped"].append("Normalized filenames are identical.")
        return result

    config_dir = Path(helpers.CONFIG_DIR)
    kometa_root = Path(app.config.get("KOMETA_ROOT", "."))
    config_file = config_dir / f"{old_norm}_config.yml"
    new_config_file = config_dir / f"{new_norm}_config.yml"
    kometa_file = kometa_root / "config" / f"{old_norm}_config.yml"
    new_kometa_file = kometa_root / "config" / f"{new_norm}_config.yml"

    if new_config_file.exists() or new_kometa_file.exists():
        result["errors"].append("Target config filename already exists.")
        return result

    archive_root = config_dir / "archives"
    old_archive = archive_root / old_norm
    new_archive = archive_root / new_norm
    old_managed_root = helpers.get_managed_config_artifact_root(old_norm)
    new_managed_root = helpers.get_managed_config_artifact_root(new_norm)
    old_managed_dirs = helpers.get_managed_library_artifact_paths(old_norm)
    new_managed_dirs = helpers.get_managed_library_artifact_paths(new_norm)
    old_legacy_managed_dirs = helpers.get_legacy_managed_library_artifact_paths(old_norm)
    new_legacy_managed_dirs = helpers.get_legacy_managed_library_artifact_paths(new_norm)
    if old_archive.exists():
        if new_archive.exists():
            result["errors"].append("Target archive directory already exists.")
            return result
        existing_names = {p.name for p in old_archive.glob("*.yml")}
        for path in old_archive.glob(f"{old_norm}_config_*.yml"):
            target_name = path.name.replace(f"{old_norm}_config_", f"{new_norm}_config_", 1)
            if target_name in existing_names and target_name != path.name:
                result["errors"].append(f"Archive file already exists: {target_name}")
                return result

    if old_managed_root.exists() and new_managed_root.exists():
        result["errors"].append(f"Target managed config directory already exists: {new_managed_root}")
        return result

    for old_managed, new_managed in zip(old_managed_dirs, new_managed_dirs):
        if old_managed.exists() and new_managed.exists():
            result["errors"].append(f"Target managed library directory already exists: {new_managed}")
            return result
    for old_managed, new_managed in zip(old_legacy_managed_dirs, new_managed_dirs):
        if old_managed.exists() and new_managed.exists():
            result["errors"].append(f"Target managed library directory already exists: {new_managed}")
            return result
    for old_managed, new_managed in zip(old_legacy_managed_dirs, new_legacy_managed_dirs):
        if old_managed.exists() and new_managed.exists():
            result["errors"].append(f"Target legacy managed library directory already exists: {new_managed}")
            return result

    if dry_run:
        result["success"] = True
        return result

    completed = []
    try:
        if config_file.exists():
            config_file.rename(new_config_file)
            completed.append((config_file, new_config_file))
            result["renamed"].append(str(new_config_file))
        if kometa_file.exists():
            kometa_file.rename(new_kometa_file)
            completed.append((kometa_file, new_kometa_file))
            result["renamed"].append(str(new_kometa_file))
        if old_managed_root.exists():
            new_managed_root.parent.mkdir(parents=True, exist_ok=True)
            old_managed_root.rename(new_managed_root)
            completed.append((old_managed_root, new_managed_root))
            result["renamed"].append(str(new_managed_root))
        for old_managed, new_managed in zip(old_managed_dirs, new_managed_dirs):
            if old_managed.exists():
                new_managed.parent.mkdir(parents=True, exist_ok=True)
                old_managed.rename(new_managed)
                completed.append((old_managed, new_managed))
                result["renamed"].append(str(new_managed))
        for old_managed, new_managed in zip(old_legacy_managed_dirs, new_managed_dirs):
            if old_managed.exists():
                new_managed.parent.mkdir(parents=True, exist_ok=True)
                old_managed.rename(new_managed)
                completed.append((old_managed, new_managed))
                result["renamed"].append(str(new_managed))

        if old_archive.exists():
            old_archive.rename(new_archive)
            completed.append((old_archive, new_archive))
            result["renamed"].append(str(new_archive))
            file_ops = []
            for path in new_archive.glob(f"{old_norm}_config_*.yml"):
                new_path = new_archive / path.name.replace(f"{old_norm}_config_", f"{new_norm}_config_", 1)
                if new_path.exists() and new_path != path:
                    raise FileExistsError(f"Archive file already exists: {new_path.name}")
                file_ops.append((path, new_path))
            for src, dst in file_ops:
                src.rename(dst)
                completed.append((src, dst))
                result["renamed"].append(str(dst))
    except Exception as exc:
        result["errors"].append(f"Rename failed: {exc}")
        for src, dst in reversed(completed):
            try:
                if Path(dst).exists():
                    Path(dst).rename(src)
            except Exception as rollback_exc:
                result["rollback_errors"].append(str(rollback_exc))
        return result

    result["success"] = True
    return result
