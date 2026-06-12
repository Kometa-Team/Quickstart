from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Movies"
    video_format_entry = next((entry for entry in overlays if entry.get("default") == "video_format"), None)
    assert video_format_entry is not None, "Expected video_format overlay entry"
    return video_format_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-collection_collectionless": True,
        "mov-library_movies-movie-overlay_video_format": True,
    }
    for key, value in template_vars.items():
        data[f"mov-library_movies-movie-template_overlay_video_format[{key}]"] = value
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
            config_name="pytest_video_format_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_video_format_yaml_contract_keeps_use_key_toggles(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_remux": False,
            "use_bluray": False,
            "use_web": False,
            "use_hdtv": False,
            "use_dvd": False,
            "use_sdtv": False,
            "use_telesync": False,
            "use_cam": False,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_remux"] is False
    assert template_vars["use_bluray"] is False
    assert template_vars["use_web"] is False
    assert template_vars["use_hdtv"] is False
    assert template_vars["use_dvd"] is False
    assert template_vars["use_sdtv"] is False
    assert template_vars["use_telesync"] is False
    assert template_vars["use_cam"] is False
