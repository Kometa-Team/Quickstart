"""Tests for config-lifecycle and library-autosave routes.

Covers:
  - blueprints/config_routes.py  → /activate-config, /clear_session,
    /clear_data/<name>, /clear_data/<name>/<section>
  - blueprints/library_routes.py → /autosave_library/<library_id>
  - blueprints/imagemaid_routes.py → /autosave-imagemaid, /validate-imagemaid
  - quickstart.py                → /lookup_template_string_value
"""

# ===========================================================================
# /activate-config
# ===========================================================================


def test_activate_config_creates_new_config_and_sets_session(client, isolated_config_dir):
    resp = client.post("/activate-config", json={"name": "myprofile"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["name"] == "myprofile"
    assert data["created"] is True  # brand-new config


def test_activate_config_existing_config_not_flagged_as_created(client, isolated_config_dir):
    # Create first
    client.post("/activate-config", json={"name": "existing"})
    # Activate again
    resp = client.post("/activate-config", json={"name": "existing"})
    data = resp.get_json()
    assert data["success"] is True
    assert data["created"] is False


def test_activate_config_empty_name_returns_400(client, isolated_config_dir):
    resp = client.post("/activate-config", json={"name": ""})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_activate_config_missing_name_returns_400(client, isolated_config_dir):
    resp = client.post("/activate-config", json={})
    assert resp.status_code == 400


def test_activate_config_sanitises_name(client, isolated_config_dir):
    # sanitize_config_name strips non-alphanumeric/underscore chars and lowercases
    resp = client.post("/activate-config", json={"name": "My Config!"})
    assert resp.status_code == 200
    data = resp.get_json()
    # "My Config!" → "myconfig" (special chars stripped)
    assert data["name"] == "myconfig"


# ===========================================================================
# /clear_session
# ===========================================================================


def test_clear_session_returns_success(client, isolated_config_dir):
    from modules import database

    # Ensure the DB table exists before the route tries to flush it
    database.get_unique_config_names()
    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_sess"
    resp = client.post("/clear_session", data={"name": "pytest_sess"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "pytest_sess" in data["message"]


def test_clear_session_without_name_uses_session_config(client, isolated_config_dir):
    from modules import database

    database.get_unique_config_names()
    with client.session_transaction() as sess:
        sess["config_name"] = "fallback_config"
    resp = client.post("/clear_session", data={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"


# ===========================================================================
# /clear_data/<name>  and  /clear_data/<name>/<section>
# ===========================================================================


def test_clear_data_redirects_to_root(client, isolated_config_dir):
    from modules import database

    # Ensure section_data table exists (reset_data does not CREATE TABLE IF NOT EXISTS)
    database.get_unique_config_names()
    resp = client.get("/clear_data/some_config")
    # Route does flash + redirect to start
    assert resp.status_code == 302


def test_clear_data_section_redirects_to_root(client, isolated_config_dir):
    from modules import database

    database.get_unique_config_names()
    resp = client.get("/clear_data/some_config/010-plex")
    assert resp.status_code == 302


def test_clear_data_removes_db_entries(client, isolated_config_dir):
    from modules import database

    config_name = "clear_data_test"
    # Seed some data (also initialises the table)
    database.save_section_data(
        name=config_name,
        section="plex",
        validated=True,
        user_entered=True,
        data={"plex": {"url": "http://localhost:32400"}},
    )
    # Clear it
    client.get(f"/clear_data/{config_name}")
    # Should no longer be retrievable
    _, _, data = database.retrieve_section_data(config_name, "plex")
    assert data is None


# ===========================================================================
# /autosave_library/<library_id>
# ===========================================================================


def test_autosave_library_returns_success_for_empty_payload(client, isolated_config_dir, qs_module, monkeypatch):
    """Empty libraries payload (no fields) should autosave without error."""
    monkeypatch.setattr(qs_module, "_selected_library_ids_from_libraries_data", lambda libs: set())
    monkeypatch.setattr(qs_module, "_validate_library_collection_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_metadata_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_overlay_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_auto_sort_hubs", lambda libs, ids: [])
    monkeypatch.setattr(
        qs_module,
        "_normalize_library_file_entries_payload",
        lambda libs, config_name, **kw: ({}, [], False),
    )
    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={"config_name": "pytest_lib"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True


def test_autosave_library_returns_400_on_collection_file_errors(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_selected_library_ids_from_libraries_data", lambda libs: set())
    monkeypatch.setattr(qs_module, "_validate_library_collection_files", lambda libs, ids: ["Bad collection"])
    monkeypatch.setattr(qs_module, "_validate_library_metadata_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_overlay_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_auto_sort_hubs", lambda libs, ids: [])

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={"config_name": "pytest_lib"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "collection" in data["error"].lower()


def test_autosave_library_returns_400_on_overlay_file_errors(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_selected_library_ids_from_libraries_data", lambda libs: set())
    monkeypatch.setattr(qs_module, "_validate_library_collection_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_metadata_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_overlay_files", lambda libs, ids: ["Bad overlay path"])
    monkeypatch.setattr(qs_module, "_validate_library_auto_sort_hubs", lambda libs, ids: [])

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={"config_name": "pytest_lib"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_autosave_library_returns_400_on_normalization_errors(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_selected_library_ids_from_libraries_data", lambda libs: set())
    monkeypatch.setattr(qs_module, "_validate_library_collection_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_metadata_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_overlay_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_auto_sort_hubs", lambda libs, ids: [])
    monkeypatch.setattr(
        qs_module,
        "_normalize_library_file_entries_payload",
        lambda libs, config_name, **kw: ({}, ["Normalization error"], False),
    )

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={"config_name": "pytest_lib"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


def test_autosave_library_reports_normalized_flag(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_selected_library_ids_from_libraries_data", lambda libs: set())
    monkeypatch.setattr(qs_module, "_validate_library_collection_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_metadata_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_overlay_files", lambda libs, ids: [])
    monkeypatch.setattr(qs_module, "_validate_library_auto_sort_hubs", lambda libs, ids: [])
    monkeypatch.setattr(
        qs_module,
        "_normalize_library_file_entries_payload",
        lambda libs, config_name, **kw: ({}, [], True),  # changed=True
    )

    resp = client.post(
        "/autosave_library/mov-library_movies",
        json={"config_name": "pytest_lib"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["normalized"] is True


# ===========================================================================
# /autosave-imagemaid
# ===========================================================================


def test_autosave_imagemaid_returns_success(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_resolve_request_config_name", lambda payload: "pytest_im")
    monkeypatch.setattr(qs_module, "_imagemaid_settings_to_form_payload", lambda payload: {})
    monkeypatch.setattr(qs_module, "_get_imagemaid_settings_section", lambda config_name: ({}, {}))

    resp = client.post("/autosave-imagemaid", json={"config_name": "pytest_im"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "changed" in data
    assert "validated" in data


def test_autosave_imagemaid_returns_validated_false_on_change(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_resolve_request_config_name", lambda payload: "pytest_im")
    monkeypatch.setattr(qs_module, "_imagemaid_settings_to_form_payload", lambda payload: {"some": "data"})
    monkeypatch.setattr(
        qs_module,
        "_save_imagemaid_settings_for_config",
        lambda config_name, form_payload: (form_payload, True),  # changed=True
    )
    # Pretend previously validated
    monkeypatch.setattr(
        qs_module,
        "_get_imagemaid_settings_section",
        lambda config_name: ({"validated": True}, {}),
    )
    monkeypatch.setattr(
        qs_module,
        "_persist_imagemaid_validation",
        lambda config_name, section, valid, reason="", details="": None,
    )

    resp = client.post("/autosave-imagemaid", json={"config_name": "pytest_im", "some": "data"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    # Changing config while previously validated should invalidate it
    assert data["validated"] is False


# ===========================================================================
# /validate-imagemaid
# ===========================================================================


def test_validate_imagemaid_returns_success_when_valid(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_resolve_request_config_name", lambda payload: "pytest_im")
    monkeypatch.setattr(qs_module, "_imagemaid_settings_to_form_payload", lambda payload: {})
    monkeypatch.setattr(qs_module, "_get_imagemaid_settings_section", lambda config_name: ({}, {}))
    monkeypatch.setattr(qs_module, "_validate_imagemaid_settings", lambda section, config_name="": (True, "ok", {}))
    monkeypatch.setattr(qs_module, "_persist_imagemaid_validation", lambda *a, **kw: None)
    monkeypatch.setattr(qs_module, "_get_stored_plex_credentials_for_config", lambda config_name: ("http://plex:32400", "token"))
    monkeypatch.setattr(qs_module, "_build_imagemaid_command", lambda *a, **kw: "imagemaid --run")

    resp = client.post("/validate-imagemaid", json={"config_name": "pytest_im"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["validated"] is True
    assert "command_preview" in data


def test_validate_imagemaid_returns_400_when_invalid(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_resolve_request_config_name", lambda payload: "pytest_im")
    monkeypatch.setattr(qs_module, "_imagemaid_settings_to_form_payload", lambda payload: {})
    monkeypatch.setattr(qs_module, "_get_imagemaid_settings_section", lambda config_name: ({}, {}))
    monkeypatch.setattr(qs_module, "_validate_imagemaid_settings", lambda section, config_name="": (False, "missing_root", "ImageMaid root not set."))
    monkeypatch.setattr(qs_module, "_persist_imagemaid_validation", lambda *a, **kw: None)
    monkeypatch.setattr(qs_module, "_get_stored_plex_credentials_for_config", lambda config_name: ("", ""))
    monkeypatch.setattr(qs_module, "_build_imagemaid_command", lambda *a, **kw: "")

    resp = client.post("/validate-imagemaid", json={"config_name": "pytest_im"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["validated"] is False


# ===========================================================================
# /lookup_template_string_value
# ===========================================================================


def test_lookup_template_string_value_requires_preset_and_value(client, isolated_config_dir):
    resp = client.post("/lookup_template_string_value", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_lookup_template_string_value_rejects_unknown_preset(client, isolated_config_dir):
    resp = client.post("/lookup_template_string_value", json={"preset": "bad_preset", "value": "123"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "Unsupported" in data.get("error", "")


def test_lookup_template_string_value_numeric_id_hit(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(
        qs_module,
        "_lookup_tmdb_numeric_id",
        lambda value, media_type="": {"valid": True, "verified": True, "label": "The Matrix", "result_type": "movie", "message": "TMDb movie: The Matrix (TMDb 603)"},
    )
    monkeypatch.setattr(qs_module, "_build_tmdb_library_type_warning", lambda *a, **kw: "")

    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "numeric_id",
            "value": "603",
            "media_type": "movie",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert data["label"] == "The Matrix"


def test_lookup_template_string_value_numeric_id_type_mismatch_adds_warning(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(
        qs_module,
        "_lookup_tmdb_numeric_id",
        lambda value, media_type="": {"valid": True, "verified": True, "label": "Breaking Bad", "result_type": "show", "message": "TMDb show: Breaking Bad (TMDb 1396)"},
    )
    monkeypatch.setattr(
        qs_module,
        "_build_tmdb_library_type_warning",
        lambda msg, result_type, expected, value_label="ID": "Type mismatch: show vs movie library",
    )

    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "numeric_id",
            "value": "1396",
            "media_type": "movie",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert data.get("level") == "warning"
    assert "mismatch" in data["message"].lower()


def test_lookup_template_string_value_imdb_id_tmdb_hit(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(
        qs_module,
        "_lookup_tmdb_by_imdb_id",
        lambda value, media_type="": {"valid": True, "verified": True, "label": "The Matrix", "result_type": "movie", "message": "TMDb movie: The Matrix (TMDb 603)"},
    )
    monkeypatch.setattr(qs_module, "_build_tmdb_library_type_warning", lambda *a, **kw: "")

    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "imdb_id_tmdb",
            "value": "tt0133093",
            "media_type": "movie",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert data["label"] == "The Matrix"


def test_lookup_template_string_value_imdb_id_plex_requires_library_name(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(
        qs_module,
        "_lookup_tmdb_by_imdb_id",
        lambda value, media_type="": {"valid": True, "verified": True, "label": "The Matrix", "result_type": "movie", "message": "TMDb movie: The Matrix"},
    )
    monkeypatch.setattr(qs_module, "_build_tmdb_library_type_warning", lambda *a, **kw: "")

    # No library_name provided for imdb_id_plex
    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "imdb_id_plex",
            "value": "tt0133093",
            "media_type": "movie",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is False
    assert "library" in data["message"].lower()


def test_lookup_template_string_value_tmdb_collection_id_hit(client, isolated_config_dir, qs_module, monkeypatch):
    from unittest.mock import MagicMock, patch
    import quickstart as qs

    collection_payload = {"id": 131296, "name": "The Matrix Collection"}
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.content = b"data"
    ok_resp.json.return_value = collection_payload

    monkeypatch.setattr(qs_module, "_get_active_tmdb_api_key", lambda: "fake-key")

    with patch.object(qs.requests, "get", return_value=ok_resp):
        resp = client.post(
            "/lookup_template_string_value",
            json={
                "preset": "tmdb_collection_id",
                "value": "131296",
            },
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is True
    assert data["label"] == "The Matrix Collection"


def test_lookup_template_string_value_tmdb_collection_id_no_key(client, isolated_config_dir, qs_module, monkeypatch):
    monkeypatch.setattr(qs_module, "_get_active_tmdb_api_key", lambda: "")

    resp = client.post(
        "/lookup_template_string_value",
        json={
            "preset": "tmdb_collection_id",
            "value": "131296",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["valid"] is False
    assert "not configured" in data["message"]
