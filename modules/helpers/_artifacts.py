"""Config artifact management utilities extracted from _legacy.py."""

import datetime
import re
import shutil

from pathlib import Path

from modules.helpers._legacy import CONFIG_DIR

MANAGED_LIBRARY_FILE_DIRS = ("metadata_files", "collection_files", "overlay_files")
MANAGED_OVERLAY_IMAGE_DIR = "overlay_images"
MANAGED_SYNC_ARTIFACT_DIRS = MANAGED_LIBRARY_FILE_DIRS + (MANAGED_OVERLAY_IMAGE_DIR,)
MANAGED_CONFIG_ARTIFACT_DIRS = ("fonts",) + MANAGED_SYNC_ARTIFACT_DIRS
RESERVED_RUNTIME_BUNDLE_NAMES = frozenset({"kometa", "imagemaid"})


def migrate_config_archives(history_limit: int | None = None) -> dict:
    """Move legacy *_config*.yml into config/archives/<name>/ and optionally prune."""
    config_dir = Path(CONFIG_DIR)
    archive_root = config_dir / "archives"
    archive_pattern = re.compile(r"^(?P<name>.+)_config_(?P<suffix>\d+)\.yml$", re.IGNORECASE)
    current_pattern = re.compile(r"^(?P<name>.+)_config\.yml$", re.IGNORECASE)

    moved = 0
    errors: list[str] = []

    if history_limit is None:
        history_limit = 0
    try:
        history_limit = int(str(history_limit).strip())
    except (TypeError, ValueError):
        history_limit = 0
    if history_limit < 0:
        history_limit = 0

    def move_config(path: Path, name: str) -> None:
        nonlocal moved
        dest_dir = archive_root / name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / path.name
        counter = 1
        while dest_path.exists():
            dest_path = dest_dir / f"{path.stem}_moved{counter}{path.suffix}"
            counter += 1
        try:
            shutil.move(str(path), str(dest_path))
            moved += 1
        except Exception as exc:
            errors.append(f"Failed to move {path} -> {dest_path}: {exc}")

    for path in config_dir.glob("*_config_*.yml"):
        if not path.is_file():
            continue
        match = archive_pattern.match(path.name)
        if not match:
            continue
        move_config(path, match.group("name"))

    for path in config_dir.glob("*_config.yml"):
        if not path.is_file():
            continue
        match = current_pattern.match(path.name)
        if not match:
            continue
        move_config(path, match.group("name"))

    if history_limit > 0 and archive_root.exists():
        for dest_dir in archive_root.iterdir():
            if not dest_dir.is_dir():
                continue
            archives = sorted(dest_dir.glob("*.yml"), key=lambda p: p.stat().st_mtime)
            if len(archives) > history_limit:
                for old_path in archives[: len(archives) - history_limit]:
                    try:
                        old_path.unlink()
                    except Exception as exc:
                        errors.append(f"Failed to prune {old_path}: {exc}")

    return {"moved": moved, "errors": errors, "history_limit": history_limit}


def normalize_config_name_for_storage(config_name: str | None) -> str:
    raw = str(config_name or "").strip()
    if not raw:
        return "default"

    name = Path(raw.replace("\\", "/")).name.strip().lower()
    if name.endswith("_config.yml"):
        name = name[:-11]
    elif name.endswith("_config.yaml"):
        name = name[:-12]
    elif name.endswith(".yml"):
        name = name[:-4]
    elif name.endswith(".yaml"):
        name = name[:-5]

    name = name.replace(" ", "_")
    return name or "default"


def require_config_name_for_storage(config_name: str | None, context: str = "Artifact operation") -> str:
    raw = str(config_name or "").strip()
    if not raw:
        raise ValueError(f"{context} requires an explicit config name.")
    normalized = normalize_config_name_for_storage(raw)
    if not normalized:
        raise ValueError(f"{context} requires an explicit config name.")
    return normalized


def is_reserved_runtime_bundle_name(config_name: str | None) -> bool:
    return normalize_config_name_for_storage(config_name) in RESERVED_RUNTIME_BUNDLE_NAMES


def get_managed_config_artifact_root(config_name: str | None) -> Path:
    normalized = require_config_name_for_storage(config_name, context="Managed config artifact paths")
    return Path(CONFIG_DIR) / normalized


def get_managed_library_artifact_paths(config_name: str | None) -> list[Path]:
    config_root = get_managed_config_artifact_root(config_name)
    return [config_root / folder for folder in MANAGED_LIBRARY_FILE_DIRS]


def get_legacy_managed_library_artifact_paths(config_name: str | None) -> list[Path]:
    normalized = require_config_name_for_storage(config_name, context="Legacy managed library artifact paths")
    config_dir = Path(CONFIG_DIR)
    return [config_dir / folder / normalized for folder in MANAGED_LIBRARY_FILE_DIRS]


def sync_managed_library_artifacts_to_kometa(
    config_name: str | None,
    kometa_root: str | Path | None = None,
    kometa_config_dir: str | Path | None = None,
) -> dict:
    from modules.helpers._file_utils import _directory_tree_signature
    from modules.helpers._kometa_paths import get_kometa_config_dir
    from modules.helpers._pid import handle_remove_readonly

    normalized = require_config_name_for_storage(config_name, context="Managed library artifact sync")
    source_root = get_managed_config_artifact_root(normalized)
    if kometa_config_dir is not None:
        destination_base = Path(kometa_config_dir)
    elif kometa_root is not None:
        destination_base = Path(kometa_root) / "config"
    else:
        destination_base = get_kometa_config_dir()
    destination_root = destination_base / normalized

    synced: list[str] = []
    removed: list[str] = []
    missing: list[str] = []
    errors: list[str] = []

    for folder in MANAGED_SYNC_ARTIFACT_DIRS:
        source_dir = source_root / folder
        destination_dir = destination_root / folder

        if source_dir.exists():
            try:
                source_resolved = source_dir.resolve()
                destination_resolved = destination_dir.resolve()
                if source_resolved == destination_resolved:
                    synced.append(str(destination_dir))
                    continue
            except Exception:
                pass

            try:
                if destination_dir.exists() and _directory_tree_signature(source_dir) == _directory_tree_signature(destination_dir):
                    synced.append(str(destination_dir))
                    continue
                destination_dir.parent.mkdir(parents=True, exist_ok=True)
                if destination_dir.exists():
                    shutil.rmtree(destination_dir, onerror=handle_remove_readonly)
                shutil.copytree(source_dir, destination_dir)
                synced.append(str(destination_dir))
            except Exception as exc:
                errors.append(f"Failed to sync {source_dir} -> {destination_dir}: {exc}")
            continue

        missing.append(folder)
        if not destination_dir.exists():
            continue
        try:
            shutil.rmtree(destination_dir, onerror=handle_remove_readonly)
            removed.append(str(destination_dir))
        except Exception as exc:
            errors.append(f"Failed to remove stale Kometa artifact directory {destination_dir}: {exc}")

    if destination_root.exists():
        try:
            if not any(destination_root.iterdir()):
                destination_root.rmdir()
        except Exception:
            pass

    return {"synced": synced, "removed": removed, "missing": missing, "errors": errors}


def delete_config_artifacts(
    config_name: str | None,
    kometa_root: str | Path | None = None,
    kometa_config_dir: str | Path | None = None,
) -> dict:
    from modules.helpers._kometa_paths import get_kometa_config_dir

    normalized = require_config_name_for_storage(config_name, context="Config artifact cleanup")
    if is_reserved_runtime_bundle_name(normalized):
        return {
            "removed": [],
            "errors": [f"Refusing to remove reserved runtime bundle: {normalized}"],
            "config_name": normalized,
        }
    config_dir = Path(CONFIG_DIR)
    archive_root = config_dir / "archives"
    removed: list[str] = []
    errors: list[str] = []

    targets = [
        config_dir / f"{normalized}_config.yml",
        archive_root / normalized,
        get_managed_config_artifact_root(normalized),
    ]
    targets.extend(get_managed_library_artifact_paths(normalized))
    targets.extend(get_legacy_managed_library_artifact_paths(normalized))

    if kometa_config_dir is not None:
        targets.append(Path(kometa_config_dir) / f"{normalized}_config.yml")
    elif kometa_root:
        targets.append(Path(kometa_root) / "config" / f"{normalized}_config.yml")
    else:
        targets.append(get_kometa_config_dir() / f"{normalized}_config.yml")

    for target in targets:
        try:
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(str(target))
        except Exception as exc:
            errors.append(f"Failed to remove {target}: {exc}")

    return {"removed": removed, "errors": errors, "config_name": normalized}


def delete_orphaned_artifact_bundle(bundle: dict | None) -> dict:
    bundle = bundle if isinstance(bundle, dict) else {}
    bundle_name = normalize_config_name_for_storage(bundle.get("name"))
    if is_reserved_runtime_bundle_name(bundle_name):
        return {
            "removed": [],
            "errors": [f"Refusing to remove reserved runtime bundle: {bundle_name}"],
            "config_name": bundle_name,
        }
    removed: list[str] = []
    errors: list[str] = []
    raw_paths = bundle.get("paths")
    candidate_paths = []

    if isinstance(raw_paths, list):
        for raw_path in raw_paths:
            text = str(raw_path or "").strip()
            if text:
                candidate_paths.append(text)

    seen: set[str] = set()
    for raw_path in candidate_paths:
        try:
            target = Path(raw_path).resolve()
        except Exception as exc:
            errors.append(f"Failed to resolve {raw_path}: {exc}")
            continue
        target_key = str(target)
        if target_key in seen:
            continue
        seen.add(target_key)
        try:
            if not target.exists():
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            removed.append(target_key)
        except Exception as exc:
            errors.append(f"Failed to remove {target}: {exc}")

    if not removed and not errors:
        errors.append(f"No filesystem artifacts were removed for {bundle_name}.")

    return {"removed": removed, "errors": errors, "config_name": bundle_name}


def list_orphaned_config_artifacts(
    active_config_names: list[str] | None = None,
    kometa_root: str | Path | None = None,
    kometa_config_dir: str | Path | None = None,
) -> dict:
    from modules.helpers._kometa_paths import get_kometa_config_dir

    config_dir = Path(CONFIG_DIR)
    archive_root = config_dir / "archives"
    current_pattern = re.compile(r"^(?P<name>.+)_config\.yml$", re.IGNORECASE)

    if active_config_names is None:
        try:
            from modules import database

            active_config_names = database.get_unique_config_names() or []
        except Exception as exc:
            return {
                "orphans": [],
                "errors": [f"Failed to load active config names: {exc}"],
            }

    active_names = {normalize_config_name_for_storage(name) for name in active_config_names if str(name or "").strip()}
    bundles: dict[str, dict] = {}

    def ensure_bundle(name: str) -> dict:
        normalized = normalize_config_name_for_storage(name)
        bundle = bundles.get(normalized)
        if bundle is None:
            bundle = {
                "name": normalized,
                "has_current_file": False,
                "has_kometa_copy": False,
                "has_archive_dir": False,
                "archive_count": 0,
                "paths": [],
            }
            bundles[normalized] = bundle
        return bundle

    for path in config_dir.iterdir():
        if not path.is_file() or not path.name.lower().endswith("_config.yml"):
            continue
        match = current_pattern.match(path.name)
        if not match:
            continue
        if is_reserved_runtime_bundle_name(match.group("name")):
            continue
        bundle = ensure_bundle(match.group("name"))
        bundle["has_current_file"] = True
        bundle["paths"].append(str(path))

    for path in config_dir.iterdir():
        if not path.is_dir():
            continue
        if is_reserved_runtime_bundle_name(path.name):
            continue
        if any((path / folder_name).exists() and (path / folder_name).is_dir() for folder_name in MANAGED_CONFIG_ARTIFACT_DIRS):
            bundle = ensure_bundle(path.name)
            path_text = str(path)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

    for folder_name in MANAGED_LIBRARY_FILE_DIRS:
        managed_root = config_dir / folder_name
        if not managed_root.exists() or not managed_root.is_dir():
            continue
        for path in managed_root.iterdir():
            if not path.is_dir():
                continue
            if is_reserved_runtime_bundle_name(path.name):
                continue
            bundle = ensure_bundle(path.name)
            path_text = str(path)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

    if archive_root.exists():
        for path in archive_root.iterdir():
            if not path.is_dir():
                continue
            if is_reserved_runtime_bundle_name(path.name):
                continue
            bundle = ensure_bundle(path.name)
            bundle["has_archive_dir"] = True
            bundle["archive_count"] = sum(1 for child in path.glob("*.yml") if child.is_file())
            bundle["paths"].append(str(path))

    active_kometa_config_dir = None
    if kometa_config_dir is not None:
        active_kometa_config_dir = Path(kometa_config_dir)
    elif kometa_root:
        active_kometa_config_dir = Path(kometa_root) / "config"
    else:
        active_kometa_config_dir = get_kometa_config_dir()

    if active_kometa_config_dir and active_kometa_config_dir.exists():
        for path in active_kometa_config_dir.iterdir():
            if not path.is_file() or not path.name.lower().endswith("_config.yml"):
                continue
            match = current_pattern.match(path.name)
            if not match:
                continue
            if is_reserved_runtime_bundle_name(match.group("name")):
                continue
            bundle = ensure_bundle(match.group("name"))
            bundle["has_kometa_copy"] = True
            bundle["paths"].append(str(path))

    for bundle in bundles.values():
        name = bundle.get("name")
        if not name:
            continue
        if is_reserved_runtime_bundle_name(name):
            continue
        current_file = config_dir / f"{name}_config.yml"
        if current_file.exists() and current_file.is_file():
            bundle["has_current_file"] = True
            path_text = str(current_file)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

        archive_dir = archive_root / name
        if archive_dir.exists() and archive_dir.is_dir():
            bundle["has_archive_dir"] = True
            bundle["archive_count"] = sum(1 for child in archive_dir.glob("*.yml") if child.is_file())
            path_text = str(archive_dir)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)

        if active_kometa_config_dir is not None:
            kometa_file = active_kometa_config_dir / f"{name}_config.yml"
            if kometa_file.exists() and kometa_file.is_file():
                bundle["has_kometa_copy"] = True
                path_text = str(kometa_file)
                if path_text not in bundle["paths"]:
                    bundle["paths"].append(path_text)

        for managed_path in get_managed_library_artifact_paths(name):
            if managed_path.exists() and managed_path.is_dir():
                path_text = str(managed_path)
                if path_text not in bundle["paths"]:
                    bundle["paths"].append(path_text)
        managed_root = get_managed_config_artifact_root(name)
        if managed_root.exists() and managed_root.is_dir():
            path_text = str(managed_root)
            if path_text not in bundle["paths"]:
                bundle["paths"].append(path_text)
        for legacy_path in get_legacy_managed_library_artifact_paths(name):
            if legacy_path.exists() and legacy_path.is_dir():
                path_text = str(legacy_path)
                if path_text not in bundle["paths"]:
                    bundle["paths"].append(path_text)

    orphans = [bundle for name, bundle in sorted(bundles.items()) if name not in active_names and not is_reserved_runtime_bundle_name(name)]
    return {"orphans": orphans, "errors": [], "active_names": sorted(active_names)}


def list_orphaned_config_versions(config_name: str | None) -> dict:
    normalized = normalize_config_name_for_storage(config_name)
    config_dir = Path(CONFIG_DIR)
    archive_dir = config_dir / "archives" / normalized
    versions: list[dict] = []

    def add_version(path: Path, kind: str) -> None:
        try:
            stats = path.stat()
        except Exception:
            return
        versions.append(
            {
                "name": normalized,
                "path": str(path.resolve()),
                "kind": kind,
                "filename": path.name,
                "mtime": stats.st_mtime,
                "modified_at": datetime.datetime.fromtimestamp(stats.st_mtime, datetime.UTC).isoformat().replace("+00:00", "Z"),
                "size": stats.st_size,
            }
        )

    current_file = config_dir / f"{normalized}_config.yml"
    if current_file.exists() and current_file.is_file():
        add_version(current_file, "current")

    if archive_dir.exists() and archive_dir.is_dir():
        for path in archive_dir.glob("*.yml"):
            if path.is_file():
                add_version(path, "archive")

    versions.sort(
        key=lambda item: (
            item.get("mtime") or 0,
            1 if item.get("kind") == "current" else 0,
        ),
        reverse=True,
    )
    return {"name": normalized, "versions": versions}


def prune_unrecoverable_orphaned_config_artifacts(
    active_config_names: list[str] | None = None,
    kometa_root: str | Path | None = None,
    kometa_config_dir: str | Path | None = None,
) -> dict:
    inventory = list_orphaned_config_artifacts(
        active_config_names=active_config_names,
        kometa_root=kometa_root,
        kometa_config_dir=kometa_config_dir,
    )
    if inventory.get("errors"):
        return {
            "removed": [],
            "skipped": [],
            "errors": list(inventory.get("errors", [])),
        }

    removed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for bundle in inventory.get("orphans", []):
        if not isinstance(bundle, dict):
            continue
        name = normalize_config_name_for_storage(bundle.get("name"))
        if not name:
            continue
        result = delete_orphaned_artifact_bundle(bundle)
        if result.get("errors"):
            errors.extend(result["errors"])
            continue
        removed.append(name)

    return {"removed": removed, "skipped": skipped, "errors": errors}


def prune_orphaned_config_archives(
    active_config_names: list[str] | None = None,
) -> dict:
    archive_root = Path(CONFIG_DIR) / "archives"
    removed: list[str] = []
    errors: list[str] = []

    if active_config_names is None:
        try:
            from modules import database

            active_config_names = database.get_unique_config_names() or []
        except Exception as exc:
            return {
                "removed": [],
                "errors": [f"Failed to load active config names: {exc}"],
            }

    active_names = {normalize_config_name_for_storage(name) for name in active_config_names if str(name or "").strip()}
    if not archive_root.exists():
        return {"removed": [], "errors": []}

    for path in archive_root.iterdir():
        if not path.is_dir():
            continue
        normalized = normalize_config_name_for_storage(path.name)
        should_remove = normalized not in active_names
        if not should_remove:
            try:
                should_remove = not any(path.iterdir())
            except Exception as exc:
                errors.append(f"Failed to inspect archive directory {path}: {exc}")
                continue
        if not should_remove:
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except Exception as exc:
            errors.append(f"Failed to remove archive directory {path}: {exc}")

    return {"removed": removed, "errors": errors}
