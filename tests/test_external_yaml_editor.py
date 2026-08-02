from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("kind", "filename", "root"),
    [
        ("collection_files", "collections.yml", "collections:"),
        ("metadata_files", "metadata.yml", "metadata:"),
        ("overlay_files", "overlays.yml", "overlays:"),
        ("playlist_files", "playlists.yml", "playlists:"),
    ],
)
def test_external_yaml_read_returns_create_template(client, isolated_config_dir, kind, filename, root):
    response = client.post(
        "/external_yaml_file/read",
        json={
            "kind": kind,
            "config_name": "pytest_editor",
            "library_id": "mov-library_movies",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["created"] is True
    assert payload["location"] == f"config/pytest_editor/{kind}/mov-library_movies/{filename}"
    assert root in payload["content"]


def test_external_yaml_save_blocks_invalid_yaml(client, isolated_config_dir):
    location = "config/pytest_editor/collection_files/mov-library_movies/collections.yml"
    response = client.post(
        "/external_yaml_file/save",
        json={
            "kind": "collection_files",
            "location": location,
            "content": "collections:\n  Broken: [",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["validation"]["can_save"] is False
    assert not (isolated_config_dir / "pytest_editor" / "collection_files" / "mov-library_movies" / "collections.yml").exists()


def test_external_yaml_validate_reports_tab_indentation_line(client, isolated_config_dir):
    response = client.post(
        "/external_yaml_file/validate",
        json={
            "kind": "collection_files",
            "content": "collections:\n\tBad Indent: {}\n",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    validation = payload["validation"]
    assert validation["can_save"] is False
    assert validation["issues"][0]["severity"] == "error"
    assert validation["issues"][0]["line"] == 2
    assert validation["issues"][0]["column"] == 1
    assert "tabs" in validation["issues"][0]["message"]


def test_external_yaml_save_allows_schema_warnings(client, isolated_config_dir):
    location = "config/pytest_editor/collection_files/mov-library_movies/collections.yml"
    response = client.post(
        "/external_yaml_file/save",
        json={
            "kind": "collection_files",
            "location": location,
            "content": "not_collections:\n  Example: {}\n",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] == "Saved with schema warnings."
    assert any("collections" in warning for warning in payload["validation"]["warnings"])

    saved = isolated_config_dir / "pytest_editor" / "collection_files" / "mov-library_movies" / "collections.yml"
    assert saved.read_text(encoding="utf-8") == "not_collections:\n  Example: {}\n"


def test_external_yaml_validate_reports_schema_issue_path_and_line(client, isolated_config_dir):
    response = client.post(
        "/external_yaml_file/validate",
        json={
            "kind": "collection_files",
            "content": "collections: {}\n",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    validation = payload["validation"]
    assert validation["can_save"] is True
    assert validation["schema_valid"] is False
    assert validation["issues"][0]["severity"] == "warning"
    assert validation["issues"][0]["line"] == 1
    assert validation["issues"][0]["path"] == "collections"


def test_external_yaml_validate_warns_for_non_string_mapping_keys(client, isolated_config_dir):
    response = client.post(
        "/external_yaml_file/validate",
        json={
            "kind": "collection_files",
            "content": "collections:\n  false:\n    summary: Boolean-like collection key\n",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    validation = payload["validation"]
    assert validation["can_save"] is True
    assert validation["schema_valid"] is False
    assert any("parsed mapping key" in warning for warning in validation["warnings"])
    assert any(issue.get("path") == "collections.False" for issue in validation["issues"])


def test_external_yaml_read_rejects_remote_sources(client, isolated_config_dir):
    response = client.post(
        "/external_yaml_file/read",
        json={
            "kind": "collection_files",
            "location": "https://example.com/collections.yml",
        },
    )

    assert response.status_code == 400
    assert "read-only" in response.get_json()["error"]


def test_external_yaml_save_rejects_path_traversal(client, isolated_config_dir):
    response = client.post(
        "/external_yaml_file/save",
        json={
            "kind": "metadata_files",
            "location": "config/pytest_editor/../escape.yml",
            "content": "metadata: {}\n",
        },
    )

    assert response.status_code == 400
    assert "parent directory" in response.get_json()["error"]
    assert not Path(isolated_config_dir / "escape.yml").exists()


def test_external_yaml_folder_files_lists_yaml_only(client, isolated_config_dir):
    folder = isolated_config_dir / "pytest_editor" / "collection_files" / "mov-library_movies" / "folder"
    folder.mkdir(parents=True)
    (folder / "a.yml").write_text("collections:\n  A: {}\n", encoding="utf-8")
    (folder / "b.yaml").write_text("collections:\n  B: {}\n", encoding="utf-8")
    (folder / "ignore.txt").write_text("nope", encoding="utf-8")

    response = client.post(
        "/external_yaml_file/folder_files",
        json={
            "kind": "collection_files",
            "location": "config/pytest_editor/collection_files/mov-library_movies/folder",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert [item["name"] for item in payload["files"]] == ["a.yml", "b.yaml"]


def test_external_yaml_folder_files_filters_by_required_root(client, isolated_config_dir):
    folder = isolated_config_dir / "pytest_editor" / "overlay_files" / "mov-library_movies" / "folder"
    folder.mkdir(parents=True)
    (folder / "collections.yml").write_text("collections:\n  Wrong Kind: {}\n", encoding="utf-8")
    (folder / "empty_overlays.yml").write_text("overlays: {}\n", encoding="utf-8")
    (folder / "invalid.yml").write_text("overlays:\n  Broken: [\n", encoding="utf-8")
    (folder / "overlays.yml").write_text("overlays:\n  Valid Overlay:\n    overlay:\n      name: Valid Overlay\n", encoding="utf-8")

    response = client.post(
        "/external_yaml_file/folder_files",
        json={
            "kind": "overlay_files",
            "location": "config/pytest_editor/overlay_files/mov-library_movies/folder",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert [item["name"] for item in payload["files"]] == ["overlays.yml"]


def test_external_yaml_remote_read_suggests_managed_local_copy(client, isolated_config_dir, monkeypatch):
    class FakeResponse:
        status_code = 200
        reason = "OK"
        text = "collections:\n  Remote: {}\n"

    def fake_get(url, timeout):
        assert url == "https://example.com/remote.yml"
        assert timeout == 15
        return FakeResponse()

    monkeypatch.setattr("modules.external_yaml_editor.requests.get", fake_get)

    response = client.post(
        "/external_yaml_file/remote_read",
        json={
            "kind": "collection_files",
            "source_type": "url",
            "location": "https://example.com/remote.yml",
            "config_name": "pytest_editor",
            "library_id": "mov-library_movies",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["content"] == "collections:\n  Remote: {}\n"
    assert payload["location"].startswith("config/pytest_editor/collection_files/mov-library_movies/remote_copies/remote_")
    assert not (isolated_config_dir / "pytest_editor" / "collection_files" / "mov-library_movies" / "remote_copies").exists()
