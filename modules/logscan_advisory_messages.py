"""Advisory-message builder for the logscan recommendation engine.

Split out of :mod:`modules.logscan_recommendations_engine` -- this
module owns Phase 3 of ``make_recommendations``: turning the ~50
error/warning buckets populated by Phase 2 into the markdown
advisory strings that Quickstart's log-scan result page displays.

## What lives here

Single public entry point :func:`build_advisory_messages` (renamed
from the leading-underscore private name so external test-suites
can call it directly without importing a private symbol).

The function is a linear walk through every issue bucket in the
same order the legacy ``make_recommendations`` did.  For each
populated bucket, either:

* :func:`~modules._logscan_advisory_table.render_advisory` renders
  the standard-template markdown (icon, title, body, URL, count
  line) from an :class:`~modules._logscan_advisory_table.Advisory`
  record -- see the ``_append_std`` nested helper below.
* An inline block builds a bespoke markdown string when the bucket
  needs analyzer-attribute interpolation, multi-URL citations, or
  iteration over tuple payloads.

Either way the result is appended to the caller's
``special_check_lines`` list.

At the end it also computes the four platform-level
recommendations (WSL, run-time, memory, db_cache) via the
analyzer's wrapper methods and returns them as a dict so
:func:`build_issue_counts` can roll them into ``platform_system``.

## Why not a data table?

Most blocks *are* a data table now.  49 of the ~57 buckets share the
same ``(icon+title, body lines, url, count label)`` shape and live in
:mod:`modules._logscan_advisory_table` as :class:`~modules._logscan_advisory_table.Advisory`
records.  A single-line ``_append_std(bucket_key, bucket)`` call
inside :func:`build_advisory_messages` renders each one when its
bucket is populated.

The remaining ~8 blocks stay inline because they need something the
template can't express:

* ``timeout_errors``, ``flixpatrol_paywall``, the two version-update
  buckets -- interpolate analyzer attributes like ``plex_timeout`` or
  ``current_kometa_version`` into the body.
* ``convert_errors``, ``metadata_attribute_errors`` -- multi-paragraph
  bodies with ``\n\n`` breaks that make a hand-written string clearer.
* ``overlay_apply_errors`` -- cites *two* URLs.
* ``rounding_errors``, ``security_vuln_hits`` -- iterate over tuples
  ``(server_name, version, line_num)`` to build the body.
* ``incomplete_message`` -- uses the *value* of the bucket variable
  (a preformatted string) as the body, not a fixed template.

## Backward compatibility

``modules.logscan_recommendations_engine`` re-exports
:func:`build_advisory_messages` under the legacy
``_build_advisory_messages`` name so nothing in the engine's
Phase 3 call site had to change.
"""

from __future__ import annotations

from datetime import timedelta

from modules._logscan_advisory_table import (
    STANDARD_ADVISORIES,
    render_advisory,
)
from modules.logscan_pms_versions import (
    VULNERABLE_RANGE_HIGH,
    VULNERABLE_RANGE_LOW,
    format_version_tuple,
)

# Lookup by bucket key so each ``if bucket:`` block can defer to a
# single-line ``_append_std`` call inside ``build_advisory_messages``.
_ADVISORY = {advisory.bucket_key: advisory for advisory in STANDARD_ADVISORIES}


def build_advisory_messages(
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

    def _append_std(bucket_key: str, bucket) -> None:
        """Append a standard-template advisory when *bucket* is populated.

        Looks up the :class:`Advisory` record by *bucket_key* and
        appends the rendered markdown to the enclosing scope's
        ``special_check_lines`` list.  Standard advisories are the
        ones that fit the ``(body, url, count_label)`` template;
        see :mod:`modules._logscan_advisory_table`.
        """
        if bucket:
            special_check_lines.append(
                render_advisory(_ADVISORY[bucket_key], bucket, analyzer),
            )

    _append_std("anidb69_errors", anidb69_errors)
    _append_std("anidb_auth_errors", anidb_auth_errors)
    _append_std("api_blank_errors", api_blank_errors)
    _append_std("bad_version_found_errors", bad_version_found_errors)
    _append_std("cache_false", cache_false)
    _append_std("checkFiles", checkFiles)
    _append_std("other_award", other_award)
    _append_std("critical_errors", critical_errors)
    _append_std("error_errors", error_errors)
    _append_std("warning_errors", warning_errors)

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

    _append_std("corrupt_image_errors", corrupt_image_errors)
    _append_std("delete_unmanaged_collections_errors", delete_unmanaged_collections_errors)
    _append_std("flixpatrol_errors", flixpatrol_errors)

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

    _append_std("git_kometa_errors", git_kometa_errors)
    _append_std("pmm_legacy_errors", pmm_legacy_errors)
    _append_std("image_size", image_size)

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

    _append_std("internal_server_errors", internal_server_errors)
    _append_std("lsio_errors", lsio_errors)
    _append_std("mal_connection_errors", mal_connection_errors)
    _append_std("mass_update_errors", mass_update_errors)
    _append_std("mdblist_attr_errors", mdblist_attr_errors)
    _append_std("mdblist_errors", mdblist_errors)
    _append_std("mdblist_api_limit_errors", mdblist_api_limit_errors)

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

    _append_std("metadata_load_errors", metadata_load_errors)
    _append_std("overlay_load_errors", overlay_load_errors)
    _append_std("playlist_load_errors", playlist_load_errors)
    _append_std("missing_path_errors", missing_path_errors)

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

    _append_std("no_items_found_errors", no_items_found_errors)
    _append_std("omdb_errors", omdb_errors)
    _append_std("omdb_api_limit_errors", omdb_api_limit_errors)
    _append_std("overlay_font_missing", overlay_font_missing)
    _append_std("overlays_bloat", overlays_bloat)

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

    _append_std("overlay_image_missing", overlay_image_missing)
    _append_std("overlay_level_errors", overlay_level_errors)
    _append_std("playlist_errors", playlist_errors)

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

    _append_std("plex_regex_errors", plex_regex_errors)
    _append_std("plex_lib_errors", plex_lib_errors)
    _append_std("plex_url_errors", plex_url_errors)

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

    _append_std("ruamel_errors", ruamel_errors)
    _append_std("run_order_errors", run_order_errors)

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

    _append_std("traceback_errors", traceback_errors)
    _append_std("tautulli_apikey_errors", tautulli_apikey_errors)
    _append_std("tautulli_url_errors", tautulli_url_errors)
    _append_std("tmdb_api_errors", tmdb_api_errors)

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

    _append_std("tmdb_fail_errors", tmdb_fail_errors)
    _append_std("to_be_configured_errors", to_be_configured_errors)
    _append_std("trakt_connection_errors", trakt_connection_errors)

    return {
        "wsl": wsl_recommendation,
        "time": kometa_time_recommendation,
        "memory": kometa_mem_recommendation,
        "db_cache": kometa_db_cache_recommendation,
    }
