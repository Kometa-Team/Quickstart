"""Font management utilities extracted from _legacy.py."""

import os
import shutil
import sys

from pathlib import Path

from modules.helpers._legacy import CONFIG_DIR, FONT_EXTENSIONS, MEIPASS_DIR, BASE_DIR, WORKING_DIR


def get_pyfiglet_fonts():
    """Retrieve available PyFiglet fonts from static/fonts, sorted with custom order."""
    if getattr(sys, "frozen", False):  # running in frozen/packaged mode
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    fonts_dir = os.path.join(base_path, "static", "fonts")

    # Ensure predefined fonts are at the top
    predefined_fonts = ["none", "single line", "standard"]
    fonts = set(predefined_fonts)  # Using set to prevent duplicates

    # Append all .flf files, removing extension
    if os.path.exists(fonts_dir):
        fonts.update(f.replace(".flf", "") for f in os.listdir(fonts_dir) if f.endswith(".flf"))

    # Sort remaining fonts (excluding predefined ones)
    sorted_fonts = sorted(fonts - set(predefined_fonts))

    # Combine predefined fonts with sorted remaining fonts
    return predefined_fonts + sorted_fonts


def get_legacy_custom_fonts_dir() -> Path:
    return Path(CONFIG_DIR) / "fonts"


def get_custom_fonts_dir(config_name: str | None = None) -> Path:
    if config_name:
        from modules import helpers as _helpers_fonts

        return _helpers_fonts.get_managed_config_artifact_root(config_name) / "fonts"
    return get_legacy_custom_fonts_dir()


def get_kometa_fonts_dir(kometa_root: Path | None = None) -> Path:
    if kometa_root is not None:
        return Path(kometa_root) / "config" / "fonts"
    from modules.helpers._kometa_paths import get_kometa_config_dir

    return get_kometa_config_dir() / "fonts"


def get_font_dirs(
    include_static: bool = True,
    include_custom: bool = True,
    config_name: str | None = None,
) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    if include_custom:
        custom_paths = []
        if config_name:
            custom_paths.append(get_custom_fonts_dir(config_name))
        custom_paths.extend((get_legacy_custom_fonts_dir(), get_kometa_fonts_dir()))
        for path in custom_paths:
            key = str(path)
            if key not in seen:
                dirs.append(path)
                seen.add(key)

    if include_static:
        for base in (MEIPASS_DIR, BASE_DIR, WORKING_DIR):
            path = Path(base) / "static" / "fonts"
            key = str(path)
            if key not in seen:
                dirs.append(path)
                seen.add(key)

    return dirs


def list_custom_fonts(config_name: str | None = None) -> list[str]:
    fonts: set[str] = set()
    folders = [get_kometa_fonts_dir(), get_legacy_custom_fonts_dir()]
    if config_name:
        folders.insert(0, get_custom_fonts_dir(config_name))
    for folder in folders:
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
                fonts.add(entry.name)
    return sorted(fonts)


def list_available_fonts(
    include_static: bool = True,
    include_custom: bool = True,
    config_name: str | None = None,
) -> list[str]:
    fonts: set[str] = set()
    for folder in get_font_dirs(include_static=include_static, include_custom=include_custom, config_name=config_name):
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
                fonts.add(entry.name)
    return sorted(fonts)


def migrate_legacy_custom_fonts_to_config(
    config_name: str | None,
    font_names: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict:
    from modules import helpers as _helpers_fonts

    try:
        normalized = _helpers_fonts.require_config_name_for_storage(config_name, context="Config-scoped font migration")
    except ValueError as exc:
        return {"copied": [], "skipped": [], "errors": [str(exc)]}

    source_dir = get_legacy_custom_fonts_dir()
    destination_dir = get_custom_fonts_dir(normalized)
    copied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    if not source_dir.is_dir():
        return {"copied": copied, "skipped": skipped, "errors": errors}

    requested: set[str] | None = None
    if font_names is not None:
        requested = {str(name or "").strip() for name in font_names if str(name or "").strip()}
        if not requested:
            return {"copied": copied, "skipped": skipped, "errors": errors}

    destination_dir.mkdir(parents=True, exist_ok=True)

    for entry in sorted(source_dir.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file() or entry.suffix.lower() not in FONT_EXTENSIONS:
            continue
        if requested is not None and entry.name not in requested:
            continue
        target = destination_dir / entry.name
        if target.exists():
            skipped.append(entry.name)
            continue
        try:
            shutil.copy2(entry, target)
            copied.append(entry.name)
        except Exception as exc:
            errors.append(f"Failed to migrate legacy font {entry} -> {target}: {exc}")

    return {"copied": copied, "skipped": skipped, "errors": errors}


def sync_custom_fonts(kometa_root: Path | None = None, config_name: str | None = None) -> list[str]:
    source_dir = get_custom_fonts_dir(config_name)
    if not source_dir.is_dir():
        return []
    dest_dir = get_kometa_fonts_dir(kometa_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for entry in source_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() in FONT_EXTENSIONS:
            shutil.copy2(entry, dest_dir / entry.name)
            copied.append(entry.name)
    return copied


def collect_font_references(config_data) -> list[str]:
    fonts: set[str] = set()

    def normalize(value):
        if isinstance(value, dict):
            raw = value.get("value")
            if isinstance(raw, str):
                return raw.strip()
            return None
        if isinstance(value, str):
            return value.strip()
        return None

    def walk(obj):
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(key, str) and (key == "font" or key.endswith("_font")):
                    norm = normalize(val)
                    if norm and norm.lower() != "none":
                        fonts.add(norm)
                walk(val)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(config_data)
    return sorted(fonts)


def copy_fonts_to_kometa(
    font_refs,
    kometa_root: Path | None = None,
    kometa_config_dir: Path | None = None,
    config_name: str | None = None,
) -> dict:
    dest_dir = Path(kometa_config_dir) / "fonts" if kometa_config_dir is not None else get_kometa_fonts_dir(kometa_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    migration = migrate_legacy_custom_fonts_to_config(config_name, font_refs) if config_name else {"copied": [], "skipped": [], "errors": []}
    sources = get_font_dirs(include_static=True, include_custom=True, config_name=config_name)
    copied: list[str] = []
    missing: list[str] = []
    errors: list[str] = list(migration.get("errors", []))

    for ref in font_refs or []:
        ref_str = str(ref or "").strip()
        if not ref_str:
            continue
        base = os.path.basename(ref_str)
        if not base:
            continue

        source_path = None
        candidate = Path(ref_str)
        if candidate.exists():
            source_path = candidate
        else:
            for folder in sources:
                candidate = Path(folder) / base
                if candidate.exists():
                    source_path = candidate
                    break

        if source_path is None:
            missing.append(base)
            continue

        dest_path = dest_dir / base
        try:
            if dest_path.resolve() == source_path.resolve():
                continue
        except Exception:
            pass

        try:
            shutil.copy2(source_path, dest_path)
            copied.append(base)
        except Exception as exc:
            errors.append(f"Failed to copy {source_path} -> {dest_path}: {exc}")

    return {"copied": copied, "missing": missing, "errors": errors}
