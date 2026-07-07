"""Data table + render helper for standard-template log-scan advisories.

Split out of :mod:`modules.logscan_advisory_messages` -- this module owns
the ~50 near-identical ``if bucket: url_line = ...; msg = (...)`` blocks
that used to make ``build_advisory_messages`` a 900-line linear walk.

## Why a data table

Nearly all advisory messages share the same shape::

    <icon> **<TITLE>**
    <body line 1>
    <body line 2>
    ...
    For more information on <topic>, <url>
    <N> line(s) with <label>. Line number(s): <formatted>

That template collapses to a single record per bucket:

* :class:`Advisory` -- immutable record holding the message body
  prefix (everything except the count line, with ``{url_line}``
  placeholders where the URL should land), the URL itself, and the
  bucket-specific count label.

* :func:`render_advisory` -- assembles the final markdown string
  given the record, the (populated) bucket, and the analyzer whose
  ``format_contiguous_lines`` renders the "L45-48, L92" summary.

The 49 entries in :data:`STANDARD_ADVISORIES` cover every bucket whose
message can be described purely by ``(body, url, count_label)``.  The
handful of buckets that need analyzer-attribute interpolation
(``timeout_errors``, the version-update trio, ``flixpatrol_paywall``)
or that emit non-standard shapes (``convert_errors``,
``metadata_attribute_errors``, ``overlay_apply_errors``,
``rounding_errors``, ``security_vuln_hits``, ``incomplete_message``)
stay inline in the parent module.

## Ordering

The tuple is in **source order** to preserve the append order of
``special_check_lines``.  ``build_advisory_messages`` walks it
linearly and interleaves the inline specials at their original
positions, so the output list matches the pre-refactor byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Advisory:
    """Immutable descriptor for one standard-template advisory message.

    Attributes:
        bucket_key: Name of the bucket this advisory describes.  Kept
            for documentation/lookup; the render function receives the
            populated bucket directly.
        body: Everything except the trailing count line, including the
            header (``"<icon> **<TITLE>**\\n"``), body lines, and the
            "For more information on ..., {url_line}\\n" line.  The
            literal placeholder ``{url_line}`` is substituted with
            :attr:`url` at render time.
        url: The wiki/forums URL that fills in ``{url_line}``.  May be
            empty for the rare bucket that doesn't cite one (e.g.
            ``checkFiles``).
        count_label: The human-readable label inserted into the count
            line, e.g. ``"ANIDB69 errors"`` -> ``"7 line(s) with ANIDB69
            errors. Line number(s): L12-15"``.
    """

    bucket_key: str
    body: str
    url: str
    count_label: str


def render_advisory(advisory: Advisory, bucket, analyzer) -> str:
    """Render *advisory* against a populated *bucket* using *analyzer*.

    Substitutes the ``{url_line}`` placeholder in the advisory body,
    formats the affected line numbers via
    ``analyzer.format_contiguous_lines``, and returns the final
    markdown string ready to append to ``special_check_lines``.
    """
    formatted_errors = analyzer.format_contiguous_lines(bucket)
    body = advisory.body.replace("{url_line}", advisory.url)
    return f"{body}{len(bucket)} line(s) with {advisory.count_label}. Line number(s): {formatted_errors}"


# The order of this tuple mirrors the source order of the legacy
# ``if bucket:`` blocks in ``build_advisory_messages`` so the caller
# can walk it linearly and interleave the inline specials at their
# original positions without shifting the final output.
STANDARD_ADVISORIES: tuple[Advisory, ...] = (
    Advisory(
        bucket_key="anidb69_errors",
        body="❌ **ANIDB69 ERROR**\nKometa uses AniDB ID 69 to test that it can connect to AniDB.\nThis error indicates that the test request sent to AniDB failed and AniDB could not be reached.\nFor more information on configuring AniDB, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/anidb]",
        count_label="ANIDB69 errors",
    ),
    Advisory(
        bucket_key="anidb_auth_errors",
        body="❌ **ANIDB AUTH ERRORS**\nKometa uses AniDB settings to connect to AniDB.\nThis error indicates that the setting is not correctly setup in config.yml.\nFor more information on configuring AniDB, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/anidb]",
        count_label="ANIDB AUTH errors",
    ),
    Advisory(
        bucket_key="api_blank_errors",
        body="❌🔒 **BLANK API KEY ERROR**\nAn API key is required for certain services, and it appears to be blank in your configuration.\nMake sure to provide the required API key to enable proper functionality.\nFor more information on configuring API keys, {url_line}\nIn the Kometa discord thread, type `!wiki` for more information and search for the service with the missing apikey \n",
        url="[https://kometa.wiki/en/latest/config/trakt/?q=api]",
        count_label="BLANK API KEY errors",
    ),
    Advisory(
        bucket_key="bad_version_found_errors",
        body="💥 **BAD PLEX VERSION ERROR**\nYou are running a version of Plex that is known to have issues with Kometa.\nYou should downgrade/upgrade to a version that is not `1.32.7.*`.\nFor more information on this issue, {url_line}\n",
        url="[https://forums.plex.tv/t/refresh-endpoint-put-post-requests-started-throwing-404s-in-version-1-32-7-7484/853588]",
        count_label="Plex Version 1.32.7.*",
    ),
    Advisory(
        bucket_key="cache_false",
        body="💬 **Kometa CACHE**\nKometa cache setting is set to false(`cache: false`). Normally, you would want this set to true to improve performance.\nFor more information on handling this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/settings#cache]",
        count_label="`cache: false`",
    ),
    Advisory(
        bucket_key="checkFiles",
        body="⚠️ **CHECKFILES=1 DETECTED**\n`checkFiles=1` detected. Notifying Kometa staff.\n",
        url="",
        count_label="`checkFiles=1` messages",
    ),
    Advisory(
        bucket_key="other_award",
        body="⚠️ **LEGACY SCHEMA DETECTED**\nAs of 1.20 `other_award` is no longer used and should be removed. All of those awards now have their own individual files.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/faqs/?h=other_award#pmm-120-release-changes]",
        count_label="`other_award` issues",
    ),
    Advisory(
        bucket_key="critical_errors",
        body="💥 **[CRITICAL]**\nCritical messages found in your attached log.\nThere is a very strong likelihood that Kometa aborted the run or part of the run early thus not all of what you wanted was applied.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/?h=%5Bcritical%5D#critical]",
        count_label="[CRITICAL] messages",
    ),
    Advisory(
        bucket_key="error_errors",
        body="❌ **[ERROR]**\nError messages found in your attached log.\nThere is a very strong likelihood that Kometa did not complete all of what you wanted. Some [ERROR] lines can be ignored.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]",
        count_label="[ERROR] messages",
    ),
    Advisory(
        bucket_key="warning_errors",
        body="⚠️ **[WARNING]**\nWarning messages found in your attached log.\nThis is a Kometa warning and usually does not require any immediate action. Most [WARNING] lines can be ignored.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/?h=%5Bwarning%5D#warning]",
        count_label="[WARNING] messages",
    ),
    Advisory(
        bucket_key="convert_errors",
        body="💬 **CONVERT WARNING**\nConvert Warning: No * ID Found for * ID.\nThese sorts of errors indicate that the thing can't be cross-referenced between sites.  For example:\n\nConvert Warning: No TVDb ID Found for TMDb ID: 15733\n\nIn the above scenario, the TMDB record for `The Two Mrs. Grenvilles` `ID 15733` didn't contain a TVDB ID. This could be because the record just hasn't been updated, or because `The Two Mrs. Grenvilles` isn't listed on TVDB.\n\nThe fix is for someone `like you, perhaps` to go to the relevant site and fill in the missing data.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/#warning]",
        count_label="Convert Warnings",
    ),
    Advisory(
        bucket_key="corrupt_image_errors",
        body="❌ **CORRUPT FILE ERROR**\nLikely, when processing overlays, Kometa encountered a file that it could not process because it was corrupt.\nReview the lines in your log file and based on the lines shown here and determine if those files are ok or not with your favorite image editor.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/#error]",
        count_label="`PIL.UnidentifiedImageError` reported",
    ),
    Advisory(
        bucket_key="delete_unmanaged_collections_errors",
        body="⚠️ **LEGACY SCHEMA DETECTED**\n`delete_unmanaged_collections` is a Library operation and should be adjusted in your config file accordingly.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/operations/#delete-collections]",
        count_label="`delete_unmanaged_collections` errors",
    ),
    Advisory(
        bucket_key="flixpatrol_errors",
        body="❌ **FLIXPATROL ERROR**\nThere was an issue with FlixPatrol data.\nThis is a known issue with Kometa 1.19.0 (master/latest branch).\nSwitch to the 1.19.1 nightly21 or greater Kometa release for a fix.\nIn the Kometa discord thread, for more information on how to switch branches, type `!branch`.\nFor more information on handling FlixPatrol errors, {url_line}\nIf the problem persists, your IP address might be banned by FlixPatrol. Contact their support to have it unbanned.\n",
        url="[https://kometa.wiki/en/latest/kometa/faqs/?h=flixpatrol#flixpatrol]",
        count_label="FlixPatrol errors",
    ),
    Advisory(
        bucket_key="git_kometa_errors",
        body="💬 **OLD Kometa YAML**\nYou are using an old config.yml with references to metadata files that date to a version of Kometa that is pre 1.18\nIn the Kometa discord thread, type `!118` for more information.\nFor more information on handling this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/overview/?h=configuration]",
        count_label="OLD Kometa YAML",
    ),
    Advisory(
        bucket_key="pmm_legacy_errors",
        body="💬 **PRE KOMETA YAML**\nYou are using an old config.yml with references to metadata files that date to a version of this script that is pre Kometa\nIn your config.yml, search for `- pmm: ` and replace with `- default: ` .\nFor more information on handling this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/overview/?h=configuration]",
        count_label="PRE Kometa YAML",
    ),
    Advisory(
        bucket_key="image_size",
        body="❌ **IMAGE SIZE ERRORS**\nIt seems that you are attempting to upload or apply artwork and it's greater than the maximum `10MB`.\nThis usually means that you have internal server errors (500) as well in this log. Change the image to one that is less than 10MB. For more information on handling this, {url_line}\n",
        url="[https://www.google.com]",
        count_label="IMAGE SIZE errors",
    ),
    Advisory(
        bucket_key="internal_server_errors",
        body="💥 **INTERNAL SERVER ERROR**\nAn internal server error has occurred. This could be due to an issue with the service's server.\nIn the Kometa discord thread, type `!500` for more information.\nFor more information on handling internal server errors, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/faqs/?h=errors+issues#errors-issues]",
        count_label="INTERNAL SERVER errors",
    ),
    Advisory(
        bucket_key="lsio_errors",
        body="⚠️🖥️ **LINUXSERVER IMAGE DETECTED**\nYou are not using the official Kometa container image.\nIn the Kometa discord thread, type `!lsio` for more information.\nFor more information on this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/install/images/?h=linuxserver#linuxserver]",
        count_label="LINUXSERVER IMAGE issues",
    ),
    Advisory(
        bucket_key="mal_connection_errors",
        body="❌ **MY ANIME LIST CONNECTION ERROR**\nThere was an issue connecting to My Anime List (MAL) service.\nThis will affect any functionality that relies on MAL data.\nIn the Kometa discord thread, type `!mal` for more information\nFor more information on configuring the My Anime List (MAL) service, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/myanimelist]",
        count_label="MY ANIME LIST CONNECTION errors",
    ),
    Advisory(
        bucket_key="mass_update_errors",
        body="❌ **MASS_*_UPDATE ERROR**\nYou have specified a `mass_*_update` operation in your config file however you have not configured the corresponding service so this will never work.\nReview each of the lines mentioned in this message to understand what all the config issues are.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on `mass_*_update` operations, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/operations]",
        count_label="`mass_*_update` config errors",
    ),
    Advisory(
        bucket_key="mdblist_attr_errors",
        body="❌ **MDBLIST ATTRIBUTE ERROR**\nMDBList functionality does not currently support season-level collections.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on MDBList configuration, {url_line}\n",
        url="[https://kometa.wiki/en/latest/files/builders/mdblist/?h=mdblist+builders]",
        count_label="MDBList attribute errors",
    ),
    Advisory(
        bucket_key="mdblist_errors",
        body="❌ **MDBLIST ERROR**\nYour configuration contains an invalid API key for MdbList.\nThis will cause any services that rely on MdbList to fail.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on configuring MdbList, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/mdblist/?h=mdblist+attributes#mdblist-attributes]",
        count_label="MDBLIST errors",
    ),
    Advisory(
        bucket_key="mdblist_api_limit_errors",
        body="❌ **MDBLIST API LIMIT ERROR**\nYou have hit the MDBLIST API LIMIT. The free apikey is limited to 1000 requests per day so if you hit your limit Kometa should be able to pick up where it left off the next day as long as the Kometa cache setting is enabled in yur config.yml file.\nThis will cause any metadata updates that rely on MdbList to fail until the limit is reset (usually daily).\nFor more information on configuring MdbList, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/mdblist/?h=mdblist+attributes#mdblist-attributes]",
        count_label="MDBLIST API Limit errors",
    ),
    Advisory(
        bucket_key="metadata_attribute_errors",
        body="❌ **METADATA ATTRIBUTE ERRORS**\nIf you are using Kometa nightly48 or newer, this is expected behaviour.\n`metadata_path` and `overlay_path` are now legacy attributes, and using them will cause the `YAML Error: metadata attribute is required` error.\nThe error can be ignored as it won't cause any issues, or you can update your config.yml to use the new `collection_files`, `overlay_files` and `metadata_files` attributes.\n\nThe steps to take are:\n:one: - Look at every file referred to within your config.yml and see what the first level indentation yaml file attributes are. They should be one of these(`collections:, dynamic_collections:, overlays:, metadata:, playlists:, templates:, external_templates:`) and can contain more than 1. For now, ignore the `templates:` and `external_templates:` attributes.\n:two: - if it's `metadata:`, file it under the `metadata_file:` section of your config.yml\n:three: - if it's `collections:` or `dynamic_collections:`, file it under the `collection_files:` section of your config.yml\n:four: - if it's `playlists:`,  file it under the `playlist_files:` section of your config.yml\n:five: - if it's `overlays:`,  file it under the `overlay_files:` section of your config.yml\n\n`*NOTE:` If you only see `templates:` or `external_templates:`, this is a special case and you typically would not be referring to it directly in your config.yml file.\n\nWithin the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\nFor more information on this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/files/#example]",
        count_label="METADATA ATTRIBUTE errors",
    ),
    Advisory(
        bucket_key="metadata_load_errors",
        body="❌ **METADATA LOAD ERRORS**\nKometa is trying to load a file from your config file.\nThis error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\nWithin the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\nFor more information on this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/overview/?h=configuration]",
        count_label="METADATA LOAD errors",
    ),
    Advisory(
        bucket_key="overlay_load_errors",
        body="❌ **OVERLAY LOAD ERRORS**\nKometa is trying to load a file from your config file.\nThis error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\nWithin the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\nFor more information on this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/overview/?h=configuration]",
        count_label="OVERLAY LOAD errors",
    ),
    Advisory(
        bucket_key="playlist_load_errors",
        body="❌ **PLAYLIST LOAD ERRORS**\nKometa is trying to load a file from your config file.\nThis error indicates that the setting is not correctly setup in config.yml. Usually wrong path to the file, or a badly formatted yml file.\nWithin the attached log file, go to the indicated line(s) for more details on the exact issue and take actions to fix.\nFor more information on this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/overview/?h=configuration]",
        count_label="PLAYLIST LOAD errors",
    ),
    Advisory(
        bucket_key="missing_path_errors",
        body="⚠️ **LEGACY SCHEMA DETECTED**\n`missing_path` or `save_missing` is no longer used and should be replaced/removed. Use `report_path` instead.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/libraries/?h=report_path#attributes]",
        count_label="`missing_path` or `save_missing` errors",
    ),
    Advisory(
        bucket_key="no_items_found_errors",
        body="⚠️ **NO ITEMS FOUND IN PLEX**\nThe criteria defined by a search/filter returned 0 results.\nThis is often expected - for example, if you try to apply a 1080P overlay to a 4K library then no items will get the overlay since no items have a 1080P resolution.\nIt is worth noting that search and filters are case-sensitive, so `1080P` and `1080p` are treated as two separate things.\nFor more information on this error, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]",
        count_label="'No Items found in Plex' errors",
    ),
    Advisory(
        bucket_key="omdb_errors",
        body="❌ **OMDB ERROR**\nYour configuration contains an invalid API key for OMDb.\nThis will cause any services that rely on OMDb to fail.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on configuring OMDb, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/omdb/#omdb-attributes]",
        count_label="OMDb errors",
    ),
    Advisory(
        bucket_key="omdb_api_limit_errors",
        body="❌ **OMDB API LIMIT ERROR**\nYou have hit the OMDB API LIMIT. The free apikey is limited to 1000 requests per day so if you hit your limit Kometa should be able to pick up where it left off the next day as long as the Kometa cache setting is enabled in yur config.yml file.\nThis will cause any metadata updates that rely on OMDB to fail until the limit is reset (usually daily).\nFor more information on configuring OMDB, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/omdb/?h=omdb#omdb-attributes]",
        count_label="OMDB API Limit errors",
    ),
    Advisory(
        bucket_key="overlay_font_missing",
        body="❌ **OVERLAY FONT MISSING**\nWe detected that you are referencing a font that Kometa cannot find.\nThis can lead to overlays not being applied when a font is required.\nIn the Kometa discord thread, type `!wiki` for more information or follow this link: {url_line}\n",
        url="[https://kometa.wiki/en/latest/showcase/overlays/?h=font#example-2]",
        count_label="`Overlay Error: font:` errors",
    ),
    Advisory(
        bucket_key="overlays_bloat",
        body="⚠️ **REAPPLY / RESET OVERLAYS**\n\nWe detected that you are using either reapply_overlays OR reset_overlays within your config.\n\n**You should NOT be using reapply_overlays unless you have a specific reason to. If you are not sure do NOT enable it.**\n\nThis can lead to your system creating additional posters within Plex causing bloat\n\nTypically these config lines are only used for very specific cases so if this is your case, then you can ignore this recommendation\n\nIn the Kometa discord thread, type `!bloat` for more information or follow this link: {url_line}\n\n",
        url="[https://kometa.wiki/en/latest/kometa/scripts/imagemaid]",
        count_label="reapply_overlays or reset_overlays",
    ),
    Advisory(
        bucket_key="overlay_image_missing",
        body="❌ **OVERLAY IMAGE MISSING ERROR**\nKometa attempts to apply an overlay to things, but finds that the overlay itself is not found and thus cannot be applied to the art.\nValidate the path and also ensure that the case of the file(i.e. `4K.png` is NOT the same as `4k.png`) is the same as found in the line within the log.\nFor more information on overlays, {url_line}\n",
        url="[https://kometa.wiki/en/latest/defaults/overlays]",
        count_label="OVERLAY IMAGE MISSING errors",
    ),
    Advisory(
        bucket_key="overlay_level_errors",
        body="⚠️ **LEGACY SCHEMA DETECTED**\n`overlay_level:` is no longer used and should be replaced by `builder_level:`.\nFor more information on handling these, {url_line}\n",
        url="[https://kometa.wiki/en/latest/files/settings/?h=builder_level]",
        count_label="`overlay_level` errors",
    ),
    Advisory(
        bucket_key="playlist_errors",
        body="❌ **PLAYLIST ERROR**\nA playlist is trying to use a library that does not exist in Plex.\nEnsure that all libraries being defined actually exist.\nThe Kometa Defaults `playlist` file expects libraries called `Movies` and `TV Shows`, template variables can be used to change this.\nFor more information: {url_line}\n",
        url="[https://kometa.wiki/en/latest/defaults/playlist/?h=playlist]",
        count_label="playlist errors",
    ),
    Advisory(
        bucket_key="plex_regex_errors",
        body="⚠️ **PLEX REGEX ERROR**\nKometa is trying to perform a regex search, and 0 items match the regex pattern.\nThis is often an expected error and can be ignored in most cases.\nIf you need assistance with this error, raise a support thread in `#kometa-help`.\nFor more information on handling regex issues, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]",
        count_label="Plex regex errors",
    ),
    Advisory(
        bucket_key="plex_lib_errors",
        body="❌ **PLEX LIBRARY ERROR**\nYour configuration contains an invalid Plex Library Name.\nKometa will not be able to update a library that does not exist.\nCheck for spelling `case sensitive` and ensure that you have `show_options: true` within your settings within config.yml\nFor more information on configuring the show_options, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/settings/?h=show_options#show-options]",
        count_label="PLEX LIBRARY errors",
    ),
    Advisory(
        bucket_key="plex_url_errors",
        body="❌ **PLEX URL ERROR**\nYour configuration contains an invalid Plex URL.\nThis will cause any services that rely on this URL to fail.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on configuring the Plex URL, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/#getting-a-plex-url-and-token]",
        count_label="PLEX URL errors",
    ),
    Advisory(
        bucket_key="ruamel_errors",
        body="💥 **YAML ERROR**\nYAML is very sensitive with regards to spaces and indentation.\nSearch for `ruamel.yaml.` in your log file to get hints as to where the problem lies.\nIn the Kometa discord thread, type `!yaml` and `!editors` for more information.\nFor more information on handling YAML issues, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/yaml/]",
        count_label="YAML errors",
    ),
    Advisory(
        bucket_key="run_order_errors",
        body="⚠️ **RUN_ORDER WARNING**\nTypically, and in almost EVERY situation, you want ` - operations` to precede both metadata and overlays processing. To fix this, place `- operations` first in the `run_order` section of the config.yml file\nFor more information on this, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/settings/?h=run_order#run-order]",
        count_label="RUN_ORDER warnings",
    ),
    Advisory(
        bucket_key="traceback_errors",
        body="💥 **TRACEBACK ERROR**\nYour KOMETA run contains traceback errors.\nThis likely means that the run ended prematurely or did not complete certain tasks (i.e. overlays ended early or did not apply).\nIn the Kometa discord thread, type `!wiki` for more information and search.\n",
        url="[https://kometa.wiki/en/latest/config/tautulli]",
        count_label="Traceback errors",
    ),
    Advisory(
        bucket_key="tautulli_apikey_errors",
        body="❌ **TAUTULLI API ERROR**\nYour configuration contains an invalid API key for Tautulli.\nThis will cause any services that rely on Tautulli to fail.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on configuring Tautulli, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/tautulli]",
        count_label="Tautulli errors",
    ),
    Advisory(
        bucket_key="tautulli_url_errors",
        body="❌ **TAUTULLI URL ERROR**\nYour configuration contains an invalid Tautulli URL.\nThis will cause any services that rely on this URL to fail.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on configuring the Tautulli URL, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/tautulli#tautulli-attributes]",
        count_label="TAUTULLI URL errors",
    ),
    Advisory(
        bucket_key="tmdb_api_errors",
        body="❌ **TMDB API ERROR**\nYour configuration contains an invalid API key for TMDb.\nThis will cause any services that rely on TMDb to fail.\nIn the Kometa discord thread, type `!wiki` for more information and search.\nFor more information on configuring TMDb, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/#getting-a-tmdb-api-key]",
        count_label="TMDb errors",
    ),
    Advisory(
        bucket_key="tmdb_fail_errors",
        body="❌ **TMDB ERROR**\nThis error appears when your host machine is unable to connect to TMDb.\nEnsure that your networking (particularly docker container) is configured to allow Kometa to make internet calls.\nFor more information on network configuration, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/install/wt/wt-01-basic-config/]",
        count_label="TMDB errors. Line number location",
    ),
    Advisory(
        bucket_key="to_be_configured_errors",
        body="❌ **TO BE CONFIGURED ERROR**\nYou are using a builder that has not been configured yet.\nThis will affect any functionality that relies on these connections. Review all lines below and resolve.\nIn the Kometa discord thread, type `!wiki` and search for more information\nFor more information on configuring services, {url_line}\n",
        url="[https://kometa.wiki/en/latest/kometa/logs/?h=%5Berror%5D#error]",
        count_label="`to be configured` errors",
    ),
    Advisory(
        bucket_key="trakt_connection_errors",
        body="❌ **TRAKT CONNECTION ERROR**\nThere was an issue connecting to the Trakt service.\nThis will affect any functionality that relies on Trakt data.\nIn the Kometa discord thread, type `!trakt` for more information\nFor more information on configuring the Trakt service, {url_line}\n",
        url="[https://kometa.wiki/en/latest/config/trakt/#trakt-attributes]",
        count_label="TRAKT CONNECTION errors",
    ),
)
