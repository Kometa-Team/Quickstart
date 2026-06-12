from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Movies"
    audio_codec_entry = next((entry for entry in overlays if entry.get("default") == "audio_codec"), None)
    assert audio_codec_entry is not None, "Expected audio_codec overlay entry"
    return audio_codec_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-collection_collectionless": True,
        "mov-library_movies-movie-overlay_audio_codec": True,
    }
    for key, value in template_vars.items():
        data[f"mov-library_movies-movie-template_overlay_audio_codec[{key}]"] = value
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
            config_name="pytest_audio_codec_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_audio_codec_yaml_contract_keeps_official_use_toggles(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_truehd_atmos": False,
            "use_dtsx": False,
            "use_plus_atmos": False,
            "use_dolby_atmos": False,
            "use_truehd": False,
            "use_ma": False,
            "use_flac": False,
            "use_pcm": False,
            "use_hra": False,
            "use_plus": False,
            "use_dtses": False,
            "use_dts": False,
            "use_digital": False,
            "use_aac": False,
            "use_mp3": False,
            "use_opus": False,
            "style": "standard",
            "horizontal_offset": 0,
            "vertical_offset": 15,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_truehd_atmos"] is False
    assert template_vars["use_dtsx"] is False
    assert template_vars["use_plus_atmos"] is False
    assert template_vars["use_dolby_atmos"] is False
    assert template_vars["use_truehd"] is False
    assert template_vars["use_ma"] is False
    assert template_vars["use_flac"] is False
    assert template_vars["use_pcm"] is False
    assert template_vars["use_hra"] is False
    assert template_vars["use_plus"] is False
    assert template_vars["use_dtses"] is False
    assert template_vars["use_dts"] is False
    assert template_vars["use_digital"] is False
    assert template_vars["use_aac"] is False
    assert template_vars["use_mp3"] is False
    assert template_vars["use_opus"] is False
