"""Managed YAML references must resolve from Kometa's cwd, not the config's parent."""

import copy
import json
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from flask import session
from ruamel.yaml import YAML

KINDS = [
    ("collection_files", "collections", "plex_all: true"),
    ("metadata_files", "metadata", "title: Example"),
    ("overlay_files", "overlays", "overlay: {name: text(Example)}"),
    ("playlist_files", "playlists", "plex_all: true"),
]


@pytest.mark.parametrize("kind,root,builder", KINDS)
@pytest.mark.parametrize("entry_type", ["file", "folder"])
@pytest.mark.parametrize("custom_target", [False, True])
def test_managed_file_save_reload_export_resolves_in_kometa(client, app, qs_module, isolated_config_dir, monkeypatch, tmp_path, kind, root, builder, entry_type, custom_target):
    from modules import bundle_artifacts, helpers, output, output_render, persistence
    from modules.library_file_entries import _normalize_imported_libraries_payload

    config_name = "custom_main"
    scope = "shared_playlist_files" if kind == "playlist_files" else "mov-library_movies"
    content = f"{root}:\n  Example:\n    {builder}\n"
    original = tmp_path / "original" / f"{root}.yml"
    original.parent.mkdir()
    original.write_text(content, encoding="utf-8")
    source = original if entry_type == "file" else original.parent
    monkeypatch.setitem(app.config, "KOMETA_INSTALL_MODE", "managed")
    singular = kind.removesuffix("s")
    request_data = {"config_name": config_name, "library_id": scope, f"{singular}_type": entry_type, f"{singular}_location": str(source)}
    response = client.post(f"/validate_{singular}", json=request_data)
    assert response.status_code == 200, response.get_json()
    location = response.get_json()["normalized_location"]
    assert location.startswith(f"config/{config_name}/{kind}/{scope}/")
    managed = isolated_config_dir / location.removeprefix("config/")
    managed_file = managed if entry_type == "file" else managed / original.name

    # Appending through the editor must preserve the managed filename on revalidation.
    appended = content + "# appended by the editor\n"
    edited_location = "config/" + managed_file.relative_to(isolated_config_dir).as_posix()
    saved = client.post("/external_yaml_file/save", json={"kind": kind, "location": edited_location, "content": appended})
    assert saved.status_code == 200, saved.get_json()
    request_data[f"{singular}_location"] = location
    again = client.post(f"/validate_{singular}", json=request_data)
    assert again.status_code == 200, again.get_json()
    assert again.get_json()["normalized_location"] == location
    assert again.get_json()["organized"] is False
    assert original.read_text(encoding="utf-8") == content

    if custom_target:
        monkeypatch.setitem(app.config, "KOMETA_INSTALL_MODE", "external")
        monkeypatch.setitem(app.config, "KOMETA_CONFIG_DIR", str(tmp_path / "different config directory"))
    monkeypatch.setitem(app.config, "QS_OPTIMIZE_DEFAULTS", False)
    monkeypatch.setattr(output_render, "render_yaml_header", lambda *_args: "# test config\n")
    entry = {"type": entry_type, "location": location, "schedule": "daily", "template_variables": {"test": "preserved"}, "validated": True}
    field = "playlist_files_entries" if kind == "playlist_files" else f"mov-library_movies-{kind}"
    data = {"mov-library_movies-library": "Movies", field: json.dumps([entry])}
    normalized, errors = _normalize_imported_libraries_payload({"libraries": data}, config_name)
    assert not errors
    assert json.loads(normalized["libraries"][field]) == [entry]

    with app.test_request_context("/step/900-kometa"):
        session["config_name"] = config_name
        persistence.save_settings("025-libraries", {**normalized["libraries"], "validated": True})
    # Use a fresh request to exercise database reload rather than the request cache.
    with app.test_request_context("/step/900-kometa"):
        session["config_name"] = config_name
        reloaded = persistence.retrieve_settings("025-libraries")
        assert json.loads(reloaded["libraries"][field]) == [entry]
        _valid, _error, _config, yaml_text, _errors = output.build_config("single line", config_name=config_name)
        finalized, changed, errors = qs_module._normalize_generated_config_library_files(copy.deepcopy(_config), config_name)
        assert not errors
        assert not changed
        assert finalized == _config
        parsed = YAML(typ="safe").load(yaml_text)
        entries = parsed["playlist_files"] if kind == "playlist_files" else parsed["libraries"]["Movies"][kind]
        emitted_entry = next(item for item in entries if entry_type in item)
        emitted = emitted_entry[entry_type]
        target_root = helpers.get_kometa_root_path()
        target_config = helpers.get_kometa_config_dir()
        expected = target_config / location.removeprefix("config/")
        assert (target_root / emitted).resolve() == expected.resolve()
        if kind != "overlay_files":
            assert emitted_entry["schedule"] == "daily"
        assert emitted_entry["template_variables"] == {"test": "preserved"}
        filename = helpers.save_to_named_config(yaml_text, config_name)
        assert (target_config / filename).read_text(encoding="utf-8") == yaml_text
        copied_file = expected if entry_type == "file" else expected / original.name
        assert copied_file.read_text(encoding="utf-8") == appended
        assert managed_file.read_text(encoding="utf-8") == appended

        artifacts, portable_yaml = bundle_artifacts.bundle_artifacts_from_yaml(yaml_text, config_name)
        assert len(artifacts) == 1
        assert artifacts[0]["archive"] == location.removeprefix("config/")
        portable = YAML(typ="safe").load(portable_yaml)
        portable_entries = portable["playlist_files"] if kind == "playlist_files" else portable["libraries"]["Movies"][kind]
        assert next(item[entry_type] for item in portable_entries if entry_type in item) == location
        bundle = bundle_artifacts.build_config_bundle(portable_yaml, filename, [], artifact_files=artifacts, config_name=config_name)
        extracted = tmp_path / "extracted"
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(extracted)
        rewritten = bundle_artifacts.rewrite_bundle_library_paths(portable, extracted)
        rewritten_entries = rewritten["playlist_files"] if kind == "playlist_files" else rewritten["libraries"]["Movies"][kind]
        imported_path = next(item[entry_type] for item in rewritten_entries if entry_type in item)
        assert Path(imported_path).exists()
        imported_entry = {**entry, "location": imported_path}
        imported, errors = _normalize_imported_libraries_payload({"libraries": {**data, field: json.dumps([imported_entry])}}, "imported_copy")
        assert not errors
        imported_location = json.loads(imported["libraries"][field])[0]["location"]
        assert imported_location.startswith(f"config/imported_copy/{kind}/{scope}/")
        assert managed_file.read_text(encoding="utf-8") == appended


@pytest.mark.parametrize("kind,root,builder", KINDS)
@pytest.mark.parametrize("separator", ["/", "\\"])
def test_old_saved_managed_tokens_export_without_moving_files(app, isolated_config_dir, monkeypatch, kind, root, builder, separator):
    from modules.library_file_entries import _normalize_library_external_entry
    from modules.output_file_entries import _parse_config_file_block_entries
    from modules.output_playlists import _normalize_playlist_file_entry_for_output

    relative = f"main/{kind}/shared/existing.yml"
    file = isolated_config_dir / relative
    file.parent.mkdir(parents=True)
    file.write_text(f"{root}:\n  Example: {{{builder}}}\n", encoding="utf-8")
    entry = {"type": "file", "location": relative.replace("/", separator), "validated": True}
    monkeypatch.setitem(app.config, "KOMETA_INSTALL_MODE", "managed")
    before = {path.relative_to(isolated_config_dir) for path in file.parent.rglob("*")}
    with app.app_context():
        parser = _normalize_playlist_file_entry_for_output if kind == "playlist_files" else lambda value: _parse_config_file_block_entries([value])[0]
        assert parser(entry)["file"] == f"config/{relative}"
        normalized, _changed, error = _normalize_library_external_entry(kind, entry, "main", "shared", validate_local=True)
        assert not error
        assert normalized["location"] == f"config/{relative}"
    assert {path.relative_to(isolated_config_dir) for path in file.parent.rglob("*")} == before
    assert file.exists()


@pytest.mark.parametrize("kind,root,builder", KINDS)
@pytest.mark.parametrize(
    "working,config_directory",
    [
        (PurePosixPath("/opt/kometa"), PurePosixPath("/opt/kometa/config")),
        (PurePosixPath("/app"), PurePosixPath("/config")),  # separate Docker volume
        (PurePosixPath("/app"), PurePosixPath("/app/custom config")),
        (PureWindowsPath("C:/Kometa"), PureWindowsPath("C:/Kometa/config")),
        (PureWindowsPath("C:/Kometa"), PureWindowsPath("D:/My Configs")),
    ],
)
def test_runtime_paths_windows_linux_and_docker(kind, root, builder, working, config_directory):
    from modules.managed_file_paths import managed_runtime_path

    token = f"config/custom_name/{kind}/shared/file.yml"
    emitted = managed_runtime_path(token, config_directory=config_directory, working_directory=working)
    assert working / emitted == config_directory / "custom_name" / kind / "shared/file.yml"
    if config_directory == working / "config":
        assert emitted == token


def test_playlist_only_bundle_and_scope(isolated_config_dir):
    from modules.bundle_artifacts import iter_bundle_artifacts, rewrite_bundle_library_paths

    relative = "main/playlist_files/shared_playlist_files/playlists_97bfe05e18.yml"
    file = isolated_config_dir / relative
    file.parent.mkdir(parents=True)
    file.write_text("playlists: {Example: {plex_all: true}}\n", encoding="utf-8")
    config = {"playlist_files": [{"file": f"config/{relative}"}], "libraries": {"Movies": {"playlist_files": [{"file": "invalid-library-scope.yml"}]}}}
    assert [artifact["source"] for artifact in iter_bundle_artifacts(config)] == [file.resolve()]
    imported = rewrite_bundle_library_paths(copy.deepcopy(config), isolated_config_dir)
    assert imported["playlist_files"][0]["file"] == str(file.resolve())
    assert imported["libraries"] == config["libraries"]


def test_playlist_sync_preserves_preexisting_target_files(app, isolated_config_dir):
    from modules import helpers

    target_root = Path(app.config["KOMETA_ROOT"])
    target = target_root / "config/main/playlist_files/shared_playlist_files"
    target.mkdir(parents=True)
    existing = target / "manually_appended.yml"
    existing.write_text("playlists: {Existing: {plex_all: true}}\n", encoding="utf-8")
    assert not helpers.sync_managed_library_artifacts_to_kometa("main", kometa_root=target_root)["errors"]
    assert existing.exists()
    source = isolated_config_dir / "main/playlist_files/shared_playlist_files/new.yml"
    source.parent.mkdir(parents=True)
    source.write_text("playlists: {New: {plex_all: true}}\n", encoding="utf-8")
    assert not helpers.sync_managed_library_artifacts_to_kometa("main", kometa_root=target_root)["errors"]
    assert (target / source.name).read_bytes() == source.read_bytes()
    assert existing.read_text(encoding="utf-8").startswith("playlists: {Existing:")


def test_final_page_exports_normalized_references_instead_of_stale_yaml(client, app, qs_module, isolated_config_dir, tmp_path, monkeypatch):
    from modules import bundle_artifacts

    source = tmp_path / "playlists.yml"
    source.write_text("playlists: {Example: {plex_all: true}}\n", encoding="utf-8")
    config = {"playlist_files": [{"file": str(source), "schedule": "daily", "template_variables": {"test": "preserved"}}]}
    original_yaml = bundle_artifacts.dump_yaml_text(config)
    captured = {}
    monkeypatch.setitem(app.config, "KOMETA_INSTALL_MODE", "managed")
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, "", copy.deepcopy(config), original_yaml, []))
    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *_args, **_kwargs: {
            "stage": "kometa",
            "todo_count": 0,
            "todo_blockers": [],
            "bulk_validation_fresh": True,
            "bulk_validation_at": qs_module.utc_now_iso(),
            "validation_ttl_hours": 12,
            "can_build_config": True,
            "config_valid": False,
        },
    )

    def save_yaml(text, name, _fonts):
        captured["text"] = text
        return f"{name}_config.yml"

    monkeypatch.setattr(qs_module.helpers, "save_to_named_config", save_yaml)
    with client.session_transaction() as state:
        state["config_name"] = "pytest_final_paths"
    response = client.get("/step/900-kometa")
    assert response.status_code == 200
    exported = YAML(typ="safe").load(captured["text"])["playlist_files"][0]
    assert exported["file"].startswith("config/pytest_final_paths/playlist_files/shared_playlist_files/")
    assert (isolated_config_dir / exported["file"].removeprefix("config/")).read_bytes() == source.read_bytes()
    assert exported["schedule"] == "daily"
    assert exported["template_variables"] == {"test": "preserved"}
    with client.session_transaction() as state:
        assert state["yaml_content"] == captured["text"]


@pytest.mark.parametrize(
    "location",
    [
        "/config/playlists.yml",
        "C:\\Kometa\\playlists.yml",
        "other/custom.yml",
        "https://example.com/playlists.yml",
        "../main/playlist_files/test.yml",
        "config/collection_files/main/existing.yml",
    ],
)
def test_unmanaged_references_are_not_prefixed(location):
    from modules.managed_file_paths import managed_file_location_for_output

    assert managed_file_location_for_output(location) == location


@pytest.mark.parametrize("kind,root,builder", KINDS)
def test_valid_user_relative_paths_resembling_managed_tokens_are_preserved(app, isolated_config_dir, monkeypatch, kind, root, builder):
    from modules.managed_file_paths import managed_file_location_for_output

    monkeypatch.setitem(app.config, "KOMETA_INSTALL_MODE", "managed")
    location = f"main/{kind}/user-owned.yml"
    file = Path(app.config["KOMETA_ROOT"]) / location
    file.parent.mkdir(parents=True)
    file.write_text(f"{root}: {{Example: {{{builder}}}}}\n", encoding="utf-8")
    with app.app_context():
        assert managed_file_location_for_output(location) == location
    assert not (isolated_config_dir / location).exists()


@pytest.mark.parametrize("kind,root,builder", KINDS)
@pytest.mark.parametrize("entry_type", ["file", "folder"])
def test_existing_type_first_layout_is_preserved_without_migration(app, qs_module, isolated_config_dir, monkeypatch, kind, root, builder, entry_type):
    from modules.library_file_entries import _normalize_library_external_entry

    monkeypatch.setitem(app.config, "KOMETA_INSTALL_MODE", "managed")
    legacy_file = isolated_config_dir / kind / "main/shared/existing.yml"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text(f"{root}:\n  Example:\n    {builder}\n", encoding="utf-8")
    source = legacy_file if entry_type == "file" else legacy_file.parent
    location = "config/" + source.relative_to(isolated_config_dir).as_posix()
    original = {entry_type: location, "template_variables": {"test": "preserved"}}
    config = {"playlist_files": [original]} if kind == "playlist_files" else {"libraries": {"Movies": {kind: [original]}}}
    before = sorted(str(path.relative_to(isolated_config_dir)) for path in (isolated_config_dir / kind).rglob("*"))
    with app.app_context():
        normalized, changed, error = _normalize_library_external_entry(kind, {"type": entry_type, "location": location}, "main", "shared")
        assert not error
        assert not changed
        assert normalized["location"] == location
        finalized, changed, errors = qs_module._normalize_generated_config_library_files(copy.deepcopy(config), "main")
        assert not errors
        assert not changed
        assert finalized == config
    assert sorted(str(path.relative_to(isolated_config_dir)) for path in (isolated_config_dir / kind).rglob("*")) == before
    assert not (isolated_config_dir / "main" / kind).exists()
