"""Backward-compatibility facade for the validations package.

Sprint 4 split the once-monolithic ``modules/validations.py`` (1828
lines) into thematic siblings:

* ``modules.validations_shared`` -- tiny path/repo helpers shared by
  every extraction.
* ``modules.validations_overlay_images`` -- overlay-source-override
  image validation / storage / cleanup (24 functions + constants).
* ``modules.validations_yaml_files`` -- Metadata/Collection/Overlay/
  Playlist YAML file+folder validators (26 functions across 3 tiers).
* ``modules.validations_services`` -- external-service connectivity
  validators (Plex / Tautulli / Trakt / Radarr / Sonarr / OMDb /
  GitHub / TMDb / MDBList / Gotify / Ntfy / Apprise / Webhook /
  Notifiarr / MAL).

This file re-exports every moved name so external callers -- blueprints,
``quickstart.py``, other modules, and 35 test-suite monkeypatches --
keep working via ``modules.validations.<name>``.

The only real code that still lives here is a pair of thin ISO code
wrappers (``validate_iso3166_1`` / ``validate_iso639_1``) that don't
fit any of the other clusters.
"""

# ``requests`` is imported here purely to keep it accessible as
# ``modules.validations.requests`` -- 14 test-suite monkeypatches (e.g.
# ``monkeypatch.setattr(qs_module.validations.requests, "get", ...)``)
# depend on this attribute being present.  Python module identity means
# the patch propagates to the ``requests`` module object that the
# extracted validators (``validations_yaml_files``,
# ``validations_services``, ``validations_overlay_images``) also see.
import requests  # noqa: F401  (load-bearing: tests monkeypatch validations.requests.get)

from modules import (  # noqa: F401 (persistence is load-bearing: tests monkeypatch validations.persistence.retrieve_settings)
    iso,
    helpers,
    path_validation,
    persistence,
    url_validation,
)

from modules.validations_shared import (  # noqa: F401
    _normalize_custom_repo_base,
    _resolve_managed_library_path,
    _saved_custom_repo_base,
)
from modules.validations_overlay_images import (  # noqa: F401
    MAX_OVERLAY_SOURCE_OVERRIDE_BYTES,
    OVERLAY_SOURCE_OVERRIDE_FORMAT_CONTENT_TYPES,
    OVERLAY_SOURCE_OVERRIDE_FORMAT_SUFFIXES,
    OVERLAY_SOURCE_OVERRIDE_LARGE_DIMENSION,
    OVERLAY_SOURCE_OVERRIDE_MIN_DIMENSION,
    OVERLAY_SOURCE_OVERRIDE_POSTER_SIZES,
    _coerce_overlay_source_locations,
    _collect_overlay_badge_warnings,
    _display_managed_overlay_image_location,
    _is_managed_overlay_image_path,
    _managed_overlay_scope_dir,
    _normalize_content_type,
    _prune_empty_managed_overlay_dirs,
    _resolve_overlay_source_override_remote_url,
    _resolve_scoped_managed_overlay_image_path,
    _safe_overlay_image_slug,
    _validate_allowed_image_format,
    _validate_image_bytes,
    _validate_overlay_badge_content_type,
    _validate_overlay_badge_image,
    _validate_overlay_badge_size,
    _validate_overlay_badge_suffix,
    cleanup_overlay_source_override_payload,
    cleanup_overlay_source_override_server,
    make_overlay_source_override_local_payload,
    make_overlay_source_override_local_server,
    normalize_overlay_source_override_file_location,
    store_overlay_source_override_image_bytes,
    validate_overlay_source_override_payload,
    validate_overlay_source_override_server,
)
from modules.validations_yaml_files import (  # noqa: F401
    _display_yaml_source_name,
    _normalize_metadata_validation_result,
    _summarize_folder_validation_failures,
    _validate_collection_yaml_folder,
    _validate_collection_yaml_location,
    _validate_collection_yaml_text,
    _validate_metadata_yaml_location,
    _validate_metadata_yaml_text,
    _validate_overlay_yaml_folder,
    _validate_overlay_yaml_location,
    _validate_overlay_yaml_text,
    _validate_playlist_yaml_location,
    _validate_playlist_yaml_text,
    _validate_required_top_level_mapping,
    _validate_yaml_folder,
    _validate_yaml_location,
    _validate_yaml_location_suffix,
    _validate_yaml_text,
    validate_collection_file_payload,
    validate_collection_file_server,
    validate_metadata_file_payload,
    validate_metadata_file_server,
    validate_overlay_file_payload,
    validate_overlay_file_server,
    validate_playlist_file_payload,
    validate_playlist_file_server,
)
from modules.validations_services import (  # noqa: F401
    _validate_service_url,
    validate_apprise_server,
    validate_gotify_server,
    validate_github_server,
    validate_mal_server,
    validate_mdblist_server,
    validate_notifiarr_server,
    validate_ntfy_server,
    validate_omdb_server,
    validate_plex_server,
    validate_radarr_payload,
    validate_radarr_server,
    validate_sonarr_payload,
    validate_sonarr_server,
    validate_tautulli_server,
    validate_tmdb_server,
    validate_trakt_server,
    validate_webhook_server,
)


def validate_iso3166_1(code):
    try:
        return iso.get_country(alpha2=code, alpha3=code).alpha2
    except (NameError, ValueError):
        return None


def validate_iso639_1(code):
    try:
        return iso.get_language(alpha2=code, alpha3=code).alpha2
    except (NameError, ValueError):
        return None
