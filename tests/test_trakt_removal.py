import json
from pathlib import Path

from modules.output_render import _strip_retired_trakt_fields

ROOT = Path(__file__).resolve().parents[1]


def _walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def test_trakt_is_absent_from_quickstart_catalogs():
    collections = json.loads((ROOT / "static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    attributes = json.loads((ROOT / "static/json/quickstart_attributes.json").read_text(encoding="utf-8"))
    overlays = json.loads((ROOT / "static/json/quickstart_overlays.json").read_text(encoding="utf-8"))

    objects = [item for item in _walk(collections) if isinstance(item, dict)]
    assert all(item.get("id") != "collection_trakt" for item in objects)
    assert all(item.get("key") not in {"trakt_list", "child_trakt_list_overrides"} for item in objects)

    option_values = [item[0] for item in _walk(attributes) if isinstance(item, list) and item]
    assert "trakt" not in option_values
    assert "trakt_user" not in option_values
    assert "mdb_trakt" in option_values

    overlay_options = [item.get("value") for item in _walk(overlays) if isinstance(item, dict)]
    assert "trakt" not in overlay_options


def test_retired_trakt_fields_are_scrubbed_from_generated_data():
    config = {
        "trakt": {"client_id": "secret"},
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "seasonal",
                        "template_variables": {
                            "trakt_list": "https://trakt.tv/example",
                            "trakt_list_halloween": ["https://trakt.tv/halloween"],
                            "rating_source": "trakt_user",
                            "mdb_rating_source": "mdb_trakt",
                            "overlay_value": "mdb_trakt_rating",
                            "imdb_list": "https://imdb.com/list/ls1",
                        },
                    }
                ]
            }
        },
    }

    _strip_retired_trakt_fields(config)

    assert "trakt" not in config
    variables = config["libraries"]["Movies"]["collection_files"][0]["template_variables"]
    assert variables == {
        "mdb_rating_source": "mdb_trakt",
        "overlay_value": "mdb_trakt_rating",
        "imdb_list": "https://imdb.com/list/ls1",
    }
