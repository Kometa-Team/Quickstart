from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Movies"
    resolution_entry = next((entry for entry in overlays if entry.get("default") == "resolution"), None)
    assert resolution_entry is not None, "Expected resolution overlay entry"
    return resolution_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-collection_collectionless": True,
        "mov-library_movies-movie-overlay_resolution": True,
    }
    for key, value in template_vars.items():
        data[f"mov-library_movies-movie-template_overlay_resolution[{key}]"] = value
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
    monkeypatch.setattr(qs_module.output.helpers, "get_library_summaries", lambda _names: "Movies")

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        return {"validated": False}

    monkeypatch.setattr(qs_module.output.persistence, "retrieve_settings", fake_retrieve_settings)
    with qs_module.app.app_context():
        validated, _validation_error, _config_data, yaml_content, _validation_errors = qs_module.output.build_config(
            header_style="single line",
            config_name="pytest_resolution_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_resolution_yaml_contract_keeps_child_filters_when_edition_enabled(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_edition": True,
            "use_resolution": True,
            "use_4k": False,
            "use_4k_dvhdrplus": False,
            "use_1080p": False,
            "use_1080p_dv": False,
            "use_720p_hdr": False,
            "use_576p_dvhdr": False,
            "use_480p_plus": False,
            "use_dv": False,
            "use_plus": False,
            "use_dvhdr": False,
            "use_extended": False,
            "use_openmatte": False,
            "horizontal_offset": 15,
            "vertical_offset": 15,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_4k"] is False
    assert template_vars["use_4k_dvhdrplus"] is False
    assert template_vars["use_1080p"] is False
    assert template_vars["use_1080p_dv"] is False
    assert template_vars["use_720p_hdr"] is False
    assert template_vars["use_576p_dvhdr"] is False
    assert template_vars["use_480p_plus"] is False
    assert template_vars["use_dv"] is False
    assert template_vars["use_plus"] is False
    assert template_vars["use_dvhdr"] is False
    assert template_vars["use_extended"] is False
    assert template_vars["use_openmatte"] is False


def test_resolution_yaml_contract_keeps_both_master_toggles_false(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_edition": False,
            "use_resolution": False,
            "horizontal_offset": 15,
            "vertical_offset": 15,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_edition"] is False
    assert template_vars["use_resolution"] is False
