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

    resp = client.get("/step/900-final")
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

    resp = client.get("/step/900-final")
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

    resp = client.get("/step/900-final")
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

    resp = client.get("/step/900-final")
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
