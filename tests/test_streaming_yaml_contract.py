from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Movies"
    overlay_entry = next((entry for entry in overlays if entry.get("default") == "streaming"), None)
    assert overlay_entry is not None, "Expected streaming overlay entry"
    return overlay_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-collection_collectionless": True,
        "mov-library_movies-movie-overlay_streaming": True,
    }
    for key, value in template_vars.items():
        data[f"mov-library_movies-movie-template_overlay_streaming[{key}]"] = value
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
            config_name="pytest_streaming_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_streaming_yaml_contract_keeps_use_key_toggles(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_netflix": False,
            "use_amazon": False,
            "use_disney": False,
            "use_hbomax": False,
            "use_crunchyroll": False,
            "use_movistar": False,
            "use_atresplayer": False,
            "use_youtube": False,
            "use_hulu": False,
            "use_paramount": False,
            "use_amc": False,
            "use_appletv": False,
            "use_peacock": False,
            "use_discovery": False,
            "use_crave": False,
            "use_now": False,
            "use_channel4": False,
            "use_itvx": False,
            "use_bet": False,
            "use_hayu": False,
            "use_tubi": False,
            "use_filmin": False,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_netflix"] is False
    assert template_vars["use_amazon"] is False
    assert template_vars["use_disney"] is False
    assert template_vars["use_hbomax"] is False
    assert template_vars["use_crunchyroll"] is False
    assert template_vars["use_movistar"] is False
    assert template_vars["use_atresplayer"] is False
    assert template_vars["use_youtube"] is False
    assert template_vars["use_hulu"] is False
    assert template_vars["use_paramount"] is False
    assert template_vars["use_amc"] is False
    assert template_vars["use_appletv"] is False
    assert template_vars["use_peacock"] is False
    assert template_vars["use_discovery"] is False
    assert template_vars["use_crave"] is False
    assert template_vars["use_now"] is False
    assert template_vars["use_channel4"] is False
    assert template_vars["use_itvx"] is False
    assert template_vars["use_bet"] is False
    assert template_vars["use_hayu"] is False
    assert template_vars["use_tubi"] is False
    assert template_vars["use_filmin"] is False
