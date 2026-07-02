"""Persist a generated YAML config under a named identity.

Extracted from _legacy.py. Handles:

- Archiving previous versions (with optional history-limit pruning)
- Writing to both the Quickstart-owned config dir and the Kometa-owned one
- Copying referenced fonts and syncing managed library artifacts
- Idempotency: skips writes when the YAML is unchanged
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app as app

from modules.helpers._kometa_paths import get_kometa_config_dir, get_kometa_root_path
from modules.helpers._legacy import CONFIG_DIR
from modules.helpers._logging import ts_log


def save_to_named_config(yaml_text, config_name, font_refs=None):
    from modules import helpers as _h
    from modules.helpers._file_utils import _read_text_if_exists

    config_dir = Path(CONFIG_DIR)
    kometa_root = get_kometa_root_path()
    kometa_config_dir = get_kometa_config_dir()

    name = _h.require_config_name_for_storage(config_name, context="Saving a named config")
    latest_filename = f"{name}_config.yml"
    latest_path = config_dir / latest_filename
    kometa_path = kometa_config_dir / latest_filename
    history_limit = app.config.get("QS_CONFIG_HISTORY", 0)
    try:
        history_limit = int(str(history_limit).strip())
    except (TypeError, ValueError):
        history_limit = 0
    if history_limit < 0:
        history_limit = 0

    existing_local_yaml = _read_text_if_exists(latest_path)
    local_needs_write = existing_local_yaml != yaml_text

    config_dir.mkdir(parents=True, exist_ok=True)
    kometa_write_ok = True
    try:
        kometa_config_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        kometa_write_ok = False
        ts_log(f"Failed to create Kometa config directory {kometa_config_dir}: {exc}", level="WARNING")

    if kometa_write_ok:
        existing_kometa_yaml = _read_text_if_exists(kometa_path)
        kometa_needs_write = existing_kometa_yaml != yaml_text
    else:
        kometa_needs_write = False

    # Only rotate config history when the generated YAML actually changed.
    if local_needs_write and latest_path.exists():
        archive_dir = config_dir / "archives" / name
        archive_dir.mkdir(parents=True, exist_ok=True)
        counter = 1
        while True:
            archive_path = archive_dir / f"{name}_config_{counter}.yml"
            if not archive_path.exists():
                latest_path.rename(archive_path)
                ts_log(f"Archived old config to: {archive_path}")
                break
            counter += 1
        if history_limit > 0:
            archives = sorted(archive_dir.glob(f"{name}_config_*.yml"), key=lambda p: p.stat().st_mtime)
            if len(archives) > history_limit:
                for old_path in archives[: len(archives) - history_limit]:
                    try:
                        old_path.unlink()
                    except Exception as exc:
                        ts_log(f"Failed to prune archive {old_path}: {exc}", level="WARNING")

    if local_needs_write:
        try:
            with open(latest_path, "w", encoding="utf-8") as f:
                f.write(yaml_text)
        except OSError as exc:
            ts_log(f"Failed to write Quickstart config to {latest_path}: {exc}", level="WARNING")
            raise

    if kometa_write_ok and kometa_needs_write:
        try:
            with open(kometa_path, "w", encoding="utf-8") as f:
                f.write(yaml_text)
        except OSError as exc:
            kometa_write_ok = False
            ts_log(f"Failed to write Kometa config to {kometa_path}: {exc}", level="WARNING")

    if font_refs and kometa_write_ok:
        try:
            font_result = _h.copy_fonts_to_kometa(font_refs, kometa_root=kometa_root, kometa_config_dir=kometa_config_dir, config_name=name)
            missing = font_result.get("missing", [])
            errors = font_result.get("errors", [])
            if missing:
                ts_log(f"Missing fonts not copied to Kometa: {', '.join(missing)}", level="WARNING")
            for err in errors:
                ts_log(err, level="WARNING")
        except Exception as exc:
            ts_log(f"Failed to sync fonts to Kometa: {exc}", level="WARNING")

    if kometa_write_ok:
        try:
            artifact_result = _h.sync_managed_library_artifacts_to_kometa(name, kometa_root=kometa_root, kometa_config_dir=kometa_config_dir)
            synced = artifact_result.get("synced", [])
            removed = artifact_result.get("removed", [])
            errors = artifact_result.get("errors", [])
            if synced:
                ts_log(f"Synced {len(synced)} managed library artifact tree(s) to Kometa target/{name}.")
            if removed:
                ts_log(f"Removed {len(removed)} stale managed library artifact tree(s) from Kometa target/{name}.")
            for err in errors:
                ts_log(err, level="WARNING")
        except Exception as exc:
            ts_log(f"Failed to sync managed library artifacts to Kometa: {exc}", level="WARNING")

    if local_needs_write:
        ts_log(f"Saved new config to: {latest_path}")
    else:
        ts_log(f"Config unchanged; reused existing Quickstart config at: {latest_path}")
    if kometa_write_ok and kometa_needs_write:
        ts_log(f"Also copied config to: {kometa_path}")
    elif kometa_write_ok:
        ts_log(f"Kometa config unchanged; reused existing copy at: {kometa_path}")

    # Return POSIX-style filename (used for CLI path like --config config/name_config.yml)
    return latest_path.name
