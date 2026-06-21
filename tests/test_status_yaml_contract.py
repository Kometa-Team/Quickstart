from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    shows = libraries.get("Shows", {})
    overlays = shows.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Shows"
    overlay_entry = next((entry for entry in overlays if entry.get("default") == "status"), None)
    assert overlay_entry is not None, "Expected status overlay entry"
    return overlay_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "sho-library_shows-library": "Shows",
        "sho-library_shows-collection_collectionless": True,
        "sho-library_shows-show-overlay_status": True,
    }
    for key, value in template_vars.items():
        data[f"sho-library_shows-show-template_overlay_status[{key}]"] = value
    return {"validated": True, "libraries": data}


def _run_build_config_with_payload(qs_module, monkeypatch, payload):
    monkeypatch.setattr(
        qs_module.output.helpers,
        "get_template_list",
        lambda: {
            "libraries": {
                "name": "Libraries",
                "stem": "025-libraries",
                "raw_name": "libraries",
            }
        },
    )
    monkeypatch.setattr(qs_module.output.helpers, "get_plex_summary", lambda: "Plex summary unavailable")
    monkeypatch.setattr(qs_module.output.helpers, "get_quickstart_settings_summary", lambda: [])
    monkeypatch.setattr(qs_module.output.helpers, "get_library_summaries", lambda _names: "Shows")

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        return {"validated": False}

    monkeypatch.setattr(qs_module.output.persistence, "retrieve_settings", fake_retrieve_settings)
    with qs_module.app.app_context():
        validated, _validation_error, _config_data, yaml_content, _validation_errors = qs_module.output.build_config(
            header_style="single line",
            config_name="pytest_status_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_status_yaml_contract_keeps_use_key_toggles(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_airing": False,
            "use_returning": False,
            "use_canceled": False,
            "use_ended": False,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_airing"] is False
    assert template_vars["use_returning"] is False
    assert template_vars["use_canceled"] is False
    assert template_vars["use_ended"] is False


def test_status_yaml_contract_emits_alignment_template_variables(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "horizontal_align": "center",
            "vertical_align": "bottom",
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["horizontal_align"] == "center"
    assert template_vars["vertical_align"] == "bottom"
