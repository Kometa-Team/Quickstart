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


def test_yaml_generation_sets_session_and_redacts(client, isolated_config_dir, monkeypatch, qs_module):
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
        qs_module.output,
        "build_config",
        lambda *_args, **_kwargs: (False, "Missing sections", {}, "", []),
    )

    with client.session_transaction() as sess:
        sess["config_name"] = "pytest_yaml_missing"

    resp = client.get("/step/900-final")
    assert resp.status_code == 200
    assert b"Missing sections" in resp.data


def test_list_uploaded_images_includes_builtin_guides(client):
    expected = {"overlay_alignment_guide.png", "overlay_alignment_guide_episodes.png"}

    for image_type in ("movie", "show", "season", "episode"):
        resp = client.get(f"/list_uploaded_images?type={image_type}")
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "success"
        assert expected.issubset(set(payload["images"]))
