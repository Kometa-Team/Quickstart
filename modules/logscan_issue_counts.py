"""Issue-counts dict builder for the logscan recommendation engine.

Split out of :mod:`modules.logscan_recommendations_engine` -- this
module owns Phase 6 of ``make_recommendations``: assembling the
issue-counts dict that the dashboard consumes.

The recommendation engine's Phase 2 populates ~50 error/warning
"buckets" (each a list of line indices where a particular pattern
was detected).  Phase 6 boils those down to a single flat dict of
``category_or_bucket_name -> int_count`` for the frontend.

## Structure of the returned dict

The dict has two shape-layers:

**Rollup categories** -- coarse groupings the dashboard highlights.
Each is a *sum* of several bucket lengths:

* ``service_connectivity`` -- TMDb/Trakt/OMDb/MDBList/MAL/Tautulli/
  FlixPatrol/LSIO
* ``config_setup`` -- to_be_configured / api_blank / bad_version /
  missing_path / cache_false / mass_update / other_award /
  delete_unmanaged_collections
* ``plex_issues`` -- plex_url / plex_regex / plex_lib / rounding
* ``metadata_overlay_playlist`` -- metadata + overlay + playlist
  bucket lengths
* ``convert_issues``, ``image_issues``, ``runtime_behavior``,
  ``update_version``, ``platform_system``, ``anidb_issues``, ``misc``
  -- smaller rollups

**Per-bucket detail counts** -- 40+ individual bucket lengths so
the dashboard can drill down (e.g. ``tmdb_api_errors``,
``plex_url_errors``, ``overlay_font_missing``).

## Backward compatibility

``modules.logscan_recommendations_engine`` re-exports
:func:`build_issue_counts` so its ``make_recommendations`` can call
it, and any future test-side monkeypatch would work against the
sibling module (patched directly) if needed.
"""

from __future__ import annotations


def build_issue_counts(buckets, platform_recs):
    """Build the flat issue-counts dict from per-bucket line-index lists.

    :param buckets: dict mapping bucket-name -> list of line indices
        where that pattern was detected (populated by Phase 2 of
        ``make_recommendations``).  All values are lists; ``len(v)``
        is what enters the counts.
    :param platform_recs: dict with keys ``wsl``, ``time``, ``memory``,
        ``db_cache`` -- each a truthy/falsy platform recommendation.
    :returns: flat dict of ``category_or_bucket_name -> int_count``.
    """
    wsl_recommendation = platform_recs["wsl"]
    kometa_time_recommendation = platform_recs["time"]
    kometa_mem_recommendation = platform_recs["memory"]
    kometa_db_cache_recommendation = platform_recs["db_cache"]

    # Aliases so the body reads like the original inline code.
    tmdb_api_errors = buckets["tmdb_api_errors"]
    tmdb_fail_errors = buckets["tmdb_fail_errors"]
    trakt_connection_errors = buckets["trakt_connection_errors"]
    omdb_errors = buckets["omdb_errors"]
    omdb_api_limit_errors = buckets["omdb_api_limit_errors"]
    mdblist_errors = buckets["mdblist_errors"]
    mdblist_api_limit_errors = buckets["mdblist_api_limit_errors"]
    mdblist_attr_errors = buckets["mdblist_attr_errors"]
    mal_connection_errors = buckets["mal_connection_errors"]
    tautulli_url_errors = buckets["tautulli_url_errors"]
    tautulli_apikey_errors = buckets["tautulli_apikey_errors"]
    flixpatrol_errors = buckets["flixpatrol_errors"]
    flixpatrol_paywall = buckets["flixpatrol_paywall"]
    lsio_errors = buckets["lsio_errors"]
    to_be_configured_errors = buckets["to_be_configured_errors"]
    api_blank_errors = buckets["api_blank_errors"]
    bad_version_found_errors = buckets["bad_version_found_errors"]
    missing_path_errors = buckets["missing_path_errors"]
    cache_false = buckets["cache_false"]
    mass_update_errors = buckets["mass_update_errors"]
    other_award = buckets["other_award"]
    delete_unmanaged_collections_errors = buckets["delete_unmanaged_collections_errors"]
    plex_url_errors = buckets["plex_url_errors"]
    plex_regex_errors = buckets["plex_regex_errors"]
    plex_lib_errors = buckets["plex_lib_errors"]
    rounding_errors = buckets["rounding_errors"]
    metadata_attribute_errors = buckets["metadata_attribute_errors"]
    metadata_load_errors = buckets["metadata_load_errors"]
    overlay_load_errors = buckets["overlay_load_errors"]
    overlay_apply_errors = buckets["overlay_apply_errors"]
    overlay_level_errors = buckets["overlay_level_errors"]
    overlay_font_missing = buckets["overlay_font_missing"]
    overlay_image_missing = buckets["overlay_image_missing"]
    playlist_load_errors = buckets["playlist_load_errors"]
    playlist_errors = buckets["playlist_errors"]
    overlays_bloat = buckets["overlays_bloat"]
    convert_errors = buckets["convert_errors"]
    corrupt_image_errors = buckets["corrupt_image_errors"]
    image_size = buckets["image_size"]
    run_order_errors = buckets["run_order_errors"]
    checkFiles = buckets["checkFiles"]
    timeout_errors = buckets["timeout_errors"]
    new_version_found_errors = buckets["new_version_found_errors"]
    new_plexapi_version_found_errors = buckets["new_plexapi_version_found_errors"]
    git_kometa_errors = buckets["git_kometa_errors"]
    anidb69_errors = buckets["anidb69_errors"]
    anidb_auth_errors = buckets["anidb_auth_errors"]
    internal_server_errors = buckets["internal_server_errors"]
    no_items_found_errors = buckets["no_items_found_errors"]
    pmm_legacy_errors = buckets["pmm_legacy_errors"]

    return {
        "service_connectivity": (
            len(tmdb_api_errors)
            + len(tmdb_fail_errors)
            + len(trakt_connection_errors)
            + len(omdb_errors)
            + len(omdb_api_limit_errors)
            + len(mdblist_errors)
            + len(mdblist_api_limit_errors)
            + len(mdblist_attr_errors)
            + len(mal_connection_errors)
            + len(tautulli_url_errors)
            + len(tautulli_apikey_errors)
            + len(flixpatrol_errors)
            + len(flixpatrol_paywall)
            + len(lsio_errors)
        ),
        "config_setup": (
            len(to_be_configured_errors)
            + len(api_blank_errors)
            + len(bad_version_found_errors)
            + len(missing_path_errors)
            + len(cache_false)
            + len(mass_update_errors)
            + len(other_award)
            + len(delete_unmanaged_collections_errors)
        ),
        "plex_issues": len(plex_url_errors) + len(plex_regex_errors) + len(plex_lib_errors) + len(rounding_errors),
        "metadata_overlay_playlist": (
            len(metadata_attribute_errors)
            + len(metadata_load_errors)
            + len(overlay_load_errors)
            + len(overlay_apply_errors)
            + len(overlay_level_errors)
            + len(overlay_font_missing)
            + len(overlay_image_missing)
            + len(playlist_load_errors)
            + len(playlist_errors)
            + len(overlays_bloat)
        ),
        "convert_issues": len(convert_errors),
        "image_issues": len(corrupt_image_errors) + len(image_size),
        "runtime_behavior": len(run_order_errors) + len(checkFiles) + len(timeout_errors),
        "update_version": len(new_version_found_errors) + len(new_plexapi_version_found_errors) + len(git_kometa_errors),
        "platform_system": (
            (1 if wsl_recommendation else 0) + (1 if kometa_time_recommendation else 0) + (1 if kometa_mem_recommendation else 0) + (1 if kometa_db_cache_recommendation else 0)
        ),
        "anidb_issues": len(anidb69_errors) + len(anidb_auth_errors),
        "misc": len(internal_server_errors) + len(no_items_found_errors) + len(pmm_legacy_errors),
        "tmdb_api_errors": len(tmdb_api_errors),
        "tmdb_fail_errors": len(tmdb_fail_errors),
        "trakt_connection_errors": len(trakt_connection_errors),
        "omdb_errors": len(omdb_errors),
        "omdb_api_limit_errors": len(omdb_api_limit_errors),
        "mdblist_errors": len(mdblist_errors),
        "mdblist_api_limit_errors": len(mdblist_api_limit_errors),
        "mdblist_attr_errors": len(mdblist_attr_errors),
        "mal_connection_errors": len(mal_connection_errors),
        "tautulli_url_errors": len(tautulli_url_errors),
        "tautulli_apikey_errors": len(tautulli_apikey_errors),
        "flixpatrol_errors": len(flixpatrol_errors),
        "flixpatrol_paywall": len(flixpatrol_paywall),
        "lsio_errors": len(lsio_errors),
        "config_to_be_configured": len(to_be_configured_errors),
        "config_api_blank": len(api_blank_errors),
        "config_bad_version": len(bad_version_found_errors),
        "config_missing_path": len(missing_path_errors),
        "config_cache_false": len(cache_false),
        "config_mass_update": len(mass_update_errors),
        "config_other_award": len(other_award),
        "config_delete_unmanaged": len(delete_unmanaged_collections_errors),
        "plex_url_errors": len(plex_url_errors),
        "plex_regex_errors": len(plex_regex_errors),
        "plex_library_errors": len(plex_lib_errors),
        "plex_rounding_errors": len(rounding_errors),
        "metadata_attribute_errors": len(metadata_attribute_errors),
        "metadata_load_errors": len(metadata_load_errors),
        "overlay_load_errors": len(overlay_load_errors),
        "overlay_apply_errors": len(overlay_apply_errors),
        "overlay_level_errors": len(overlay_level_errors),
        "overlay_font_missing": len(overlay_font_missing),
        "overlay_image_missing": len(overlay_image_missing),
        "playlist_load_errors": len(playlist_load_errors),
        "playlist_errors": len(playlist_errors),
        "overlays_bloat": len(overlays_bloat),
        "image_corrupt": len(corrupt_image_errors),
        "image_size": len(image_size),
        "runtime_run_order": len(run_order_errors),
        "runtime_checkfiles": len(checkFiles),
        "runtime_timeout": len(timeout_errors),
        "update_kometa": len(new_version_found_errors),
        "update_plexapi": len(new_plexapi_version_found_errors),
        "update_git": len(git_kometa_errors),
        "platform_wsl": 1 if wsl_recommendation else 0,
        "platform_kometa_time": 1 if kometa_time_recommendation else 0,
        "platform_memory": 1 if kometa_mem_recommendation else 0,
        "platform_db_cache": 1 if kometa_db_cache_recommendation else 0,
        "anidb_69": len(anidb69_errors),
        "anidb_auth": len(anidb_auth_errors),
        "misc_internal_server": len(internal_server_errors),
        "misc_no_items": len(no_items_found_errors),
        "misc_pmm_legacy": len(pmm_legacy_errors),
    }
