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

from modules.logscan_advisory_messages import build_advisory_messages
from modules.logscan_issue_counts import build_issue_counts
from modules.logscan_pms_versions import (
    is_vulnerable_pms_version,
)

# Backward-compat alias: this module used to define the advisory-message
# builder as a private function; the extraction to
# modules.logscan_advisory_messages renamed it to a public
# ``build_advisory_messages``.  Keep the private name pointing at the
# new public function so no caller has to change.
_build_advisory_messages = build_advisory_messages

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
    issue_counts = build_issue_counts(
        buckets={
            "tmdb_api_errors": tmdb_api_errors,
            "tmdb_fail_errors": tmdb_fail_errors,
            "trakt_connection_errors": trakt_connection_errors,
            "omdb_errors": omdb_errors,
            "omdb_api_limit_errors": omdb_api_limit_errors,
            "mdblist_errors": mdblist_errors,
            "mdblist_api_limit_errors": mdblist_api_limit_errors,
            "mdblist_attr_errors": mdblist_attr_errors,
            "mal_connection_errors": mal_connection_errors,
            "tautulli_url_errors": tautulli_url_errors,
            "tautulli_apikey_errors": tautulli_apikey_errors,
            "flixpatrol_errors": flixpatrol_errors,
            "flixpatrol_paywall": flixpatrol_paywall,
            "lsio_errors": lsio_errors,
            "to_be_configured_errors": to_be_configured_errors,
            "api_blank_errors": api_blank_errors,
            "bad_version_found_errors": bad_version_found_errors,
            "missing_path_errors": missing_path_errors,
            "cache_false": cache_false,
            "mass_update_errors": mass_update_errors,
            "other_award": other_award,
            "delete_unmanaged_collections_errors": delete_unmanaged_collections_errors,
            "plex_url_errors": plex_url_errors,
            "plex_regex_errors": plex_regex_errors,
            "plex_lib_errors": plex_lib_errors,
            "rounding_errors": rounding_errors,
            "metadata_attribute_errors": metadata_attribute_errors,
            "metadata_load_errors": metadata_load_errors,
            "overlay_load_errors": overlay_load_errors,
            "overlay_apply_errors": overlay_apply_errors,
            "overlay_level_errors": overlay_level_errors,
            "overlay_font_missing": overlay_font_missing,
            "overlay_image_missing": overlay_image_missing,
            "playlist_load_errors": playlist_load_errors,
            "playlist_errors": playlist_errors,
            "overlays_bloat": overlays_bloat,
            "convert_errors": convert_errors,
            "corrupt_image_errors": corrupt_image_errors,
            "image_size": image_size,
            "run_order_errors": run_order_errors,
            "checkFiles": checkFiles,
            "timeout_errors": timeout_errors,
            "new_version_found_errors": new_version_found_errors,
            "new_plexapi_version_found_errors": new_plexapi_version_found_errors,
            "git_kometa_errors": git_kometa_errors,
            "anidb69_errors": anidb69_errors,
            "anidb_auth_errors": anidb_auth_errors,
            "internal_server_errors": internal_server_errors,
            "no_items_found_errors": no_items_found_errors,
            "pmm_legacy_errors": pmm_legacy_errors,
        },
        platform_recs=platform_recs,
    )

    return recommendation_messages, issue_counts


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
