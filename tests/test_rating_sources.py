import copy
import json
from pathlib import Path

import jsonschema
import pytest
from werkzeug.datastructures import MultiDict

from modules import dependency_reasons, persistence
from modules.helpers._overlays import enrich_quickstart_overlay_config
from modules.rating_sources import RATING_SOURCE_DETAILS, extend_rating_source_schema, rating_source_options

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("builder", ["movie", "show", "season", "episode"])
def test_rating_sources_are_filtered_by_builder(builder):
    values = {option["value"] for option in rating_source_options([builder])}
    expected = {source for source, (_label, _service, levels) in RATING_SOURCE_DETAILS.items() if builder in levels}
    assert values == expected | {""}
    if builder == "episode":
        assert expected == {"critic", "audience", "user", "imdb", "tmdb", "floppy", "serializd"}
    if builder == "season":
        assert expected == {"user", "tmdb"}


def test_runtime_overlay_catalog_expands_each_slot_without_mutating_raw_catalog():
    raw = json.loads((ROOT / "static/json/quickstart_overlays.json").read_text(encoding="utf-8"))
    original = copy.deepcopy(raw)
    enriched = enrich_quickstart_overlay_config(raw)
    assert raw == original
    ratings = [overlay for group in enriched for overlay in group["overlays"] if overlay["id"] == "overlay_ratings"]
    assert len(ratings) == 2
    for overlay in ratings:
        for slot in (key for key in overlay["template_variables"] if key in {"rating1", "rating2", "rating3"}):
            assert overlay["template_variables"][slot]["options"] == rating_source_options(overlay["media_types"])


@pytest.mark.parametrize("source", list(RATING_SOURCE_DETAILS))
def test_config_schema_accepts_supported_direct_rating_sources(source):
    schema = json.loads((ROOT / "tests/fixtures/schema/config-schema.json").read_text(encoding="utf-8"))
    extend_rating_source_schema(schema)
    for slot in ("rating1", "rating2", "rating3"):
        field = schema["definitions"]["template-variables-overlays"]["properties"][slot]
        jsonschema.validate(source, field)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate("not_a_kometa_source", field)


def test_output_loader_extends_the_runtime_config_schema(monkeypatch):
    from modules import output_render

    monkeypatch.setattr(output_render.helpers, "ensure_json_schema", lambda: None)
    monkeypatch.setattr(output_render.helpers, "JSON_SCHEMA_DIR", str(ROOT / "tests/fixtures/schema"))
    _yaml, schema = output_render._load_config_schema()
    assert set(RATING_SOURCE_DETAILS) <= set(schema["definitions"]["template-variables-overlays"]["properties"]["rating1"]["enum"])


def test_schema_extension_is_idempotent_and_preserves_other_constraints():
    schema = {"definitions": {"template-variables-overlays": {"properties": {"rating1": {"enum": ["critic"]}, "rating1_image": {"enum": ["imdb"]}}}}}
    extend_rating_source_schema(schema)
    original = copy.deepcopy(schema)
    extend_rating_source_schema(schema)
    assert schema == original
    assert schema["definitions"]["template-variables-overlays"]["properties"]["rating1_image"]["enum"] == ["imdb"]
    extend_rating_source_schema({})


@pytest.mark.parametrize(
    "source", [source for source, (_label, service, _levels) in RATING_SOURCE_DETAILS.items() if service in {"omdb", "mdblist", "anidb", "mal", "serializd", "floppy"}]
)
def test_dependencies_follow_selected_source_not_badge(source):
    libraries = {
        "sho-library_tv-library": "TV",
        "sho-library_tv-show-overlay_ratings": True,
        "sho-library_tv-show-template_overlay_ratings[rating1]": source,
        "sho-library_tv-show-template_overlay_ratings[rating1_image]": "imdb",
    }
    service = RATING_SOURCE_DETAILS[source][1]
    for provider in ("omdb", "mdblist", "anidb", "mal", "serializd", "floppy"):
        resolver = getattr(dependency_reasons, f"_libraries_data_{provider}_dependency_reasons")
        assert bool(resolver(libraries)) is (provider == service)
        inactive = dict(libraries, **{"sho-library_tv-show-overlay_ratings": False})
        assert resolver(inactive) == []


@pytest.mark.parametrize("source", ["user", "critic", "plex_tomatoes", "plex_tomatoesaudience", "none", ""])
@pytest.mark.parametrize("image", ["rt_tomato", "rt_popcorn", "letterboxd", "anidb", "mal"])
def test_badge_alone_never_requires_an_unselected_provider(source, image):
    libraries = {
        "mov-library_movies-library": "Movies",
        "mov-library_movies-movie-overlay_ratings": True,
        "mov-library_movies-movie-template_overlay_ratings[rating1]": source,
        "mov-library_movies-movie-template_overlay_ratings[rating1_image]": image,
    }
    for provider in ("omdb", "mdblist", "anidb", "mal"):
        assert getattr(dependency_reasons, f"_libraries_data_{provider}_dependency_reasons")(libraries) == []


@pytest.mark.parametrize("slot", ["rating1", "rating2", "rating3", "rating1_image", "rating2_image", "rating3_image"])
@pytest.mark.parametrize("value", ["", "none", " None "])
def test_cleared_rating_selectors_save_explicit_none(slot, value):
    key = f"mov-library_movies-movie-template_overlay_ratings[{slot}]"
    cleaned = persistence.clean_form_data(MultiDict({key: value, "ordinary_field": ""}))
    assert cleaned[key] == "none"
    assert cleaned["ordinary_field"] is None


@pytest.mark.parametrize("source,provider", [("mdb_tomatoes", "mdblist"), ("omdb", "omdb"), ("anidb", "anidb"), ("mal", "mal"), ("serializd", "serializd"), ("floppy", "floppy")])
@pytest.mark.parametrize("image", ["", "none", None])
def test_explicitly_disabled_image_does_not_require_its_direct_source(source, provider, image):
    libraries = {
        "sho-library_tv-library": "TV",
        "sho-library_tv-show-overlay_ratings": True,
        "sho-library_tv-show-template_overlay_ratings[rating1]": source,
        "sho-library_tv-show-template_overlay_ratings[rating1_image]": image,
    }
    assert getattr(dependency_reasons, f"_libraries_data_{provider}_dependency_reasons")(libraries) == []


def test_serializd_source_moves_setup_into_required_steps(monkeypatch, qs_module):
    from modules import workspace_status

    monkeypatch.setattr(
        workspace_status.database,
        "retrieve_config_sections",
        lambda _name: [
            {
                "section": "libraries",
                "data": {
                    "libraries": {
                        "sho-library_tv-library": "TV",
                        "sho-library_tv-show-overlay_ratings": True,
                        "sho-library_tv-show-template_overlay_ratings[rating1]": "serializd",
                    }
                },
            }
        ],
    )
    context = workspace_status._build_workspace_status_context(
        "ratings", [("065-serializd.html", "Serializd")], available_configs=["ratings"], include_app_readiness_overrides=False
    )
    assert "065-serializd" in context["required_keys"]
    assert context["serializd_requirement_reasons"] == ["TV: show ratings overlay uses serializd"]


def test_serializd_dependency_hint_uses_unsaved_overlay_source(client):
    response = client.post(
        "/libraries_serializd_dependency_hint",
        json={
            "source_library_id": "sho-library_tv",
            "source_payload": {
                "__loaded_sections": ["overlays"],
                "sho-library_tv-library": "TV",
                "sho-library_tv-episode-overlay_ratings": True,
                "sho-library_tv-episode-template_overlay_ratings[rating1]": "serializd",
            },
        },
    )
    assert response.status_code == 200
    assert response.json["required"] is True
    assert response.json["reasons"] == ["TV: episode ratings overlay uses serializd"]
