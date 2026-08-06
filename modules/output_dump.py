"""YAML section serialization for build_config.

Extracted from the original ``modules/output.py`` monolith.  Every
config section (``plex``, ``tmdb``, ``libraries``, etc.) that
``build_config`` emits is passed through ``dump_section`` -- a
recursive cleaner + ``ruamel.yaml`` dumper + validation-comment
prepender.

Public surface: nothing here is a public API.  ``build_config`` calls
``dump_section`` locally; everything else in this module is a helper
of that call site.

Design notes:

* The ``_EMPTY_OUTPUT`` sentinel drives recursive pruning of empty
  values (``None``, whitespace-only strings, empty containers).
  ``dict.pop`` semantics matter -- the sentinel signals "this entry
  should be dropped from its parent", which propagates upward through
  the walk.
* ``clean_data`` and ``_prune_empty_output_values`` were two separate
  nested closures in the original code.  They stay as separate top-level
  helpers here because their responsibilities do differ subtly:
  ``clean_data`` also alphabetically sorts certain sections and strips
  a ``valid`` key; ``_prune_empty_output_values`` only handles the
  scalar leaves.
* Section-name-set constants (``_ALPHABETICALLY_SORTED_SECTIONS``,
  ``_PLAIN_SCALAR_SECTIONS``) are hoisted to module scope so they're
  not recreated on every ``dump_section`` call.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import PlainScalarString

from modules import database, helpers
from modules.output_collections import _LOOKUP_LABELS_SUFFIX, _normalize_settings_section_value, _TEMPLATE_VARIABLE_COMMENTS_KEY, _parse_template_lookup_labels
from modules.output_headers import render_section_header
from modules.output_values import _normalize_asset_directory_values

# Sentinel returned by pruning to say "drop this from its parent".
# Sits at module scope so identity comparisons (`is _EMPTY_OUTPUT`)
# stay stable across recursive calls.
_EMPTY_OUTPUT = object()


# Sections whose top-level keys should be emitted in alphabetical order
# (for readability of the generated config.yml).
_ALPHABETICALLY_SORTED_SECTIONS = frozenset(
    {
        "settings",
        "webhooks",
        "plex",
        "tmdb",
        "tautulli",
        "tracearr",
        "github",
        "omdb",
        "mdblist",
        "serializd",
        "floppy",
        "notifiarr",
        "gotify",
        "ntfy",
        "apprise",
        "yamtrack",
        "anidb",
        "radarr",
        "sonarr",
        "trakt",
        "mal",
    }
)


# Sections that carry secret/opaque tokens which YAML's folding logic
# tends to line-wrap.  We coerce every string in these sections to a
# PlainScalarString so ruamel.yaml keeps them on one line.
_PLAIN_SCALAR_SECTIONS = frozenset(
    {
        "plex",
        "tmdb",
        "tautulli",
        "tracearr",
        "github",
        "omdb",
        "mdblist",
        "serializd",
        "floppy",
        "notifiarr",
        "gotify",
        "ntfy",
        "apprise",
        "yamtrack",
        "anidb",
        "radarr",
        "sonarr",
        "trakt",
        "mal",
    }
)


_SETTINGS_KEEP_EMPTY_KEYS = frozenset({"auto_sort_hubs", "ignore_ids", "ignore_imdb_ids", "playlist_exclude_users"})


# --- pruning / cleaning ---------------------------------------------------


def _prune_empty_output_values(obj):
    """Walk ``obj`` and return ``_EMPTY_OUTPUT`` for empty leaves.

    Empty here means:
      * ``None``
      * empty or whitespace-only string
      * a dict where every value pruned to ``_EMPTY_OUTPUT``
      * a list where every item pruned to ``_EMPTY_OUTPUT``

    A ``valid`` key inside a dict is always dropped -- it's a transient
    validation flag that should never land in the emitted YAML.

    Note: in the current call graph this function only ever receives
    scalar arguments (``clean_data`` calls it on non-dict, non-list
    leaves), so the dict/list branches are effectively defensive.  They
    were preserved from the original nested-closure form to keep this
    extraction behavior-neutral.
    """
    if isinstance(obj, dict):
        pruned = {}
        for key, value in obj.items():
            if key == "valid":
                continue
            cleaned_value = _prune_empty_output_values(value)
            if cleaned_value is _EMPTY_OUTPUT:
                continue
            pruned[key] = cleaned_value
        return pruned if pruned else _EMPTY_OUTPUT
    if isinstance(obj, list):
        cleaned_items = []
        for value in obj:
            cleaned_value = _prune_empty_output_values(value)
            if cleaned_value is _EMPTY_OUTPUT:
                continue
            cleaned_items.append(cleaned_value)
        return cleaned_items if cleaned_items else _EMPTY_OUTPUT
    if obj is None:
        return _EMPTY_OUTPUT
    if isinstance(obj, str) and obj.strip() == "":
        return _EMPTY_OUTPUT
    return obj


def _clean_data(obj, dump_name):
    """Recursively clean a section's data dict for YAML emission.

    Behaviors, applied top-down:
      * Dicts in the ``_ALPHABETICALLY_SORTED_SECTIONS`` list get their
        keys alphabetically sorted (readability of the emitted YAML).
      * A ``valid`` key inside any dict is dropped.
      * Empty values (``None``, empty string, empty containers) are
        pruned via ``_EMPTY_OUTPUT`` sentinel semantics.
      * Scalars go through ``_prune_empty_output_values`` for leaf-level
        empty detection.
    """
    if isinstance(obj, dict):
        if dump_name in _ALPHABETICALLY_SORTED_SECTIONS:
            obj = dict(sorted(obj.items()))
        cleaned_dict = {}
        for k, v in obj.items():
            if k == "valid":
                continue
            cleaned_value = _clean_data(v, dump_name)
            if cleaned_value is _EMPTY_OUTPUT:
                continue
            cleaned_dict[k] = cleaned_value
        return cleaned_dict if cleaned_dict else _EMPTY_OUTPUT
    if isinstance(obj, list):
        cleaned_list = []
        for v in obj:
            cleaned_value = _clean_data(v, dump_name)
            if cleaned_value is _EMPTY_OUTPUT:
                continue
            cleaned_list.append(cleaned_value)
        return cleaned_list if cleaned_list else _EMPTY_OUTPUT
    return _prune_empty_output_values(obj)


def _plainify_strings(obj):
    """Recursively coerce every string in ``obj`` to a PlainScalarString.

    Used for sections that hold API tokens / opaque strings so
    ``ruamel.yaml`` doesn't emit them in folded style.  Structural
    containers are re-created (fresh dicts/lists) but their scalar
    leaves are wrapped in-place.
    """
    if isinstance(obj, dict):
        return {k: _plainify_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plainify_strings(v) for v in obj]
    if isinstance(obj, str):
        return PlainScalarString(obj)
    return obj


def _format_inline_comment(value):
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    return text.strip()


def _split_comment_values(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _format_value_comment(value, labels):
    values = _split_comment_values(value)
    if len(values) == 1:
        return _format_inline_comment(labels.get(values[0]))
    comments = []
    for item in values:
        label = _format_inline_comment(labels.get(str(item).strip()))
        if label:
            comments.append(f"{item}: {label}")
    return "; ".join(comments)


def _apply_comment_map_to_template_vars(template_vars, comment_map):
    if not isinstance(template_vars, dict) or not isinstance(comment_map, dict):
        return template_vars

    commented_template_vars = template_vars if isinstance(template_vars, CommentedMap) else CommentedMap(template_vars)
    for template_key, labels in comment_map.items():
        if not isinstance(labels, dict) or template_key not in commented_template_vars:
            continue
        values = commented_template_vars.get(template_key)
        if isinstance(values, list):
            commented_values = CommentedSeq(values)
            for index, item in enumerate(commented_values):
                comment = _format_inline_comment(labels.get(str(item).strip()))
                if comment:
                    commented_values.yaml_add_eol_comment(comment, index)
            commented_template_vars[template_key] = commented_values
            continue
        comment = _format_value_comment(values, labels)
        if comment:
            commented_template_vars.yaml_add_eol_comment(comment, key=template_key)
    return commented_template_vars


def _pop_lookup_label_sidecars(container):
    if not isinstance(container, dict):
        return {}

    comment_map = {}
    for key in list(container.keys()):
        key_text = str(key or "")
        if not key_text.endswith(_LOOKUP_LABELS_SUFFIX):
            continue
        template_key = key_text[: -len(_LOOKUP_LABELS_SUFFIX)]
        labels = _parse_template_lookup_labels(container.pop(key, None))
        if template_key and labels:
            comment_map[template_key] = labels
    return comment_map


def _apply_settings_lookup_comments(cleaned_data):
    settings_block = cleaned_data.get("settings") if isinstance(cleaned_data, dict) else None
    if not isinstance(settings_block, dict):
        return

    comment_map = _pop_lookup_label_sidecars(settings_block)
    if not comment_map:
        return

    cleaned_data["settings"] = _apply_comment_map_to_template_vars(settings_block, comment_map)


def _apply_template_variable_comments(cleaned_data):
    """Attach saved lookup labels as YAML end-of-line comments.

    The UI persists label metadata beside template string-list fields under
    ``__template_variable_comments``.  That key is internal to Quickstart: it
    must be consumed before dumping so Kometa never sees it.
    """
    libraries = cleaned_data.get("libraries") if isinstance(cleaned_data, dict) else None
    if not isinstance(libraries, dict):
        return

    for library_data in libraries.values():
        if not isinstance(library_data, dict):
            continue
        library_comment_map = library_data.pop(_TEMPLATE_VARIABLE_COMMENTS_KEY, None)
        if isinstance(library_comment_map, dict) and isinstance(library_data.get("template_variables"), dict):
            library_data["template_variables"] = _apply_comment_map_to_template_vars(library_data["template_variables"], library_comment_map)

        collection_files = library_data.get("collection_files")
        if not isinstance(collection_files, list):
            continue

        for entry in collection_files:
            if not isinstance(entry, dict):
                continue
            comment_map = entry.pop(_TEMPLATE_VARIABLE_COMMENTS_KEY, None)
            if not isinstance(comment_map, dict):
                continue
            template_vars = entry.get("template_variables")
            if not isinstance(template_vars, dict):
                continue

            entry["template_variables"] = _apply_comment_map_to_template_vars(template_vars, comment_map)


# --- per-section post-cleaning tweaks -------------------------------------


def _coerce_int_or_ignore(container, key):
    """Coerce ``container[key]`` to ``int`` in place; swallow any exception."""
    if key not in container:
        return
    try:
        container[key] = int(container[key])
    except Exception:
        pass


def _apply_mal_trakt_int_coercions(cleaned_data, dump_name):
    """MAL/TRAKT sections carry ``expires_in`` and ``cache_expiration`` fields that
    must land in YAML as ints, not strings.
    """
    section = cleaned_data.get(dump_name, {})
    if not isinstance(section, dict):
        return
    auth = section.get("authorization")
    if isinstance(auth, dict):
        _coerce_int_or_ignore(auth, "expires_in")
    _coerce_int_or_ignore(section, "cache_expiration")


_TRAKT_PREFERRED_ORDER = ("authorization", "client_id", "client_secret", "pin", "force_refresh")


def _apply_trakt_reorder(cleaned_data):
    """TRAKT has a legacy ``force_refresh`` key living under ``authorization`` that
    should be hoisted to the section root, and the section's top-level keys
    should be emitted in a specific order.
    """
    section = cleaned_data.get("trakt")
    if not isinstance(section, dict):
        return
    auth = section.get("authorization")
    if isinstance(auth, dict) and "force_refresh" in auth and "force_refresh" not in section:
        section["force_refresh"] = auth.pop("force_refresh")

    ordered_section = {key: section[key] for key in _TRAKT_PREFERRED_ORDER if key in section}
    for key, value in section.items():
        if key not in ordered_section:
            ordered_section[key] = value
    cleaned_data["trakt"] = ordered_section


def _has_nonblank_oauth_value(value):
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"none", "null", "false"}


def _drop_unusable_trakt_section(cleaned_data):
    """Drop token-only Trakt residue left after a user clears visible inputs.

    Imported bundles can leave ``authorization`` tokens behind after the Trakt
    page is visually cleared. Without a client identity, those tokens cannot be
    validated as a configured Trakt setup and should not keep being emitted.
    """
    section = cleaned_data.get("trakt")
    if not isinstance(section, dict):
        return
    auth = section.get("authorization") if isinstance(section.get("authorization"), dict) else {}
    has_visible_identity = any(
        _has_nonblank_oauth_value(value)
        for value in (
            section.get("client_id"),
            section.get("client_secret"),
            section.get("pin"),
            auth.get("client_id"),
            auth.get("client_secret"),
        )
    )
    if not has_visible_identity:
        cleaned_data.pop("trakt", None)


def _apply_settings_normalization(cleaned_data):
    """Normalize settings-block values, mirroring the schema shapes expected
    by Kometa.  ``asset_directory`` in particular can arrive as a multi-line
    string and needs list-splitting.
    """
    settings_block = cleaned_data.get("settings")
    if not isinstance(settings_block, dict):
        settings_block = {}
        cleaned_data["settings"] = settings_block

    for setting_key in list(settings_block.keys()):
        normalized_value = _normalize_settings_section_value(setting_key, settings_block.get(setting_key))
        if normalized_value is None:
            settings_block.pop(setting_key, None)
        else:
            settings_block[setting_key] = normalized_value

    if "asset_directory" in settings_block and isinstance(settings_block["asset_directory"], (str, list)):
        settings_block["asset_directory"] = _normalize_asset_directory_values(settings_block["asset_directory"])

    for setting_key in _SETTINGS_KEEP_EMPTY_KEYS:
        settings_block.setdefault(setting_key, None)

    cleaned_data["settings"] = dict(sorted(settings_block.items()))


# --- validation comment ---------------------------------------------------


def _format_validation_timestamp(raw):
    """Render an ISO-8601 timestamp as ``YYYY-MM-DD HH:MM:SS`` in local time.

    Returns the raw input unchanged if parsing fails, or ``""`` for
    empty input.  Missing timezone defaults to UTC.
    """
    if not raw:
        return ""
    try:
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local = parsed.astimezone()
        return local.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw


def build_validation_comment(section_key, config_name):
    """Return a ``# validation: <status> (last_validated: <ts>)`` comment,
    or ``""`` if there's nothing on record for this section.
    """
    if not config_name:
        return ""
    stored = database.retrieve_section_data(config_name, section_key)
    if not stored or not isinstance(stored[2], dict):
        return ""
    stored_validated = helpers.booler(stored[0])
    payload = stored[2]
    status = payload.get("validation_status")
    if not status:
        if stored_validated:
            status = "validated"
        else:
            fallback_timestamp = payload.get("validated_at")
            status = "failed" if fallback_timestamp else ""
    if not status:
        return ""
    updated_at = payload.get("validation_updated_at") or payload.get("validated_at")
    last_validated = _format_validation_timestamp(updated_at)
    if last_validated:
        return f"# validation: {status} (last_validated: {last_validated})"
    return f"# validation: {status}"


# --- YAML dumper factory --------------------------------------------------


def _build_dump_yaml():
    """Return a fresh ``YAML`` instance configured for Kometa output.

    Key settings:
      * ``default_flow_style = False`` -- always block-style
      * ``sort_keys = False`` -- respect insertion order (post-cleaning)
      * ``width = 4096`` -- avoid mid-string wrapping of long secrets
      * ``None`` renders as ``""`` rather than the string ``null``
    """
    dump_yaml = YAML()
    dump_yaml.default_flow_style = False
    dump_yaml.sort_keys = False
    dump_yaml.width = 4096
    dump_yaml.representer.add_representer(
        type(None),
        lambda self, _: self.represent_scalar("tag:yaml.org,2002:null", ""),
    )
    return dump_yaml


# --- the dumper -----------------------------------------------------------


def dump_section(title, dump_name, data, header_style, config_name):
    """Clean and YAML-dump one config section, returning the assembled string.

    Returns a multi-line string of the form::

        <title>
        <validation_comment>
        <yaml_body>

    where ``<title>`` is the pre-rendered header (from
    ``render_section_header``), ``<validation_comment>`` is a
    ``# validation:`` line (empty if nothing stored), and
    ``<yaml_body>`` is the ruamel-dumped output with section headers
    injected for the ``libraries`` block.

    ``header_style`` is passed through to
    ``_inject_library_section_headers`` and drives whether ratings
    overlays / collection-file blocks etc. get their own ASCII art
    dividers within the libraries section.  When ``header_style ==
    'none'`` no header injection happens.
    """
    cleaned_data = _clean_data(data, dump_name)
    if cleaned_data is _EMPTY_OUTPUT:
        cleaned_data = {}
    if dump_name == "libraries" and isinstance(cleaned_data, dict) and "libraries" not in cleaned_data:
        cleaned_data = {"libraries": cleaned_data}
    if dump_name == "anidb":
        section = cleaned_data.get("anidb")
        if isinstance(section, dict):
            section.pop("enable", None)

    if dump_name in _PLAIN_SCALAR_SECTIONS:
        cleaned_data = _plainify_strings(cleaned_data)

    if dump_name in ("mal", "trakt"):
        _apply_mal_trakt_int_coercions(cleaned_data, dump_name)

    if dump_name == "trakt":
        _drop_unusable_trakt_section(cleaned_data)
        if "trakt" not in cleaned_data:
            return ""
        _apply_trakt_reorder(cleaned_data)

    if dump_name == "settings":
        _apply_settings_normalization(cleaned_data)
        _apply_settings_lookup_comments(cleaned_data)

    if dump_name == "libraries":
        _apply_template_variable_comments(cleaned_data)

    dump_yaml = _build_dump_yaml()
    with io.StringIO() as stream:
        dump_yaml.dump(cleaned_data, stream)
        section_output = stream.getvalue().strip()

    if header_style != "none":
        section_output = _inject_library_section_headers(section_output, header_style)

    validation_comment = build_validation_comment(dump_name, config_name)
    blocks = []
    if title:
        blocks.append(title)
    if validation_comment:
        blocks.append(validation_comment)
    blocks.append(section_output)
    return "\n".join(blocks) + "\n\n"


# --- library section header injection -------------------------------------
#
# When emitting the ``libraries`` block, we walk the already-dumped YAML
# string and drop ASCII-art headers above each library name / each of
# ``collection_files``, ``metadata_files``, ``overlay_files``.


_LIBRARY_SUBHEADER_TITLES = {
    "collection_files:": "Collections",
    "metadata_files:": "Metadata Files",
    "overlay_files:": "Overlays",
}


def _inject_library_section_headers(yaml_string, font):
    """Insert ``render_section_header`` output above each library block and
    each of its ``collection_files:`` / ``metadata_files:`` / ``overlay_files:``
    child keys, so the emitted YAML is readable at a glance.
    """
    lines = yaml_string.splitlines()
    output = []
    in_libraries_block = False

    for line in lines:
        stripped = line.strip()

        if stripped == "libraries:":
            in_libraries_block = True
            output.append(line)
            continue

        if in_libraries_block and not line.startswith("  ") and not stripped.startswith("#") and ":" in line:
            in_libraries_block = False

        # Only inject header for lines like "  Movies:" or "  TV Shows:" inside the libraries block
        if in_libraries_block and line.startswith("  ") and not line.startswith("   ") and stripped.endswith(":") and not stripped.startswith("-"):
            library_name = stripped.rstrip(":")
            output.append(render_section_header(library_name, font))
        else:
            subheader_title = None
            for prefix, title in _LIBRARY_SUBHEADER_TITLES.items():
                if stripped.startswith(prefix):
                    subheader_title = title
                    break
            if subheader_title is not None:
                output.append(render_section_header(subheader_title, font))

        output.append(line)

    return "\n".join(output)
