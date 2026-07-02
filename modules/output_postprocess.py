"""Post-processing helpers for finalized config dicts.

Extracted from the original ``modules/output.py`` monolith.  These two
helpers run after ``build_libraries_section`` / ``build_config`` have
assembled the config dict but before the YAML dump -- final cleanup
passes over the fully-built structure.

* ``clean_section_data`` -- strip transient ``tmp_*`` keys from a
  section before it lands in the output config.
* ``_rewrite_custom_font_paths`` -- walk the config tree and rewrite
  bare font filenames (``MyFont.ttf``) to the on-disk
  ``config/fonts/MyFont.ttf`` path that Kometa expects.

Public surface: ``clean_section_data`` has no underscore prefix (it's
a slightly-public helper).  Neither has external callers today, but
both are re-exported by ``output.py`` so historical
``output.clean_section_data(...)`` style calls keep working if any
test reaches for them.
"""

from __future__ import annotations

import copy
import os

from modules import helpers


def clean_section_data(section_data, config_attribute):
    """Cleans out temporary or irrelevant data before integrating into config.yml.

    Keeps only the ``config_attribute`` key from ``section_data``, and
    when its value is a dict, strips any sub-keys prefixed with
    ``tmp_``.  Everything retained is deep-copied so downstream mutation
    can't leak back into the source section.
    """
    clean_data = {}

    for key, value in section_data.items():
        if key != config_attribute:
            continue
        if isinstance(value, dict):
            clean_sub_data = {sub_key: copy.deepcopy(sub_value) for sub_key, sub_value in value.items() if not sub_key.startswith("tmp_")}
            clean_data[key] = clean_sub_data
        else:
            clean_data[key] = copy.deepcopy(value)

    return clean_data


def _normalize_font_value(value, available_fonts):
    """Rewrite one font-field value in-place, returning the (possibly-updated) value.

    Handles two shapes: ``{"value": "MyFont.ttf"}`` (form-submission
    style) and bare strings.  If the basename matches a known available
    font, rewrite to ``config/fonts/<basename>``; otherwise leave alone.
    """
    if isinstance(value, dict):
        raw = value.get("value")
        if isinstance(raw, str):
            updated = _normalize_font_value(raw, available_fonts)
            if updated != raw:
                value["value"] = updated
        return value
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    base = os.path.basename(stripped)
    if base in available_fonts:
        return f"config/fonts/{base}"
    return value


def _walk_config_for_fonts(obj, available_fonts):
    """Recursively walk ``obj``, rewriting every ``font`` / ``*_font`` value."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(key, str) and (key == "font" or key.endswith("_font")):
                obj[key] = _normalize_font_value(val, available_fonts)
            else:
                _walk_config_for_fonts(val, available_fonts)
    elif isinstance(obj, list):
        for item in obj:
            _walk_config_for_fonts(item, available_fonts)


def _rewrite_custom_font_paths(config_data):
    """Rewrite bare font filenames to full ``config/fonts/<name>`` paths.

    Kometa expects font references in the config to be paths under
    ``config/fonts/``.  Users often paste just the filename
    (``MyFont.ttf``); this walker resolves those against the set of
    available fonts and rewrites in-place.
    """
    available_fonts = set(helpers.list_available_fonts(include_static=True, include_custom=True))
    if not available_fonts:
        return config_data
    _walk_config_for_fonts(config_data, available_fonts)
    return config_data
