"""Line-scan detector for the logscan recommendation engine.

Split out of :mod:`modules.logscan_recommendations_engine` -- this
module owns Phase 2 of ``make_recommendations``: iterating the log
content line-by-line, matching known error/warning patterns, and
populating ~57 per-issue "buckets" of line indices.

## What lives here

Single public entry point :func:`scan_content` that takes the
analyzer and raw log content, and returns a dict of bucket-name
-> list of line indices where each pattern was detected.  The
downstream Phases 3 (advisory-message builder) and 6 (issue-counts
dict) consume this dict.

## The detector

The main loop is a long chain of ``if``/``elif`` line-substring
tests kept in the same order the legacy make_recommendations
used.  Two branches are richer than simple string matches:

* ``rounding_errors`` -- gated on the analyzer having populated
  ``server_versions`` (a list of ``(server_name, server_version)``
  tuples).  Only fires on ``mass_user_rating_update`` /
  ``mass_episode_user_ratings_update`` lines.

* ``security_vuln_hits`` -- runs the PMS version regex from
  ``modules.logscan_pms_versions`` on any ``Connected to server``
  line and reports vulnerable versions.

Everything else is a straight substring/regex check that pushes
the current line index onto its bucket.

## Follow-up refactor notes

The engine's own docstring flagged this line-scan block for a
future data-driven refactor: replacing the if/elif chain with a
list of ``(predicate, bucket_key)`` tuples.  That would drop the
loop body to ~15 lines and let contributors add new detectors
without wading through the whole chain.  Intentionally out of
scope for the extraction PR -- kept as a pure byte-identical move
so review can focus on the file split.
"""

from __future__ import annotations

import re

from modules.logscan_pms_versions import is_vulnerable_pms_version


def scan_content(analyzer, content):
    """Scan the log *content* for known error/warning patterns.

    :param analyzer: the ``LogscanAnalyzer`` instance whose
        ``server_versions`` list gates the ``rounding_errors``
        detector.
    :param content: the raw log text to scan.
    :returns: dict mapping bucket-name -> list of line indices
        (1-based) where each pattern was detected.  Every bucket
        listed in the make_recommendations Phase 1 initialization
        block is present in the returned dict, even if empty.
    """
    lines = content.splitlines()
    anidb69_errors = []
    anidb_auth_errors = []
    api_blank_errors = []
    bad_version_found_errors = []
    cache_false = []
    checkFiles = []
    other_award = []
    convert_errors = []
    corrupt_image_errors = []
    critical_errors = []
    error_errors = []
    warning_errors = []
    delete_unmanaged_collections_errors = []
    flixpatrol_errors = []
    flixpatrol_paywall = []
    git_kometa_errors = []
    pmm_legacy_errors = []
    image_size = []
    internal_server_errors = []
    lsio_errors = []
    mal_connection_errors = []
    mass_update_errors = []
    mdblist_attr_errors = []
    mdblist_errors = []
    mdblist_api_limit_errors = []
    metadata_attribute_errors = []
    metadata_load_errors = []
    missing_path_errors = []
    new_version_found_errors = []
    new_plexapi_version_found_errors = []
    no_items_found_errors = []
    omdb_errors = []
    omdb_api_limit_errors = []
    overlays_bloat = []
    overlay_font_missing = []
    overlay_apply_errors = []
    overlay_image_missing = []
    overlay_level_errors = []
    overlay_load_errors = []
    playlist_load_errors = []
    playlist_errors = []
    plex_lib_errors = []
    plex_regex_errors = []
    plex_url_errors = []
    rounding_errors = []
    ruamel_errors = []
    run_order_errors = []
    security_vuln_hits = []
    traceback_errors = []
    tautulli_url_errors = []
    tautulli_apikey_errors = []
    timeout_errors = []
    to_be_configured_errors = []
    tmdb_api_errors = []
    tmdb_fail_errors = []
    trakt_connection_errors = []

    for idx, line in enumerate(lines, start=1):
        if "run_order:" in line:
            next_line = lines[idx] if idx < len(lines) else None
            if next_line and "- operations" not in next_line:
                run_order_errors.append(idx)
        if "No Anime Found for AniDB ID: 69" in line:
            anidb69_errors.append(idx)
        if re.search(r"\bcache: false\b", line):
            cache_false.append(idx)
        if analyzer.server_versions and ("mass_user_rating_update" in line or "mass_episode_user_ratings_update" in line):

            # Set to keep track of unique (server_name, server_version, idx) combinations
            unique_entries = set()

            # Iterate through each (server_name, server_version) tuple in analyzer.server_versions
            for server_name, server_version in analyzer.server_versions:

                # Create a unique identifier for the tuple
                identifier = (server_name, server_version, idx)

                # Check if the identifier is not in unique_entries (i.e., it's a new entry)
                if identifier not in unique_entries:
                    # Append server info to rounding_errors
                    rounding_errors.append((server_name, server_version, idx))
                    # Add the identifier to unique_entries set to mark it as processed
                    unique_entries.add(identifier)

        # Detect PMS versions in "Connected to server ..." lines and flag the vulnerable range
        m = re.search(r"Connected to server\s+(.+?)\s+(?:\(?\s*(?:version|Version:)\s+)(\d+\.\d+\.\d+\.\d+(?:-[A-Za-z0-9]+)?)", line)
        if m:
            sn = m.group(1).strip()
            ver = m.group(2).strip()
            if is_vulnerable_pms_version(ver):
                security_vuln_hits.append((sn, ver, idx))

        if "Config Error: anidb sub-attribute" in line or "AniDB Error: Login failed" in line:
            anidb_auth_errors.append(idx)
        elif "apikey is blank" in line:
            api_blank_errors.append(idx)
        elif "1.32.7" in line and "Connected to server " in line:
            bad_version_found_errors.append(idx)
        elif "Convert Warning: No " in line and "ID Found for" in line:
            convert_errors.append(idx)
        elif "PIL.UnidentifiedImageError: cannot" in line:
            corrupt_image_errors.append(idx)
        elif "checkFiles=1" in line:
            checkFiles.append(idx)
        elif "other_award" in line:
            other_award.append(idx)
        elif "delete_unmanaged_collections" in line:
            delete_unmanaged_collections_errors.append(idx)
        elif "internal_server_error" in line:
            internal_server_errors.append(idx)
        elif "FlixPatrol Error: " in line and "failed to parse" in line:
            flixpatrol_errors.append(idx)
        elif "flixpatrol" in line and "- pmm:" in line:
            flixpatrol_paywall.append(idx)
        elif "- git: PMM" in line:
            git_kometa_errors.append(idx)
        elif "- pmm: " in line:
            pmm_legacy_errors.append(idx)
        elif ", in _upload_image" in line:
            image_size.append(idx)
        elif "(Linuxserver" in line and "Version:" in line:
            lsio_errors.append(idx)
        elif "My Anime List Connection Failed" in line:
            mal_connection_errors.append(idx)
        elif "Config Error: Operation mass_" in line and "without a successful" in line:
            mass_update_errors.append(idx)
        elif "mdblist_list attribute not allowed with Collection Level: Season" in line:
            mdblist_attr_errors.append(idx)
        elif "MdbList Error: Invalid API key" in line:
            mdblist_errors.append(idx)
        elif "MDBList Error: API Limit Reached" in line or "MDBList Error: API Rate Limit Reached" in line:
            mdblist_api_limit_errors.append(idx)
        elif "metadata attribute is required" in line:
            metadata_attribute_errors.append(idx)
        elif "Metadata File Failed To Load" in line:
            metadata_load_errors.append(idx)
        elif "Overlay File Failed To Load" in line:
            overlay_load_errors.append(idx)
        elif "Playlist File Failed To Load" in line:
            playlist_load_errors.append(idx)
        elif "missing_path" in line or "save_missing" in line:
            missing_path_errors.append(idx)
        elif "Newest Version: " in line:
            new_version_found_errors.append(idx)
        elif "requires an update to:" in line:
            new_plexapi_version_found_errors.append(idx)
        elif "OMDb Error: Invalid API key" in line:
            omdb_errors.append(idx)
        elif "OMDb Error: Request limit reached" in line:
            omdb_api_limit_errors.append(idx)
        elif "Overlay Error: Poster already has an Overlay" in line:
            overlay_apply_errors.append(idx)
        elif "| Overlay Error: Overlay Image not found" in line:
            overlay_image_missing.append(idx)
        elif "overlay_level:" in line:
            overlay_level_errors.append(idx)
        elif "Plex Error: No Items found in Plex" in line:
            no_items_found_errors.append(idx)
        elif "Overlay Error: font:" in line:
            overlay_font_missing.append(idx)
        elif "Reapply Overlays: True" in line or "Reset Overlays: [" in line:
            overlays_bloat.append(idx)
        elif "Playlist Error: Library: " in line and "not defined" in line:
            playlist_errors.append(idx)
        elif "Plex Error: Plex Library " in line and "not found" in line:
            plex_lib_errors.append(idx)
        elif "Plex Error: " in line and "No matches found with regex pattern" in line:
            plex_regex_errors.append(idx)
        elif "Plex Error: Plex url is invalid" in line:
            plex_url_errors.append(idx)
        elif "ruamel.yaml." in line:
            ruamel_errors.append(idx)
        elif "TMDb Error: Invalid API key" in line:
            tmdb_api_errors.append(idx)
        elif "Traceback (most recent call last):" in line:
            traceback_errors.append(idx)
        elif "Tautulli Error: Invalid apikey" in line:
            tautulli_apikey_errors.append(idx)
        elif "Tautulli Error: Invalid URL" in line:
            tautulli_url_errors.append(idx)
        elif "timed out." in line:
            timeout_errors.append(idx)
        elif "Failed to Connect to https://api.themoviedb.org/3" in line:
            tmdb_fail_errors.append(idx)
        elif "Error: " in line and " requires " in line and " to be configured" in line:
            to_be_configured_errors.append(idx)
        elif "Trakt Connection Failed" in line:
            trakt_connection_errors.append(idx)
        elif "[CRITICAL]" in line:
            critical_errors.append(idx)
        elif "[ERROR]" in line:
            error_errors.append(idx)
        elif "[WARNING]" in line:
            warning_errors.append(idx)

    return {
        "anidb69_errors": anidb69_errors,
        "anidb_auth_errors": anidb_auth_errors,
        "api_blank_errors": api_blank_errors,
        "bad_version_found_errors": bad_version_found_errors,
        "cache_false": cache_false,
        "checkFiles": checkFiles,
        "other_award": other_award,
        "convert_errors": convert_errors,
        "corrupt_image_errors": corrupt_image_errors,
        "critical_errors": critical_errors,
        "error_errors": error_errors,
        "warning_errors": warning_errors,
        "delete_unmanaged_collections_errors": delete_unmanaged_collections_errors,
        "flixpatrol_errors": flixpatrol_errors,
        "flixpatrol_paywall": flixpatrol_paywall,
        "git_kometa_errors": git_kometa_errors,
        "pmm_legacy_errors": pmm_legacy_errors,
        "image_size": image_size,
        "internal_server_errors": internal_server_errors,
        "lsio_errors": lsio_errors,
        "mal_connection_errors": mal_connection_errors,
        "mass_update_errors": mass_update_errors,
        "mdblist_attr_errors": mdblist_attr_errors,
        "mdblist_errors": mdblist_errors,
        "mdblist_api_limit_errors": mdblist_api_limit_errors,
        "metadata_attribute_errors": metadata_attribute_errors,
        "metadata_load_errors": metadata_load_errors,
        "missing_path_errors": missing_path_errors,
        "new_version_found_errors": new_version_found_errors,
        "new_plexapi_version_found_errors": new_plexapi_version_found_errors,
        "no_items_found_errors": no_items_found_errors,
        "omdb_errors": omdb_errors,
        "omdb_api_limit_errors": omdb_api_limit_errors,
        "overlays_bloat": overlays_bloat,
        "overlay_font_missing": overlay_font_missing,
        "overlay_apply_errors": overlay_apply_errors,
        "overlay_image_missing": overlay_image_missing,
        "overlay_level_errors": overlay_level_errors,
        "overlay_load_errors": overlay_load_errors,
        "playlist_load_errors": playlist_load_errors,
        "playlist_errors": playlist_errors,
        "plex_lib_errors": plex_lib_errors,
        "plex_regex_errors": plex_regex_errors,
        "plex_url_errors": plex_url_errors,
        "rounding_errors": rounding_errors,
        "ruamel_errors": ruamel_errors,
        "run_order_errors": run_order_errors,
        "security_vuln_hits": security_vuln_hits,
        "traceback_errors": traceback_errors,
        "tautulli_url_errors": tautulli_url_errors,
        "tautulli_apikey_errors": tautulli_apikey_errors,
        "timeout_errors": timeout_errors,
        "to_be_configured_errors": to_be_configured_errors,
        "tmdb_api_errors": tmdb_api_errors,
        "tmdb_fail_errors": tmdb_fail_errors,
        "trakt_connection_errors": trakt_connection_errors,
    }
