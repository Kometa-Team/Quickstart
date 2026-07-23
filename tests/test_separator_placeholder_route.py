from blueprints import library_routes


def _plex_settings():
    return {
        "plex": {
            "tmp_movie_libraries": "Movies",
            "tmp_show_libraries": "TV Shows",
        }
    }


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
