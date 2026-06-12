from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Movies"
    overlay_entry = next((entry for entry in overlays if entry.get("default") == "ribbon"), None)
    assert overlay_entry is not None, "Expected ribbon overlay entry"
    return overlay_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-collection_collectionless": True,
        "mov-library_movies-movie-overlay_ribbon": True,
    }
    for key, value in template_vars.items():
        data[f"mov-library_movies-movie-template_overlay_ribbon[{key}]"] = value
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
            config_name="pytest_ribbon_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_ribbon_yaml_contract_keeps_use_key_toggles(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "use_oscars": False,
            "use_oscars_director": False,
            "use_golden": False,
            "use_golden_director": False,
            "use_bafta": False,
            "use_cannes": False,
            "use_berlinale": False,
            "use_venice": False,
            "use_sundance": False,
            "use_emmys": False,
            "use_choice": False,
            "use_spirit": False,
            "use_cesar": False,
            "use_imdb": False,
            "use_letterboxd": False,
            "use_rottenverified": False,
            "use_rotten": False,
            "use_metacritic": False,
            "use_common": False,
            "use_razzie": False,
        }
    )

    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))

    assert template_vars["use_oscars"] is False
    assert template_vars["use_oscars_director"] is False
    assert template_vars["use_golden"] is False
    assert template_vars["use_golden_director"] is False
    assert template_vars["use_bafta"] is False
    assert template_vars["use_cannes"] is False
    assert template_vars["use_berlinale"] is False
    assert template_vars["use_venice"] is False
    assert template_vars["use_sundance"] is False
    assert template_vars["use_emmys"] is False
    assert template_vars["use_choice"] is False
    assert template_vars["use_spirit"] is False
    assert template_vars["use_cesar"] is False
    assert template_vars["use_imdb"] is False
    assert template_vars["use_letterboxd"] is False
    assert template_vars["use_rottenverified"] is False
    assert template_vars["use_rotten"] is False
    assert template_vars["use_metacritic"] is False
    assert template_vars["use_common"] is False
    assert template_vars["use_razzie"] is False
