from ruamel.yaml import YAML


def _template_vars_from_yaml(yaml_content):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    assert overlays, "Expected at least one overlay entry for Movies"
    ratings_entry = next((entry for entry in overlays if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None, "Expected ratings overlay entry"
    return ratings_entry.get("template_variables", {})


def _build_library_payload(template_vars):
    data = {
        "mov-library_movies-library": "Movies",
        # Overlay extraction in build_libraries_section currently runs inside the
        # collection branch, so keep a minimal collection key present.
        "mov-library_movies-collection_collectionless": True,
        "mov-library_movies-movie-overlay_ratings": True,
    }
    for key, value in template_vars.items():
        data[f"mov-library_movies-movie-template_overlay_ratings[{key}]"] = value
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
            config_name="pytest_ratings_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def test_ratings_yaml_contract_keeps_three_slot_horizontal_order(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "rating_alignment": "horizontal",
            "horizontal_position": "left",
            "vertical_position": "center",
            "addon_position": "left",
            "back_height": 80,
            "back_width": 270,
            "back_padding": 15,
            "rating1": "user",
            "rating1_image": "rt_tomato",
            "rating1_horizontal_offset": 30,
            "rating1_vertical_offset": -125,
            "rating2": "critic",
            "rating2_image": "imdb",
            "rating2_horizontal_offset": 345,
            "rating2_vertical_offset": 0,
            "rating3": "audience",
            "rating3_image": "tmdb",
            "rating3_horizontal_offset": 660,
            "rating3_vertical_offset": 125,
        }
    )
    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))
    assert template_vars["rating_alignment"] == "horizontal"
    assert template_vars["rating1"] == "user"
    assert template_vars["rating2"] == "critic"
    assert template_vars["rating3"] == "audience"
    assert "rating1_horizontal_offset" not in template_vars
    assert "rating2_horizontal_offset" not in template_vars
    assert "rating3_horizontal_offset" not in template_vars


def test_ratings_yaml_contract_compacts_two_slots(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "rating_alignment": "horizontal",
            "horizontal_position": "left",
            "vertical_position": "center",
            "back_height": 80,
            "back_width": 270,
            "back_padding": 15,
            "rating1": "user",
            "rating1_image": "rt_tomato",
            "rating1_horizontal_offset": 45,
            "rating1_vertical_offset": -30,
            "rating3": "audience",
            "rating3_image": "tmdb",
            "rating3_horizontal_offset": 405,
            "rating3_vertical_offset": 30,
        }
    )
    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))
    assert template_vars["rating1"] == "user"
    assert template_vars["rating1_image"] == "rt_tomato"
    assert template_vars["rating2"] == "audience"
    assert template_vars["rating2_image"] == "tmdb"
    assert "rating3" not in template_vars
    assert template_vars["rating1_horizontal_offset"] == 45
    assert template_vars["rating2_horizontal_offset"] == 405


def test_ratings_yaml_contract_compacts_single_slot(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "rating_alignment": "vertical",
            "horizontal_position": "center",
            "vertical_position": "top",
            "back_height": 160,
            "back_width": 160,
            "back_padding": 15,
            "rating2": "critic",
            "rating2_image": "imdb",
            "rating2_horizontal_offset": 15,
            "rating2_vertical_offset": 30,
        }
    )
    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))
    assert template_vars["rating1"] == "critic"
    assert template_vars["rating1_image"] == "imdb"
    assert "rating2" not in template_vars
    assert "rating3" not in template_vars
    # Single-slot normalization currently applies back_padding to horizontal offset.
    assert template_vars["rating1_horizontal_offset"] == 30
    assert "rating1_vertical_offset" not in template_vars


def test_ratings_yaml_contract_bottom_horizontal_prunes_default_offsets(monkeypatch, qs_module):
    payload = _build_library_payload(
        {
            "rating_alignment": "horizontal",
            "horizontal_position": "center",
            "vertical_position": "bottom",
            "back_height": 80,
            "back_width": 270,
            "back_padding": 15,
            "rating1": "user",
            "rating1_image": "rt_tomato",
            "rating1_horizontal_offset": -335,
            "rating1_vertical_offset": -30,
            "rating2": "critic",
            "rating2_image": "imdb",
            "rating2_horizontal_offset": 0,
            "rating2_vertical_offset": -30,
            "rating3": "audience",
            "rating3_image": "tmdb",
            "rating3_horizontal_offset": 335,
            "rating3_vertical_offset": -30,
        }
    )
    template_vars = _template_vars_from_yaml(_run_build_config_with_payload(qs_module, monkeypatch, payload))
    assert template_vars["rating_alignment"] == "horizontal"
    assert template_vars["horizontal_position"] == "center"
    assert template_vars["vertical_position"] == "bottom"
    assert "rating1_horizontal_offset" not in template_vars
    assert "rating2_horizontal_offset" not in template_vars
    assert "rating3_horizontal_offset" not in template_vars
    assert "rating1_vertical_offset" not in template_vars
    assert "rating2_vertical_offset" not in template_vars
    assert "rating3_vertical_offset" not in template_vars
    assert "back_height" not in template_vars
    assert "back_width" not in template_vars
    assert "addon_position" not in template_vars
