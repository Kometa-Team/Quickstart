"""Recommendation engine for LogscanAnalyzer.

Extracted from :class:`modules.logscan.LogscanAnalyzer` to isolate
the 1000+ line ``make_recommendations`` function.

This module scans a Kometa log for known error/warning patterns
and builds a list of markdown-formatted recommendation messages
plus a dict of issue counts.  It's the core of what Quickstart
displays as ``Log Recommendations`` on the log-scan result page.

The public entry point :func:`make_recommendations` still takes
the :class:`LogscanAnalyzer` instance as its first argument
(``analyzer``) so it has access to fields like ``server_versions``,
``current_kometa_version``, ``run_time``, ``plex_timeout``, etc.
that are populated during the wider log-scan pipeline.  Method
calls like ``analyzer.calculate_recommendation(...)`` still
delegate through the analyzer's thin wrappers to the extracted
modules -- see :mod:`modules.logscan_recommendations` and friends.

Follow-up refactor notes (for future PRs):

* The line-detector block (~200 lines) is a big if/elif chain that
  could become data-driven with a list of (predicate, bucket)
  tuples.

* The advisory-builder blocks (~800 lines) mostly follow a shared
  template shape (icon + title + body + url + count line) and
  could collapse to a data table with a dozen inline exceptions.

Both are pure refactors that would materially shrink this module
without changing behavior.  Kept for a later pass to keep this
PR reviewable as a straight move.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from modules.logscan_pms_versions import (
    VULNERABLE_RANGE_HIGH,
    VULNERABLE_RANGE_LOW,
    format_version_tuple,
    is_vulnerable_pms_version,
)

mylogger = logging.getLogger("logscan")


def make_recommendations(analyzer, content, incomplete_message):
    """Scan *content* for known issues and build a recommendation list.

    Arguments:
        analyzer -- the :class:`LogscanAnalyzer` instance whose state
                    (``server_versions``, ``run_time``,
                    ``current_kometa_version``, etc.) drives some
                    branches.  This function also WRITES back the
                    ``checkfiles_flg`` attribute on the analyzer.
        content -- the raw log text to scan.
        incomplete_message -- optional string (or falsy) describing
                              why the log looks incomplete; when
                              present a "INCOMPLETE LOGS" advisory
                              is added.

    Returns:
        (recommendation_messages, issue_counts) where
        * recommendation_messages is a list of
          ``{"first_line": str, "message": str}`` dicts, unsorted
          (:meth:`LogscanAnalyzer.reorder_recommendations` handles
          that ordering downstream).
        * issue_counts is a dict of coarse and fine-grained counts
          keyed by issue-category name.
    """
    # ------------------------------------------------------------------
    # PHASE 1 -- initialize per-bucket line-index accumulators
    # ------------------------------------------------------------------
    analyzer.checkfiles_flg = None
    lines = content.splitlines()
    special_check_lines = []
    anidb69_errors = []
    anidb_auth_errors = []
    api_blank_errors = []
    bad_version_found_errors = []
    cache_false = []
    checkFiles = []
    current_year = []
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

    # ------------------------------------------------------------------
    # PHASE 2 -- line-scan detector (populates the buckets above)
    # ------------------------------------------------------------------
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
        elif "current_year" in line:
            current_year.append(idx)
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

    # ------------------------------------------------------------------
    # PHASE 3 -- build advisory messages from the populated buckets
    # ------------------------------------------------------------------
    platform_recs = _build_advisory_messages(
        analyzer=analyzer,
        content=content,
        incomplete_message=incomplete_message,
        special_check_lines=special_check_lines,
        # buckets
        anidb69_errors=anidb69_errors,
        anidb_auth_errors=anidb_auth_errors,
        api_blank_errors=api_blank_errors,
        bad_version_found_errors=bad_version_found_errors,
        cache_false=cache_false,
        checkFiles=checkFiles,
        other_award=other_award,
        critical_errors=critical_errors,
        error_errors=error_errors,
        warning_errors=warning_errors,
        convert_errors=convert_errors,
        corrupt_image_errors=corrupt_image_errors,
        delete_unmanaged_collections_errors=delete_unmanaged_collections_errors,
        flixpatrol_errors=flixpatrol_errors,
        flixpatrol_paywall=flixpatrol_paywall,
        git_kometa_errors=git_kometa_errors,
        pmm_legacy_errors=pmm_legacy_errors,
        image_size=image_size,
        internal_server_errors=internal_server_errors,
        lsio_errors=lsio_errors,
        mal_connection_errors=mal_connection_errors,
        mass_update_errors=mass_update_errors,
        mdblist_attr_errors=mdblist_attr_errors,
        mdblist_errors=mdblist_errors,
        mdblist_api_limit_errors=mdblist_api_limit_errors,
        metadata_attribute_errors=metadata_attribute_errors,
        metadata_load_errors=metadata_load_errors,
        overlay_load_errors=overlay_load_errors,
        playlist_load_errors=playlist_load_errors,
        missing_path_errors=missing_path_errors,
        new_plexapi_version_found_errors=new_plexapi_version_found_errors,
        new_version_found_errors=new_version_found_errors,
        no_items_found_errors=no_items_found_errors,
        omdb_errors=omdb_errors,
        omdb_api_limit_errors=omdb_api_limit_errors,
        overlay_font_missing=overlay_font_missing,
        overlays_bloat=overlays_bloat,
        overlay_apply_errors=overlay_apply_errors,
        overlay_image_missing=overlay_image_missing,
        overlay_level_errors=overlay_level_errors,
        playlist_errors=playlist_errors,
        plex_regex_errors=plex_regex_errors,
        plex_lib_errors=plex_lib_errors,
        plex_url_errors=plex_url_errors,
        rounding_errors=rounding_errors,
        ruamel_errors=ruamel_errors,
        run_order_errors=run_order_errors,
        security_vuln_hits=security_vuln_hits,
        traceback_errors=traceback_errors,
        tautulli_apikey_errors=tautulli_apikey_errors,
        tautulli_url_errors=tautulli_url_errors,
        tmdb_api_errors=tmdb_api_errors,
        timeout_errors=timeout_errors,
        tmdb_fail_errors=tmdb_fail_errors,
        to_be_configured_errors=to_be_configured_errors,
        trakt_connection_errors=trakt_connection_errors,
    )

    # ------------------------------------------------------------------
    # PHASE 4 -- side-effect: flip the checkfiles flag
    # ------------------------------------------------------------------
    if checkFiles:
        analyzer.checkfiles_flg = 1

    # ------------------------------------------------------------------
    # PHASE 5 -- assemble the {first_line, message} dict list
    # ------------------------------------------------------------------
    recommendation_messages = []
    for idx, message in enumerate(special_check_lines, start=1):
        # Split the message into lines and log the first line with a label
        message_lines = message.split("\n")
        first_line = message_lines[0] if message_lines else ""
        mylogger.debug(f"Kometa Recommendation {idx}: {first_line}")
        recommendation_messages.append({"first_line": first_line, "message": message})

    # ------------------------------------------------------------------
    # PHASE 6 -- issue-counts dict for the dashboard
    # ------------------------------------------------------------------
    wsl_recommendation = platform_recs["wsl"]
    kometa_time_recommendation = platform_recs["time"]
    kometa_mem_recommendation = platform_recs["memory"]
    kometa_db_cache_recommendation = platform_recs["db_cache"]

    issue_counts = {
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

    return recommendation_messages, issue_counts


def _build_advisory_messages(
    *,
    analyzer,
    content,
    incomplete_message,
    special_check_lines,
    anidb69_errors,
    anidb_auth_errors,
    api_blank_errors,
    bad_version_found_errors,
    cache_false,
    checkFiles,
    other_award,
    critical_errors,
    error_errors,
    warning_errors,
    convert_errors,
    corrupt_image_errors,
    delete_unmanaged_collections_errors,
    flixpatrol_errors,
    flixpatrol_paywall,
    git_kometa_errors,
    pmm_legacy_errors,
    image_size,
    internal_server_errors,
    lsio_errors,
    mal_connection_errors,
    mass_update_errors,
    mdblist_attr_errors,
    mdblist_errors,
    mdblist_api_limit_errors,
    metadata_attribute_errors,
    metadata_load_errors,
    overlay_load_errors,
    playlist_load_errors,
    missing_path_errors,
    new_plexapi_version_found_errors,
    new_version_found_errors,
    no_items_found_errors,
    omdb_errors,
    omdb_api_limit_errors,
    overlay_font_missing,
    overlays_bloat,
    overlay_apply_errors,
    overlay_image_missing,
    overlay_level_errors,
    playlist_errors,
    plex_regex_errors,
    plex_lib_errors,
    plex_url_errors,
    rounding_errors,
    ruamel_errors,
    run_order_errors,
    security_vuln_hits,
    traceback_errors,
    tautulli_apikey_errors,
    tautulli_url_errors,
    tmdb_api_errors,
    timeout_errors,
    tmdb_fail_errors,
    to_be_configured_errors,
    trakt_connection_errors,
):
    """Append advisory messages to *special_check_lines* for each populated bucket.

    Runs through each detected issue bucket in the same order the
    legacy make_recommendations did, appending markdown advisory
    strings to the caller's ``special_check_lines`` list.  Also
    inserts platform-recommendation strings computed via the
    analyzer wrapper methods (WSL/time/memory/db_cache).

    Returns a dict of the platform-recommendation truthiness flags
    ``{'wsl': ..., 'time': ..., 'memory': ..., 'db_cache': ...}``
    so the caller can populate the ``issue_counts`` dict without
    re-running the extraction pipeline.
    """
    if anidb69_errors:
        url_line = "[https://kometa.wiki/en/latest/config/anidb]"
        formatted_errors = analyzer.format_contiguous_lines(anidb69_errors)
        anidb69_error_message = (
            "❌ **ANIDB69 ERROR**\n"
            "Kometa uses AniDB ID 69 to test that it can connect to AniDB.\n"
            "This error indicates that the test request sent to AniDB failed and AniDB could not be reached.\n"
            f"For more information on configuring AniDB, {url_line}\n"
            f"{len(anidb69_errors)} line(s) with ANIDB69 errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(anidb69_error_message)

    if anidb_auth_errors:
        url_line = "[https://kometa.wiki/en/latest/config/anidb]"
        formatted_errors = analyzer.format_contiguous_lines(anidb_auth_errors)
        anidb_auth_errors_message = (
            "❌ **ANIDB AUTH ERRORS**\n"
            "Kometa uses AniDB settings to connect to AniDB.\n"
            "This error indicates that the setting is not correctly setup in config.yml.\n"
            f"For more information on configuring AniDB, {url_line}\n"
            f"{len(anidb_auth_errors)} line(s) with ANIDB AUTH errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(anidb_auth_errors_message)

    if api_blank_errors:
        url_line = "[https://kometa.wiki/en/latest/config/trakt/?q=api]"
        formatted_errors = analyzer.format_contiguous_lines(api_blank_errors)
        api_blank_error_message = (
            "❌🔒 **BLANK API KEY ERROR**\n"
            "An API key is required for certain services, and it appears to be blank in your configuration.\n"
            "Make sure to provide the required API key to enable proper functionality.\n"
            f"For more information on configuring API keys, {url_line}\n"
            "In the Kometa discord thread, type `!wiki` for more information and search for the service with the missing apikey \n"
            f"{len(api_blank_errors)} line(s) with BLANK API KEY errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(api_blank_error_message)

    if bad_version_found_errors:
        url_line = "[https://forums.plex.tv/t/refresh-endpoint-put-post-requests-started-throwing-404s-in-version-1-32-7-7484/853588]"
        formatted_errors = analyzer.format_contiguous_lines(bad_version_found_errors)
        bad_version_found_errors_message = (
            "💥 **BAD PLEX VERSION ERROR**\n"
            "You are running a version of Plex that is known to have issues with Kometa.\n"
            "You should downgrade/upgrade to a version that is not `1.32.7.*`.\n"
            f"For more information on this issue, {url_line}\n"
            f"{len(bad_version_found_errors)} line(s) with Plex Version 1.32.7.*. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(bad_version_found_errors_message)

    if cache_false:
        url_line = "[https://kometa.wiki/en/latest/config/settings#cache]"
        formatted_errors = analyzer.format_contiguous_lines(cache_false)
        cache_false_message = (
            "💬 **Kometa CACHE**\n"
            "Kometa cache setting is set to false(`cache: false`). Normally, you would want this set to true to improve performance.\n"
            f"For more information on handling this, {url_line}\n"
            f"{len(cache_false)} line(s) with `cache: false`. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(cache_false_message)

    if checkFiles:
        formatted_errors = analyzer.format_contiguous_lines(checkFiles)
        checkFiles_message = (
            "⚠️ **CHECKFILES=1 DETECTED**\n"
            "`checkFiles=1` detected. Notifying Kometa staff.\n"
            f"{len(checkFiles)} line(s) with `checkFiles=1` messages. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(checkFiles_message)

    # if current_year:
    #     url_line = "[https://kometa.wiki/en/latest/files/dynamic_types/?h=latest#imdb-awards]"
    #     formatted_errors = analyzer.format_contiguous_lines(current_year)
    #     current_year_message = (
    #             "⚠️ **LEGACY SCHEMA DETECTED**\n"
    #             "As of 1.20 `current_year` is no longer used and should be replaced with `latest`.\n"
    #             f"For more information on handling these, {url_line}\n"
    #             f"{len(current_year)} line(s) with `current_year` issues. Line number(s): {formatted_errors}"
    #     )
    #     special_check_lines.append(current_year_message)

    if other_award:
        url_line = "[https://kometa.wiki/en/latest/kometa/faqs/?h=other_award#pmm-120-release-changes]"
        formatted_errors = analyzer.format_contiguous_lines(other_award)
        other_award_message = (
            "⚠️ **LEGACY SCHEMA DETECTED**\n"
            "As of 1.20 `other_award` is no longer used and should be removed. All of those awards now have their own individual files.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(other_award)} line(s) with `other_award` issues. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(other_award_message)

    if critical_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Bcritical%5D#critical]"
        formatted_errors = analyzer.format_contiguous_lines(critical_errors)
        critical_error_message = (
            "💥 **[CRITICAL]**\n"
            f"Critical messages found in your attached log.\n"
            f"There is a very strong likelihood that Kometa aborted the run or part of the run early thus not all of what you wanted was applied.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(critical_errors)} line(s) with [CRITICAL] messages. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(critical_error_message)

    if error_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
        formatted_errors = analyzer.format_contiguous_lines(error_errors)
        error_error_message = (
            "❌ **[ERROR]**\n"
            f"Error messages found in your attached log.\n"
            f"There is a very strong likelihood that Kometa did not complete all of what you wanted. Some [ERROR] lines can be ignored.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(error_errors)} line(s) with [ERROR] messages. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(error_error_message)

    if warning_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Bwarning%5D#warning]"
        formatted_errors = analyzer.format_contiguous_lines(warning_errors)
        warning_error_message = (
            f"⚠️ **[WARNING]**\n"
            f"Warning messages found in your attached log.\n"
            f"This is a Kometa warning and usually does not require any immediate action. Most [WARNING] lines can be ignored.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(warning_errors)} line(s) with [WARNING] messages. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(warning_error_message)

    if convert_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/#warning]"
        formatted_errors = analyzer.format_contiguous_lines(convert_errors)
        convert_error_message = (
            "💬 **CONVERT WARNING**\n"
            "Convert Warning: No * ID Found for * ID.\n"
            "These sorts of errors indicate that the thing can't be cross-referenced between sites.  For example:\n\n"
            "Convert Warning: No TVDb ID Found for TMDb ID: 15733\n\n"
            "In the above scenario, the TMDB record for `The Two Mrs. Grenvilles` `ID 15733` didn't contain a TVDB ID. This could be because the record just hasn't been updated, or because `The Two Mrs. Grenvilles` isn't listed on TVDB.\n\n"
            "The fix is for someone `like you, perhaps` to go to the relevant site and fill in the missing data.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(convert_errors)} line(s) with Convert Warnings. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(convert_error_message)

    if corrupt_image_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/#error]"
        formatted_errors = analyzer.format_contiguous_lines(corrupt_image_errors)
        corrupt_image_message = (
            "❌ **CORRUPT FILE ERROR**\n"
            "Likely, when processing overlays, Kometa encountered a file that it could not process because it was corrupt.\n"
            "Review the lines in your log file and based on the lines shown here and determine if those files are ok or not with your favorite image editor.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(corrupt_image_errors)} line(s) with `PIL.UnidentifiedImageError` reported. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(corrupt_image_message)

    if delete_unmanaged_collections_errors:
        url_line = "[https://kometa.wiki/en/latest/config/operations/#delete-collections]"
        formatted_errors = analyzer.format_contiguous_lines(delete_unmanaged_collections_errors)
        delete_unmanaged_collections_errors_message = (
            "⚠️ **LEGACY SCHEMA DETECTED**\n"
            "`delete_unmanaged_collections` is a Library operation and should be adjusted in your config file accordingly.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(delete_unmanaged_collections_errors)} line(s) with `delete_unmanaged_collections` errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(delete_unmanaged_collections_errors_message)

    if flixpatrol_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/faqs/?h=flixpatrol#flixpatrol]"
        formatted_errors = analyzer.format_contiguous_lines(flixpatrol_errors)
        flixpatrol_error_message = (
            "❌ **FLIXPATROL ERROR**\n"
            "There was an issue with FlixPatrol data.\n"
            "This is a known issue with Kometa 1.19.0 (master/latest branch).\n"
            "Switch to the 1.19.1 nightly21 or greater Kometa release for a fix.\n"
            "In the Kometa discord thread, for more information on how to switch branches, type `!branch`.\n"
            f"For more information on handling FlixPatrol errors, {url_line}\n"
            "If the problem persists, your IP address might be banned by FlixPatrol. Contact their support to have it unbanned.\n"
            f"{len(flixpatrol_errors)} line(s) with FlixPatrol errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(flixpatrol_error_message)

    if flixpatrol_paywall:
        url_line = "[https://flixpatrol.com/about/premium/]"
        url_line2 = "[https://discord.com/channels/822460010649878528/1099773891733377065/1214929432754651176]"
        formatted_errors = analyzer.format_contiguous_lines(flixpatrol_paywall)
        flixpatrol_paywall_message = (
            "❌💰 **FLIXPATROL PAYWALL ERROR**\n"
            "FlixPatrol decided to implement a Paywall which causes Kometa to no longer gather data from them.\n"
            "Even if you pay, this will not work with Kometa.\n"
            f"For more information on the FlixPatrol paywall, {url_line}\n"
            f"As of Kometa 1.20.0-nightly34 (you are on {analyzer.current_kometa_version}), we have eliminated FlixPatrol. See this announcement: {url_line2}\n"
            f"{len(flixpatrol_paywall)} line(s) with `- pmm: flixpatrol` detected. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(flixpatrol_paywall_message)

    if git_kometa_errors:
        url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
        formatted_errors = analyzer.format_contiguous_lines(git_kometa_errors)
        git_kometa_error_message = (
            "💬 **OLD Kometa YAML**\n"
            "You are using an old config.yml with references to metadata files that date to a version of Kometa that is pre 1.18\n"
            "In the Kometa discord thread, type `!118` for more information.\n"
            f"For more information on handling this, {url_line}\n"
            f"{len(git_kometa_errors)} line(s) with OLD Kometa YAML. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(git_kometa_error_message)

    if pmm_legacy_errors:
        url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
        formatted_errors = analyzer.format_contiguous_lines(pmm_legacy_errors)
        pmm_legacy_error_message = (
            "💬 **PRE KOMETA YAML**\n"
            "You are using an old config.yml with references to metadata files that date to a version of this script that is pre Kometa\n"
            "In your config.yml, search for `- pmm: ` and replace with `- default: ` .\n"
            f"For more information on handling this, {url_line}\n"
            f"{len(pmm_legacy_errors)} line(s) with PRE Kometa YAML. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(pmm_legacy_error_message)

    if image_size:
        url_line = "[https://www.google.com]"
        formatted_errors = analyzer.format_contiguous_lines(image_size)
        image_size_message = (
            "❌ **IMAGE SIZE ERRORS**\n"
            "It seems that you are attempting to upload or apply artwork and it's greater than the maximum `10MB`.\n"
            f"This usually means that you have internal server errors (500) as well in this log. Change the image to one that is less than 10MB. For more information on handling this, {url_line}\n"
            f"{len(image_size)} line(s) with IMAGE SIZE errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(image_size_message)

    if incomplete_message:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/#providing-log-files-on-discord]"
        incomplete_errors_message = (
            "❌🛠️ **INCOMPLETE LOGS**\n"
            f"{incomplete_message}\n"
            "**The attached file seems incomplete. Without a complete log file troubleshooting is limited as we might be missing valuable information!**\n"
            "Type `!logs` for more information about providing logs."
            f"For more information on providing logs, {url_line}\n"
        )
        special_check_lines.append(incomplete_errors_message)

    if internal_server_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/faqs/?h=errors+issues#errors-issues]"
        formatted_errors = analyzer.format_contiguous_lines(internal_server_errors)
        internal_server_error_message = (
            "💥 **INTERNAL SERVER ERROR**\n"
            "An internal server error has occurred. This could be due to an issue with the service's server.\n"
            "In the Kometa discord thread, type `!500` for more information.\n"
            f"For more information on handling internal server errors, {url_line}\n"
            f"{len(internal_server_errors)} line(s) with INTERNAL SERVER errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(internal_server_error_message)

    if lsio_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/install/images/?h=linuxserver#linuxserver]"
        formatted_errors = analyzer.format_contiguous_lines(lsio_errors)
        lsio_error_message = (
            "⚠️🖥️ **LINUXSERVER IMAGE DETECTED**\n"
            "You are not using the official Kometa container image.\n"
            "In the Kometa discord thread, type `!lsio` for more information.\n"
            f"For more information on this, {url_line}\n"
            f"{len(lsio_errors)} line(s) with LINUXSERVER IMAGE issues. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(lsio_error_message)

    if mal_connection_errors:
        url_line = "[https://kometa.wiki/en/latest/config/myanimelist]"
        formatted_errors = analyzer.format_contiguous_lines(mal_connection_errors)
        mal_connection_error_message = (
            "❌ **MY ANIME LIST CONNECTION ERROR**\n"
            "There was an issue connecting to My Anime List (MAL) service.\n"
            "This will affect any functionality that relies on MAL data.\n"
            "In the Kometa discord thread, type `!mal` for more information\n"
            f"For more information on configuring the My Anime List (MAL) service, {url_line}\n"
            f"{len(mal_connection_errors)} line(s) with MY ANIME LIST CONNECTION errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(mal_connection_error_message)

    if mass_update_errors:
        url_line = "[https://kometa.wiki/en/latest/config/operations]"
        formatted_errors = analyzer.format_contiguous_lines(mass_update_errors)
        mass_update_errors_message = (
            "❌ **MASS_*_UPDATE ERROR**\n"
            "You have specified a `mass_*_update` operation in your config file however you have not configured the corresponding service so this will never work.\n"
            "Review each of the lines mentioned in this message to understand what all the config issues are.\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on `mass_*_update` operations, {url_line}\n"
            f"{len(mass_update_errors)} line(s) with `mass_*_update` config errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(mass_update_errors_message)

    if mdblist_attr_errors:
        url_line = "[https://kometa.wiki/en/latest/files/builders/mdblist/?h=mdblist+builders]"
        formatted_errors = analyzer.format_contiguous_lines(mdblist_attr_errors)
        mdblist_attr_error_message = (
            f"❌ **MDBLIST ATTRIBUTE ERROR**\n"
            f"MDBList functionality does not currently support season-level collections.\n"
            f"In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on MDBList configuration, {url_line}\n"
            f"{len(mdblist_attr_errors)} line(s) with MDBList attribute errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(mdblist_attr_error_message)

    if mdblist_errors:
        url_line = "[https://kometa.wiki/en/latest/config/mdblist/?h=mdblist+attributes#mdblist-attributes]"
        formatted_errors = analyzer.format_contiguous_lines(mdblist_errors)
        mdblist_error_message = (
            f"❌ **MDBLIST ERROR**\n"
            f"Your configuration contains an invalid API key for MdbList.\n"
            f"This will cause any services that rely on MdbList to fail.\n"
            f"In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on configuring MdbList, {url_line}\n"
            f"{len(mdblist_errors)} line(s) with MDBLIST errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(mdblist_error_message)

    if mdblist_api_limit_errors:
        url_line = "[https://kometa.wiki/en/latest/config/mdblist/?h=mdblist+attributes#mdblist-attributes]"
        formatted_errors = analyzer.format_contiguous_lines(mdblist_api_limit_errors)
        mdblist_api_limit_error_message = (
            f"❌ **MDBLIST API LIMIT ERROR**\n"
            f"You have hit the MDBLIST API LIMIT. The free apikey is limited to 1000 requests per day so if you hit your limit Kometa should be able to pick up where it left off the next day as long as the Kometa cache setting is enabled in yur config.yml file.\n"
            f"This will cause any metadata updates that rely on MdbList to fail until the limit is reset (usually daily).\n"
            f"For more information on configuring MdbList, {url_line}\n"
            f"{len(mdblist_api_limit_errors)} line(s) with MDBLIST API Limit errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(mdblist_api_limit_error_message)

    if metadata_attribute_errors:
        url_line = "[https://kometa.wiki/en/latest/config/files/#example]"
        formatted_errors = analyzer.format_contiguous_lines(metadata_attribute_errors)
        metadata_attribute_errors_message = (
            f"❌ **METADATA ATTRIBUTE ERRORS**\n"
            f"If you are using Kometa nightly48 or newer, this is expected behaviour.\n"
            f"`metadata_path` and `overlay_path` are now legacy attributes, and using them will cause the `YAML Error: metadata attribute is required` error.\n"
            f"The error can be ignored as it won't cause any issues, or you can update your config.yml to use the new `collection_files`, `overlay_files` and `metadata_files` attributes.\n\n"
            f"The steps to take are:\n"
            f":one: - Look at every file referred to within your config.yml and see what the first level indentation yaml file attributes are. They should be one of these(`collections:, dynamic_collections:, overlays:, metadata:, playlists:, templates:, external_templates:`) and can contain more than 1. For now, ignore the `templates:` and `external_templates:` attributes.\n"
            f":two: - if it's `metadata:`, file it under the `metadata_file:` section of your config.yml\n"
            f":three: - if it's `collections:` or `dynamic_collections:`, file it under the `collection_files:` section of your config.yml\n"
            f":four: - if it's `playlists:`,  file it under the `playlist_files:` section of your config.yml\n"
            f":five: - if it's `overlays:`,  file it under the `overlay_files:` section of your config.yml\n\n"
            f"`*NOTE:` If you only see `templates:` or `external_templates:`, this is a special case and you typically would not be referring to it directly in your config.yml file.\n\n"
            f"Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
            f"For more information on this, {url_line}\n"
            f"{len(metadata_attribute_errors)} line(s) with METADATA ATTRIBUTE errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(metadata_attribute_errors_message)

    if metadata_load_errors:
        url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
        formatted_errors = analyzer.format_contiguous_lines(metadata_load_errors)
        metadata_load_errors_message = (
            f"❌ **METADATA LOAD ERRORS**\n"
            f"Kometa is trying to load a file from your config file.\n"
            f"This error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\n"
            f"Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
            f"For more information on this, {url_line}\n"
            f"{len(metadata_load_errors)} line(s) with METADATA LOAD errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(metadata_load_errors_message)

    if overlay_load_errors:
        url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
        formatted_errors = analyzer.format_contiguous_lines(overlay_load_errors)
        overlay_load_errors_message = (
            "❌ **OVERLAY LOAD ERRORS**\n"
            "Kometa is trying to load a file from your config file.\n"
            "This error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\n"
            "Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
            f"For more information on this, {url_line}\n"
            f"{len(overlay_load_errors)} line(s) with OVERLAY LOAD errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(overlay_load_errors_message)

    if playlist_load_errors:
        url_line = "[https://kometa.wiki/en/latest/config/overview/?h=configuration]"
        formatted_errors = analyzer.format_contiguous_lines(playlist_load_errors)
        playlist_load_errors_message = (
            "❌ **PLAYLIST LOAD ERRORS**\n"
            "Kometa is trying to load a file from your config file.\n"
            "This error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\n"
            "Within the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\n"
            f"For more information on this, {url_line}\n"
            f"{len(playlist_load_errors)} line(s) with PLAYLIST LOAD errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(playlist_load_errors_message)

    if missing_path_errors:
        url_line = "[https://kometa.wiki/en/latest/config/libraries/?h=report_path#attributes]"
        formatted_errors = analyzer.format_contiguous_lines(missing_path_errors)
        missing_path_errors_message = (
            "⚠️ **LEGACY SCHEMA DETECTED**\n"
            "`missing_path` or `save_missing` is no longer used and should be replaced/removed. Use `report_path` instead.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(missing_path_errors)} line(s) with `missing_path` or `save_missing` errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(missing_path_errors_message)

    if new_plexapi_version_found_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/#checking-kometa-version]"
        formatted_errors = analyzer.format_contiguous_lines(new_plexapi_version_found_errors)
        new_plexapi_version_found_errors_message = (
            "🚀 **PYTHON MODULE UPDATE NEEDED**\n"
            # f"PlexAPI: {analyzer.current_plexapi_version}\n\n"
            "In the Kometa discord thread, type `!update` for instructions on how to update your requirements.\n"
            f"For more information on updating, {url_line}\n"
            f"{len(new_plexapi_version_found_errors)} line(s) with New Python Module Updates. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(new_plexapi_version_found_errors_message)

    if new_version_found_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/#checking-kometa-version]"
        formatted_errors = analyzer.format_contiguous_lines(new_version_found_errors)
        new_version_found_errors_message = (
            "🚀 **VERSION UPDATE AVAILABLE**\n"
            f"**Current Version:** {analyzer.current_kometa_version}\n"
            f"**Newest Version (at the time of this log):** {analyzer.kometa_newest_version}\n\n"
            "In the Kometa discord thread, type `!update` for instructions on how to update.\n"
            f"For more information on updating, {url_line}\n"
            f"{len(new_version_found_errors)} line(s) with New Version errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(new_version_found_errors_message)

    if no_items_found_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
        formatted_errors = analyzer.format_contiguous_lines(no_items_found_errors)
        no_items_error_message = (
            "⚠️ **NO ITEMS FOUND IN PLEX**\n"
            "The criteria defined by a search/filter returned 0 results.\n"
            "This is often expected - for example, if you try to apply a 1080P overlay to a 4K library then no items will get the overlay since no items have a 1080P resolution.\n"
            "It is worth noting that search and filters are case-sensitive, so `1080P` and `1080p` are treated as two separate things.\n"
            f"For more information on this error, {url_line}\n"
            f"{len(no_items_found_errors)} line(s) with 'No Items found in Plex' errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(no_items_error_message)

    if omdb_errors:
        url_line = "[https://kometa.wiki/en/latest/config/omdb/#omdb-attributes]"
        formatted_errors = analyzer.format_contiguous_lines(omdb_errors)
        omdb_error_message = (
            "❌ **OMDB ERROR**\n"
            "Your configuration contains an invalid API key for OMDb.\n"
            "This will cause any services that rely on OMDb to fail.\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on configuring OMDb, {url_line}\n"
            f"{len(omdb_errors)} line(s) with OMDb errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(omdb_error_message)

    if omdb_api_limit_errors:
        url_line = "[https://kometa.wiki/en/latest/config/omdb/?h=omdb#omdb-attributes]"
        formatted_errors = analyzer.format_contiguous_lines(omdb_api_limit_errors)
        omdb_api_limit_error_message = (
            f"❌ **OMDB API LIMIT ERROR**\n"
            f"You have hit the OMDB API LIMIT. The free apikey is limited to 1000 requests per day so if you hit your limit Kometa should be able to pick up where it left off the next day as long as the Kometa cache setting is enabled in yur config.yml file.\n"
            f"This will cause any metadata updates that rely on OMDB to fail until the limit is reset (usually daily).\n"
            f"For more information on configuring OMDB, {url_line}\n"
            f"{len(omdb_api_limit_errors)} line(s) with OMDB API Limit errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(omdb_api_limit_error_message)

    if overlay_font_missing:
        url_line = "[https://kometa.wiki/en/latest/showcase/overlays/?h=font#example-2]"
        formatted_errors = analyzer.format_contiguous_lines(overlay_font_missing)
        overlay_font_missing_message = (
            "❌ **OVERLAY FONT MISSING**\n"
            "We detected that you are referencing a font that Kometa cannot find.\n"
            "This can lead to overlays not being applied when a font is required.\n"
            f"In the Kometa discord thread, type `!wiki` for more information or follow this link: {url_line}\n"
            f"{len(overlay_font_missing)} line(s) with `Overlay Error: font:` errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(overlay_font_missing_message)

    if overlays_bloat:
        url_line = "[https://kometa.wiki/en/latest/kometa/scripts/imagemaid]"
        formatted_errors = analyzer.format_contiguous_lines(overlays_bloat)
        overlays_bloat_message = (
            "⚠️ **REAPPLY / RESET OVERLAYS**\n\n"
            "We detected that you are using either reapply_overlays OR reset_overlays within your config.\n\n"
            "**You should NOT be using reapply_overlays unless you have a specific reason to. If you are not sure do NOT enable it.**\n\n"
            "This can lead to your system creating additional posters within Plex causing bloat\n\n"
            "Typically these config lines are only used for very specific cases so if this is your case, then you can ignore this recommendation\n\n"
            f"In the Kometa discord thread, type `!bloat` for more information or follow this link: {url_line}\n\n"
            f"{len(overlays_bloat)} line(s) with reapply_overlays or reset_overlays. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(overlays_bloat_message)

    if overlay_apply_errors:
        url_line = "[https://kometa.wiki/en/latest/defaults/overlays]"
        url_line2 = "[https://kometa.wiki/en/latest/kometa/guides/assets]"
        formatted_errors = analyzer.format_contiguous_lines(overlay_apply_errors)
        overlay_apply_errors_message = (
            "⚠️ **OVERLAY APPLY ERROR**\n"
            "Kometa attempts to apply an overlay to things, but finds that the art on the item is already an overlaid poster from Kometa with an EXIF tag:\n"
            "```Abraham Season 1\n  Overlay Error: Poster already has an Overlay\nArchie Bunker''s Place S03E14\n  Overlay Error: Poster already has an Overlay\nAs Time Goes By Season 10\n  Overlay Error: Poster already has an Overlay\nCHiPs Season 3\n  Overlay Error: Poster already has an Overlay```\n\n"
            "For `Season` posters, this is often because Plex has assigned higher-level art [like the show poster to a season that has no art of its own].\n"
            "For `Movies`, `Show`, and `Episode` posters, this is often because an art item was selected or part of the assets pipeline that already had an overlay image on it.\n\n"
            "You can fix this by going to each item in Plex, hitting the pencil icon, selecting Poster, and choosing art that does not have an overlay.\n"
            "Alternatively if you are using the asset pipeline in Kometa, updating your asset pipeline with the art that does not have an overlay.\n"
            "In the Kometa discord thread, type `!overlaylabel` for more information.\n\n"
            f"For more information on overlays, {url_line}\n"
            f"For more information on the asset pipeline, {url_line2}\n"
            f"{len(overlay_apply_errors)} line(s) with OVERLAY APPLY errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(overlay_apply_errors_message)

    if overlay_image_missing:
        url_line = "[https://kometa.wiki/en/latest/defaults/overlays]"
        formatted_errors = analyzer.format_contiguous_lines(overlay_image_missing)
        overlay_image_missing_message = (
            "❌ **OVERLAY IMAGE MISSING ERROR**\n"
            "Kometa attempts to apply an overlay to things, but finds that the overlay itself is not found and thus cannot be applied to the art.\n"
            "Validate the path and also ensure that the case of the file(i.e. `4K.png` is NOT the same as `4k.png`) is the same as found in the line within the log.\n"
            f"For more information on overlays, {url_line}\n"
            f"{len(overlay_image_missing)} line(s) with OVERLAY IMAGE MISSING errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(overlay_image_missing_message)

    if overlay_level_errors:
        url_line = "[https://kometa.wiki/en/latest/files/settings/?h=builder_level]"
        formatted_errors = analyzer.format_contiguous_lines(overlay_level_errors)
        overlay_level_errors_message = (
            "⚠️ **LEGACY SCHEMA DETECTED**\n"
            "`overlay_level:` is no longer used and should be replaced by `builder_level:`.\n"
            f"For more information on handling these, {url_line}\n"
            f"{len(overlay_level_errors)} line(s) with `overlay_level` errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(overlay_level_errors_message)

    if playlist_errors:
        url_line = "[https://kometa.wiki/en/latest/defaults/playlist/?h=playlist]"
        formatted_errors = analyzer.format_contiguous_lines(playlist_errors)
        playlist_error_message = (
            "❌ **PLAYLIST ERROR**\n"
            "A playlist is trying to use a library that does not exist in Plex.\n"
            "Ensure that all libraries being defined actually exist.\n"
            "The Kometa Defaults `playlist` file expects libraries called `Movies` and `TV Shows`, template variables can be used to change this.\n"
            f"For more information: {url_line}\n"
            f"{len(playlist_errors)} line(s) with playlist errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(playlist_error_message)

    # Extract scheduled run time
    kometa_scheduled_time = analyzer.extract_scheduled_run_time(content)
    maintenance_start_time, maintenance_end_time = analyzer.extract_maintenance_times(content)
    kometa_time_recommendation = None
    if isinstance(analyzer.run_time, timedelta):
        kometa_time_recommendation = analyzer.calculate_recommendation(
            kometa_scheduled_time,
            maintenance_start_time,
            maintenance_end_time,
        )
    if kometa_time_recommendation:
        special_check_lines.append(kometa_time_recommendation)

    # Extract Memory value:
    kometa_mem_recommendation = analyzer.calculate_memory_recommendation(content)
    if kometa_mem_recommendation:
        special_check_lines.append(kometa_mem_recommendation)

    # Extract DB Cache value:
    kometa_db_cache_recommendation = analyzer.make_db_cache_recommendations(content)
    if kometa_db_cache_recommendation:
        special_check_lines.append(kometa_db_cache_recommendation)

    # Extract WSL information
    wsl_recommendation = analyzer.detect_wsl_and_recommendation(content)
    if wsl_recommendation:
        special_check_lines.append(wsl_recommendation)

    if plex_regex_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
        formatted_errors = analyzer.format_contiguous_lines(plex_regex_errors)
        plex_regex_error_message = (
            "⚠️ **PLEX REGEX ERROR**\n"
            "Kometa is trying to perform a regex search, and 0 items match the regex pattern.\n"
            "This is often an expected error and can be ignored in most cases.\n"
            "If you need assistance with this error, raise a support thread in `#kometa-help`.\n"
            f"For more information on handling regex issues, {url_line}\n"
            f"{len(plex_regex_errors)} line(s) with Plex regex errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(plex_regex_error_message)

    if plex_lib_errors:
        url_line = "[https://kometa.wiki/en/latest/config/settings/?h=show_options#show-options]"
        formatted_errors = analyzer.format_contiguous_lines(plex_lib_errors)
        plex_lib_error_message = (
            "❌ **PLEX LIBRARY ERROR**\n"
            "Your configuration contains an invalid Plex Library Name.\n"
            "Kometa will not be able to update a library that does not exist.\n"
            "Check for spelling `case sensitive` and ensure that you have `show_options: true` within your settings within config.yml\n"
            f"For more information on configuring the show_options, {url_line}\n"
            f"{len(plex_lib_errors)} line(s) with PLEX LIBRARY errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(plex_lib_error_message)

    if plex_url_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/#getting-a-plex-url-and-token]"
        formatted_errors = analyzer.format_contiguous_lines(plex_url_errors)
        plex_url_error_message = (
            "❌ **PLEX URL ERROR**\n"
            "Your configuration contains an invalid Plex URL.\n"
            "This will cause any services that rely on this URL to fail.\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on configuring the Plex URL, {url_line}\n"
            f"{len(plex_url_errors)} line(s) with PLEX URL errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(plex_url_error_message)

    if rounding_errors:
        url_line = "[https://forums.plex.tv/t/plex-rounding-down-user-ratings-when-set-via-api/875806/8]"

        # Construct the message with server names and versions
        rounding_errors_message = (
            "⚠️ **USER RATINGS ROUNDING ISSUE**\n"
            "We have detected that you are running `mass_user_rating_update` or `mass_episode_user_ratings_update` with Plex versions that will cause rounding issues with user ratings. To avoid this, downgrade your Plex Media server to `1.40.0.7998` or upgrade it to `1.40.3.8555` or later.\n"
            f"For more information on this issue, {url_line}\n"
            f"Detected issues on the following servers:\n"
        )
        # Append server names, versions, and line numbers to the message
        for server_name, server_version, line_num in rounding_errors:
            rounding_errors_message += f"- Server: {server_name}, Version: {server_version}, Line: {line_num}\n"

        special_check_lines.append(rounding_errors_message)

    if ruamel_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/yaml/]"
        formatted_errors = analyzer.format_contiguous_lines(ruamel_errors)
        ruamel_error_message = (
            "💥 **YAML ERROR**\n"
            "YAML is very sensitive with regards to spaces and indentation.\n"
            "Search for `ruamel.yaml.` in your log file to get hints as to where the problem lies.\n"
            "In the Kometa discord thread, type `!yaml` and `!editors` for more information.\n"
            f"For more information on handling YAML issues, {url_line}\n"
            f"{len(ruamel_errors)} line(s) with YAML errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(ruamel_error_message)

    if run_order_errors:
        url_line = "[https://kometa.wiki/en/latest/config/settings/?h=run_order#run-order]"
        formatted_errors = analyzer.format_contiguous_lines(run_order_errors)
        run_order_error_message = (
            "⚠️ **RUN_ORDER WARNING**\n"
            f"Typically, and in almost EVERY situation, you want ` - operations` to precede both metadata and overlays processing. To fix this, place `- operations` first in the `run_order` section of the config.yml file\n"
            f"For more information on this, {url_line}\n"
            f"{len(run_order_errors)} line(s) with RUN_ORDER warnings. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(run_order_error_message)

    if security_vuln_hits:
        seen = set()
        items = []
        for sn, ver, ln in security_vuln_hits:
            key = (sn, ver, ln)
            if key not in seen:
                seen.add(key)
                items.append((sn, ver, ln))

        vuln_low_str = format_version_tuple(VULNERABLE_RANGE_LOW)
        vuln_high_str = format_version_tuple(VULNERABLE_RANGE_HIGH)
        url_line = "[https://forums.plex.tv/t/plex-media-server-security-update/928341]"

        msg = (
            "🚀 **PMS SECURITY ALERT**\n"
            "A Plex Media Server version in a **known vulnerable range** was detected.\n"
            f"**Affected range:** `{vuln_low_str}` **through** `{vuln_high_str}`\n"
            "Please **upgrade Plex Media Server** to a safe release as soon as possible.\n"
            "Until then, Plex will block access from others reaching your server.\n"
            "UPGRADE IMMEDIATELY!\n"
            f"For more information on this see url: {url_line}\n"
            f"{len(security_vuln_hits)} line(s) with these errors."
            "Detected on:\n"
        )
        for sn, ver, ln in items:
            msg += f"- Server: {sn}, Version: `{ver}`, Line: {ln}\n"

        special_check_lines.append(msg)

    if traceback_errors:
        url_line = "[https://kometa.wiki/en/latest/config/tautulli]"
        formatted_errors = analyzer.format_contiguous_lines(traceback_errors)
        traceback_errors_message = (
            "💥 **TRACEBACK ERROR**\n"
            "Your KOMETA run contains traceback errors.\n"
            "This likely means that the run ended prematurely or did not complete certain tasks (i.e. overlays ended early or did not apply).\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"{len(traceback_errors)} line(s) with Traceback errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(traceback_errors_message)

    if tautulli_apikey_errors:
        url_line = "[https://kometa.wiki/en/latest/config/tautulli]"
        formatted_errors = analyzer.format_contiguous_lines(tautulli_apikey_errors)
        tautulli_apikey_errors_message = (
            "❌ **TAUTULLI API ERROR**\n"
            "Your configuration contains an invalid API key for Tautulli.\n"
            "This will cause any services that rely on Tautulli to fail.\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on configuring Tautulli, {url_line}\n"
            f"{len(tautulli_apikey_errors)} line(s) with Tautulli errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(tautulli_apikey_errors_message)

    if tautulli_url_errors:
        url_line = "[https://kometa.wiki/en/latest/config/tautulli#tautulli-attributes]"
        formatted_errors = analyzer.format_contiguous_lines(tautulli_url_errors)
        tautulli_url_error_message = (
            "❌ **TAUTULLI URL ERROR**\n"
            "Your configuration contains an invalid Tautulli URL.\n"
            "This will cause any services that rely on this URL to fail.\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on configuring the Tautulli URL, {url_line}\n"
            f"{len(tautulli_url_errors)} line(s) with TAUTULLI URL errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(tautulli_url_error_message)

    if tmdb_api_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/#getting-a-tmdb-api-key]"
        formatted_errors = analyzer.format_contiguous_lines(tmdb_api_errors)
        tmdb_api_errors_message = (
            "❌ **TMDB API ERROR**\n"
            "Your configuration contains an invalid API key for TMDb.\n"
            "This will cause any services that rely on TMDb to fail.\n"
            "In the Kometa discord thread, type `!wiki` for more information and search.\n"
            f"For more information on configuring TMDb, {url_line}\n"
            f"{len(tmdb_api_errors)} line(s) with TMDb errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(tmdb_api_errors_message)

    if timeout_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/install/overview/]"
        formatted_errors = analyzer.format_contiguous_lines(timeout_errors)
        timeout_error_message = (
            "❌⏱️ **TIMEOUT ERROR**\n"
            "There were timeout issues while trying to connect to different services.\n"
            "Ensure that your network configuration allows Kometa to make internet calls.\n"
            f"Typically this is your Plex server timing out when Kometa tries to connect to it. There's nothing Kometa can do about this directly. Currently your timeout for plex is set to: `{analyzer.plex_timeout}` seconds. You can try increasing the connection timeout in `config.yml`:\n"
            "```plex:\n  url: http://bing.bang.boing\n  token: REDACTED\n  timeout: 360   <<< right here```\n"
            "But that's not a guarantee.\n\nEffectively what's happening here is that you're ringing the doorbell and no one's answering. You can't do anything about that aside from waiting longer. You can't ring the doorbell differently.\n\n"
            "This seems to happen most often in an Appbox context, so perhaps contact your appbox provider to discuss it.\n\n"
            "In the Kometa discord thread, type `!timeout` for more information.\n"
            f"For more information on network configuration, {url_line}\n"
            f"{len(timeout_errors)} line(s) with timeout errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(timeout_error_message)

    if tmdb_fail_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/]"
        formatted_errors = analyzer.format_contiguous_lines(tmdb_fail_errors)
        tmdb_fail_error_message = (
            "❌ **TMDB ERROR**\n"
            "This error appears when your host machine is unable to connect to TMDb.\n"
            "Ensure that your networking (particularly docker container) is configured to allow Kometa to make internet calls.\n"
            f"For more information on network configuration, {url_line}\n"
            f"{len(tmdb_fail_errors)} line(s) with TMDB errors. Line number location. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(tmdb_fail_error_message)

    if to_be_configured_errors:
        url_line = "[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]"
        formatted_errors = analyzer.format_contiguous_lines(to_be_configured_errors)
        to_be_configured_errors_message = (
            "❌ **TO BE CONFIGURED ERROR**\n"
            "You are using a builder that has not been configured yet.\n"
            "This will affect any functionality that relies on these connections. Review all lines below and resolve.\n"
            "In the Kometa discord thread, type `!wiki` and search for more information\n"
            f"For more information on configuring services, {url_line}\n"
            f"{len(to_be_configured_errors)} line(s) with `to be configured` errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(to_be_configured_errors_message)

    if trakt_connection_errors:
        url_line = "[https://kometa.wiki/en/latest/config/trakt/#trakt-attributes]"
        formatted_errors = analyzer.format_contiguous_lines(trakt_connection_errors)
        trakt_connection_error_message = (
            "❌ **TRAKT CONNECTION ERROR**\n"
            "There was an issue connecting to the Trakt service.\n"
            "This will affect any functionality that relies on Trakt data.\n"
            "In the Kometa discord thread, type `!trakt` for more information\n"
            f"For more information on configuring the Trakt service, {url_line}\n"
            f"{len(trakt_connection_errors)} line(s) with TRAKT CONNECTION errors. Line number(s): {formatted_errors}"
        )
        special_check_lines.append(trakt_connection_error_message)

    return {
        "wsl": wsl_recommendation,
        "time": kometa_time_recommendation,
        "memory": kometa_mem_recommendation,
        "db_cache": kometa_db_cache_recommendation,
    }


# ---------------------------------------------------------------------------
# Recommendation post-processing helpers.
#
# These are pure functions that operate on the recommendation-message
# list returned by :func:`make_recommendations` (or the ``counts`` dict
# built by the same pipeline).  Kept here so ALL logic that touches
# recommendation data lives in one module.
# ---------------------------------------------------------------------------

_PRIORITY_ICONS = {"\U0001f680", "\U0001f4a5", "\u274c", "\u26a0", "\U0001f4ac", "\u2139"}
_PRIORITY_ORDER = {
    "\U0001f680": 1,  # rocket
    "\U0001f4a5": 2,  # collision
    "\u274c": 3,  # cross mark
    "\u26a0": 4,  # warning sign
    "\U0001f4ac": 5,  # speech balloon
    "\u2139": 5,  # information source
}


def ensure_recommendation_icons(recommendations):
    """Prepend the default speech-balloon icon to any un-iconed messages.

    Mutates *recommendations* in place.  A message whose first
    non-whitespace character isn't one of the six priority icons
    gets prefixed with a speech balloon so the dashboard renders a
    consistent left-column glyph.
    """
    for rec in recommendations:
        first_line = rec.get("first_line", "") or ""
        trimmed = first_line.lstrip()
        if not trimmed:
            rec["first_line"] = "\U0001f4ac Recommendation"
            continue
        first_symbol = trimmed[0].rstrip("\ufe0f")
        if first_symbol not in _PRIORITY_ICONS:
            rec["first_line"] = f"\U0001f4ac {trimmed}"


def reorder_recommendations(recommendations):
    """Return *recommendations* sorted by leading-icon priority.

    Priority is rocket -> collision -> cross -> warning -> speech/info.
    Messages whose first character isn't one of those icons sort
    to the end.  Non-mutating: returns a new list.
    """

    def sort_key(recommendation):
        first_symbol = recommendation.get("first_line", "No first line available")[0]
        first_symbol = first_symbol.rstrip("\ufe0f")
        return _PRIORITY_ORDER.get(first_symbol, float("inf"))

    return sorted(recommendations, key=sort_key)


def extract_analyze_issue_counts(content):
    """Count coarse "convert/anidb/regex" issue mentions in *content*.

    Returns a dict with three canonical keys plus their long
    ``analyze_*`` aliases (kept for callers that hard-coded the
    older key names).  Empty content yields all-zero counts.
    """
    patterns = {
        "analyze_convert": re.compile(r"\bconvert\s+(warning|error)\b", re.IGNORECASE),
        "analyze_anidb": re.compile(r"\banidb\b.*\b(error|warning|failed)\b", re.IGNORECASE),
        "analyze_regex": re.compile(r"\bregex\b.*\b(error|warning|invalid|failed)\b", re.IGNORECASE),
    }
    counts = {key: 0 for key in patterns}
    if not content:
        counts["convert"] = 0
        counts["anidb"] = 0
        counts["regex"] = 0
        return counts
    for line in content.splitlines():
        for key, pattern in patterns.items():
            if pattern.search(line):
                counts[key] += 1
    counts["convert"] = counts["analyze_convert"]
    counts["anidb"] = counts["analyze_anidb"]
    counts["regex"] = counts["analyze_regex"]
    return counts
