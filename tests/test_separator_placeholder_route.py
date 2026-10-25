import json

import pytest

from blueprints import library_routes


def _plex_settings():
    return {
        "plex": {
            "tmp_movie_libraries": "Movies",
            "tmp_show_libraries": "TV Shows",
        }
    }


@pytest.mark.parametrize(
    "movie_libraries,show_libraries",
    [
        ("1,3", "2"),
        ('["1", "3"]', '["2"]'),
        ([1, 3], [2]),
        ('[{"id": 1}, {"id": 3}]', '[{"id": 2}]'),
    ],
    ids=["csv", "json-ids", "list-ids", "json-descriptors"],
)
@pytest.mark.parametrize(
    "library_name,media_type",
    [("Movies", "movie"), ("Movies - 4K", "movie"), ("TV Shows", "show")],
)
def test_top_item_route_resolves_stored_library_ids(client, monkeypatch, movie_libraries, show_libraries, library_name, media_type):
    library_routes._top_placeholder_cache.clear()
    settings = {
        "plex": {
            "tmp_movie_libraries": movie_libraries,
            "tmp_show_libraries": show_libraries,
            "tmp_library_names": json.dumps({"1": "Movies", "3": "Movies - 4K", "2": "TV Shows"}),
        }
    }
    monkeypatch.setattr(library_routes.persistence, "retrieve_settings", lambda section: settings)
    calls = []
    items = [{"title": "Placeholder", "imdb_id": "tt123"}]

    def lookup(*args):
        calls.append(args)
        return items, None

    monkeypatch.setattr(library_routes.helpers, "get_top_imdb_items", lookup)

    response = client.get(f"/get_top_imdb_items/{library_name}", query_string={"type": media_type, "placeholder_id": "tt123"})

    assert response.status_code == 200
    assert response.get_json() == {"status": "success", "items": items, "saved_item": None}
    assert calls == [(library_name, media_type, "tt123")]


@pytest.mark.parametrize("library_name,media_type", [("Missing", "movie"), ("TV Shows", "movie"), ("Movies", "show")])
def test_top_item_route_rejects_libraries_outside_requested_type(client, monkeypatch, library_name, media_type):
    library_routes._top_placeholder_cache.clear()
    settings = {
        "plex": {
            "tmp_movie_libraries": "1,3",
            "tmp_show_libraries": "2",
            "tmp_library_names": json.dumps({"1": "Movies", "3": "Movies - 4K", "2": "TV Shows"}),
        }
    }
    monkeypatch.setattr(library_routes.persistence, "retrieve_settings", lambda section: settings)

    def unexpected_lookup(*_args):
        pytest.fail("Unconfigured libraries must not trigger a Plex lookup")

    monkeypatch.setattr(library_routes.helpers, "get_top_imdb_items", unexpected_lookup)

    response = client.get(f"/get_top_imdb_items/{library_name}", query_string={"type": media_type})

    assert response.status_code == 200
    assert response.get_json() == {"status": "error", "message": f"Library '{library_name}' not found in Plex settings."}


def test_top_item_route_returns_controlled_failure(client, monkeypatch):
    library_routes._top_placeholder_cache.clear()
    monkeypatch.setattr(library_routes.persistence, "retrieve_settings", lambda section: _plex_settings())

    def fail_lookup(*_args, **_kwargs):
        raise RuntimeError("Plex search failed")

    monkeypatch.setattr(library_routes.helpers, "get_top_imdb_items", fail_lookup)

    response = client.get("/get_top_imdb_items/Movies?type=movie")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "lookup_unavailable"
    assert payload["items"] == []
    assert "Plex" in payload["message"]


def test_top_item_route_caches_successful_lookup(client, monkeypatch):
    library_routes._top_placeholder_cache.clear()
    monkeypatch.setattr(library_routes.persistence, "retrieve_settings", lambda section: _plex_settings())
    calls = {"count": 0}

    def lookup(*_args, **_kwargs):
        calls["count"] += 1
        return ([{"title": "Movie", "imdb_id": "tt123", "tmdb_movie": "1", "tvdb_show": ""}], None)

    monkeypatch.setattr(library_routes.helpers, "get_top_imdb_items", lookup)

    first = client.get("/get_top_imdb_items/Movies?type=movie")
    second = client.get("/get_top_imdb_items/Movies?type=movie")

    assert first.status_code == 200
    assert second.status_code == 200
    assert "cached" not in first.get_json()
    assert second.get_json()["cached"] is True
    assert calls["count"] == 1
