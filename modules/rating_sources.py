"""Supported sources for Kometa's ratings overlay template."""

_LIBRARY_LEVELS = ("movie", "show")
_ITEM_LEVELS = ("movie", "show", "episode")
_ALL_LEVELS = ("movie", "show", "season", "episode")

# Keep the source names aligned with defaults/overlays/ratings.yml, not its badge names.
RATING_SOURCE_DETAILS = {
    "critic": ("Critic", "plex", _ITEM_LEVELS),
    "audience": ("Audience", "plex", _ITEM_LEVELS),
    "user": ("User", "plex", _ALL_LEVELS),
    "imdb": ("IMDb", None, _ITEM_LEVELS),
    "tmdb": ("TMDb", "tmdb", _ALL_LEVELS),
    "floppy": ("Floppy", "floppy", _ITEM_LEVELS),
    "serializd": ("Serializd", "serializd", ("show", "episode")),
    "omdb": ("OMDb", "omdb", _LIBRARY_LEVELS),
    "omdb_imdb": ("OMDb: IMDb", "omdb", _LIBRARY_LEVELS),
    "omdb_metascore": ("OMDb: Metacritic", "omdb", _LIBRARY_LEVELS),
    "omdb_tomatoes": ("OMDb: RT", "omdb", _LIBRARY_LEVELS),
    "mdb": ("MDBList Score", "mdblist", _LIBRARY_LEVELS),
    "mdb_average": ("MDBList Average", "mdblist", _LIBRARY_LEVELS),
    "mdb_imdb": ("MDBList: IMDb", "mdblist", _LIBRARY_LEVELS),
    "mdb_metacritic": ("MDBList: Metacritic", "mdblist", _LIBRARY_LEVELS),
    "mdb_metacriticuser": ("MDBList: Metacritic User", "mdblist", _LIBRARY_LEVELS),
    "mdb_tomatoes": ("MDBList: RT", "mdblist", _LIBRARY_LEVELS),
    "mdb_tomatoesaudience": ("MDBList: RT Audience", "mdblist", _LIBRARY_LEVELS),
    "mdb_tmdb": ("MDBList: TMDb", "mdblist", _LIBRARY_LEVELS),
    "mdb_letterboxd": ("MDBList: Letterboxd", "mdblist", _LIBRARY_LEVELS),
    "mdb_myanimelist": ("MDBList: MyAnimeList", "mdblist", _LIBRARY_LEVELS),
    "anidb": ("AniDB", "anidb", _LIBRARY_LEVELS),
    "anidb_average": ("AniDB Average", "anidb", _LIBRARY_LEVELS),
    "anidb_score": ("AniDB Review Score", "anidb", _LIBRARY_LEVELS),
    "mal": ("MyAnimeList", "mal", _LIBRARY_LEVELS),
    "plex_imdb": ("Plex: IMDb", "plex", _LIBRARY_LEVELS),
    "plex_tmdb": ("Plex: TMDb", "plex", _LIBRARY_LEVELS),
    "plex_tomatoes": ("Plex: RT", "plex", _LIBRARY_LEVELS),
    "plex_tomatoesaudience": ("Plex: RT Audience", "plex", _LIBRARY_LEVELS),
}


def rating_source_options(media_types):
    allowed_types = set(media_types)
    options = [{"value": "", "label": "None"}]
    for source, (label, _service, supported_types) in RATING_SOURCE_DETAILS.items():
        if allowed_types.intersection(supported_types):
            options.append({"value": source, "label": label, "media_types": list(supported_types)})
    return options


def rating_sources_for_service(service):
    return {source for source, (_label, source_service, _types) in RATING_SOURCE_DETAILS.items() if source_service == service}


def extend_rating_source_schema(schema):
    # Upstream's config schema still lists only critic/audience/user/floppy.
    properties = schema.get("definitions", {}).get("template-variables-overlays", {}).get("properties", {})
    for key in ("rating1", "rating2", "rating3"):
        allowed = properties.get(key, {}).get("enum")
        if isinstance(allowed, list):
            allowed.extend(source for source in RATING_SOURCE_DETAILS if source not in allowed)
