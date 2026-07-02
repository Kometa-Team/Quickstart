"""Per-library operation builders for build_libraries_section.

Extracted incrementally from the giant ``add_entry`` closure inside
``modules/output.py``.  Each function here takes the raw
``attr_group`` dict for one library plus a couple of identity keys,
and returns the operation's YAML-ready value (or ``None`` when the
operation is disabled).

The naming convention is ``build_<operation_name>_operation`` so it's
obvious what shape the return type matches.

Public surface: none.  These helpers are called from the
``build_libraries_section`` orchestrator; ``output.py`` imports each
name without underscore because they're consumed inside the same
package.
"""

from __future__ import annotations

from modules import helpers
from modules.output_values import _coerce_bool

# Values that we treat as "no override provided" for the numeric-ish
# knobs inside operation blocks.  Users can wipe a field by clearing
# the form input, which arrives as one of these placeholders.
_EMPTY_OVERRIDE_VALUES = frozenset({None, "", "None", "none"})


def _attr_key(library_type, lib_id, suffix):
    """Compose the per-library attribute lookup key.

    Consolidates the ``f\"{library_type}-library_{lib_id}-attribute_{...}\"``
    string builder that appears literally dozens of times inside
    ``add_entry``.  Not exported for now -- callers stay within this
    module.
    """
    return f"{library_type}-library_{lib_id}-attribute_{suffix}"


def build_delete_collections_operation(attr_group, library_type, lib_id):
    """Return the ``delete_collections`` operations dict, or an empty dict.

    Reads four attribute inputs off ``attr_group``:

    * ``delete_collections_configured`` -- bool
    * ``delete_collections_managed`` -- bool
    * ``delete_collections_ignore_empty_smart_collections`` -- bool
    * ``delete_collections_less`` -- int (or empty)

    Returns an empty dict when none of the four are actually set --
    callers should treat that as "don't emit a delete_collections
    block".  When at least one input is set, returns a dict shaped
    like the Kometa ``operations.delete_collections`` schema:

        {
            "configured": bool,
            "managed": bool,
            "less": int,                              # if provided
            "ignore_empty_smart_collections": True,   # if enabled
        }
    """
    configured_value = _coerce_bool(attr_group.get(_attr_key(library_type, lib_id, "delete_collections_configured")))
    managed_value = _coerce_bool(attr_group.get(_attr_key(library_type, lib_id, "delete_collections_managed")))
    ignore_value = _coerce_bool(attr_group.get(_attr_key(library_type, lib_id, "delete_collections_ignore_empty_smart_collections")))

    less_value = None
    raw_less = attr_group.get(_attr_key(library_type, lib_id, "delete_collections_less"))
    if raw_less not in _EMPTY_OVERRIDE_VALUES:
        try:
            less_value = int(raw_less)
        except Exception:
            helpers.ts_log(f"Skipping invalid delete_collections_less value: {raw_less}", level="DEBUG")

    enabled = configured_value is True or managed_value is True or ignore_value is True or less_value is not None
    if not enabled:
        return {}

    result = {
        "configured": configured_value if configured_value is not None else False,
        "managed": managed_value if managed_value is not None else False,
    }
    if less_value is not None:
        result["less"] = less_value
    if ignore_value is True:
        result["ignore_empty_smart_collections"] = True
    return result
