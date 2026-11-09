"""Path vocabulary shared by managed YAML storage, output and bundles.

Storage/archive paths are relative to Quickstart's CONFIG_DIR. Kometa file
references are relative to its working directory, including for playlists and
external templates; the location of the main config does not change that.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath

LIBRARY_FILE_KINDS = ("metadata_files", "collection_files", "overlay_files")
MANAGED_YAML_FILE_KINDS = LIBRARY_FILE_KINDS + ("playlist_files",)


def parse_managed_yaml_path(path_value):
    raw = str(path_value or "").strip().replace("\\", "/")
    if not raw or PurePosixPath(raw).is_absolute() or PureWindowsPath(raw).drive:
        return None
    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts or ".." in parts:
        return None
    has_config_prefix = parts[0] == "config"
    if has_config_prefix:
        parts = parts[1:]
    if len(parts) >= 3 and parts[1] in MANAGED_YAML_FILE_KINDS:
        layout, config_name, kind = "config_first", parts[0], parts[1]
    elif len(parts) >= 3 and parts[0] in MANAGED_YAML_FILE_KINDS:
        layout, config_name, kind = "type_first", parts[1], parts[0]
    else:
        return None
    return {"layout": layout, "config_name": config_name, "kind": kind, "remainder": parts[2:], "has_config_prefix": has_config_prefix, "parts": parts}


def iter_config_file_blocks(config_data):
    """Yield (kind, scope, entries) at their Kometa-supported scope."""
    if not isinstance(config_data, dict):
        return
    blocks = [("shared_playlist_files", config_data, ("playlist_files",))]
    libraries = config_data.get("libraries")
    if isinstance(libraries, dict):
        blocks.extend((name, library, LIBRARY_FILE_KINDS) for name, library in libraries.items() if isinstance(library, dict))
    for scope, section, kinds in blocks:
        for kind in kinds:
            entries = section.get(kind)
            if isinstance(entries, list):
                yield kind, scope, entries


def iter_config_file_entries(config_data):
    """Yield file-entry dictionaries, preserving top-level playlist scope."""
    for _kind, _scope, entries in iter_config_file_blocks(config_data):
        yield from (entry for entry in entries if isinstance(entry, dict))


def managed_runtime_path(location, *, config_directory, working_directory):
    """Translate a managed token to the destination, without changing user paths.

    Pure paths allow the same contract to be checked for Windows and POSIX.
    Absolute references are necessary when the target is outside Kometa's cwd.
    """
    info = parse_managed_yaml_path(location)
    if not info:
        return location
    target = config_directory.joinpath(info["config_name"], info["kind"], *info["remainder"])
    if config_directory == working_directory / "config":
        return target.relative_to(working_directory).as_posix()
    return target.as_posix()


def managed_file_location_for_output(location):
    """Use one serialization rule for all four file kinds, including old state."""
    from flask import has_app_context

    from modules import helpers

    info = parse_managed_yaml_path(location)
    # Old type-first references can already be valid in Kometa. Do not silently
    # change their layout during serialization; this is not a file migration.
    if not info or info["layout"] == "type_first":
        return location
    if has_app_context():
        config_directory = helpers.get_kometa_config_dir()
        working_directory = helpers.get_kometa_root_path()
        if not info["has_config_prefix"]:
            # A similarly named user path can already be valid from Kometa's
            # cwd. Repair old managed tokens only when they do not refer to
            # such an existing unmanaged destination.
            stored = Path(helpers.CONFIG_DIR).joinpath(*info["parts"])
            runtime = working_directory.joinpath(*info["parts"])
            if not stored.exists() and runtime.exists():
                return location
    else:
        config_directory, working_directory = PurePosixPath("config"), PurePosixPath(".")
    return managed_runtime_path(location, config_directory=config_directory, working_directory=working_directory)
