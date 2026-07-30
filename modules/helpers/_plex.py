"""Plex query and metadata helpers extracted from the original helpers.py monolith.

Wraps plexapi for read-only operations against the user's Plex server:
top-N IMDb picks, library summaries, per-library metadata, and item lookups
by title or IMDb ID. Uses ``modules.persistence`` for stored Plex credentials
and ``modules.helpers._plex_cache`` for cached metadata payloads.
"""

from __future__ import annotations

import re

from plexapi.server import PlexServer

from modules import persistence
from modules.helpers._logging import ts_log


def _normalize_library_identifier(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def get_top_imdb_items(library_id, media_type, placeholder_id=None):
    ts_log("Fetching Plex credentials for '010-plex'", level="DEBUG")
    plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")

    ts_log(f"Connecting to Plex with URL: {plex_url}", level="DEBUG")
    plex = PlexServer(plex_url, plex_token)

    for section in plex.library.sections():
        ts_log(f"Section: key={section.key}, title={section.title}", level="DEBUG")

    ts_log(f"Searching for section with ID or title: {library_id}", level="DEBUG")
    normalized_library_id = _normalize_library_identifier(library_id)
    section = next(
        (s for s in plex.library.sections() if str(s.key) == str(library_id) or _normalize_library_identifier(getattr(s, "title", "")) == normalized_library_id),
        None,
    )

    if not section:
        raise ValueError(f"Library ID {library_id} not found.")

    ts_log(f"Fetching items from '{section.title}' sorted by audienceRating", level="DEBUG")
    items = section.search(sort="audienceRating:desc", maxresults=50)

    source_counts = {"imdb_id": 0}
    source_counts["tvdb_show" if str(media_type).lower() == "show" else "tmdb_movie"] = 0
    imdb_items = []
    for item in items:
        imdb_id = None
        tmdb_id = None
        tvdb_id = None
        for guid in getattr(item, "guids", []) or []:
            guid_id = str(getattr(guid, "id", "") or "").strip()
            if guid_id.startswith("imdb://"):
                imdb_id = guid_id.replace("imdb://", "", 1)
            elif guid_id.startswith("tmdb://"):
                tmdb_id = guid_id.replace("tmdb://", "", 1)
            elif guid_id.startswith("tvdb://"):
                tvdb_id = guid_id.replace("tvdb://", "", 1)
        if imdb_id or tmdb_id or tvdb_id:
            imdb_items.append(
                {
                    "id": imdb_id or tmdb_id or tvdb_id,
                    "imdb_id": imdb_id or "",
                    "tmdb_movie": tmdb_id or "",
                    "tvdb_show": tvdb_id or "",
                    "title": item.title,
                }
            )
            if imdb_id:
                source_counts["imdb_id"] += 1
            if "tmdb_movie" in source_counts and tmdb_id:
                source_counts["tmdb_movie"] += 1
            if "tvdb_show" in source_counts and tvdb_id:
                source_counts["tvdb_show"] += 1
        if all(count >= 10 for count in source_counts.values()):
            break

    # Best-effort placeholder recovery; disabled fallback to avoid missing module issues
    saved_item = None

    ts_log(f"Returning {len(imdb_items)} Plex top items", level="DEBUG")
    return imdb_items, saved_item


def get_plex_key_by_name(full_list, target_name):
    """
    Given a list of dicts with 'name' and 'plex_key', return the matching plex_key by name.
    """
    for lib in full_list:
        if lib.get("name") == target_name:
            return lib.get("plex_key")
    return None  # Or raise an exception if you prefer


def _extract_imdb_id_from_item(item):
    for guid in getattr(item, "guids", []) or []:
        guid_id = str(getattr(guid, "id", "") or "").strip().lower()
        if guid_id.startswith("imdb://"):
            return guid_id.replace("imdb://", "", 1)
    return ""


def _normalize_lookup_title(value):
    normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return normalized


def find_item_by_title(library_name, title):
    normalized_title = _normalize_lookup_title(title)
    if not normalized_title:
        return None

    plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
    if not plex_url or not plex_token:
        return None

    plex = PlexServer(plex_url, plex_token, timeout=8)

    try:
        section = plex.library.section(library_name)
    except Exception:
        return None

    results = section.search(title=title, maxresults=20)
    for item in results or []:
        item_title = str(getattr(item, "title", "") or "").strip()
        if _normalize_lookup_title(item_title) == normalized_title:
            return {"title": item_title}
    return None


def find_item_by_imdb_id(library_name, imdb_id, media_type, fallback_title=None):
    normalized_imdb_id = str(imdb_id or "").strip().lower()
    if not normalized_imdb_id:
        return None

    plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
    if not plex_url or not plex_token:
        return None

    plex = PlexServer(plex_url, plex_token, timeout=8)

    try:
        section = plex.library.section(library_name)
    except Exception:
        return None

    def build_match(item, source):
        title = str(getattr(item, "title", "") or "").strip()
        if not title:
            return None
        return {"id": normalized_imdb_id, "title": title, "source": source}

    def find_exact_imdb_match(candidates, source):
        for item in candidates or []:
            if _extract_imdb_id_from_item(item) == normalized_imdb_id:
                return build_match(item, source)
        return None

    direct_guid_match = find_exact_imdb_match(
        section.search(guid=f"imdb://{normalized_imdb_id}"),
        "plex-guid",
    )
    if direct_guid_match:
        return direct_guid_match

    if fallback_title:
        title_results = section.search(title=fallback_title, maxresults=20)
        exact_title_guid_match = find_exact_imdb_match(title_results, "plex-title-guid")
        if exact_title_guid_match:
            return exact_title_guid_match

        normalized_fallback_title = _normalize_lookup_title(fallback_title)
        for item in title_results or []:
            if _normalize_lookup_title(getattr(item, "title", "")) == normalized_fallback_title:
                return build_match(item, "plex-title")

    return None


def get_plex_summary():
    try:
        metadata = get_plex_metadata()
        if not isinstance(metadata, dict):
            return "Plex summary unavailable."

        server_name = metadata.get("server_name") or "Plex Server"
        version = metadata.get("version") or "Unknown Version"
        platform = metadata.get("platform") or "Unknown OS"
        platform_version = metadata.get("platformVersion") or "Unknown Version"
        db_cache_str = metadata.get("db_cache") or "Unknown"

        update_channel = metadata.get("update_channel")
        if update_channel == "Public update channel":
            update_channel_str = "Public update channel."
        elif update_channel == "PlexPass update channel":
            update_channel_str = "PlexPass update channel."
        elif update_channel:
            update_channel_str = f"{update_channel}."
        else:
            update_channel_str = "Unknown update channel."

        plex_pass = metadata.get("plex_pass", "Unknown")
        plex_pass_str = f"PlexPass: {plex_pass} on {update_channel_str}"
        maintenance_window_value = metadata.get("maintenance_window") or "Unavailable"
        if maintenance_window_value and maintenance_window_value != "Unavailable":
            maintenance_window = f"Scheduled maintenance running between {maintenance_window_value}"
        else:
            maintenance_window = "Scheduled maintenance times could not be found."

        # Final summary string
        return (
            f"Connected to Plex server {server_name} version {version}\n"
            f"Running on {platform} version {platform_version}\n"
            f"Plex DB cache setting: {db_cache_str}\n"
            f"{plex_pass_str}\n"
            f"{maintenance_window}"
        )

    except Exception as e:
        return f"Plex summary unavailable due to error: {e}"


def get_plex_maintenance_hours(plex_url, plex_token):
    if not plex_url or not plex_token:
        return None, None
    try:
        plex = PlexServer(plex_url, plex_token, timeout=8)
        settings = plex.settings
        start_hour = int(settings.get("butlerStartHour").value)
        end_hour = int(settings.get("butlerEndHour").value)
        return start_hour, end_hour
    except Exception:
        return None, None


def get_library_summaries(configured_library_names):
    try:
        metadata = get_plex_metadata()
        lib_metadata = metadata.get("libraries", {})

        output_lines = []
        for lib_name in configured_library_names:
            info = lib_metadata.get(lib_name)
            if not info:
                output_lines.append(f"Library '{lib_name}' not found on Plex server.")
                continue

            output_lines.append(f"Information on library: {lib_name}")
            output_lines.append(f"Type: {info.get('type', 'Unknown').capitalize()}")
            output_lines.append(f"Agent: {info.get('agent', 'Unknown')}")
            output_lines.append(f"Scanner: {info.get('scanner', 'Unknown')}")
            output_lines.append(f"Ratings Source: {info.get('ratings_source', 'N/A')}")

            if info.get("type") == "movie":
                count = info.get("movie_count", 0)
                output_lines.append(f"Content Count: {count} movies")

            elif info.get("type") == "show":
                show_count = info.get("show_count", 0)
                episode_count = info.get("episode_count", 0)
                output_lines.append(f"Content Count: {show_count} shows / {episode_count} episodes")

            else:
                item_count = info.get("item_count", 0)
                output_lines.append(f"Content Count: {item_count} items")

            output_lines.append("")  # Blank line between libraries

        return "\n".join(output_lines).strip()

    except Exception as e:
        return f"Plex library summary unavailable: {str(e)}"


def get_plex_metadata(plex_url=None, plex_token=None):
    try:
        if not plex_url or not plex_token:
            plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")

        from modules import helpers as _h_plex_cache

        cached = _h_plex_cache.get_cached_plex_metadata(plex_url, plex_token)
        if cached:
            ts_log("Using cached Plex metadata payload.", level="DEBUG")
            return cached

        plex = PlexServer(plex_url, plex_token)

        # Plex Pass
        try:
            plex_pass = plex.myPlexAccount().subscriptionActive
        except Exception:
            plex_pass = False

        # Update Channel
        try:
            update_channel_value = plex.settings.get("butlerUpdateChannel").value
            if update_channel_value == "16":
                update_channel = "Public update channel"
            elif update_channel_value == "8":
                update_channel = "PlexPass update channel"
            else:
                update_channel = f"Unknown update channel (raw: {update_channel_value})"
        except Exception:
            update_channel = "Unknown update channel"

        # DB Cache
        try:
            db_cache_size = plex.settings.get("DatabaseCacheSize").value
            db_cache_str = f"{db_cache_size} MB"
        except Exception:
            db_cache_str = "Unknown"

        # Maintenance window
        try:
            start_hour = int(plex.settings.get("butlerStartHour").value)
            end_hour = int(plex.settings.get("butlerEndHour").value)
            maintenance_window = f"{start_hour:02d}:00 – {end_hour:02d}:00"
        except Exception:
            maintenance_window = "Unavailable"

        # Per-library info. Fetch sections once so metadata and counts share the same section list.
        sections = plex.library.sections()
        library_metadata = get_library_metadata(plex=plex, sections=sections)

        metadata = {
            "plex_pass": plex_pass,
            "update_channel": update_channel,
            "server_name": plex.friendlyName,
            "version": plex.version,
            "platform": plex.platform,
            "platformVersion": plex.platformVersion,
            "db_cache": db_cache_str,
            "maintenance_window": maintenance_window,
            "libraries": library_metadata,
        }
        from modules import helpers as _h_plex_cache

        _h_plex_cache.set_cached_plex_metadata(plex_url, plex_token, metadata)
        return metadata

    except Exception as e:
        return {
            "plex_pass": False,
            "update_channel": None,
            "error": str(e),
            "libraries": {},
            "ratings_source": "Unavailable",
            "db_cache": "Unavailable",
            "maintenance_window": "Unavailable",
        }


def get_library_metadata(plex=None, sections=None, plex_url=None, plex_token=None):
    try:
        if plex is None:
            if not plex_url or not plex_token:
                plex_url, plex_token = persistence.get_stored_plex_credentials("010-plex")
            plex = PlexServer(plex_url, plex_token)

        library_data = {}
        if sections is None:
            sections = plex.library.sections()

        for section in sections:
            try:
                lib_info = {
                    "agent": section.agent,
                    "scanner": section.scanner,
                    "type": section.type,
                    "ratings_source": "N/A",
                }

                # Ratings source
                try:
                    settings = section.settings()
                    ratings_setting = next((s for s in settings if s.id == "ratingsSource"), None)
                    if ratings_setting:
                        lib_info["ratings_source"] = ratings_setting.enumValues.get(ratings_setting.value, "Unknown")
                except Exception:
                    pass  # Keep "N/A" if ratingsSource isn't available

                # Optimized content counts
                try:
                    if section.type == "movie":
                        lib_info["movie_count"] = section.totalSize
                    elif section.type == "show":
                        lib_info["show_count"] = section.totalSize
                        try:
                            lib_info["episode_count"] = section.totalViewSize(libtype="episode")
                        except Exception as e:
                            lib_info["episode_count"] = 0
                            lib_info["episode_error"] = str(e)
                    else:
                        lib_info["item_count"] = section.totalSize
                except Exception as e:
                    lib_info["error"] = str(e)

                library_data[section.title] = lib_info

            except Exception as lib_err:
                library_data[section.title] = {
                    "agent": "Unknown",
                    "scanner": "Unknown",
                    "type": "Unknown",
                    "ratings_source": f"Error: {lib_err}",
                }

        return library_data

    except Exception as e:
        return {"error": str(e)}
