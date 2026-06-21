import re

import pytest


def _contains_dummy_field(value, expected):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "dummy_field" and item == expected:
                return True
            if _contains_dummy_field(item, expected):
                return True
    elif isinstance(value, list):
        return any(_contains_dummy_field(item, expected) for item in value)
    return False


def test_config_round_trip_all_steps(client, isolated_config_dir, monkeypatch, app, qs_module):
    from modules import database, helpers, persistence

    config_name = "pytest_config"

    # Avoid heavy YAML generation in the final step during this sweep
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_, **__: (True, None, {}, "test: true\n", []))

    with app.app_context():
        templates = helpers.get_template_list()
    assert templates

    core_sections = {"plex", "tmdb", "libraries", "settings"}

    for rec in templates.values():
        step_name = rec["stem"]
        source, source_name = persistence.extract_names(step_name)

        resp = client.post(
            f"/step/{step_name}",
            data={"configSelector": config_name, "dummy_field": f"val-{source_name}"},
            headers={"Referer": f"http://localhost/step/{step_name}"},
        )
        assert resp.status_code in (200, 302)

        with app.app_context():
            validated, user_entered, data = database.retrieve_section_data(config_name, source_name)
        if source_name in core_sections:
            assert data is not None
            assert data.get(source_name, {}).get("dummy_field") == f"val-{source_name}"
            assert user_entered is True
        elif data is not None:
            assert _contains_dummy_field(data.get(source_name, {}), f"val-{source_name}")


def test_step_rejects_invalid_path_payload(client, isolated_config_dir):
    from modules import database

    config_name = "pytest_invalid_path"
    step_name = "150-settings"

    resp = client.post(
        f"/step/{step_name}",
        data={"configSelector": config_name, "temp_path": "relative/path"},
        headers={"Referer": f"http://localhost/step/{step_name}"},
    )
    assert resp.status_code == 200
    assert b"Invalid values:" in resp.data

    validated, user_entered, data = database.retrieve_section_data(config_name, "settings")
    assert data is None
    assert validated is False
    assert user_entered is False


def test_step_rejects_invalid_auto_sort_hubs_payload(client, isolated_config_dir):
    from modules import database

    config_name = "pytest_invalid_auto_sort_hubs"
    step_name = "150-settings"

    resp = client.post(
        f"/step/{step_name}",
        data={"configSelector": config_name, "auto_sort_hubs": "bogus"},
        headers={"Referer": f"http://localhost/step/{step_name}"},
    )
    assert resp.status_code == 200
    assert b"auto_sort_hubs must be one of" in resp.data

    validated, user_entered, data = database.retrieve_section_data(config_name, "settings")
    assert data is None
    assert validated is False
    assert user_entered is False


def test_settings_page_disables_auto_sort_hubs_without_plex_pass(client, monkeypatch, qs_module):
    original_retrieve_settings = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(target):
        data = original_retrieve_settings(target)
        if target == "150-settings":
            data.setdefault("settings", {})["auto_sort_hubs"] = "alpha"
        elif target == "010-plex":
            data.setdefault("plex", {})["telemetry"] = {"plex_pass": False}
        elif target == "plex_telemetry":
            data["plex_telemetry"] = {"plex_pass": False}
        return data

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    resp = client.get("/step/150-settings")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    match = re.search(r'<select class="form-select" id="auto_sort_hubs"([^>]*)>', html)
    assert match is not None
    attrs = match.group(1)
    assert 'disabled aria-disabled="true"' in attrs
    assert 'name="auto_sort_hubs"' not in attrs
    assert 'name="auto_sort_hubs" value="alpha"' in html
    assert "Requires Plex Pass. Validate Plex first if this should be available." in html


def test_settings_page_enables_auto_sort_hubs_with_plex_pass(client, monkeypatch, qs_module):
    original_retrieve_settings = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(target):
        data = original_retrieve_settings(target)
        if target == "150-settings":
            data.setdefault("settings", {})["auto_sort_hubs"] = "configured.desc"
        elif target == "010-plex":
            data.setdefault("plex", {})["telemetry"] = {"plex_pass": True}
        elif target == "plex_telemetry":
            data["plex_telemetry"] = {"plex_pass": True}
        return data

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    resp = client.get("/step/150-settings")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    match = re.search(r'<select class="form-select" id="auto_sort_hubs"([^>]*)>', html)
    assert match is not None
    attrs = match.group(1)
    assert 'name="auto_sort_hubs"' in attrs
    assert "disabled" not in attrs
    assert 'value="configured.desc" selected' in html


def test_validate_apprise_rejects_bad_url(client):
    resp = client.post("/validate_apprise", json={"apprise_location": "not-a-url"})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False


def test_validate_apprise_accepts_existing_local_file(client, tmp_path):
    apprise_file = tmp_path / "apprise.yml"
    apprise_file.write_text("urls:\n  - discord://token\n", encoding="utf-8")

    resp = client.post("/validate_apprise", json={"apprise_location": str(apprise_file)})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True


def test_validate_apprise_rejects_non_yaml_extension(client, tmp_path):
    apprise_file = tmp_path / "apprise.txt"
    apprise_file.write_text("urls:\n  - discord://token\n", encoding="utf-8")

    resp = client.post("/validate_apprise", json={"apprise_location": str(apprise_file)})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert ".yml or .yaml" in payload["error"]


def test_validate_apprise_rejects_invalid_local_yaml(client, tmp_path):
    apprise_file = tmp_path / "apprise.yml"
    apprise_file.write_text("urls: [broken\n", encoding="utf-8")

    resp = client.post("/validate_apprise", json={"apprise_location": str(apprise_file)})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "valid YAML" in payload["error"]


def test_validate_apprise_rejects_empty_local_yaml(client, tmp_path):
    apprise_file = tmp_path / "apprise.yml"
    apprise_file.write_text("", encoding="utf-8")

    resp = client.post("/validate_apprise", json={"apprise_location": str(apprise_file)})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "must not be empty" in payload["error"]


def test_lookup_template_string_value_imdb_id_plex_returns_plex_title(client, monkeypatch, qs_module):
    monkeypatch.setattr(
        qs_module.helpers,
        "find_item_by_imdb_id",
        lambda library_name, imdb_id, media_type: {"id": imdb_id, "title": "The Matrix"},
    )

    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "imdb_id_plex",
            "value": "tt0133093",
            "library_name": "Movies",
            "media_type": "movie",
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["verified"] is True
    assert payload["label"] == "The Matrix"
    assert payload["message"] == "Plex: The Matrix"


def test_lookup_template_string_value_imdb_id_plex_warns_when_missing(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "find_item_by_imdb_id", lambda library_name, imdb_id, media_type: None)

    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "imdb_id_plex",
            "value": "tt0133093",
            "library_name": "Movies",
            "media_type": "movie",
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is False
    assert payload["verified"] is False
    assert "no matching item was found" in payload["message"]


def test_validate_apprise_rejects_invalid_remote_yaml(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 200
        reason = "OK"
        text = "urls: [broken\n"

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())

    resp = client.post("/validate_apprise", json={"apprise_location": "https://example.com/apprise.yml"})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "valid YAML" in payload["error"]


def test_validate_apprise_rejects_empty_remote_yaml(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 200
        reason = "OK"
        text = ""

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())

    resp = client.post("/validate_apprise", json={"apprise_location": "https://example.com/apprise.yml"})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "must not be empty" in payload["error"]


def test_validate_metadata_file_accepts_existing_local_file(client, tmp_path):
    metadata_file = tmp_path / "metadata.yml"
    metadata_file.write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "file", "metadata_file_location": str(metadata_file)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True


def test_validate_collection_file_accepts_existing_local_file(client, tmp_path):
    collection_file = tmp_path / "collections.yml"
    collection_file.write_text("collections:\n  test:\n    plex_search:\n      any:\n        title: Example\n", encoding="utf-8")

    resp = client.post(
        "/validate_collection_file",
        json={"collection_file_type": "file", "collection_file_location": str(collection_file)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True


def test_validate_overlay_file_accepts_existing_local_file(client, tmp_path):
    overlay_file = tmp_path / "overlays.yml"
    overlay_file.write_text("overlays:\n  test:\n    template:\n      - name: ribbon\n", encoding="utf-8")

    resp = client.post(
        "/validate_overlay_file",
        json={"overlay_file_type": "file", "overlay_file_location": str(overlay_file)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True


def test_validate_metadata_file_organizes_local_file_into_managed_store(client, isolated_config_dir, tmp_path):
    from pathlib import Path

    config_name = "pytest_validate_library_files"
    metadata_file = tmp_path / "metadata.yml"
    metadata_file.write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={
            "config_name": config_name,
            "library_id": "mov-library_movies",
            "metadata_file_type": "file",
            "metadata_file_location": str(metadata_file),
        },
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["organized"] is True
    normalized_location = payload["normalized_location"]
    assert normalized_location.startswith(f"config/{config_name}/metadata_files/mov-library_movies/")
    managed_file = isolated_config_dir.parent / Path(normalized_location)
    assert managed_file.exists()
    assert managed_file.read_text(encoding="utf-8") == metadata_file.read_text(encoding="utf-8")


def test_validate_collection_file_rejects_missing_top_level_collections(client, tmp_path):
    collection_file = tmp_path / "collections.yml"
    collection_file.write_text("templates:\n  test:\n    default: true\n", encoding="utf-8")

    resp = client.post(
        "/validate_collection_file",
        json={"collection_file_type": "file", "collection_file_location": str(collection_file)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "Top-level `collections:` was not found" in payload["error"]
    assert "`collections.yml`" in payload["error"]


def test_validate_collection_file_rejects_empty_top_level_collections(client, tmp_path):
    collection_file = tmp_path / "collections.yml"
    collection_file.write_text("collections: {}\n", encoding="utf-8")

    resp = client.post(
        "/validate_collection_file",
        json={"collection_file_type": "file", "collection_file_location": str(collection_file)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "Top-level `collections:` in `collections.yml` must be a non-empty mapping." == payload["error"]


def test_validate_overlay_file_rejects_missing_top_level_overlays(client, tmp_path):
    overlay_file = tmp_path / "overlays.yml"
    overlay_file.write_text("templates:\n  test:\n    default: true\n", encoding="utf-8")

    resp = client.post(
        "/validate_overlay_file",
        json={"overlay_file_type": "file", "overlay_file_location": str(overlay_file)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "Top-level `overlays:` was not found" in payload["error"]
    assert "`overlays.yml`" in payload["error"]


def test_validate_metadata_file_rejects_missing_top_level_metadata(client, tmp_path):
    metadata_file = tmp_path / "metadata.yml"
    metadata_file.write_text("templates:\n  test:\n    default: true\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "file", "metadata_file_location": str(metadata_file)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "Top-level `metadata:` was not found" in payload["error"]
    assert "`metadata.yml`" in payload["error"]


def test_validate_metadata_file_rejects_empty_top_level_metadata(client, tmp_path):
    metadata_file = tmp_path / "metadata.yml"
    metadata_file.write_text("metadata: {}\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "file", "metadata_file_location": str(metadata_file)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "Top-level `metadata:` in `metadata.yml` must be a non-empty mapping." == payload["error"]


def test_validate_metadata_file_rejects_invalid_type(client):
    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "default", "metadata_file_location": "config/metadata.yml"},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "file, folder, url, git, or repo" in payload["error"]


def test_validate_metadata_folder_accepts_top_level_yaml_files(client, tmp_path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "godzilla.yml").write_text("metadata:\n  test:\n    title: Godzilla\n", encoding="utf-8")
    (metadata_dir / "refresh.yaml").write_text("metadata:\n  refresh:\n    title: Refresh\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "folder", "metadata_file_location": str(metadata_dir)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["validated_files"] == 2
    assert payload["files"] == ["godzilla.yml", "refresh.yaml"]
    assert payload["message"] == "Validated 2 YAML files in folder."


def test_validate_metadata_folder_organizes_generic_folder_name_into_descriptive_managed_store(client, isolated_config_dir, tmp_path):
    source_dir = tmp_path / "movies" / "metadata_files"
    source_dir.mkdir(parents=True)
    (source_dir / "godzilla.yml").write_text("metadata:\n  test:\n    title: Godzilla\n", encoding="utf-8")

    config_name = "pytest_metadata_folder_name"
    resp = client.post(
        "/validate_metadata_file",
        json={
            "metadata_file_type": "folder",
            "metadata_file_location": str(source_dir),
            "library_id": "mov-library_movies",
            "config_name": config_name,
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    normalized_location = str(payload["normalized_location"]).replace("\\", "/")
    assert normalized_location.startswith(f"config/{config_name}/metadata_files/mov-library_movies/")
    assert "/movies_metadata_files_" in normalized_location
    assert (isolated_config_dir.parent / normalized_location).exists()


def test_validate_collection_folder_accepts_top_level_yaml_files(client, tmp_path):
    collection_dir = tmp_path / "collections"
    collection_dir.mkdir()
    (collection_dir / "godzilla.yml").write_text("collections:\n  test:\n    title: Godzilla\n", encoding="utf-8")
    (collection_dir / "refresh.yaml").write_text("collections:\n  refresh:\n    title: Refresh\n", encoding="utf-8")

    resp = client.post(
        "/validate_collection_file",
        json={"collection_file_type": "folder", "collection_file_location": str(collection_dir)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["validated_files"] == 2
    assert payload["files"] == ["godzilla.yml", "refresh.yaml"]
    assert payload["message"] == "Validated 2 YAML files in folder."


def test_validate_collection_folder_accepts_managed_relative_folder_path(client, isolated_config_dir):
    managed_dir = isolated_config_dir / "collection_files"
    managed_dir.mkdir(parents=True, exist_ok=True)
    (managed_dir / "godzilla.yml").write_text("collections:\n  test:\n    title: Godzilla\n", encoding="utf-8")

    resp = client.post(
        "/validate_collection_file",
        json={
            "config_name": "pytest_managed_collection_folder",
            "library_id": "mov-library_movies",
            "collection_file_type": "folder",
            "collection_file_location": "collection_files",
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["normalized_location"].startswith("config/pytest_managed_collection_folder/collection_files/mov-library_movies/")
    assert payload["organized"] is True


def test_validate_metadata_folder_rejects_empty_folder(client, tmp_path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "folder", "metadata_file_location": str(metadata_dir)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "at least one top-level .yml or .yaml file" in payload["error"]


def test_validate_metadata_folder_does_not_recurse_into_subfolders(client, tmp_path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "godzilla.yml").write_text("metadata:\n  test:\n    title: Godzilla\n", encoding="utf-8")
    nested_dir = metadata_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "broken.yml").write_text("metadata: [broken\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "folder", "metadata_file_location": str(metadata_dir)},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["validated_files"] == 1
    assert payload["files"] == ["godzilla.yml"]


def test_validate_metadata_folder_rejects_top_level_yaml_without_metadata(client, tmp_path):
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "godzilla.yml").write_text("metadata:\n  test:\n    title: Godzilla\n", encoding="utf-8")
    (metadata_dir / "broken.yml").write_text("templates:\n  sample:\n    test: true\n", encoding="utf-8")
    (metadata_dir / "empty.yml").write_text("metadata: {}\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "folder", "metadata_file_location": str(metadata_dir)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert payload["error"] == "Metadata folder path: Scanned 3 top-level YAML files and found 2 invalid files."
    assert payload["error_details"]["text"] == payload["error"]
    assert payload["files"] == ["Top-level `metadata:` was not found in `broken.yml`.", "Top-level `metadata:` in `empty.yml` must be a non-empty mapping."]


def test_validate_collection_folder_rejects_top_level_yaml_without_collections(client, tmp_path):
    collection_dir = tmp_path / "collections"
    collection_dir.mkdir()
    (collection_dir / "godzilla.yml").write_text("collections:\n  test:\n    title: Godzilla\n", encoding="utf-8")
    (collection_dir / "broken.yml").write_text("templates:\n  sample:\n    test: true\n", encoding="utf-8")
    (collection_dir / "empty.yml").write_text("collections: {}\n", encoding="utf-8")

    resp = client.post(
        "/validate_collection_file",
        json={"collection_file_type": "folder", "collection_file_location": str(collection_dir)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert payload["error"] == "Collection folder path: Scanned 3 top-level YAML files and found 2 invalid files."
    assert payload["error_details"]["text"] == payload["error"]
    assert payload["files"] == ["Top-level `collections:` was not found in `broken.yml`.", "Top-level `collections:` in `empty.yml` must be a non-empty mapping."]


def test_validate_metadata_url_rejects_missing_top_level_metadata(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 200
        reason = "OK"
        text = "templates:\n  sample:\n    default: true\n"

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "url", "metadata_file_location": "https://example.com/metadata.yml"},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert payload["error"] == "Top-level `metadata:` was not found in `metadata.yml`."


def test_validate_metadata_file_accepts_git(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 200
        reason = "OK"
        text = "metadata:\n  test:\n    title: Example\n"

    captured = {}

    def _fake_get(url, timeout=10):
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr(qs_module.validations.requests, "get", _fake_get)

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "git", "metadata_file_location": "bullmoose20/godzilla.yml"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True
    assert captured["url"] == "https://raw.githubusercontent.com/Kometa-Team/Community-Configs/master/bullmoose20/godzilla.yml"


def test_validate_collection_file_rejects_repo_without_custom_repo(client):
    resp = client.post(
        "/validate_collection_file",
        json={"collection_file_type": "repo", "collection_file_location": "bullmoose20/collections.yml"},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert payload["error"] == "Collection file repo entries require Custom Repo to be configured and saved first within the Settings page."


def test_validate_metadata_file_rejects_repo_without_custom_repo(client):
    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "repo", "metadata_file_location": "bullmoose20/godzilla.yml"},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert payload["error"] == "Metadata file repo entries require Custom Repo to be configured and saved first within the Settings page."


def test_validate_metadata_file_accepts_repo_with_saved_custom_repo(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 200
        reason = "OK"
        text = "metadata:\n  test:\n    title: Example\n"

    captured = {}

    def _fake_get(url, timeout=10):
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr(
        qs_module.validations.persistence,
        "retrieve_settings",
        lambda _section: {"settings": {"custom_repo": "https://github.com/example/custom-repo/tree/master"}},
    )
    monkeypatch.setattr(qs_module.validations.requests, "get", _fake_get)

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "repo", "metadata_file_location": "bullmoose20/godzilla.yml"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["valid"] is True
    assert captured["url"] == "https://raw.githubusercontent.com/example/custom-repo/master/bullmoose20/godzilla.yml"


def test_validate_metadata_file_rejects_url_in_file_mode(client):
    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "file", "metadata_file_location": "https://example.com/metadata.yml"},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "local file path" in payload["error"]


def test_validate_metadata_file_rejects_invalid_local_yaml(client, tmp_path):
    metadata_file = tmp_path / "metadata.yml"
    metadata_file.write_text("metadata: [broken\n", encoding="utf-8")

    resp = client.post(
        "/validate_metadata_file",
        json={"metadata_file_type": "file", "metadata_file_location": str(metadata_file)},
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "valid YAML" in payload["error"]


def test_autosave_library_rejects_invalid_metadata_files(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 404
        reason = "Not Found"
        text = ""

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={
            "mov-library_movies-library": "Movies",
            "mov-library_movies-metadata_files": '[{"type":"url","location":"https://example.com/missing.yml"}]',
        },
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Invalid metadata files" in payload["error"]


def test_autosave_library_rejects_invalid_collection_files(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 404
        reason = "Not Found"
        text = ""

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_files": '[{"type":"url","location":"https://example.com/missing.yml"}]',
        },
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Invalid collection files" in payload["error"]


def test_autosave_library_accepts_managed_relative_collection_folder_path(client, isolated_config_dir, monkeypatch, qs_module):
    import json

    managed_dir = isolated_config_dir / "collection_files"
    managed_dir.mkdir(parents=True, exist_ok=True)
    (managed_dir / "godzilla.yml").write_text("collections:\n  test:\n    title: Godzilla\n", encoding="utf-8")

    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={
            "config_name": "pytest_autosave_managed_collection_folder",
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_files": '[{"type":"folder","location":"collection_files","validated":true}]',
        },
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    saved_entries = json.loads(payload["libraries"]["mov-library_movies-collection_files"])
    assert len(saved_entries) == 1
    assert saved_entries[0]["type"] == "folder"
    assert saved_entries[0]["validated"] is True
    assert saved_entries[0]["location"].startswith("config/pytest_autosave_managed_collection_folder/collection_files/mov-library_movies/")


def test_autosave_library_rejects_invalid_overlay_files(client, monkeypatch, qs_module):
    class _Resp:
        status_code = 404
        reason = "Not Found"
        text = ""

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={
            "mov-library_movies-library": "Movies",
            "mov-library_movies-overlay_files": '[{"type":"url","location":"https://example.com/missing.yml"}]',
        },
    )
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Invalid overlay files" in payload["error"]


def test_autosave_library_organizes_overlay_folder(client, isolated_config_dir, tmp_path):
    import json

    from modules import database

    config_name = "pytest_autosave_overlay_folder"
    overlay_dir = tmp_path / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    (overlay_dir / "movies.yml").write_text("overlays:\n  test:\n    template:\n      - name: ribbon\n", encoding="utf-8")

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={
            "config_name": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-overlay_files": json.dumps([{"type": "folder", "location": str(overlay_dir)}], ensure_ascii=True),
        },
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["normalized"] is True

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert validated is False
    assert user_entered is True
    overlay_entries = json.loads(stored["libraries"]["mov-library_movies-overlay_files"])
    assert len(overlay_entries) == 1
    assert overlay_entries[0]["type"] == "folder"
    managed_location = overlay_entries[0]["location"]
    assert managed_location.startswith(f"config/{config_name}/overlay_files/mov-library_movies/")
    managed_dir = isolated_config_dir.parent / managed_location
    assert managed_dir.is_dir()
    assert (managed_dir / "movies.yml").exists()


def test_output_metadata_file_entries_are_sorted():
    import json

    from modules import output

    parsed = output._parse_metadata_file_entries(
        json.dumps(
            [
                {"type": "url", "location": "https://example.com/zeta.yml"},
                {"type": "repo", "location": "custom/movies.yml"},
                {"type": "file", "location": "config/beta.yml"},
                {"type": "folder", "location": "config/zeta"},
                {"type": "git", "location": "community/alpha.yml"},
                {"type": "file", "location": "config/alpha.yml"},
                {"type": "folder", "location": "config/alpha"},
                {"type": "url", "location": "https://example.com/alpha.yml"},
            ]
        )
    )

    assert parsed == [
        {"file": "config/alpha.yml"},
        {"file": "config/beta.yml"},
        {"folder": "config/alpha"},
        {"folder": "config/zeta"},
        {"git": "community/alpha.yml"},
        {"repo": "custom/movies.yml"},
        {"url": "https://example.com/alpha.yml"},
        {"url": "https://example.com/zeta.yml"},
    ]


def test_output_collection_file_entries_are_sorted():
    import json

    from modules import output

    parsed = output._parse_collection_file_block_entries(
        json.dumps(
            [
                {"type": "url", "location": "https://example.com/zeta.yml"},
                {"type": "repo", "location": "custom/movies.yml"},
                {"type": "file", "location": "config/beta.yml"},
                {"type": "folder", "location": "config/zeta"},
                {"type": "git", "location": "community/alpha.yml"},
                {"type": "file", "location": "config/alpha.yml"},
                {"type": "folder", "location": "config/alpha"},
                {"type": "url", "location": "https://example.com/alpha.yml"},
            ]
        )
    )

    assert parsed == [
        {"file": "config/alpha.yml"},
        {"file": "config/beta.yml"},
        {"folder": "config/alpha"},
        {"folder": "config/zeta"},
        {"git": "community/alpha.yml"},
        {"repo": "custom/movies.yml"},
        {"url": "https://example.com/alpha.yml"},
        {"url": "https://example.com/zeta.yml"},
    ]


def test_output_overlay_file_entries_are_sorted():
    import json

    from modules import output

    parsed = output._parse_overlay_file_block_entries(
        json.dumps(
            [
                {"type": "url", "location": "https://example.com/zeta.yml"},
                {"type": "repo", "location": "custom/movies.yml"},
                {"type": "file", "location": "config/beta.yml"},
                {"type": "folder", "location": "config/zeta"},
                {"type": "git", "location": "community/alpha.yml"},
                {"type": "file", "location": "config/alpha.yml"},
                {"type": "folder", "location": "config/alpha"},
                {"type": "url", "location": "https://example.com/alpha.yml"},
            ]
        )
    )

    assert parsed == [
        {"file": "config/alpha.yml"},
        {"file": "config/beta.yml"},
        {"folder": "config/alpha"},
        {"folder": "config/zeta"},
        {"git": "community/alpha.yml"},
        {"repo": "custom/movies.yml"},
        {"url": "https://example.com/alpha.yml"},
        {"url": "https://example.com/zeta.yml"},
    ]


def test_clean_form_data_preserves_overlay_language_multiselect_values():
    from werkzeug.datastructures import MultiDict

    from modules import persistence

    payload = MultiDict(
        [
            ("mov-library_movies-movie-template_overlay_languages[languages]", "en"),
            ("mov-library_movies-movie-template_overlay_languages[languages]", "ja"),
            ("mov-library_movies-movie-template_overlay_languages[style]", "square"),
        ]
    )

    cleaned = persistence.clean_form_data(payload)

    assert cleaned["mov-library_movies-movie-template_overlay_languages[languages]"] == ["en", "ja"]
    assert cleaned["mov-library_movies-movie-template_overlay_languages[style]"] == "square"


def test_build_libraries_section_emits_metadata_files(app):
    import json

    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-metadata_files": json.dumps(
                        [
                            {"type": "url", "location": "https://example.com/movies_refresh.yml"},
                            {"type": "repo", "location": "custom/movies_meta.yml"},
                            {"type": "file", "location": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
                            {"type": "folder", "location": "config\\metadata\\movies"},
                            {"type": "git", "location": "bullmoose20/collections/godzilla.yml"},
                        ]
                    )
                }
            },
            {},
            {},
            {},
            {},
            {},
        )

        assert libraries_section["libraries"]["Movies"]["metadata_files"] == [
            {"file": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
            {"folder": "config\\metadata\\movies"},
            {"git": "bullmoose20/collections/godzilla.yml"},
            {"repo": "custom/movies_meta.yml"},
            {"url": "https://example.com/movies_refresh.yml"},
        ]
    assert list(libraries_section["libraries"]["Movies"].keys())[:2] == ["template_variables", "metadata_files"]


def test_build_libraries_section_emits_raw_overlay_files(app):
    import json

    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-overlay_files": json.dumps(
                        [
                            {"type": "url", "location": "https://example.com/movies_refresh.yml"},
                            {"type": "repo", "location": "custom/movies_overlay.yml"},
                            {"type": "file", "location": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\overlays.yml"},
                            {"type": "folder", "location": "config\\overlays\\movies"},
                            {"type": "git", "location": "bullmoose20/overlays.yml"},
                        ]
                    )
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

        assert libraries_section["libraries"]["Movies"]["overlay_files"] == [
            {"file": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\overlays.yml"},
            {"folder": "config\\overlays\\movies"},
            {"git": "bullmoose20/overlays.yml"},
            {"repo": "custom/movies_overlay.yml"},
            {"url": "https://example.com/movies_refresh.yml"},
        ]
    assert list(libraries_section["libraries"]["Movies"].keys())[:2] == ["template_variables", "overlay_files"]


def test_build_libraries_section_emits_collection_files(app):
    import json

    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {"movies": {"mov-library_movies-collection_collectionless": True}},
            {},
            {
                "movies": {
                    "mov-library_movies-collection_files": json.dumps(
                        [
                            {"type": "url", "location": "https://example.com/movies_refresh.yml"},
                            {"type": "repo", "location": "custom/movies_meta.yml"},
                            {"type": "file", "location": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
                            {"type": "folder", "location": "config\\metadata\\movies"},
                            {"type": "git", "location": "bullmoose20/collections/godzilla.yml"},
                        ]
                    )
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

        assert libraries_section["libraries"]["Movies"]["collection_files"] == [
            {"default": "collectionless"},
            {"file": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
            {"folder": "config\\metadata\\movies"},
            {"git": "bullmoose20/collections/godzilla.yml"},
            {"repo": "custom/movies_meta.yml"},
            {"url": "https://example.com/movies_refresh.yml"},
        ]


def test_build_libraries_section_preserves_collection_include_and_exclude(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {
                "movies": {
                    "mov-library_movies-collection_actor": True,
                    "mov-library_movies-template_collection_actor_include": ["Tom Hanks"],
                    "mov-library_movies-template_collection_actor_exclude": ["Morgan Freeman"],
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    actor_entry = next(
        (entry for entry in libraries_section["libraries"]["Movies"]["collection_files"] if entry.get("default") == "actor"),
        None,
    )
    assert actor_entry is not None
    assert actor_entry["template_variables"]["include"] == ["Tom Hanks"]
    assert actor_entry["template_variables"]["exclude"] == ["Morgan Freeman"]


def test_build_libraries_section_preserves_chart_builder_size_template_variables(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {
                "movies": {
                    "mov-library_movies-collection_tautulli": True,
                    "mov-library_movies-template_collection_tautulli_list_days": "14",
                    "mov-library_movies-template_collection_tautulli_list_size": "50",
                    "mov-library_movies-template_collection_tautulli_list_days_popular": "7",
                    "mov-library_movies-template_collection_tautulli_list_size_watched": "25",
                    "mov-library_movies-collection_trakt": True,
                    "mov-library_movies-template_collection_trakt_limit": "75",
                    "mov-library_movies-template_collection_trakt_limit_popular": "50",
                    "mov-library_movies-template_collection_trakt_limit_recommended": "30",
                    "mov-library_movies-collection_tmdb": True,
                    "mov-library_movies-template_collection_tmdb_limit": "60",
                    "mov-library_movies-template_collection_tmdb_limit_airing": "20",
                    "mov-library_movies-template_collection_tmdb_limit_trending": "40",
                    "mov-library_movies-collection_simkl": True,
                    "mov-library_movies-template_collection_simkl_limit_trending_today": "15",
                    "mov-library_movies-template_collection_simkl_limit_dvd": "10",
                    "mov-library_movies-collection_anilist": True,
                    "mov-library_movies-template_collection_anilist_limit": "80",
                    "mov-library_movies-template_collection_anilist_limit_popular": "40",
                    "mov-library_movies-template_collection_anilist_limit_season": "25",
                    "mov-library_movies-collection_myanimelist": True,
                    "mov-library_movies-template_collection_myanimelist_limit": "90",
                    "mov-library_movies-template_collection_myanimelist_limit_favorited": "45",
                    "mov-library_movies-template_collection_myanimelist_limit_airing": "12",
                    "mov-library_movies-collection_basic": True,
                    "mov-library_movies-template_collection_basic_limit": "20",
                    "mov-library_movies-template_collection_basic_limit_released": "10",
                    "mov-library_movies-template_collection_basic_limit_episodes": "5",
                    "mov-library_movies-collection_letterboxd": True,
                    "mov-library_movies-template_collection_letterboxd_limit": "120",
                    "mov-library_movies-template_collection_letterboxd_limit_1001_movies": "80",
                    "mov-library_movies-template_collection_letterboxd_limit_top_500": "60",
                    "mov-library_movies-template_collection_letterboxd_limit_women_directors": "40",
                    "mov-library_movies-collection_imdb": True,
                    "mov-library_movies-template_collection_imdb_limit": "250",
                    "mov-library_movies-collection_other_chart": True,
                    "mov-library_movies-template_collection_other_chart_limit": "125",
                    "mov-library_movies-collection_streaming": True,
                    "mov-library_movies-template_collection_streaming_limit": "500",
                    "mov-library_movies-template_collection_streaming_discover_limit": "150",
                    "mov-library_movies-collection_seasonal": True,
                    "mov-library_movies-template_collection_seasonal_limit": "30",
                    "mov-library_movies-template_collection_seasonal_limit_halloween": "12",
                    "mov-library_movies-collection_year": True,
                    "mov-library_movies-template_collection_year_limit": "8",
                    "mov-library_movies-collection_content_rating_us": True,
                    "mov-library_movies-template_collection_content_rating_us_limit": "40",
                    "mov-library_movies-template_collection_content_rating_us_limit_other": "5",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    collection_entries = libraries_section["libraries"]["Movies"]["collection_files"]

    tautulli_entry = next((entry for entry in collection_entries if entry.get("default") == "tautulli"), None)
    trakt_entry = next((entry for entry in collection_entries if entry.get("default") == "trakt"), None)
    tmdb_entry = next((entry for entry in collection_entries if entry.get("default") == "tmdb"), None)
    simkl_entry = next((entry for entry in collection_entries if entry.get("default") == "simkl"), None)
    anilist_entry = next((entry for entry in collection_entries if entry.get("default") == "anilist"), None)
    myanimelist_entry = next((entry for entry in collection_entries if entry.get("default") == "myanimelist"), None)
    basic_entry = next((entry for entry in collection_entries if entry.get("default") == "basic"), None)
    letterboxd_entry = next((entry for entry in collection_entries if entry.get("default") == "letterboxd"), None)
    imdb_entry = next((entry for entry in collection_entries if entry.get("default") == "imdb"), None)
    other_chart_entry = next((entry for entry in collection_entries if entry.get("default") == "other_chart"), None)
    streaming_entry = next((entry for entry in collection_entries if entry.get("default") == "streaming"), None)
    seasonal_entry = next((entry for entry in collection_entries if entry.get("default") == "seasonal"), None)
    year_entry = next((entry for entry in collection_entries if entry.get("default") == "year"), None)
    content_rating_us_entry = next((entry for entry in collection_entries if entry.get("default") == "content_rating_us"), None)

    assert tautulli_entry["template_variables"]["list_days"] == "14"
    assert tautulli_entry["template_variables"]["list_size"] == "50"
    assert tautulli_entry["template_variables"]["list_days_popular"] == "7"
    assert tautulli_entry["template_variables"]["list_size_watched"] == "25"
    assert trakt_entry["template_variables"]["limit"] == "75"
    assert trakt_entry["template_variables"]["limit_popular"] == "50"
    assert trakt_entry["template_variables"]["limit_recommended"] == "30"
    assert tmdb_entry["template_variables"]["limit"] == "60"
    assert tmdb_entry["template_variables"]["limit_airing"] == "20"
    assert tmdb_entry["template_variables"]["limit_trending"] == "40"
    assert simkl_entry["template_variables"]["limit_trending_today"] == "15"
    assert simkl_entry["template_variables"]["limit_dvd"] == "10"
    assert anilist_entry["template_variables"]["limit"] == "80"
    assert anilist_entry["template_variables"]["limit_popular"] == "40"
    assert anilist_entry["template_variables"]["limit_season"] == "25"
    assert myanimelist_entry["template_variables"]["limit"] == "90"
    assert myanimelist_entry["template_variables"]["limit_favorited"] == "45"
    assert myanimelist_entry["template_variables"]["limit_airing"] == "12"
    assert basic_entry["template_variables"]["limit"] == "20"
    assert basic_entry["template_variables"]["limit_released"] == "10"
    assert basic_entry["template_variables"]["limit_episodes"] == "5"
    assert letterboxd_entry["template_variables"]["limit"] == "120"
    assert letterboxd_entry["template_variables"]["limit_1001_movies"] == "80"
    assert letterboxd_entry["template_variables"]["limit_top_500"] == "60"
    assert letterboxd_entry["template_variables"]["limit_women_directors"] == "40"
    assert imdb_entry["template_variables"]["limit"] == "250"
    assert other_chart_entry["template_variables"]["limit"] == "125"
    assert streaming_entry["template_variables"]["limit"] == "500"
    assert streaming_entry["template_variables"]["discover_limit"] == "150"
    assert seasonal_entry["template_variables"]["limit"] == "30"
    assert seasonal_entry["template_variables"]["limit_halloween"] == "12"
    assert year_entry["template_variables"]["limit"] == "8"
    assert content_rating_us_entry["template_variables"]["limit"] == "40"
    assert content_rating_us_entry["template_variables"]["limit_other"] == "5"


def test_build_libraries_section_normalizes_collection_arr_tag_lists(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {"sho-library_shows-library": "Shows"},
            {
                "movies": {
                    "mov-library_movies-collection_franchise": True,
                    "mov-library_movies-template_collection_franchise_radarr_folder": r"C:\Media\Movies",
                    "mov-library_movies-template_collection_franchise_radarr_tag": '["4k", "favorite"]',
                    "mov-library_movies-template_collection_franchise_item_radarr_tag": '["collected", "franchise"]',
                }
            },
            {
                "shows": {
                    "sho-library_shows-collection_franchise": True,
                    "sho-library_shows-template_collection_franchise_sonarr_folder": r"C:\Media\Shows",
                    "sho-library_shows-template_collection_franchise_sonarr_monitor": "future",
                    "sho-library_shows-template_collection_franchise_sonarr_tag": '["ongoing", "priority"]',
                    "sho-library_shows-template_collection_franchise_item_sonarr_tag": '["watched", "tracked"]',
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    movie_entry = next(
        (entry for entry in libraries_section["libraries"]["Movies"]["collection_files"] if entry.get("default") == "franchise"),
        None,
    )
    show_entry = next(
        (entry for entry in libraries_section["libraries"]["Shows"]["collection_files"] if entry.get("default") == "franchise"),
        None,
    )

    assert movie_entry is not None
    assert show_entry is not None
    assert movie_entry["template_variables"]["radarr_folder"] == r"C:\Media\Movies"
    assert movie_entry["template_variables"]["radarr_tag"] == ["4k", "favorite"]
    assert movie_entry["template_variables"]["item_radarr_tag"] == ["collected", "franchise"]
    assert show_entry["template_variables"]["sonarr_folder"] == r"C:\Media\Shows"
    assert show_entry["template_variables"]["sonarr_monitor"] == "future"
    assert show_entry["template_variables"]["sonarr_tag"] == ["ongoing", "priority"]
    assert show_entry["template_variables"]["item_sonarr_tag"] == ["watched", "tracked"]


def test_build_libraries_section_expands_franchise_dynamic_child_override_maps(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {"sho-library_shows-library": "Shows"},
            {
                "movies": {
                    "mov-library_movies-collection_franchise": True,
                    "mov-library_movies-template_collection_franchise_child_name_overrides": '{"10": "Skywalker Saga"}',
                    "mov-library_movies-template_collection_franchise_child_sync_mode_overrides": '{"10": "append"}',
                    "mov-library_movies-template_collection_franchise_child_radarr_tag_overrides": '{"10": "4k,franchise"}',
                    "mov-library_movies-template_collection_franchise_child_radarr_add_missing_overrides": '{"10": "true"}',
                }
            },
            {
                "shows": {
                    "sho-library_shows-collection_franchise": True,
                    "sho-library_shows-template_collection_franchise_child_summary_overrides": '{"1399": "Dragons and dynasties"}',
                    "sho-library_shows-template_collection_franchise_child_collection_order_overrides": '{"1399": "custom"}',
                    "sho-library_shows-template_collection_franchise_child_sonarr_monitor_overrides": '{"1399": "future"}',
                    "sho-library_shows-template_collection_franchise_child_item_sonarr_tag_overrides": '{"1399": "tracked,priority"}',
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    movie_entry = next(
        (entry for entry in libraries_section["libraries"]["Movies"]["collection_files"] if entry.get("default") == "franchise"),
        None,
    )
    show_entry = next(
        (entry for entry in libraries_section["libraries"]["Shows"]["collection_files"] if entry.get("default") == "franchise"),
        None,
    )

    assert movie_entry is not None
    assert show_entry is not None
    assert movie_entry["template_variables"]["name_10"] == "Skywalker Saga"
    assert movie_entry["template_variables"]["sync_mode_10"] == "append"
    assert movie_entry["template_variables"]["radarr_tag_10"] == ["4k", "franchise"]
    assert movie_entry["template_variables"]["radarr_add_missing_10"] is True
    assert show_entry["template_variables"]["summary_1399"] == "Dragons and dynasties"
    assert show_entry["template_variables"]["collection_order_1399"] == "custom"
    assert show_entry["template_variables"]["sonarr_monitor_1399"] == "future"
    assert show_entry["template_variables"]["item_sonarr_tag_1399"] == ["tracked", "priority"]


def test_build_libraries_section_emits_library_arr_overrides(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {"sho-library_shows-library": "Shows"},
            {},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-attribute_radarr_url": "http://radarr.local:7878",
                    "mov-library_movies-attribute_radarr_quality_profile": "HD-1080p",
                    "mov-library_movies-attribute_radarr_search": "true",
                    "mov-library_movies-attribute_radarr_add_existing": "false",
                }
            },
            {
                "shows": {
                    "sho-library_shows-attribute_sonarr_url": "http://sonarr.local:8989",
                    "sho-library_shows-attribute_sonarr_language_profile": "English",
                    "sho-library_shows-attribute_sonarr_monitor": "future",
                    "sho-library_shows-attribute_sonarr_season_folder": "true",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
        )

    movies = libraries_section["libraries"]["Movies"]["radarr"]
    shows = libraries_section["libraries"]["Shows"]["sonarr"]
    assert movies["url"] == "http://radarr.local:7878"
    assert movies["quality_profile"] == "HD-1080p"
    assert movies["search"] is True
    assert movies["add_existing"] is False
    assert shows["url"] == "http://sonarr.local:8989"
    assert shows["language_profile"] == "English"
    assert shows["monitor"] == "future"
    assert shows["season_folder"] is True


def test_build_config_includes_saved_library_metadata_files(app, isolated_config_dir, monkeypatch):
    import json

    from flask import session
    from modules import database, output

    config_name = "pytest_library_metadata_output"
    metadata_value = json.dumps(
        [
            {"type": "file", "location": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
            {"type": "folder", "location": "config\\metadata\\movies"},
            {"type": "url", "location": "https://example.com/movies_refresh.yml"},
        ]
    )

    database.save_section_data(
        name=config_name,
        section="libraries",
        validated=True,
        user_entered=True,
        data={
            "libraries": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-metadata_files": metadata_value,
                "mov-template_variables": {},
                "sho-template_variables": {},
            },
            "validated_at": "2026-05-19T00:00:00Z",
        },
    )

    monkeypatch.setattr(output.helpers, "ensure_json_schema", lambda: None)
    monkeypatch.setattr(
        output.helpers,
        "check_for_update",
        lambda: {
            "kometa_branch": "nightly",
            "branch": "develop",
            "local_version": "0.10.3-build2",
            "running_on": "Local-Windows",
        },
    )
    monkeypatch.setattr(output.helpers, "get_plex_summary", lambda: "Plex summary unavailable")
    monkeypatch.setattr(output.helpers, "get_quickstart_settings_summary", lambda: [])
    monkeypatch.setattr(output.helpers, "get_library_summaries", lambda _names: "Library summary unavailable")
    monkeypatch.setattr(output.jsonschema.Draft7Validator, "iter_errors", lambda self, parsed: [])
    monkeypatch.setitem(app.config, "QS_OPTIMIZE_DEFAULTS", False)

    with app.test_request_context("/step/900-kometa"):
        session["config_name"] = config_name
        _validated, _validation_error, _config_data, yaml_content, _validation_errors = output.build_config("single line", config_name=config_name)

    assert "metadata_files:" in yaml_content
    assert "libraries:\n  libraries:" not in yaml_content
    assert "godzilla.yml" in yaml_content
    assert "config\\metadata\\movies" in yaml_content
    assert "movies_refresh.yml" in yaml_content


def test_collapse_collection_data_template_vars_handles_direct_libraries_dict():
    from modules import output

    config_data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "oscars",
                        "template_variables": {
                            "data_starting": "first",
                        },
                    },
                    {
                        "default": "year",
                        "template_variables": {
                            "data_starting": "1880",
                            "data_ending": "current_year",
                        },
                    },
                ]
            }
        }
    }

    collapsed = output._collapse_collection_data_template_vars(config_data)
    entries = collapsed["libraries"]["Movies"]["collection_files"]

    assert entries[0]["template_variables"] == {"data": {"starting": "first"}}
    assert entries[1]["template_variables"] == {"data": {"starting": 1880, "ending": "current_year"}}


def test_collapse_collection_data_template_vars_handles_actor_style_data_blocks():
    from modules import output

    config_data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "actor",
                        "template_variables": {
                            "collection_section": "001",
                            "style": "signature",
                            "data_depth": 1,
                            "data_limit": 15,
                            "sort_by": "audience_rating.desc",
                        },
                    },
                    {
                        "default": "director",
                        "template_variables": {
                            "style": "signature",
                            "data_depth": 1,
                            "data_limit": 15,
                        },
                    },
                ]
            }
        }
    }

    collapsed = output._collapse_collection_data_template_vars(config_data)
    actor_tv = collapsed["libraries"]["Movies"]["collection_files"][0]["template_variables"]
    director_tv = collapsed["libraries"]["Movies"]["collection_files"][1]["template_variables"]

    assert actor_tv == {
        "collection_section": "001",
        "style": "signature",
        "sort_by": "audience_rating.desc",
        "data": {"depth": 1, "limit": 15},
    }
    assert director_tv == {
        "style": "signature",
        "data": {"depth": 1, "limit": 15},
    }


def test_collapse_collection_data_template_vars_removes_flat_data_keys_from_all_collection_entries():
    from modules import output

    config_data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "oscars",
                        "template_variables": {
                            "data_starting": "first",
                        },
                    },
                    {
                        "default": "actor",
                        "template_variables": {
                            "style": "signature",
                            "data_depth": 1,
                            "data_limit": 15,
                        },
                    },
                    {
                        "default": "year",
                        "template_variables": {
                            "data_starting": "1880",
                            "data_ending": "current_year",
                        },
                    },
                ]
            }
        }
    }

    collapsed = output._collapse_collection_data_template_vars(config_data)
    entries = collapsed["libraries"]["Movies"]["collection_files"]

    for entry in entries:
        template_variables = entry.get("template_variables", {})
        flat_data_keys = [key for key in template_variables.keys() if isinstance(key, str) and key.startswith("data_")]
        assert flat_data_keys == []
        if "data" in template_variables:
            assert isinstance(template_variables["data"], dict)


def test_normalize_collection_template_var_value_handles_dynamic_family_controls():
    from modules import output

    assert output._normalize_collection_template_var_value("append_include", '["US", "CA", "US"]') == ["US", "CA"]
    assert output._normalize_collection_template_var_value("remove_suffix", '["Collection", " Edition ", "Collection"]') == "Collection,Edition"
    assert output._normalize_collection_template_var_value(
        "addons",
        '{"Action": ["Adventure", "Adventure", "Thriller"], "Drama": "Crime, Mystery", "": ["Skip"]}',
    ) == {
        "Action": ["Adventure", "Thriller"],
        "Drama": ["Crime", "Mystery"],
    }
    assert output._normalize_collection_template_var_value(
        "append_addons",
        '{"Top 250": ["IMDb Top 250"]}',
    ) == {"Top 250": ["IMDb Top 250"]}
    assert output._normalize_collection_template_var_value(
        "tmdb_birthday",
        '{"this_month": true, "before": 7, "after": "2"}',
    ) == {"this_month": True, "before": 7, "after": 2}
    assert output._normalize_collection_template_var_value(
        "tmdb_birthday",
        "before=14, after=3",
    ) == {"before": 14, "after": 3}


def test_dynamic_family_template_var_normalization_matches_collection_export_shapes():
    from modules import output

    template_vars = {
        "include": '["US", "CA"]',
        "append_include": '["MX", "CA"]',
        "addons": '{"US": ["Canada", "Mexico"], "CA": "United States"}',
        "append_addons": '{"US": ["Brazil"]}',
        "remove_suffix": '["Collection"]',
    }

    for list_key in ("include", "exclude", "exclude_prefix"):
        if list_key not in template_vars:
            continue
        list_values = output._parse_string_list(template_vars.get(list_key))
        if list_values:
            template_vars[list_key] = list_values
        else:
            template_vars.pop(list_key, None)

    for template_key in list(template_vars.keys()):
        normalized_value = output._normalize_collection_template_var_value(template_key, template_vars.get(template_key))
        if normalized_value is None:
            template_vars.pop(template_key, None)
        else:
            template_vars[template_key] = normalized_value

    assert template_vars == {
        "include": ["US", "CA"],
        "append_include": ["MX", "CA"],
        "addons": {
            "US": ["Canada", "Mexico"],
            "CA": ["United States"],
        },
        "append_addons": {
            "US": ["Brazil"],
        },
        "remove_suffix": "Collection",
    }


def test_build_config_prunes_default_horizontal_ratings_offsets(app, monkeypatch):
    from flask import session
    from modules import output

    ratings_payload = {
        "validated": True,
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-movie-overlay_ratings": True,
            "mov-library_movies-movie-template_overlay_ratings[rating_alignment]": "horizontal",
            "mov-library_movies-movie-template_overlay_ratings[horizontal_position]": "left",
            "mov-library_movies-movie-template_overlay_ratings[vertical_position]": "center",
            "mov-library_movies-movie-template_overlay_ratings[back_height]": 80,
            "mov-library_movies-movie-template_overlay_ratings[back_width]": 270,
            "mov-library_movies-movie-template_overlay_ratings[back_padding]": 15,
            "mov-library_movies-movie-template_overlay_ratings[rating1]": "user",
            "mov-library_movies-movie-template_overlay_ratings[rating1_image]": "rt_tomato",
            "mov-library_movies-movie-template_overlay_ratings[rating1_horizontal_offset]": 30,
            "mov-library_movies-movie-template_overlay_ratings[rating1_vertical_offset]": -125,
            "mov-library_movies-movie-template_overlay_ratings[rating2]": "critic",
            "mov-library_movies-movie-template_overlay_ratings[rating2_image]": "imdb",
            "mov-library_movies-movie-template_overlay_ratings[rating2_horizontal_offset]": 345,
            "mov-library_movies-movie-template_overlay_ratings[rating2_vertical_offset]": 0,
            "mov-library_movies-movie-template_overlay_ratings[rating3]": "audience",
            "mov-library_movies-movie-template_overlay_ratings[rating3_image]": "tmdb",
            "mov-library_movies-movie-template_overlay_ratings[rating3_horizontal_offset]": 660,
            "mov-library_movies-movie-template_overlay_ratings[rating3_vertical_offset]": 125,
        },
    }

    monkeypatch.setattr(output.persistence, "retrieve_settings", lambda section: ratings_payload if section == "025-libraries" else {"validated": False})
    monkeypatch.setattr(output.helpers, "ensure_json_schema", lambda: None)
    monkeypatch.setattr(
        output.helpers,
        "check_for_update",
        lambda: {
            "kometa_branch": "nightly",
            "branch": "develop",
            "local_version": "0.10.3-build2",
            "running_on": "Local-Windows",
        },
    )
    monkeypatch.setattr(output.helpers, "get_plex_summary", lambda: "Plex summary unavailable")
    monkeypatch.setattr(output.helpers, "get_quickstart_settings_summary", lambda: [])
    monkeypatch.setattr(output.helpers, "get_library_summaries", lambda _names: "Library summary unavailable")
    monkeypatch.setattr(output.jsonschema.Draft7Validator, "iter_errors", lambda self, parsed: [])
    monkeypatch.setitem(app.config, "QS_OPTIMIZE_DEFAULTS", True)

    with app.test_request_context("/step/900-kometa"):
        session["config_name"] = "pytest_ratings_optimized"
        _validated, _validation_error, config_data, yaml_content, _validation_errors = output.build_config(
            "single line",
            config_name="pytest_ratings_optimized",
        )

    overlays = config_data["libraries"]["Movies"]["overlay_files"]
    ratings_entry = next((entry for entry in overlays if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None
    tv = ratings_entry.get("template_variables", {})
    assert "rating1_horizontal_offset" not in tv
    assert "rating2_horizontal_offset" not in tv
    assert "rating3_horizontal_offset" not in tv
    assert tv.get("rating1_vertical_offset") == -125
    assert "rating2_vertical_offset" not in tv
    assert tv.get("rating3_vertical_offset") == 125


def test_step_post_from_libraries_persists_metadata_files(client, isolated_config_dir, monkeypatch, qs_module):
    import json
    from pathlib import Path

    from modules import database

    config_name = "pytest_step_save_metadata_files"
    metadata_file = isolated_config_dir.parent / "metadata_source.yml"
    metadata_file.write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")
    metadata_value = json.dumps(
        [
            {"type": "file", "location": str(metadata_file), "validated": True},
            {"type": "url", "location": "https://example.com/movies_refresh.yml", "validated": True},
        ]
    )

    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
    monkeypatch.setattr(qs_module.validations, "validate_metadata_file_payload", lambda _payload: (True, ""))
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
            "config_valid": True,
        },
    )

    resp = client.post(
        "/step/900-kometa",
        data={
            "configSelector": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-metadata_files": metadata_value,
        },
        headers={"Referer": "http://localhost/step/025-libraries"},
    )

    assert resp.status_code == 200

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert validated is False
    assert user_entered is True
    assert stored["libraries"]["mov-library_movies-library"] == "Movies"
    saved_entries = json.loads(stored["libraries"]["mov-library_movies-metadata_files"])
    assert saved_entries[0]["type"] == "file"
    assert saved_entries[0]["location"].startswith(f"config/{config_name}/metadata_files/mov-library_movies/")
    assert saved_entries[0]["validated"] is True
    assert saved_entries[1] == {"type": "url", "location": "https://example.com/movies_refresh.yml", "validated": True}
    managed_file = isolated_config_dir.parent / Path(saved_entries[0]["location"])
    assert managed_file.exists()
    assert managed_file.read_text(encoding="utf-8") == metadata_file.read_text(encoding="utf-8")


def test_step_post_from_libraries_persists_collection_files(client, isolated_config_dir, monkeypatch, qs_module):
    import json
    from pathlib import Path

    from modules import database

    config_name = "pytest_step_save_collection_files"
    collection_file = isolated_config_dir.parent / "collection_source.yml"
    collection_file.write_text("collections:\n  test:\n    plex_search:\n      any:\n        title: Example\n", encoding="utf-8")
    collection_value = json.dumps(
        [
            {"type": "file", "location": str(collection_file), "validated": True},
            {"type": "url", "location": "https://example.com/movies_refresh.yml", "validated": True},
        ]
    )

    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
    monkeypatch.setattr(qs_module.validations, "validate_collection_file_payload", lambda _payload: (True, "", {}))
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
            "config_valid": True,
        },
    )

    resp = client.post(
        "/step/900-kometa",
        data={
            "configSelector": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_files": collection_value,
        },
        headers={"Referer": "http://localhost/step/025-libraries"},
    )

    assert resp.status_code == 200

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert validated is False
    assert user_entered is True
    assert stored["libraries"]["mov-library_movies-library"] == "Movies"
    saved_entries = json.loads(stored["libraries"]["mov-library_movies-collection_files"])
    assert saved_entries[0]["type"] == "file"
    assert saved_entries[0]["location"].startswith(f"config/{config_name}/collection_files/mov-library_movies/")
    assert saved_entries[0]["validated"] is True
    assert saved_entries[1] == {"type": "url", "location": "https://example.com/movies_refresh.yml", "validated": True}
    managed_file = isolated_config_dir.parent / Path(saved_entries[0]["location"])
    assert managed_file.exists()
    assert managed_file.read_text(encoding="utf-8") == collection_file.read_text(encoding="utf-8")


def test_step_post_from_libraries_persists_library_arr_overrides(client, isolated_config_dir, monkeypatch, qs_module):
    from modules import database

    config_name = "pytest_step_save_library_arr_overrides"

    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
    monkeypatch.setattr(
        qs_module.validations,
        "validate_radarr_payload",
        lambda _payload: ({"valid": True, "root_folders": [{"path": "/movies"}], "quality_profiles": [{"name": "HD-1080p"}]}, 200),
    )
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
            "config_valid": True,
        },
    )
    original_retrieve_settings = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(target):
        if target == "110-radarr":
            return {"radarr": {"url": "http://global-radarr:7878", "token": "global-token"}}
        return original_retrieve_settings(target)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    resp = client.post(
        "/step/900-kometa",
        data={
            "configSelector": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-attribute_assets_for_all": "true",
            "mov-library_movies-attribute_radarr_root_folder_path": "/movies",
            "mov-library_movies-attribute_radarr_quality_profile": "HD-1080p",
            "mov-library_movies-attribute_radarr_search": "true",
            "mov-library_movies-attribute_radarr_add_existing": "false",
        },
        headers={"Referer": "http://localhost/step/025-libraries"},
    )

    assert resp.status_code == 200

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert validated is False
    assert user_entered is True
    assert stored["libraries"]["mov-library_movies-attribute_radarr_root_folder_path"] == "/movies"
    assert stored["libraries"]["mov-library_movies-attribute_radarr_quality_profile"] == "HD-1080p"
    assert stored["libraries"]["mov-library_movies-attribute_radarr_search"] is True
    assert stored["libraries"]["mov-library_movies-attribute_radarr_add_existing"] is False


def test_step_post_from_libraries_accepts_literal_none_arr_url_override(client, isolated_config_dir, monkeypatch, qs_module):
    config_name = "pytest_step_save_library_arr_none_url"

    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
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
            "config_valid": True,
        },
    )

    resp = client.post(
        "/step/900-kometa",
        data={
            "configSelector": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-attribute_radarr_url": "None",
        },
        headers={"Referer": "http://localhost/step/025-libraries"},
    )

    assert resp.status_code == 200
    assert b"Invalid values:" not in resp.data


def test_step_post_from_libraries_rejects_invalid_metadata_files(client, isolated_config_dir, monkeypatch, qs_module):
    from modules import database

    class _Resp:
        status_code = 404
        reason = "Not Found"
        text = ""

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
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
            "config_valid": True,
        },
    )

    config_name = "pytest_invalid_step_metadata_files"
    resp = client.post(
        "/step/900-kometa",
        data={
            "configSelector": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-metadata_files": '[{"type":"url","location":"https://example.com/missing.yml"}]',
        },
        headers={"Referer": "http://localhost/step/025-libraries"},
    )

    assert resp.status_code == 200
    assert b"Invalid values:" in resp.data

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert stored is None
    assert validated is False
    assert user_entered is False


def test_validate_library_service_overrides_endpoint_returns_options(client, monkeypatch, qs_module):
    original_retrieve_settings = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(target):
        if target == "110-radarr":
            return {"radarr": {"url": "http://global-radarr:7878", "token": "global-token"}}
        return original_retrieve_settings(target)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)
    monkeypatch.setattr(
        qs_module.validations,
        "validate_radarr_payload",
        lambda _payload: (
            {
                "valid": True,
                "root_folders": [{"path": "/movies"}],
                "quality_profiles": [{"name": "HD-1080p"}],
            },
            200,
        ),
    )

    resp = client.post(
        "/validate_library_service_overrides/mov-library_movies",
        json={
            "mov-library_movies-library": "Movies",
            "mov-library_movies-attribute_radarr_root_folder_path": "/movies",
            "mov-library_movies-attribute_radarr_quality_profile": "HD-1080p",
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is True
    assert payload["root_folders"][0]["path"] == "/movies"
    assert payload["quality_profiles"][0]["name"] == "HD-1080p"


def test_validate_library_service_overrides_endpoint_rejects_unknown_profile(client, monkeypatch, qs_module):
    original_retrieve_settings = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(target):
        if target == "120-sonarr":
            return {"sonarr": {"url": "http://global-sonarr:8989", "token": "global-token"}}
        return original_retrieve_settings(target)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)
    monkeypatch.setattr(
        qs_module.validations,
        "validate_sonarr_payload",
        lambda _payload: (
            {
                "valid": True,
                "root_folders": [{"path": "/shows"}],
                "quality_profiles": [{"name": "HD-TV"}],
                "language_profiles": [{"name": "English"}],
            },
            200,
        ),
    )

    resp = client.post(
        "/validate_library_service_overrides/sho-library_shows",
        json={
            "sho-library_shows-library": "Shows",
            "sho-library_shows-attribute_sonarr_quality_profile": "4K-UHD",
        },
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert any("unknown quality profile" in error for error in payload["errors"])


def test_validate_all_services_flags_invalid_library_arr_overrides(client, monkeypatch, qs_module):
    import copy

    settings_map = {
        "010-plex": {"validated": True, "plex": {}},
        "025-libraries": {
            "libraries": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-attribute_assets_for_all": "true",
                "mov-library_movies-attribute_radarr_url": "http://alt-radarr:7878",
                "mov-library_movies-attribute_radarr_token": "alt-token",
                "mov-library_movies-attribute_radarr_root_folder_path": "/bad-root",
            }
        },
    }

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda target: copy.deepcopy(settings_map.get(target, {})))
    monkeypatch.setattr(
        qs_module.validations,
        "validate_radarr_payload",
        lambda _payload: (
            {
                "valid": True,
                "root_folders": [{"path": "/movies"}],
                "quality_profiles": [{"name": "HD-1080p"}],
            },
            200,
        ),
    )

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_bulk_invalid_arr"

    resp = client.post("/validate_all_services")
    assert resp.status_code == 200
    payload = resp.get_json()
    libraries_result = payload["results"]["025-libraries"]
    assert libraries_result["status"] == "failed"
    assert libraries_result["reason"] == "invalid_arr_overrides"
    assert any("/bad-root" in detail for detail in libraries_result["details"])


def test_validate_all_services_flags_invalid_external_kometa_paths(client, monkeypatch, qs_module, tmp_path):
    import copy
    from modules import database

    config_name = "pytest_bulk_invalid_external_kometa"
    missing_external = tmp_path / "missing-external-kometa-config"

    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=False,
        user_entered=True,
        data={
            "kometa": {
                "install_mode": "external",
                "external_config_root": str(missing_external),
            }
        },
    )

    settings_map = {
        "010-plex": {"validated": True, "plex": {}},
        "025-libraries": {
            "libraries": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-attribute_assets_for_all": "true",
            }
        },
    }

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda target: copy.deepcopy(settings_map.get(target, {})))

    with client.session_transaction() as sess:
        sess["config_name"] = config_name

    resp = client.post("/validate_all_services")
    assert resp.status_code == 200
    payload = resp.get_json()
    start_result = payload["results"]["001-start"]
    assert start_result["status"] == "failed"
    assert start_result["reason"] == "invalid_paths"
    assert any(str(missing_external) in detail for detail in start_result["details"])


def test_step_post_from_libraries_rejects_invalid_collection_files(client, isolated_config_dir, monkeypatch, qs_module):
    from modules import database

    class _Resp:
        status_code = 404
        reason = "Not Found"
        text = ""

    monkeypatch.setattr(qs_module.validations.requests, "get", lambda *_args, **_kwargs: _Resp())
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (True, None, {}, "test: true\n", []))
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
            "config_valid": True,
        },
    )

    config_name = "pytest_invalid_step_collection_files"
    resp = client.post(
        "/step/900-kometa",
        data={
            "configSelector": config_name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_files": '[{"type":"url","location":"https://example.com/missing.yml"}]',
        },
        headers={"Referer": "http://localhost/step/025-libraries"},
    )

    assert resp.status_code == 200
    assert b"Invalid values:" in resp.data

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert stored is None
    assert validated is False
    assert user_entered is False


def test_helpers_extract_library_name_supports_metadata_files():
    from modules import helpers

    assert helpers.extract_library_name("mov-library_movies-metadata_files") == "movies"
    assert helpers.extract_library_name("sho-library_tv_shows-metadata_files") == "tv_shows"


def test_update_quickstart_settings_supports_independent_imagemaid_log_retention(client, qs_module, isolated_config_dir, monkeypatch):
    from modules import helpers

    writes = {}
    original_kometa_keep = qs_module.app.config.get("QS_KOMETA_LOG_KEEP", 0)
    original_imagemaid_keep = qs_module.app.config.get("QS_IMAGEMAID_LOG_KEEP", 0)

    def fake_update_env_variable(key, value):
        writes[key] = value

    monkeypatch.setattr(helpers, "update_env_variable", fake_update_env_variable)
    try:
        resp = client.post(
            "/update-quickstart-settings",
            json={"kometa_log_keep": 7, "imagemaid_log_keep": 3},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["kometa_log_keep"] == 7
        assert payload["imagemaid_log_keep"] == 3
        assert qs_module.app.config["QS_KOMETA_LOG_KEEP"] == 7
        assert qs_module.app.config["QS_IMAGEMAID_LOG_KEEP"] == 3
        assert writes["QS_KOMETA_LOG_KEEP"] == "7"
        assert writes["QS_IMAGEMAID_LOG_KEEP"] == "3"
    finally:
        qs_module.app.config["QS_KOMETA_LOG_KEEP"] = original_kometa_keep
        qs_module.app.config["QS_IMAGEMAID_LOG_KEEP"] = original_imagemaid_keep


def test_kometa_page_defaults_header_style_to_single_line(client, isolated_config_dir, monkeypatch, qs_module):
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
            "config_valid": True,
        },
    )
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_, **__: (True, None, {}, "test: true\n", []))

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200
    assert b'name="header_style" value="single line"' in resp.data


def test_kometa_page_restores_header_style_from_kometa_section(client, isolated_config_dir, monkeypatch, qs_module):
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
            "config_valid": True,
        },
    )
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_, **__: (True, None, {}, "test: true\n", []))

    original_retrieve_settings = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(target):
        if target == "900-kometa":
            return {"kometa": {"header_style": "standard"}}
        return original_retrieve_settings(target)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200
    assert b'name="header_style" value="standard"' in resp.data


def test_validate_plex_invalid_url(client):
    resp = client.post("/validate_plex", json={"plex_url": "not-a-url", "plex_token": "x"})
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "Plex URL" in payload["error"]


def test_validate_plex_bad_token(client, monkeypatch, qs_module):
    def fake_validate(_data):
        return qs_module.jsonify({"valid": False, "error": "Invalid Plex URL or Token: bad token"})

    monkeypatch.setattr(qs_module.validations, "validate_plex_server", fake_validate)

    resp = client.post("/validate_plex", json={"plex_url": "http://localhost:32400", "plex_token": "bad"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["valid"] is False
    assert "bad token" in payload["error"]


def test_validate_plex_persists_telemetry_for_current_config(client, monkeypatch, qs_module):
    calls = {"save_settings": 0, "save_section": 0}

    def fake_validate(_data):
        return qs_module.jsonify(
            {
                "validated": True,
                "db_cache": 2048,
                "user_list": ["User One"],
                "music_libraries": [],
                "movie_libraries": ["Movies"],
                "show_libraries": ["Shows"],
                "has_plex_pass": True,
            }
        )

    telemetry = {
        "server_name": "Test Plex",
        "maintenance_window": "02:00 – 05:00",
        "platform": "Windows",
    }

    monkeypatch.setattr(qs_module.validations, "validate_plex_server", fake_validate)
    monkeypatch.setattr(qs_module.helpers, "get_plex_metadata", lambda **_kwargs: telemetry)
    monkeypatch.setattr(qs_module.persistence, "save_settings", lambda *_args, **_kwargs: calls.__setitem__("save_settings", calls["save_settings"] + 1))
    monkeypatch.setattr(qs_module.database, "save_section_data", lambda **_kwargs: calls.__setitem__("save_section", calls["save_section"] + 1))

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_validate_plex"

    resp = client.post("/validate_plex", json={"plex_url": "http://localhost:32400", "plex_token": "token"})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["validated"] is True
    assert payload["maintenance_window"] == "02:00 – 05:00"
    assert calls == {"save_settings": 1, "save_section": 1}


def test_validate_plex_fetches_sections_once(app, monkeypatch, qs_module):
    qs_module.helpers.clear_plex_discovery_cache()
    calls = {"sections": 0}

    class FakeSetting:
        value = 2048

    class FakeSettings:
        def get(self, _name):
            return FakeSetting()

    class FakeUser:
        title = "User One"

    class FakeAccount:
        subscriptionActive = True

        def users(self):
            return [FakeUser()]

    class FakeSection:
        def __init__(self, title, section_type):
            self.title = title
            self.type = section_type

    class FakeLibrary:
        def sections(self):
            calls["sections"] += 1
            return [
                FakeSection("Movies", "movie"),
                FakeSection("Shows", "show"),
                FakeSection("Music", "artist"),
            ]

    class FakePlex:
        settings = FakeSettings()
        library = FakeLibrary()

        def __init__(self, *_args, **_kwargs):
            pass

        def myPlexAccount(self):
            return FakeAccount()

    monkeypatch.setattr(qs_module.validations, "PlexServer", FakePlex)

    with app.app_context():
        resp = qs_module.validations.validate_plex_server({"plex_url": "http://localhost:32400", "plex_token": "token"})

    payload = resp.get_json()
    assert payload["validated"] is True
    assert payload["movie_libraries"] == ["Movies"]
    assert payload["show_libraries"] == ["Shows"]
    assert payload["music_libraries"] == ["Music"]
    assert calls["sections"] == 1


def test_refresh_plex_libraries_reuses_short_lived_cache(client, monkeypatch, qs_module):
    qs_module.helpers.clear_plex_discovery_cache()
    calls = {"validate": 0, "metadata": 0, "update": 0, "save": 0}

    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda _name: ("http://localhost:32400", "token"))
    monkeypatch.setattr(qs_module.persistence, "get_dummy_data", lambda _name: {"url": "http://placeholder", "token": "placeholder"})

    def fake_validate(_data):
        calls["validate"] += 1
        return qs_module.jsonify(
            {
                "validated": True,
                "db_cache": 2048,
                "user_list": ["User One"],
                "music_libraries": [],
                "movie_libraries": ["Movies"],
                "show_libraries": ["Shows"],
                "has_plex_pass": True,
            }
        )

    def fake_metadata(**_kwargs):
        calls["metadata"] += 1
        return {
            "plex_pass": True,
            "server_name": "Test Plex",
            "version": "1.0",
            "platform": "Linux",
            "update_channel": "Public update channel",
            "libraries": {"Movies": {"type": "movie", "movie_count": 10}},
        }

    monkeypatch.setattr(qs_module.validations, "validate_plex_server", fake_validate)
    monkeypatch.setattr(qs_module.helpers, "get_plex_metadata", fake_metadata)
    monkeypatch.setattr(qs_module.persistence, "update_stored_plex_libraries", lambda *_args, **_kwargs: calls.__setitem__("update", calls["update"] + 1))
    monkeypatch.setattr(qs_module.persistence, "save_settings", lambda *_args, **_kwargs: calls.__setitem__("save", calls["save"] + 1))

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_plex_cache"

    first = client.post("/refresh_plex_libraries")
    second = client.post("/refresh_plex_libraries")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json() == second.get_json()
    assert calls == {"validate": 1, "metadata": 1, "update": 2, "save": 2}


def test_yaml_generation_sets_session_and_redacts(client, isolated_config_dir, monkeypatch, qs_module):
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
            "config_valid": True,
        },
    )

    def fake_build_config(*_args, **_kwargs):
        return True, None, {"plex": {"token": "secret"}}, "plex:\n  token: secret\n", []

    monkeypatch.setattr(qs_module.output, "build_config", fake_build_config)

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_yaml"

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("yaml_content") == "plex:\n  token: secret\n"

    redacted = client.get("/download_redacted")
    assert redacted.status_code == 200
    assert b"(redacted)" in redacted.data
    assert b"secret" not in redacted.data


def test_download_redacted_bundles_managed_overlay_folder(client, isolated_config_dir):
    import io
    import zipfile

    config_name = "pytest_redacted_bundle"
    managed_dir = isolated_config_dir / config_name / "overlay_files" / "mov-library_movies" / "seasonal"
    managed_dir.mkdir(parents=True, exist_ok=True)
    managed_file = managed_dir / "awards.yml"
    managed_file.write_text(
        "overlays:\n  test:\n    template:\n      - name: ribbon\nurl: http://internal.example\ntoken: secret-value\n",
        encoding="utf-8",
    )

    with client.session_transaction() as sess:
        sess["config_name"] = config_name
        sess["yaml_content"] = "libraries:\n" "  Movies:\n" "    overlay_files:\n" f"      - folder: {config_name}/overlay_files/mov-library_movies/seasonal\n"

    resp = client.get("/download_redacted")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.data)) as archive:
        names = set(archive.namelist())
        assert "config_redacted.yml" in names
        bundled_name = f"{config_name}/overlay_files/mov-library_movies/seasonal/awards.yml"
        assert bundled_name in names
        bundled_text = archive.read(bundled_name).decode("utf-8")
        assert "(redacted)" in bundled_text
        assert "secret-value" not in bundled_text
        assert "internal.example" not in bundled_text


def test_upload_fonts_store_in_active_config_directory(client, isolated_config_dir):
    import io

    config_name = "pytest_font_upload"
    with client.session_transaction() as sess:
        sess["config_name"] = config_name

    resp = client.post(
        "/upload-fonts",
        data={"fonts": (io.BytesIO(b"font-bytes"), "Poster.ttf")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "success"
    assert "Poster.ttf" in payload["fonts"]
    assert (isolated_config_dir / config_name / "fonts" / "Poster.ttf").exists()
    assert not (isolated_config_dir / "fonts" / "Poster.ttf").exists()


def test_download_bundle_adopts_legacy_fonts_into_active_config(client, isolated_config_dir):
    import io
    import zipfile

    config_name = "pytest_font_migration"
    legacy_font_dir = isolated_config_dir / "fonts"
    legacy_font_dir.mkdir(parents=True, exist_ok=True)
    (legacy_font_dir / "Poster.ttf").write_bytes(b"legacy-font")

    with client.session_transaction() as sess:
        sess["config_name"] = config_name
        sess["yaml_content"] = "settings:\n  cache: true\n"

    resp = client.get("/download")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.data)) as archive:
        names = set(archive.namelist())
        assert f"{config_name}/fonts/Poster.ttf" in names

    migrated_font = isolated_config_dir / config_name / "fonts" / "Poster.ttf"
    assert migrated_font.exists()
    assert migrated_font.read_bytes() == b"legacy-font"


def test_download_bundle_places_fonts_under_config_name(client, isolated_config_dir):
    import io
    import zipfile

    config_name = "pytest_font_bundle"
    font_dir = isolated_config_dir / config_name / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    (font_dir / "Poster.ttf").write_bytes(b"font-bytes")

    with client.session_transaction() as sess:
        sess["config_name"] = config_name
        sess["yaml_content"] = "settings:\n  cache: true\n"

    resp = client.get("/download")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"

    with zipfile.ZipFile(io.BytesIO(resp.data)) as archive:
        names = set(archive.namelist())
        assert "config.yml" in names
        assert f"{config_name}/fonts/Poster.ttf" in names


def test_import_config_preview_rejects_zip_with_unsupported_entries(client):
    import io
    import zipfile

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.yml", "settings:\n  cache: true\n")
        archive.writestr("unexpected.exe", b"nope")
    bundle.seek(0)

    resp = client.post(
        "/import-config/preview",
        data={"config_name": "pytest_bad_bundle", "file": (bundle, "bundle.zip")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "unsupported entries" in payload["message"].lower()
    assert "unexpected.exe" in payload["message"]


def test_import_config_preview_handles_yaml_date_scalars_in_cache(client):
    import io
    import json
    from pathlib import Path

    yaml_text = "settings:\n  cache: true\n  release_date: 2026-06-03\n"

    resp = client.post(
        "/import-config/preview",
        data={"config_name": "pytest_import_dates", "file": (io.BytesIO(yaml_text.encode("utf-8")), "config.yml")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    payload = resp.get_json()
    assert payload["success"] is True

    with client.session_transaction() as sess:
        cache_path = sess["import_preview_path"]

    cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    assert cached["config_data"]["settings"]["release_date"] == "2026-06-03"


def test_import_config_preview_returns_json_on_unexpected_error(client, monkeypatch, qs_module):
    import io

    def _boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(qs_module.importer, "prepare_import_payload", _boom)

    resp = client.post(
        "/import-config/preview",
        data={"config_name": "pytest_import_boom", "file": (io.BytesIO(b"settings:\n  cache: true\n"), "config.yml")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Import preview failed" in payload["message"]
    assert "kaboom" in payload["message"]


def test_import_config_preview_handles_tuple_validation_response(client, monkeypatch, qs_module):
    import io
    from flask import jsonify

    with qs_module.app.app_context():
        tuple_response = (
            jsonify({"valid": False, "validated": False, "error": "Bad Plex credentials from tuple response."}),
            400,
        )

    monkeypatch.setattr(qs_module.validations, "validate_plex_server", lambda _payload: tuple_response)

    yaml_text = "plex:\n" "  url: http://plex.local\n" "  token: imported-token\n" "libraries:\n" "  Movies:\n" "    metadata_files:\n" "      - default: basic\n"

    resp = client.post(
        "/import-config/preview",
        data={"config_name": "pytest_import_tuple", "file": (io.BytesIO(yaml_text.encode("utf-8")), "config.yml")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "Bad Plex credentials from tuple response." in payload["message"]


def test_yaml_generation_missing_sections_shows_error(client, isolated_config_dir, monkeypatch, qs_module):
    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *_args, **_kwargs: {
            "stage": "config",
            "todo_count": 0,
            "todo_blockers": [],
            "bulk_validation_fresh": True,
            "bulk_validation_at": qs_module.utc_now_iso(),
            "validation_ttl_hours": 12,
            "can_build_config": True,
            "config_valid": False,
        },
    )
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (False, "Missing sections", {}, "", []),
    )

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_yaml_missing"

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200
    assert b"Missing sections" in resp.data


def test_final_page_todo_gate_skips_config_generation(client, isolated_config_dir, monkeypatch, qs_module):
    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *_args, **_kwargs: {
            "stage": "todo",
            "todo_count": 1,
            "todo_blockers": [{"key": "010-plex", "label": "Plex", "state": "warn", "group": "required"}],
            "bulk_validation_fresh": False,
            "bulk_validation_at": "",
            "validation_ttl_hours": 12,
            "can_build_config": False,
            "config_valid": False,
        },
    )
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("build_config should not run")))

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_final_todo_gate"

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200
    assert b"Resolve setup tasks first" in resp.data
    assert b"Validation status" not in resp.data
    assert b"Section Style" not in resp.data
    assert b"Thank you for using Quickstart" not in resp.data


def test_final_page_stale_bulk_gate_skips_config_generation(client, isolated_config_dir, monkeypatch, qs_module):
    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *_args, **_kwargs: {
            "stage": "freshness",
            "todo_count": 0,
            "todo_blockers": [],
            "bulk_validation_fresh": False,
            "bulk_validation_at": "",
            "validation_ttl_hours": 12,
            "can_build_config": False,
            "config_valid": False,
        },
    )
    monkeypatch.setattr(qs_module.output, "build_config", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("build_config should not run")))

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_final_stale_gate"

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200
    assert b"Validation is stale" in resp.data
    assert b'data-auto-validate="true"' in resp.data


def test_final_page_preserves_annotated_yaml_content(client, isolated_config_dir, monkeypatch, qs_module):
    annotated_yaml = (
        "# yaml-language-server: $schema=https://example.invalid/config-schema.json\n\n" "#==================== KOMETA ====================#\n\n" "plex:\n" "  token: secret\n"
    )
    captured = {}

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
    monkeypatch.setattr(
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (True, "", {"plex": {"token": "secret"}}, annotated_yaml, []),
    )
    monkeypatch.setattr(
        qs_module,
        "_normalize_generated_config_library_files",
        lambda config_data, _config_name: (config_data, False, []),
    )

    def fake_save_to_named_config(yaml_text, config_name, used_fonts):
        captured["yaml_text"] = yaml_text
        captured["config_name"] = config_name
        captured["used_fonts"] = used_fonts
        return f"{config_name}.yml"

    monkeypatch.setattr(qs_module.helpers, "save_to_named_config", fake_save_to_named_config)

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_final_annotated_yaml"

    resp = client.get("/step/900-kometa")
    assert resp.status_code == 200
    assert b"yaml-language-server" in resp.data

    with client.session_transaction() as sess:
        assert sess.get("yaml_content") == annotated_yaml

    assert captured["yaml_text"] == annotated_yaml
    assert captured["config_name"] == "pytest_final_annotated_yaml"


def test_switch_config_returns_new_workspace_status(client, isolated_config_dir, app, qs_module):
    from modules import database

    stale_config = "pytest_switch_stale"
    ready_config = "pytest_switch_ready"

    database.save_section_data(
        name=stale_config,
        section="start",
        validated=True,
        user_entered=True,
        data={"start": {"config_name": stale_config}, "validated_at": qs_module.utc_now_iso()},
    )

    for section in ("start", "plex", "tmdb", "libraries", "settings"):
        database.save_section_data(
            name=ready_config,
            section=section,
            validated=True,
            user_entered=True,
            data={section: {"configured": True}, "validated_at": qs_module.utc_now_iso()},
        )

    with client.session_transaction() as sess:
        sess["config_name"] = stale_config

    resp = client.post("/switch-config", json={"name": ready_config})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["name"] == ready_config
    assert payload["workspace_status"]["step_statuses"]["010-plex"] == "ok"

    with client.session_transaction() as sess:
        assert sess["config_name"] == ready_config


def test_clear_data_removes_config_artifacts(client, isolated_config_dir, app):
    from modules import database
    from pathlib import Path

    config_name = "pytest_delete_me"
    config_file = isolated_config_dir / f"{config_name}_config.yml"
    archive_dir = isolated_config_dir / "archives" / config_name
    archive_file = archive_dir / f"{config_name}_config_1.yml"
    kometa_config = app.config["KOMETA_ROOT"]

    config_file.write_text("test: true\n", encoding="utf-8")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_file.write_text("archived: true\n", encoding="utf-8")
    kometa_path = Path(kometa_config) / "config"
    kometa_path.mkdir(parents=True, exist_ok=True)
    (kometa_path / f"{config_name}_config.yml").write_text("test: true\n", encoding="utf-8")

    database.save_section_data(
        name=config_name,
        section="start",
        validated=True,
        user_entered=True,
        data={"start": {"config_name": config_name}},
    )

    resp = client.get(f"/clear_data/{config_name}")
    assert resp.status_code == 302
    assert database.get_unique_config_names() == []
    assert not config_file.exists()
    assert not archive_dir.exists()
    assert not (kometa_path / f"{config_name}_config.yml").exists()


def test_bulk_delete_configs_removes_config_artifacts(client, isolated_config_dir, app):
    from modules import database
    from pathlib import Path

    first = "pytest_bulk_one"
    second = "pytest_bulk_two"
    kometa_path = Path(app.config["KOMETA_ROOT"]) / "config"
    kometa_path.mkdir(parents=True, exist_ok=True)

    for name in (first, second):
        (isolated_config_dir / f"{name}_config.yml").write_text("test: true\n", encoding="utf-8")
        archive_dir = isolated_config_dir / "archives" / name
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / f"{name}_config_1.yml").write_text("archived: true\n", encoding="utf-8")
        (isolated_config_dir / name / "metadata_files" / "mov-library_movies").mkdir(parents=True, exist_ok=True)
        (isolated_config_dir / name / "overlay_files" / "mov-library_movies").mkdir(parents=True, exist_ok=True)
        (kometa_path / f"{name}_config.yml").write_text("test: true\n", encoding="utf-8")
        database.save_section_data(
            name=name,
            section="start",
            validated=True,
            user_entered=True,
            data={"start": {"config_name": name}},
        )

    with client.session_transaction() as sess:
        sess["config_name"] = first

    resp = client.post("/bulk-delete-configs", json={"names": [first, second]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert set(payload["deleted"]) == {first, second}
    assert database.get_unique_config_names() == []

    for name in (first, second):
        assert not (isolated_config_dir / f"{name}_config.yml").exists()
        assert not (isolated_config_dir / "archives" / name).exists()
        assert not (isolated_config_dir / name / "metadata_files").exists()
        assert not (isolated_config_dir / name / "overlay_files").exists()
        assert not (kometa_path / f"{name}_config.yml").exists()


def test_orphaned_config_artifacts_route_lists_disk_only_bundles(client, isolated_config_dir, app):
    from modules import database
    from pathlib import Path

    keep_name = "keep_me"
    orphan_name = "delete_me"
    archive_dir = isolated_config_dir / "archives" / orphan_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{orphan_name}_config_1.yml").write_text("archive: true\n", encoding="utf-8")
    (isolated_config_dir / f"{orphan_name}_config.yml").write_text("current: true\n", encoding="utf-8")
    managed_dir = isolated_config_dir / orphan_name / "metadata_files" / "mov-library_movies"
    managed_dir.mkdir(parents=True, exist_ok=True)
    (managed_dir / "movies.yml").write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")

    kometa_path = Path(app.config["KOMETA_ROOT"]) / "config"
    kometa_path.mkdir(parents=True, exist_ok=True)
    (kometa_path / f"{orphan_name}_config.yml").write_text("kometa: true\n", encoding="utf-8")

    database.save_section_data(
        name=keep_name,
        section="start",
        validated=True,
        user_entered=True,
        data={"start": {"config_name": keep_name}},
    )

    resp = client.get("/orphaned-config-artifacts")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert len(payload["orphans"]) == 1
    orphan = payload["orphans"][0]
    assert orphan["name"] == orphan_name
    assert orphan["has_current_file"] is True, orphan
    assert orphan["has_kometa_copy"] is True
    assert orphan["has_archive_dir"] is True
    assert orphan["archive_count"] == 1
    assert any("metadata_files" in path for path in orphan["paths"])


def test_orphaned_config_artifacts_route_lists_font_only_default_bundle(client, isolated_config_dir):
    default_font_dir = isolated_config_dir / "default" / "fonts"
    default_font_dir.mkdir(parents=True, exist_ok=True)
    (default_font_dir / "Poster.ttf").write_bytes(b"default-font")

    resp = client.get("/orphaned-config-artifacts")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    orphan = next((item for item in payload["orphans"] if item["name"] == "default"), None)
    assert orphan is not None
    assert any(path.endswith("\\default") or path.endswith("/default") for path in orphan["paths"])


def test_delete_orphaned_config_artifacts_route_removes_selected_bundle(client, isolated_config_dir, app):
    from pathlib import Path

    orphan_name = "delete_me"
    archive_dir = isolated_config_dir / "archives" / orphan_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{orphan_name}_config_1.yml").write_text("archive: true\n", encoding="utf-8")
    (isolated_config_dir / f"{orphan_name}_config.yml").write_text("current: true\n", encoding="utf-8")
    managed_dir = isolated_config_dir / orphan_name / "collection_files" / "mov-library_movies"
    managed_dir.mkdir(parents=True, exist_ok=True)
    (managed_dir / "collections.yml").write_text("collections:\n  test:\n    plex_search:\n      any:\n        title: Example\n", encoding="utf-8")

    kometa_path = Path(app.config["KOMETA_ROOT"]) / "config"
    kometa_path.mkdir(parents=True, exist_ok=True)
    (kometa_path / f"{orphan_name}_config.yml").write_text("kometa: true\n", encoding="utf-8")

    resp = client.post("/orphaned-config-artifacts/delete", json={"names": [orphan_name]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted"] == [orphan_name]
    assert not (isolated_config_dir / f"{orphan_name}_config.yml").exists(), payload
    assert not archive_dir.exists()
    assert not (isolated_config_dir / orphan_name / "collection_files").exists()
    assert not (kometa_path / f"{orphan_name}_config.yml").exists()


def test_delete_orphaned_config_artifacts_route_removes_font_only_default_bundle(client, isolated_config_dir):
    default_font_dir = isolated_config_dir / "default" / "fonts"
    default_font_dir.mkdir(parents=True, exist_ok=True)
    (default_font_dir / "Poster.ttf").write_bytes(b"default-font")

    resp = client.post("/orphaned-config-artifacts/delete", json={"names": ["default"]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted"] == ["default"]
    assert not (isolated_config_dir / "default").exists()


def test_delete_orphaned_config_artifacts_route_removes_copy_named_yaml(client, isolated_config_dir):
    copied_path = isolated_config_dir / "qs_copy_cleanup_probe - Copy (10)_config.yml"
    copied_name = "qs_copy_cleanup_probe_-_copy_(10)"
    copied_path.write_text("current: true\n", encoding="utf-8")

    resp = client.post("/orphaned-config-artifacts/delete", json={"names": [copied_name]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted"] == [copied_name.lower().replace(" ", "_")]
    assert not copied_path.exists()


def test_orphaned_config_artifact_versions_returns_newest_first(client, isolated_config_dir):
    import os
    import time

    orphan_name = "delete_me"
    current_file = isolated_config_dir / f"{orphan_name}_config.yml"
    archive_dir = isolated_config_dir / "archives" / orphan_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    older = archive_dir / f"{orphan_name}_config_1.yml"
    newer = archive_dir / f"{orphan_name}_config_2.yml"

    current_file.write_text("settings:\n  cache: false\n", encoding="utf-8")
    older.write_text("settings:\n  cache: false\n", encoding="utf-8")
    newer.write_text("settings:\n  cache: true\n", encoding="utf-8")

    now = time.time()
    os.utime(older, (now - 100, now - 100))
    os.utime(current_file, (now - 50, now - 50))
    os.utime(newer, (now, now))

    resp = client.get(f"/orphaned-config-artifacts/versions?name={orphan_name}")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert [item["filename"] for item in payload["versions"]] == [newer.name, current_file.name, older.name]


def test_restore_orphaned_config_artifact_restores_selected_version(client, isolated_config_dir, app):
    from modules import database

    orphan_name = "delete_me"
    current_file = isolated_config_dir / f"{orphan_name}_config.yml"
    archive_dir = isolated_config_dir / "archives" / orphan_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    selected_version = archive_dir / f"{orphan_name}_config_1.yml"

    current_file.write_text("settings:\n  cache: false\n", encoding="utf-8")
    selected_version.write_text("settings:\n  cache: true\n", encoding="utf-8")

    resp = client.post(
        "/orphaned-config-artifacts/restore",
        json={"name": orphan_name, "path": str(selected_version.resolve())},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["config_name"] == orphan_name
    assert "settings" in payload["imported_sections"]

    validated, user_entered, data = database.retrieve_section_data(orphan_name, "settings")
    assert validated is False
    assert user_entered is True
    assert data["settings"]["cache"] is True

    restored_text = current_file.read_text(encoding="utf-8")
    assert "cache: true" in restored_text


def test_rename_config_moves_managed_library_file_directories(client, isolated_config_dir, app):
    from modules import database
    from pathlib import Path

    old_name = "rename_source"
    new_name = "rename_target"
    kometa_path = Path(app.config["KOMETA_ROOT"]) / "config"
    kometa_path.mkdir(parents=True, exist_ok=True)

    (isolated_config_dir / f"{old_name}_config.yml").write_text("test: true\n", encoding="utf-8")
    (kometa_path / f"{old_name}_config.yml").write_text("test: true\n", encoding="utf-8")
    metadata_dir = isolated_config_dir / old_name / "metadata_files" / "mov-library_movies"
    overlay_dir = isolated_config_dir / old_name / "overlay_files" / "mov-library_movies"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "movies.yml").write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")
    (overlay_dir / "awards.yml").write_text("overlays:\n  test:\n    template:\n      - name: ribbon\n", encoding="utf-8")
    database.save_section_data(
        name=old_name,
        section="start",
        validated=True,
        user_entered=True,
        data={"start": {"config_name": old_name}},
    )

    with client.session_transaction() as sess:
        sess["config_name"] = old_name

    resp = client.post("/rename-config", json={"old_name": old_name, "new_name": new_name})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    assert not (isolated_config_dir / old_name / "metadata_files").exists()
    assert not (isolated_config_dir / old_name / "overlay_files").exists()
    assert (isolated_config_dir / new_name / "metadata_files" / "mov-library_movies" / "movies.yml").exists()
    assert (isolated_config_dir / new_name / "overlay_files" / "mov-library_movies" / "awards.yml").exists()
    assert f"{new_name}_config.yml" in "".join(payload["files"]["renamed"])

    with client.session_transaction() as sess:
        assert sess["config_name"] == new_name

    assert new_name in database.get_unique_config_names()
    assert old_name not in database.get_unique_config_names()


def test_list_uploaded_images_includes_builtin_guides(client):
    expected_by_type = {
        "movie": {"overlay_alignment_guide.png"},
        "show": {"overlay_alignment_guide.png"},
        "season": {"overlay_alignment_guide.png"},
        "episode": {"overlay_alignment_guide_episodes.png"},
    }

    for image_type, expected in expected_by_type.items():
        resp = client.get(f"/list_uploaded_images?type={image_type}")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "success"
        assert expected.issubset(set(payload["images"]))
        assert not ({"overlay_alignment_guide.png", "overlay_alignment_guide_episodes.png"} - expected).intersection(payload["images"])


def test_clone_test_libraries_start_returns_job_payload_immediately(client, tmp_path, monkeypatch, qs_module):
    target_path = tmp_path / "plex_test_libraries"
    temp_path = tmp_path / "tmp"
    temp_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        qs_module,
        "_resolve_test_libraries_paths",
        lambda _root: (str(tmp_path), str(target_path), str(temp_path), str(temp_path), str(target_path)),
    )
    monkeypatch.setattr(qs_module, "_paths_overlap", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(qs_module, "_safe_to_replace_test_libraries", lambda *_args, **_kwargs: True)

    started = {}

    class DummyThread:
        def __init__(self, target=None, daemon=None):
            started["target"] = target
            started["daemon"] = daemon

        def start(self):
            started["started"] = True

    monkeypatch.setattr(qs_module.threading, "Thread", DummyThread)

    resp = client.post(
        "/clone-test-libraries-start",
        json={"quickstart_root": str(tmp_path), "use_config_dir": True},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["job_id"]
    assert payload["started_at"]
    assert started["started"] is True
    assert started["daemon"] is True


def test_step_post_ignores_global_config_manager_fields_in_saved_section(client, isolated_config_dir):
    from modules import database

    config_name = "pytest_leak_guard"
    resp = client.post(
        "/step/100-anidb",
        data={
            "configSelector": config_name,
            "newConfigName": "should_not_persist",
            "importMode": "new",
            "language": "en",
            "cache_expiration": "60",
            "enable_mature": "true",
        },
        headers={"Referer": "http://localhost/step/100-anidb"},
    )

    assert resp.status_code in (200, 302)

    validated, user_entered, data = database.retrieve_section_data(config_name, "anidb")
    assert validated is False
    assert user_entered is True
    assert data["anidb"]["language"] == "en"
    assert data["anidb"]["cache_expiration"] == 60
    assert data["anidb"]["enable_mature"] is True
    assert "configSelector" not in data["anidb"]
    assert "newConfigName" not in data["anidb"]
    assert "importMode" not in data["anidb"]


def test_retrieve_settings_sanitizes_already_persisted_transient_fields(client, isolated_config_dir, app):
    from modules import database, persistence
    from flask import session

    config_name = "pytest_existing_leak_guard"
    database.save_section_data(
        section="anidb",
        validated=True,
        user_entered=True,
        name=config_name,
        data={
            "anidb": {
                "configSelector": config_name,
                "newConfigName": "should_not_persist",
                "importMode": "new",
                "language": "en",
                "cache_expiration": 60,
                "enable_mature": True,
            },
            "validated_at": "2026-05-03T00:00:00Z",
        },
    )

    with app.test_request_context("/step/100-anidb"):
        session["config_name"] = config_name
        settings = persistence.retrieve_settings("100-anidb")
        assert settings["anidb"]["language"] == "en"
        assert settings["anidb"]["cache_expiration"] == 60
        assert settings["anidb"]["enable_mature"] is True
        assert "configSelector" not in settings["anidb"]
        assert "newConfigName" not in settings["anidb"]
        assert "importMode" not in settings["anidb"]

    validated, user_entered, stored = database.retrieve_section_data(config_name, "anidb")
    assert validated is True
    assert user_entered is True
    assert "configSelector" not in stored["anidb"]
    assert "newConfigName" not in stored["anidb"]
    assert "importMode" not in stored["anidb"]


def test_copy_library_settings_mirrors_metadata_files(client, isolated_config_dir, monkeypatch, app, qs_module):
    import json
    from pathlib import Path

    from modules import database
    from flask import session

    config_name = "pytest_copy_metadata_files"
    managed_dir = isolated_config_dir / config_name / "metadata_files" / "mov-library_movies"
    managed_dir.mkdir(parents=True, exist_ok=True)
    managed_file = managed_dir / "movies.yml"
    managed_file.write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")
    managed_location = managed_file.relative_to(isolated_config_dir).as_posix()
    source_metadata_files = json.dumps(
        [
            {"type": "file", "location": managed_location},
            {"type": "url", "location": "https://example.com/movie-metadata.yml"},
        ]
    )

    database.save_section_data(
        section="libraries",
        validated=False,
        user_entered=True,
        name=config_name,
        data={
            "libraries": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-metadata_files": source_metadata_files,
                "mov-library_target-library": "Other Movies",
                "libraries": "Movies,Other Movies",
            },
            "validated": False,
        },
    )
    monkeypatch.setattr(
        qs_module,
        "_build_library_lists",
        lambda: (
            [
                {"id": "mov-library_movies", "name": "Movies"},
                {"id": "mov-library_target", "name": "Other Movies"},
            ],
            [],
            {},
        ),
    )
    monkeypatch.setattr(qs_module.validations, "validate_metadata_file_payload", lambda _payload: (True, ""))

    with app.test_request_context("/copy_library_settings"):
        session["config_name"] = config_name

    with client.session_transaction() as sess:
        sess["config_name"] = config_name

    resp = client.post(
        "/copy_library_settings",
        json={
            "source_library_id": "mov-library_movies",
            "target_library_ids": ["mov-library_target"],
            "source_payload": {
                "mov-library_movies-library": "Movies",
                "mov-library_movies-metadata_files": source_metadata_files,
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert validated is False
    assert user_entered is True
    libraries = stored["libraries"]
    source_entries = json.loads(libraries["mov-library_movies-metadata_files"])
    target_entries = json.loads(libraries["mov-library_target-metadata_files"])
    assert source_entries[0]["location"] == f"config/{managed_location}"
    assert target_entries[0]["location"].startswith(f"config/{config_name}/metadata_files/mov-library_target/")
    assert target_entries[0]["location"] != source_entries[0]["location"]
    assert source_entries[1] == {"type": "url", "location": "https://example.com/movie-metadata.yml"}
    assert target_entries[1] == {"type": "url", "location": "https://example.com/movie-metadata.yml"}
    target_file = isolated_config_dir.parent / Path(target_entries[0]["location"])
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == managed_file.read_text(encoding="utf-8")


def test_sync_managed_library_artifacts_to_kometa_copies_and_prunes(isolated_config_dir, app):
    from pathlib import Path

    from modules import helpers

    config_name = "pytest_kometa_artifacts"
    metadata_dir = isolated_config_dir / config_name / "metadata_files" / "mov-library_movies"
    overlay_dir = isolated_config_dir / config_name / "overlay_files" / "mov-library_movies"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "movies.yml").write_text("metadata:\n  test:\n    title: Example\n", encoding="utf-8")
    (overlay_dir / "awards.yml").write_text("overlays:\n  test:\n    template:\n      - name: ribbon\n", encoding="utf-8")

    kometa_root = Path(app.config["KOMETA_ROOT"])
    stale_dir = kometa_root / "config" / config_name / "collection_files" / "mov-library_movies"
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "stale.yml").write_text("collections:\n  stale:\n    plex_search:\n      any:\n        title: Stale\n", encoding="utf-8")

    result = helpers.sync_managed_library_artifacts_to_kometa(config_name, kometa_root=kometa_root)

    assert (kometa_root / "config" / config_name / "metadata_files" / "mov-library_movies" / "movies.yml").exists()
    assert (kometa_root / "config" / config_name / "overlay_files" / "mov-library_movies" / "awards.yml").exists()
    assert not stale_dir.exists()
    assert any(path.endswith(f"{config_name}\\metadata_files") or path.endswith(f"{config_name}/metadata_files") for path in result["synced"])
    assert any(path.endswith(f"{config_name}\\overlay_files") or path.endswith(f"{config_name}/overlay_files") for path in result["synced"])
    assert any(path.endswith(f"{config_name}\\collection_files") or path.endswith(f"{config_name}/collection_files") for path in result["removed"])
    assert result["errors"] == []


def test_copy_fonts_to_kometa_prefers_config_scoped_fonts(isolated_config_dir, app):
    from pathlib import Path

    from modules import helpers

    config_name = "pytest_font_sync"
    config_font_dir = isolated_config_dir / config_name / "fonts"
    legacy_font_dir = isolated_config_dir / "fonts"
    config_font_dir.mkdir(parents=True, exist_ok=True)
    legacy_font_dir.mkdir(parents=True, exist_ok=True)
    (config_font_dir / "Poster.ttf").write_bytes(b"config-font")
    (legacy_font_dir / "Poster.ttf").write_bytes(b"legacy-font")

    result = helpers.copy_fonts_to_kometa(["Poster.ttf"], kometa_root=app.config["KOMETA_ROOT"], config_name=config_name)

    assert result["copied"] == ["Poster.ttf"]
    copied_font = Path(app.config["KOMETA_ROOT"]) / "config" / "fonts" / "Poster.ttf"
    assert copied_font.exists()
    assert copied_font.read_bytes() == b"config-font"


def test_copy_fonts_to_kometa_adopts_legacy_font_into_config_scope(isolated_config_dir, app):
    from pathlib import Path

    from modules import helpers

    config_name = "pytest_font_adopt"
    legacy_font_dir = isolated_config_dir / "fonts"
    legacy_font_dir.mkdir(parents=True, exist_ok=True)
    (legacy_font_dir / "Poster.ttf").write_bytes(b"legacy-font")

    result = helpers.copy_fonts_to_kometa(["Poster.ttf"], kometa_root=app.config["KOMETA_ROOT"], config_name=config_name)

    assert result["copied"] == ["Poster.ttf"]
    adopted_font = isolated_config_dir / config_name / "fonts" / "Poster.ttf"
    assert adopted_font.exists()
    assert adopted_font.read_bytes() == b"legacy-font"
    copied_font = Path(app.config["KOMETA_ROOT"]) / "config" / "fonts" / "Poster.ttf"
    assert copied_font.exists()
    assert copied_font.read_bytes() == b"legacy-font"


def test_save_to_named_config_syncs_managed_library_artifacts_to_kometa(isolated_config_dir, app):
    from pathlib import Path

    from modules import helpers

    config_name = "pytest_save_sync"
    collection_dir = isolated_config_dir / config_name / "collection_files" / "mov-library_movies"
    collection_dir.mkdir(parents=True, exist_ok=True)
    collection_file = collection_dir / "collections.yml"
    collection_file.write_text("collections:\n  test:\n    plex_search:\n      any:\n        title: Example\n", encoding="utf-8")

    with app.app_context():
        latest_filename = helpers.save_to_named_config("settings:\n  cache: true\n", config_name)

    kometa_root = Path(app.config["KOMETA_ROOT"])
    assert latest_filename == f"{config_name}_config.yml"
    assert (kometa_root / "config" / latest_filename).exists()
    synced_file = kometa_root / "config" / config_name / "collection_files" / "mov-library_movies" / "collections.yml"
    assert synced_file.exists()
    assert synced_file.read_text(encoding="utf-8") == collection_file.read_text(encoding="utf-8")


def test_save_to_named_config_writes_to_external_kometa_config_dir(isolated_config_dir, app, tmp_path):
    from modules import helpers

    config_name = "pytest_external_save_sync"
    external_config = tmp_path / "external-kometa-config"
    external_logs = external_config / "logs"
    external_logs.mkdir(parents=True, exist_ok=True)
    collection_dir = isolated_config_dir / config_name / "collection_files" / "mov-library_movies"
    collection_dir.mkdir(parents=True, exist_ok=True)
    collection_file = collection_dir / "collections.yml"
    collection_file.write_text("collections:\n  test:\n    plex_search:\n      any:\n        title: Example\n", encoding="utf-8")

    with app.app_context():
        app.config["KOMETA_INSTALL_MODE"] = "external"
        app.config["KOMETA_CONFIG_DIR"] = str(external_config)
        app.config["KOMETA_LOG_DIR"] = str(external_logs)
        latest_filename = helpers.save_to_named_config("settings:\n  cache: true\n", config_name)

    assert latest_filename == f"{config_name}_config.yml"
    assert (external_config / latest_filename).exists()
    synced_file = external_config / config_name / "collection_files" / "mov-library_movies" / "collections.yml"
    assert synced_file.exists()
    assert synced_file.read_text(encoding="utf-8") == collection_file.read_text(encoding="utf-8")


def test_save_to_named_config_rejects_blank_config_name(isolated_config_dir, app):
    from modules import helpers

    with app.app_context():
        with pytest.raises(ValueError, match="requires an explicit config name"):
            helpers.save_to_named_config("settings:\n  cache: true\n", "   ")

    assert not (isolated_config_dir / "default_config.yml").exists()
    assert not (isolated_config_dir / "default").exists()


def test_sync_managed_library_artifacts_to_kometa_rejects_blank_config_name(isolated_config_dir, app):
    from modules import helpers

    with pytest.raises(ValueError, match="requires an explicit config name"):
        helpers.sync_managed_library_artifacts_to_kometa("   ", kometa_root=app.config["KOMETA_ROOT"])


def test_import_config_confirm_rehomes_bundled_library_files(client, isolated_config_dir, monkeypatch, qs_module):
    import io
    import json
    import zipfile

    from modules import database

    class _Report:
        def __init__(self, lines=None):
            self.lines = list(lines or [])

        def summary(self):
            return {"imported": len(self.lines), "unmapped": 0, "skipped": 0}

    def _fake_prepare_import_payload(config_data, *_args, **_kwargs):
        location = config_data["libraries"]["Movies"]["metadata_files"][0]["file"]
        payload = {
            "libraries": {
                "libraries": {
                    "mov-library_movies-library": "Movies",
                    "mov-library_movies-metadata_files": json.dumps([{"type": "file", "location": location}], ensure_ascii=True),
                }
            }
        }
        return payload, _Report(
            [
                "imported: libraries.Movies.library",
                "imported: libraries.Movies.metadata_files[0].file",
                "imported: libraries.Movies.metadata_files",
            ]
        )

    monkeypatch.setattr(qs_module.importer, "prepare_import_payload", _fake_prepare_import_payload)
    monkeypatch.setattr(
        qs_module.validations,
        "validate_plex_server",
        lambda _payload: {"validated": True, "movie_libraries": ["Movies"], "show_libraries": []},
    )
    monkeypatch.setattr(qs_module.validations, "validate_tmdb_server", lambda _payload: {"valid": True})

    config_name = "pytest_import_bundle"
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "config.yml",
            "plex:\n  url: http://plex.local\n  token: test-token\ntmdb:\n  apikey: test-key\nlibraries:\n  Movies:\n    metadata_files:\n      - file: original/metadata_files/movies/source.yml\n",
        )
        archive.writestr(
            "original/metadata_files/movies/source.yml",
            "metadata:\n  imported:\n    title: Imported Example\n",
        )
        archive.writestr(
            f"{config_name}/fonts/Poster.ttf",
            b"font-bytes",
        )
    bundle.seek(0)

    preview = client.post(
        "/import-config/preview",
        data={"config_name": config_name, "file": (bundle, "bundle.zip")},
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200, preview.get_json()
    preview_payload = preview.get_json()
    assert preview_payload["success"] is True

    confirm = client.post("/import-config/confirm", json={"token": preview_payload["token"]})
    assert confirm.status_code == 200, confirm.get_json()
    confirm_payload = confirm.get_json()
    assert confirm_payload["success"] is True

    validated, user_entered, stored = database.retrieve_section_data(config_name, "libraries")
    assert validated is False
    assert user_entered is True
    metadata_entries = json.loads(stored["libraries"]["mov-library_movies-metadata_files"])
    assert len(metadata_entries) == 1
    normalized_location = metadata_entries[0]["location"]
    assert normalized_location.startswith(f"config/{config_name}/metadata_files/mov-library_movies/")
    managed_file = isolated_config_dir.parent / normalized_location
    assert managed_file.exists()
    assert "Imported Example" in managed_file.read_text(encoding="utf-8")
    bundled_font = isolated_config_dir / config_name / "fonts" / "Poster.ttf"
    assert bundled_font.exists()
    assert bundled_font.read_bytes() == b"font-bytes"


def test_build_libraries_section_emits_schedule_overlays(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {"movies": {"mov-library_movies-top_level_schedule_overlays": "weekly(saturday)"}},
            {},
        )

    movies = libraries_section["libraries"]["Movies"]
    assert movies["schedule_overlays"] == "weekly(saturday)"
    assert list(movies.keys())[:2] == ["schedule_overlays", "template_variables"]


def test_build_libraries_section_keeps_default_ratings_overlay_when_overlay_files_exist(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-movie-overlay_ratings": True,
                    "mov-library_movies-movie-template_overlay_ratings[rating1]": "critic",
                    "mov-library_movies-movie-template_overlay_ratings[rating1_image]": "imdb",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    overlay_entries = libraries_section["libraries"]["Movies"]["overlay_files"]
    ratings_entry = next((entry for entry in overlay_entries if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None
    assert ratings_entry["template_variables"]["rating1"] == "critic"
    assert ratings_entry["template_variables"]["rating1_image"] == "imdb"


def test_build_libraries_section_emits_languages_overlay_language_list(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-movie-overlay_languages": True,
                    "mov-library_movies-movie-template_overlay_languages[languages]": ["en", "ja"],
                    "mov-library_movies-movie-template_overlay_languages[style]": "square",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    overlay_entries = libraries_section["libraries"]["Movies"]["overlay_files"]
    languages_entry = next((entry for entry in overlay_entries if entry.get("default") == "languages"), None)
    assert languages_entry is not None
    assert languages_entry["template_variables"]["languages"] == ["en", "ja"]
    assert languages_entry["template_variables"]["style"] == "square"
    assert "use_subtitles" not in languages_entry["template_variables"]


def test_build_libraries_section_emits_subtitle_languages_overlay_language_list(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-movie-overlay_languages_subtitles": True,
                    "mov-library_movies-movie-template_overlay_languages_subtitles[languages]": ["en", "ja"],
                    "mov-library_movies-movie-template_overlay_languages_subtitles[style]": "square",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    overlay_entries = libraries_section["libraries"]["Movies"]["overlay_files"]
    subtitle_entry = next(
        (entry for entry in overlay_entries if entry.get("default") == "languages" and entry.get("template_variables", {}).get("use_subtitles") is True),
        None,
    )
    assert subtitle_entry is not None
    assert subtitle_entry["template_variables"]["languages"] == ["en", "ja"]
    assert subtitle_entry["template_variables"]["style"] == "square"


def test_build_libraries_section_emits_only_non_default_language_weight_overrides(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-movie-overlay_languages": True,
                    "mov-library_movies-movie-template_overlay_languages[weight_en]": "610",
                    "mov-library_movies-movie-template_overlay_languages[weight_ja]": "700",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    overlay_entries = libraries_section["libraries"]["Movies"]["overlay_files"]
    languages_entry = next((entry for entry in overlay_entries if entry.get("default") == "languages"), None)
    assert languages_entry is not None
    template_variables = languages_entry.get("template_variables", {})
    assert "weight_en" not in template_variables
    assert template_variables["weight_ja"] == 700


def test_prepare_import_payload_accepts_language_weight_override():
    from modules import importer

    config_data = {
        "libraries": {
            "Movies": {
                "overlay_files": [
                    {
                        "default": "languages",
                        "template_variables": {
                            "languages": ["en", "ja"],
                            "weight_ja": 700,
                            "use_subtitles": True,
                        },
                    }
                ]
            }
        }
    }

    payload, report = importer.prepare_import_payload(
        config_data,
        plex_movie_names={"Movies"},
        plex_show_names=set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-movie-overlay_languages_subtitles"] is True
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages_subtitles[languages]"] == ["en", "ja"]
    assert libraries_payload["mov-library_movies-movie-template_overlay_languages_subtitles[weight_ja]"] == 700
    assert report.summary()["imported"] > 0


def test_prepare_import_payload_accepts_collection_include_and_exclude_with_warning():
    from modules import importer

    config_data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "actor",
                        "template_variables": {
                            "include": ["Tom Hanks"],
                            "exclude": ["Morgan Freeman"],
                        },
                    }
                ]
            }
        }
    }

    payload, report = importer.prepare_import_payload(
        config_data,
        plex_movie_names={"Movies"},
        plex_show_names=set(),
    )

    libraries_payload = payload["libraries"]["libraries"]
    assert libraries_payload["mov-library_movies-collection_actor"] is True
    assert libraries_payload["mov-library_movies-template_collection_actor_include"] == '["Tom Hanks"]'
    assert libraries_payload["mov-library_movies-template_collection_actor_exclude"] == '["Morgan Freeman"]'
    assert any("template_variables.include_exclude_warning" in line and "include and exclude were both imported" in line for line in report.lines)


def test_build_libraries_section_includes_separator_placeholder_imdb_id(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {
                "movies": {
                    "mov-library_movies-template_variables[use_separator]": "gray",
                    "mov-library_movies-attribute_template_variables[placeholder_imdb_id]": "tt0108052",
                    "mov-library_movies-template_variables[language]": "en",
                    "mov-library_movies-template_variables[collection_mode]": "hide",
                }
            },
            {},
            {},
            {},
        )

    template_variables = libraries_section["libraries"]["Movies"]["template_variables"]
    assert template_variables["sep_style"] == "gray"
    assert template_variables["placeholder_imdb_id"] == "tt0108052"
    assert template_variables["language"] == "en"
    assert template_variables["collection_mode"] == "hide"


def test_reorder_library_section_keeps_settings_and_operations_before_library_files():
    from modules import output

    reordered = output.reorder_library_section(
        {
            "report_path": "config/Movies_Report.yml",
            "schedule": "weekly(mon)",
            "schedule_overlays": "weekly(wed)",
            "template_variables": {"sep_style": "gray"},
            "metadata_files": [{"folder": "config/example/metadata"}],
            "collection_files": [{"folder": "config/example/collections"}],
            "overlay_files": [{"folder": "config/example/overlays"}],
            "settings": {"asset_directory": ["C:\\Assets\\Movies"]},
            "radarr": {"url": "http://radarr.local"},
            "operations": {"assets_for_all": True},
        }
    )

    assert list(reordered.keys()) == [
        "report_path",
        "schedule",
        "schedule_overlays",
        "template_variables",
        "settings",
        "radarr",
        "operations",
        "metadata_files",
        "collection_files",
        "overlay_files",
    ]


def test_build_libraries_section_omits_empty_collectionless_exclude_prefix(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {
                "movies": {
                    "mov-library_movies-collection_collectionless": True,
                    "mov-library_movies-template_collection_collectionless_exclude_prefix": "[]",
                }
            },
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
        )

    collection_entries = libraries_section["libraries"]["Movies"]["collection_files"]
    collectionless_entry = next((entry for entry in collection_entries if entry.get("default") == "collectionless"), None)

    assert collectionless_entry is not None
    assert "template_variables" not in collectionless_entry


def test_build_libraries_section_emits_schedule(app):
    from modules import output

    with app.app_context():
        libraries_section = output.build_libraries_section(
            {"mov-library_movies-library": "Movies"},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {},
            {"movies": {"mov-library_movies-top_level_schedule": "weekly(saturday)"}},
            {},
        )

    movies = libraries_section["libraries"]["Movies"]
    assert movies["schedule"] == "weekly(saturday)"
    assert list(movies.keys())[:2] == ["schedule", "template_variables"]


def test_save_kometa_install_mode_persists_existing_root(client, tmp_path):
    from modules import database

    config_name = "pytest_kometa_existing_mode"
    existing_root = tmp_path / "kometa-existing"
    existing_root.mkdir(parents=True, exist_ok=True)
    (existing_root / "config").mkdir(parents=True, exist_ok=True)
    (existing_root / "kometa.py").write_text("print('kometa')\n", encoding="utf-8")
    (existing_root / "requirements.txt").write_text("requests\n", encoding="utf-8")

    resp = client.post(
        "/save-kometa-install-mode",
        json={
            "config_name": config_name,
            "install_mode": "existing",
            "existing_root": str(existing_root),
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["install_mode"] == "existing"
    assert payload["can_update"] is False

    validated, user_entered, stored = database.retrieve_section_data(config_name, "kometa")
    assert validated is True
    assert user_entered is True
    assert stored["kometa"]["install_mode"] == "existing"
    assert stored["kometa"]["existing_root"] == str(existing_root)


def test_validate_kometa_root_existing_mode_does_not_create_missing_root(client, tmp_path):
    missing_root = tmp_path / "missing-existing-kometa"

    resp = client.post(
        "/validate-kometa-root",
        json={
            "config_name": "pytest_missing_existing_root",
            "install_mode": "existing",
            "path": str(missing_root),
        },
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "does not exist" in payload["error"]
    assert not missing_root.exists()


def test_save_kometa_install_mode_rejects_non_kometa_folder(client, tmp_path):
    unrelated_root = tmp_path / "not-kometa"
    unrelated_root.mkdir(parents=True, exist_ok=True)

    resp = client.post(
        "/save-kometa-install-mode",
        json={
            "config_name": "pytest_non_kometa_existing_root",
            "install_mode": "existing",
            "existing_root": str(unrelated_root),
        },
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "kometa.py" in payload["error"]


def test_save_kometa_install_mode_persists_external_paths(client, tmp_path):
    from modules import database

    config_name = "pytest_kometa_external_mode"
    external_config = tmp_path / "kometa-config"
    external_logs = external_config / "logs"
    external_logs.mkdir(parents=True, exist_ok=True)

    resp = client.post(
        "/save-kometa-install-mode",
        json={
            "config_name": config_name,
            "install_mode": "external",
            "external_config_root": str(external_config),
            "external_log_root": str(external_logs),
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["install_mode"] == "external"
    assert payload["can_launch"] is False
    assert payload["can_update"] is False
    assert payload["kometa_config_dir_display"] == str(external_config.resolve())
    assert payload["kometa_log_dir_display"] == str(external_logs.resolve())

    validated, user_entered, stored = database.retrieve_section_data(config_name, "kometa")
    assert validated is True
    assert user_entered is True
    assert stored["kometa"]["install_mode"] == "external"
    assert stored["kometa"]["external_config_root"] == str(external_config)
    assert stored["kometa"]["external_log_root"] == str(external_logs)


def test_build_workspace_status_context_marks_start_error_for_missing_existing_kometa_root(app, tmp_path, qs_module):
    from modules import database

    config_name = "pytest_missing_existing_root_status"
    missing_root = tmp_path / "missing-existing-root"

    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=False,
        user_entered=True,
        data={"kometa": {"install_mode": "existing", "existing_root": str(missing_root)}},
    )

    template_list = [
        ("001-start.html", "Start"),
        ("900-kometa.html", "Kometa"),
    ]

    context = qs_module._build_workspace_status_context(config_name, template_list, available_configs=[config_name])

    assert context["step_statuses"]["001-start"] == "error"


def test_build_kometa_install_context_restores_existing_mode_after_restart(app, tmp_path, qs_module):
    from pathlib import Path
    from flask import session
    from modules import database, helpers

    config_name = "pytest_restart_existing_mode"
    existing_root = tmp_path / "restart-existing-kometa"
    existing_root.mkdir(parents=True, exist_ok=True)
    (existing_root / "config").mkdir(parents=True, exist_ok=True)
    (existing_root / "kometa.py").write_text("print('kometa')\n", encoding="utf-8")
    (existing_root / "requirements.txt").write_text("requests\n", encoding="utf-8")

    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=False,
        user_entered=True,
        data={"kometa": {"install_mode": "existing", "existing_root": str(existing_root)}},
    )

    with app.test_request_context("/step/001-start"):
        session.clear()
        session["config_name"] = config_name
        app.config["KOMETA_INSTALL_MODE"] = "managed"
        app.config["KOMETA_ROOT"] = str((Path(helpers.CONFIG_DIR) / "kometa").resolve())
        app.config["KOMETA_CONFIG_DIR"] = ""
        app.config["KOMETA_LOG_DIR"] = ""

        page_info = qs_module._build_kometa_install_context(config_name)

        assert page_info["kometa_install_mode"] == "existing"
        assert page_info["kometa_is_managed_install"] is False
        assert page_info["kometa_primary_path_display"] == str(existing_root.resolve())


def test_build_kometa_install_context_restores_external_mode_after_restart(app, tmp_path, qs_module):
    from pathlib import Path
    from flask import session
    from modules import database, helpers

    config_name = "pytest_restart_external_mode"
    external_config = tmp_path / "restart-external-config"
    external_logs = external_config / "logs"
    external_logs.mkdir(parents=True, exist_ok=True)

    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=False,
        user_entered=True,
        data={
            "kometa": {
                "install_mode": "external",
                "external_config_root": str(external_config),
                "external_log_root": str(external_logs),
            }
        },
    )

    with app.test_request_context("/step/001-start"):
        session.clear()
        session["config_name"] = config_name
        app.config["KOMETA_INSTALL_MODE"] = "managed"
        app.config["KOMETA_ROOT"] = str((Path(helpers.CONFIG_DIR) / "kometa").resolve())
        app.config["KOMETA_CONFIG_DIR"] = ""
        app.config["KOMETA_LOG_DIR"] = ""

        page_info = qs_module._build_kometa_install_context(config_name)

        assert page_info["kometa_install_mode"] == "external"
        assert page_info["kometa_is_external_install"] is True
        assert page_info["kometa_active_config_dir_display"] == str(external_config.resolve())
        assert page_info["kometa_active_log_dir_display"] == str(external_logs.resolve())


def test_update_kometa_existing_mode_requires_manual_update(client, tmp_path, monkeypatch, qs_module):
    existing_root = tmp_path / "kometa-existing-update"
    existing_root.mkdir(parents=True, exist_ok=True)
    (existing_root / "config").mkdir(parents=True, exist_ok=True)
    (existing_root / "kometa.py").write_text("print('kometa')\n", encoding="utf-8")
    (existing_root / "requirements.txt").write_text("requests\n", encoding="utf-8")

    resp = client.post(
        "/update-kometa",
        json={
            "config_name": "pytest_update_existing_root",
            "install_mode": "existing",
            "path": str(existing_root),
            "background": False,
        },
    )

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["success"] is False
    assert "manually outside Quickstart" in payload["error"]


def test_check_kometa_update_existing_mode_allows_status_check(client, tmp_path, monkeypatch, qs_module):
    existing_root = tmp_path / "kometa-existing-check"
    existing_root.mkdir(parents=True, exist_ok=True)
    (existing_root / "config").mkdir(parents=True, exist_ok=True)
    (existing_root / "kometa.py").write_text("print('kometa')\n", encoding="utf-8")
    (existing_root / "requirements.txt").write_text("requests\n", encoding="utf-8")

    monkeypatch.setattr(
        qs_module,
        "_probe_kometa_root_state",
        lambda _path: {
            "kometa_installed": True,
            "kometa_version": "1.0.0",
            "kometa_running": False,
            "kometa_root": str(existing_root.resolve()),
            "kometa_root_display": str(existing_root.resolve()),
            "venv_python_exists": True,
            "venv_python": "",
            "venv_python_display": "",
            "kometa_config_dir": str((existing_root / "config").resolve()),
            "kometa_config_dir_display": str((existing_root / "config").resolve()),
            "kometa_log_dir": str((existing_root / "config" / "logs").resolve()),
            "kometa_log_dir_display": str((existing_root / "config" / "logs").resolve()),
        },
    )
    monkeypatch.setattr(
        qs_module.helpers,
        "get_cached_kometa_update",
        lambda *_args, **_kwargs: {
            "local_version": "1.0.0",
            "remote_version": "1.1.0",
            "branch": "nightly",
            "cached": False,
            "update_available": True,
            "local_branch": "nightly",
            "local_sha": "abc123",
            "remote_sha": "def456",
            "comparison_basis": "version",
            "branch_mismatch": False,
        },
    )

    resp = client.post(
        "/check-kometa-update",
        json={
            "config_name": "pytest_check_existing_root",
            "install_mode": "existing",
            "path": str(existing_root),
        },
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["kometa_update_available"] is True
    assert payload["local_version"] == "1.0.0"
    assert payload["remote_version"] == "1.1.0"


def test_get_kometa_config_dir_prefers_persisted_external_selection(app, tmp_path):
    from flask import session
    from modules import database, helpers

    config_name = "pytest_persisted_external_config"
    external_config = tmp_path / "persisted-external-config"
    external_logs = external_config / "logs"
    external_logs.mkdir(parents=True, exist_ok=True)

    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=False,
        user_entered=True,
        data={
            "kometa": {
                "install_mode": "external",
                "external_config_root": str(external_config),
                "external_log_root": str(external_logs),
            }
        },
    )

    with app.test_request_context("/step/900-kometa"):
        app.config["KOMETA_INSTALL_MODE"] = "managed"
        app.config["KOMETA_CONFIG_DIR"] = ""
        app.config["KOMETA_LOG_DIR"] = ""
        session["config_name"] = config_name
        session["kometa_install_mode"] = "managed"
        session["kometa_config_dir"] = ""
        session["kometa_log_dir"] = ""
        assert helpers.get_kometa_config_dir() == external_config.resolve()
        assert helpers.get_kometa_log_dir() == external_logs.resolve()


def test_get_kometa_root_path_prefers_persisted_existing_selection(app, tmp_path):
    from flask import session
    from modules import database, helpers

    config_name = "pytest_persisted_existing_root"
    existing_root = tmp_path / "persisted-kometa"
    existing_root.mkdir(parents=True, exist_ok=True)

    database.save_section_data(
        name=config_name,
        section="kometa",
        validated=False,
        user_entered=True,
        data={"kometa": {"install_mode": "existing", "existing_root": str(existing_root)}},
    )

    from pathlib import Path

    managed_default = str((Path(helpers.CONFIG_DIR) / "kometa").resolve())
    with app.test_request_context("/step/900-kometa"):
        app.config["KOMETA_ROOT"] = managed_default
        session["config_name"] = config_name
        session["kometa_root"] = managed_default
        assert helpers.get_kometa_root_path() == existing_root.resolve()


def test_normalize_config_name_for_storage_strips_yaml_filename_suffix():
    from modules import helpers

    assert helpers.normalize_config_name_for_storage("bullmoose20_prod9_config.yml") == "bullmoose20_prod9"
    assert helpers.normalize_config_name_for_storage(r"C:\tmp\bullmoose20_prod9_config.yml") == "bullmoose20_prod9"


def test_build_validation_summary_accepts_string_errors(qs_module):
    summary = qs_module.build_validation_summary(["kometa.py not found."])

    assert summary == [
        {
            "title": "kometa.py not found.",
            "details": "",
            "doc_url": qs_module.VALIDATION_DOC_FALLBACK,
            "section": "config",
            "suggestions": [],
        }
    ]


def test_build_validation_summary_routes_library_file_string_errors_to_libraries(qs_module):
    summary = qs_module.build_validation_summary(["Movies metadata_files[1]: Metadata folder path: Path does not exist."])

    assert summary == [
        {
            "title": "Movies metadata_files[1]: Metadata folder path: Path does not exist.",
            "details": "",
            "doc_url": "/step/025-libraries",
            "section": "libraries",
            "suggestions": [],
        }
    ]


def test_validate_library_metadata_files_includes_failing_path(qs_module):
    errors = qs_module._validate_library_metadata_files(
        {
            "mov-library_movies-metadata_files": [
                {
                    "type": "folder",
                    "location": r"C:\does-not-exist\metadata",
                }
            ]
        },
        ["mov-library_movies"],
    )

    assert len(errors) == 1
    assert r"Path: C:\does-not-exist\metadata" in errors[0]


def test_normalize_generated_config_library_files_includes_failing_path(qs_module):
    config_data = {"libraries": {"Movies": {"metadata_files": [{"folder": r"C:\does-not-exist\metadata"}]}}}

    _config_data, _changed, errors = qs_module._normalize_generated_config_library_files(config_data, "pytest_config")

    assert len(errors) == 1
    assert r"Path: C:\does-not-exist\metadata" in errors[0]
