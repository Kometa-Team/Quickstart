import pytest
from ruamel.yaml import YAML


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


@pytest.mark.e2e
def test_final_yaml_contains_expected_ratings_overlay(page, live_server, monkeypatch, qs_module):
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

    page.goto(f"{live_server}/step/900-final", wait_until="domcontentloaded")
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
    assert tv.get("rating1_horizontal_offset") == 30
    assert tv.get("rating2_horizontal_offset") == 345
    assert tv.get("rating3_horizontal_offset") == 660
