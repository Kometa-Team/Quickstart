from modules import helpers


def test_json_schema_sync_manifest_includes_live_nightly_builders_and_schema_files():
    synced_files = {local_path for local_path, _remote_path in helpers.JSON_SCHEMA_SYNC_FILES}

    expected = {
        "README.md",
        "MODULE.md",
        "collection-schema.json",
        "config-schema.json",
        "kitchen_sink_config.yml",
        "metadata-schema.json",
        "overlay-schema.json",
        "playlist-schema.json",
        "prototype_comprehensive.yml",
        "prototype_config.yml",
        "template-schema.json",
        "builders/anidb.yml",
        "builders/anilist.yml",
        "builders/dynamic_collections.yml",
        "builders/imdb.yml",
        "builders/letterboxd.yml",
        "builders/mdblist.yml",
        "builders/metadata.yml",
        "builders/myanimelist.yml",
        "builders/other.yml",
        "builders/overlays.yml",
        "builders/playlists.yml",
        "builders/plex.yml",
        "builders/radarr.yml",
        "builders/sonarr.yml",
        "builders/tautulli.yml",
        "builders/tmdb.yml",
        "builders/trakt.yml",
        "builders/tvdb.yml",
        "config.yml.template",
    }

    assert expected.issubset(synced_files)
