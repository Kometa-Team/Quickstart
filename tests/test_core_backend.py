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
    assert "godzilla.yml" in yaml_content
    assert "config\\metadata\\movies" in yaml_content
    assert "movies_refresh.yml" in yaml_content


def test_step_post_from_libraries_persists_metadata_files(client, isolated_config_dir, monkeypatch, qs_module):
    import json

    from modules import database

    config_name = "pytest_step_save_metadata_files"
    metadata_value = json.dumps(
        [
            {"type": "file", "location": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
            {"type": "url", "location": "https://example.com/movies_refresh.yml"},
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
    assert stored["libraries"]["mov-library_movies-metadata_files"] == metadata_value


def test_step_post_from_libraries_persists_collection_files(client, isolated_config_dir, monkeypatch, qs_module):
    import json

    from modules import database

    config_name = "pytest_step_save_collection_files"
    collection_value = json.dumps(
        [
            {"type": "file", "location": "C:\\Users\\bullmoose20\\Community-Configs\\bullmoose20\\godzilla.yml"},
            {"type": "url", "location": "https://example.com/movies_refresh.yml"},
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
    assert stored["libraries"]["mov-library_movies-collection_files"] == collection_value


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
        return True, None, {"plex": {}}, "plex:\n  token: secret\n", []

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
    assert orphan["has_current_file"] is True
    assert orphan["has_kometa_copy"] is True
    assert orphan["has_archive_dir"] is True
    assert orphan["archive_count"] == 1


def test_delete_orphaned_config_artifacts_route_removes_selected_bundle(client, isolated_config_dir, app):
    from pathlib import Path

    orphan_name = "delete_me"
    archive_dir = isolated_config_dir / "archives" / orphan_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{orphan_name}_config_1.yml").write_text("archive: true\n", encoding="utf-8")
    (isolated_config_dir / f"{orphan_name}_config.yml").write_text("current: true\n", encoding="utf-8")

    kometa_path = Path(app.config["KOMETA_ROOT"]) / "config"
    kometa_path.mkdir(parents=True, exist_ok=True)
    (kometa_path / f"{orphan_name}_config.yml").write_text("kometa: true\n", encoding="utf-8")

    resp = client.post("/orphaned-config-artifacts/delete", json={"names": [orphan_name]})
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["deleted"] == [orphan_name]
    assert not (isolated_config_dir / f"{orphan_name}_config.yml").exists()
    assert not archive_dir.exists()
    assert not (kometa_path / f"{orphan_name}_config.yml").exists()


def test_delete_orphaned_config_artifacts_route_removes_copy_named_yaml(client, isolated_config_dir):
    copied_path = isolated_config_dir / "bullmoose20_config - Copy (10)_config.yml"
    copied_name = "bullmoose20_config_-_copy_(10)"
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

    from modules import database
    from flask import session

    config_name = "pytest_copy_metadata_files"
    source_metadata_files = json.dumps(
        [
            {"type": "file", "location": "config/metadata/movies.yml"},
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
    assert libraries["mov-library_movies-metadata_files"] == source_metadata_files
    assert libraries["mov-library_target-metadata_files"] == source_metadata_files


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
