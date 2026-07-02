"""Config-file block entry parsers for output.py.

Extracted from the original ``modules/output.py`` monolith.  This module
covers three near-identical helpers that were previously copy-pasted
three times in output.py -- one each for the ``metadata_files``,
``collection_files``, and ``overlay_files`` YAML blocks.

All three parse the same shape of input: a list (or a JSON-encoded
string of a list) of ``{"type": <kind>, "location": <path-or-url>}``
dicts, filter to entries where ``type in {file, folder, url, git, repo}``,
sort deterministically, and emit ``{<kind>: <location>}`` dicts.

The single ``_parse_config_file_block_entries`` implementation does the
work; three thin aliases preserve the historic call surface so
``output._parse_metadata_file_entries(...)`` etc. keep working (there
are direct test call sites for each name).

Note: this is a **different** shape/concern from the parsers in
``modules/library_file_entries.py``, which emit
``{"type": X, "location": Y, "validated": True}`` shapes for library
form persistence.  Do not confuse them.
"""

from __future__ import annotations

import json

_ACCEPTED_ENTRY_TYPES = frozenset({"file", "folder", "url", "git", "repo"})


def _parse_config_file_block_entries(raw_value):
    """Normalize a config-file-list block into sorted ``[{kind: location}, ...]``."""
    if isinstance(raw_value, list):
        entries = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            entries = json.loads(text)
        except Exception:
            return []
    else:
        return []

    if not isinstance(entries, list):
        return []

    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("type") or "").strip().lower()
        location = str(entry.get("location") or "").strip()
        if entry_type not in _ACCEPTED_ENTRY_TYPES or not location:
            continue
        normalized.append({entry_type: location})

    normalized.sort(key=lambda item: (next(iter(item.keys())), next(iter(item.values())).casefold()))
    return normalized


# Semantic aliases: each block kind gets its own name so call sites
# stay self-documenting.  They all share one implementation today; if
# any need to diverge later, they can be inlined without hunting.


def _parse_metadata_file_entries(raw_value):
    return _parse_config_file_block_entries(raw_value)


def _parse_collection_file_block_entries(raw_value):
    return _parse_config_file_block_entries(raw_value)


def _parse_overlay_file_block_entries(raw_value):
    return _parse_config_file_block_entries(raw_value)
