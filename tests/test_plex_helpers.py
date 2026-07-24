from modules.helpers import _plex


class _Guid:
    def __init__(self, guid_id):
        self.id = guid_id


class _Item:
    def __init__(self, title, guids):
        self.title = title
        self.guids = [_Guid(guid) for guid in guids]


class _Section:
    def __init__(self, items, title="Movies", key="1"):
        self._items = items
        self.title = title
        self.key = key

    def search(self, sort=None, maxresults=None):
        assert sort == "audienceRating:desc"
        assert maxresults == 50
        return self._items


class _Library:
    def __init__(self, section):
        self._section = section

    def sections(self):
        return [self._section]


class _Plex:
    def __init__(self, section):
        self.library = _Library(section)


def test_get_top_imdb_items_returns_top_ten_with_source_ids(monkeypatch):
    items = [_Item(f"Movie {index}", [f"imdb://tt12345{index:02d}", f"tmdb://{600 + index}"]) for index in range(12)]
    section = _Section(items)

    monkeypatch.setattr(_plex.persistence, "get_stored_plex_credentials", lambda page: ("http://plex", "token"))
    monkeypatch.setattr(_plex, "PlexServer", lambda url, token: _Plex(section))

    result, saved_item = _plex.get_top_imdb_items("Movies", "movie")

    assert saved_item is None
    assert len(result) == 10
    assert result[0] == {
        "id": "tt1234500",
        "imdb_id": "tt1234500",
        "tmdb_movie": "600",
        "tvdb_show": "",
        "title": "Movie 0",
    }
    assert result[-1]["imdb_id"] == "tt1234509"


def test_get_top_imdb_items_continues_until_each_relevant_source_has_top_ten(monkeypatch):
    items = [_Item(f"IMDb Only {index}", [f"imdb://tt20000{index:02d}"]) for index in range(10)] + [_Item(f"TMDb Only {index}", [f"tmdb://{900 + index}"]) for index in range(10)]
    section = _Section(items)

    monkeypatch.setattr(_plex.persistence, "get_stored_plex_credentials", lambda page: ("http://plex", "token"))
    monkeypatch.setattr(_plex, "PlexServer", lambda url, token: _Plex(section))

    result, _saved_item = _plex.get_top_imdb_items("Movies", "movie")

    assert len(result) == 20
    assert [item["tmdb_movie"] for item in result if item["tmdb_movie"]] == [str(900 + index) for index in range(10)]


def test_get_top_imdb_items_matches_plex_section_titles_with_outer_spaces(monkeypatch):
    items = [_Item("Movie", ["imdb://tt1234567", "tmdb://42"])]
    section = _Section(items, title=" Movies")

    monkeypatch.setattr(_plex.persistence, "get_stored_plex_credentials", lambda page: ("http://plex", "token"))
    monkeypatch.setattr(_plex, "PlexServer", lambda url, token: _Plex(section))

    result, _saved_item = _plex.get_top_imdb_items("Movies", "movie")

    assert result[0]["title"] == "Movie"
    assert result[0]["imdb_id"] == "tt1234567"
