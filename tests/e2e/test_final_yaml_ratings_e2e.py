import pytest
from ruamel.yaml import YAML


def _allow_final_gate(qs_module, monkeypatch):
    monkeypatch.setattr(
        qs_module,
        "_build_final_gate",
        lambda *_args, **_kwargs: {
            "stage": "kometa",
            "todo_count": 0,
            "todo_blockers": [],
            "dependency_cards": [],
            "setup_blockers": [],
            "bulk_validation_fresh": True,
            "bulk_validation_at": qs_module.utc_now_iso(),
            "validation_ttl_hours": 12,
            "can_build_config": True,
            "config_valid": True,
        },
    )


def _ratings_libraries_settings():
    return {
        "validated": True,
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-movie-overlay_ratings": True,
            "mov-library_movies-movie-template_overlay_ratings[rating_alignment]": "horizontal",
            "mov-library_movies-movie-template_overlay_ratings[horizontal_position]": "left",
            "mov-library_movies-movie-template_overlay_ratings[vertical_position]": "center",
            "mov-library_movies-movie-template_overlay_ratings[back_height]": 80,
            "mov-library_movies-movie-template_overlay_ratings[back_width]": 270,
            "mov-library_movies-movie-template_overlay_ratings[back_padding]": 15,
            "mov-library_movies-movie-template_overlay_ratings[rating1]": "user",
            "mov-library_movies-movie-template_overlay_ratings[rating1_image]": "rt_tomato",
            "mov-library_movies-movie-template_overlay_ratings[rating1_horizontal_offset]": 30,
            "mov-library_movies-movie-template_overlay_ratings[rating1_vertical_offset]": -125,
            "mov-library_movies-movie-template_overlay_ratings[rating2]": "critic",
            "mov-library_movies-movie-template_overlay_ratings[rating2_image]": "imdb",
            "mov-library_movies-movie-template_overlay_ratings[rating2_horizontal_offset]": 345,
            "mov-library_movies-movie-template_overlay_ratings[rating2_vertical_offset]": 0,
            "mov-library_movies-movie-template_overlay_ratings[rating3]": "audience",
            "mov-library_movies-movie-template_overlay_ratings[rating3_image]": "tmdb",
            "mov-library_movies-movie-template_overlay_ratings[rating3_horizontal_offset]": 660,
            "mov-library_movies-movie-template_overlay_ratings[rating3_vertical_offset]": 125,
        },
    }


def _ratings_libraries_settings_bottom_center():
    return {
        "validated": True,
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-movie-overlay_ratings": True,
            "mov-library_movies-movie-template_overlay_ratings[rating_alignment]": "horizontal",
            "mov-library_movies-movie-template_overlay_ratings[horizontal_position]": "center",
            "mov-library_movies-movie-template_overlay_ratings[vertical_position]": "bottom",
            "mov-library_movies-movie-template_overlay_ratings[back_height]": 80,
            "mov-library_movies-movie-template_overlay_ratings[back_width]": 270,
            "mov-library_movies-movie-template_overlay_ratings[back_padding]": 15,
            "mov-library_movies-movie-template_overlay_ratings[rating1]": "user",
            "mov-library_movies-movie-template_overlay_ratings[rating1_image]": "rt_tomato",
            "mov-library_movies-movie-template_overlay_ratings[rating1_horizontal_offset]": -335,
            "mov-library_movies-movie-template_overlay_ratings[rating1_vertical_offset]": -30,
            "mov-library_movies-movie-template_overlay_ratings[rating2]": "critic",
            "mov-library_movies-movie-template_overlay_ratings[rating2_image]": "imdb",
            "mov-library_movies-movie-template_overlay_ratings[rating2_horizontal_offset]": 0,
            "mov-library_movies-movie-template_overlay_ratings[rating2_vertical_offset]": -30,
            "mov-library_movies-movie-template_overlay_ratings[rating3]": "audience",
            "mov-library_movies-movie-template_overlay_ratings[rating3_image]": "tmdb",
            "mov-library_movies-movie-template_overlay_ratings[rating3_horizontal_offset]": 335,
            "mov-library_movies-movie-template_overlay_ratings[rating3_vertical_offset]": -30,
        },
    }


def _ratings_libraries_settings_left_top_negative_slot():
    return {
        "validated": True,
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-movie-overlay_ratings": True,
            "mov-library_movies-movie-template_overlay_ratings[rating_alignment]": "horizontal",
            "mov-library_movies-movie-template_overlay_ratings[horizontal_position]": "left",
            "mov-library_movies-movie-template_overlay_ratings[vertical_position]": "top",
            "mov-library_movies-movie-template_overlay_ratings[back_height]": 80,
            "mov-library_movies-movie-template_overlay_ratings[back_width]": 270,
            "mov-library_movies-movie-template_overlay_ratings[back_padding]": 15,
            "mov-library_movies-movie-template_overlay_ratings[rating1]": "user",
            "mov-library_movies-movie-template_overlay_ratings[rating1_image]": "rt_tomato",
            "mov-library_movies-movie-template_overlay_ratings[rating1_horizontal_offset]": -285,
            "mov-library_movies-movie-template_overlay_ratings[rating1_vertical_offset]": 30,
            "mov-library_movies-movie-template_overlay_ratings[rating2]": "critic",
            "mov-library_movies-movie-template_overlay_ratings[rating2_image]": "imdb",
            "mov-library_movies-movie-template_overlay_ratings[rating2_horizontal_offset]": 30,
            "mov-library_movies-movie-template_overlay_ratings[rating2_vertical_offset]": 30,
            "mov-library_movies-movie-template_overlay_ratings[rating3]": "audience",
            "mov-library_movies-movie-template_overlay_ratings[rating3_image]": "tmdb",
            "mov-library_movies-movie-template_overlay_ratings[rating3_horizontal_offset]": 345,
            "mov-library_movies-movie-template_overlay_ratings[rating3_vertical_offset]": 30,
        },
    }


def _ratings_libraries_settings_single_slot_center_top_nudged():
    return {
        "validated": True,
        "libraries": {
            "mov-library_movies-library": "Movies",
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-movie-overlay_ratings": True,
            "mov-library_movies-movie-template_overlay_ratings[rating_alignment]": "vertical",
            "mov-library_movies-movie-template_overlay_ratings[horizontal_position]": "center",
            "mov-library_movies-movie-template_overlay_ratings[vertical_position]": "top",
            "mov-library_movies-movie-template_overlay_ratings[back_height]": 160,
            "mov-library_movies-movie-template_overlay_ratings[back_width]": 160,
            "mov-library_movies-movie-template_overlay_ratings[back_padding]": 15,
            "mov-library_movies-movie-template_overlay_ratings[rating2]": "critic",
            "mov-library_movies-movie-template_overlay_ratings[rating2_image]": "imdb",
            "mov-library_movies-movie-template_overlay_ratings[rating2_horizontal_offset]": 15,
            "mov-library_movies-movie-template_overlay_ratings[rating2_vertical_offset]": 45,
        },
    }


@pytest.mark.e2e
def test_final_yaml_contains_expected_ratings_overlay(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return _ratings_libraries_settings()
        return {"validated": False}

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    yaml_text = page.locator("#final-yaml").input_value()
    assert yaml_text

    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_text)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    ratings_entry = next((entry for entry in overlays if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None, "ratings overlay missing from final YAML"

    tv = ratings_entry.get("template_variables", {})
    assert tv.get("rating_alignment") == "horizontal"
    assert tv.get("rating1") == "user"
    assert tv.get("rating2") == "critic"
    assert tv.get("rating3") == "audience"
    # Horizontal offsets are default-equivalent for this combo and should be omitted.
    assert "rating1_horizontal_offset" not in tv
    assert "rating2_horizontal_offset" not in tv
    assert "rating3_horizontal_offset" not in tv
    # Vertical offsets are custom for slot 1/3 in this fixture and should remain.
    assert tv.get("rating1_vertical_offset") == -125
    assert "rating2_vertical_offset" not in tv
    assert tv.get("rating3_vertical_offset") == 125


@pytest.mark.e2e
def test_final_yaml_bottom_center_horizontal_ratings_use_non_negative_vertical_offsets(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return _ratings_libraries_settings_bottom_center()
        return {"validated": False}

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    yaml_text = page.locator("#final-yaml").input_value()
    assert yaml_text

    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_text)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    ratings_entry = next((entry for entry in overlays if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None, "ratings overlay missing from final YAML"

    tv = ratings_entry.get("template_variables", {})
    assert tv.get("rating_alignment") == "horizontal"
    assert tv.get("horizontal_position") == "center"
    assert tv.get("vertical_position") == "bottom"
    assert "rating1_horizontal_offset" not in tv
    assert "rating2_horizontal_offset" not in tv
    assert "rating3_horizontal_offset" not in tv
    assert "rating1_vertical_offset" not in tv
    assert "rating2_vertical_offset" not in tv
    assert "rating3_vertical_offset" not in tv
    assert "back_height" not in tv
    assert "back_width" not in tv
    assert "addon_position" not in tv


@pytest.mark.e2e
def test_final_yaml_preserves_left_top_negative_rating_offset_without_mutating_source(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    payload = _ratings_libraries_settings_left_top_negative_slot()

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        return {"validated": False}

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    yaml_text = page.locator("#final-yaml").input_value()
    assert yaml_text

    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_text)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    ratings_entry = next((entry for entry in overlays if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None, "ratings overlay missing from final YAML"

    tv = ratings_entry.get("template_variables", {})
    assert tv.get("horizontal_position") == "left"
    assert tv.get("vertical_position") == "top"
    assert tv.get("rating1_horizontal_offset") == -285

    source_h = payload["libraries"]["mov-library_movies-movie-template_overlay_ratings[rating1_horizontal_offset]"]
    assert source_h == -285


@pytest.mark.e2e
def test_final_yaml_preserves_single_slot_nudged_horizontal_offset_without_padding(page, live_server, monkeypatch, qs_module):
    _allow_final_gate(qs_module, monkeypatch)
    monkeypatch.setattr(
        qs_module.persistence,
        "check_minimum_settings",
        lambda: (True, True, True, True),
    )

    payload = _ratings_libraries_settings_single_slot_center_top_nudged()

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        return {"validated": False}

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)

    page.goto(f"{live_server}/step/900-kometa", wait_until="domcontentloaded")
    yaml_text = page.locator("#final-yaml").input_value()
    assert yaml_text

    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_text)
    libraries = parsed.get("libraries", {})
    movies = libraries.get("Movies", {})
    overlays = movies.get("overlay_files", [])
    ratings_entry = next((entry for entry in overlays if entry.get("default") == "ratings"), None)
    assert ratings_entry is not None, "ratings overlay missing from final YAML"

    tv = ratings_entry.get("template_variables", {})
    assert tv.get("horizontal_position") == "center"
    assert tv.get("vertical_position") == "top"
    assert tv.get("rating1") == "critic"
    assert tv.get("rating1_image") == "imdb"
    assert tv.get("rating1_horizontal_offset") == 15
    assert tv.get("rating1_vertical_offset") == 45

    source_h = payload["libraries"]["mov-library_movies-movie-template_overlay_ratings[rating2_horizontal_offset]"]
    source_v = payload["libraries"]["mov-library_movies-movie-template_overlay_ratings[rating2_vertical_offset]"]
    assert source_h == 15
    assert source_v == 45
