"""PMS (Plex Media Server) version parsing and vulnerability checks.

Extracted from ``modules.logscan``.

Kometa doesn't ship with a curated CVE database; instead the logscan
recommendations flag Plex versions that fall inside a specific
known-bad range (currently 1.41.7.x -- 1.42.0.x).  This module owns:

* :func:`parse_version_tuple` -- turn a PMS version string like
  ``"1.41.7.9100"`` or ``"1.42.0.9700-abc123"`` into a
  ``(major, minor, patch, build)`` int-tuple.  Missing components
  default to 0.  The ``-suffix`` (build tag) is stripped.  Never
  raises on malformed input -- non-int components resolve to 0.

* :func:`version_in_inclusive_range` -- given a version string and
  inclusive ``low``/``high`` tuples, return True when the parsed
  version lies within.

* :data:`VULNERABLE_RANGE_LOW` / :data:`VULNERABLE_RANGE_HIGH` --
  the currently-flagged vulnerable-version window.  Update these
  when a new CVE window needs flagging.

* :func:`is_vulnerable_pms_version` -- terse convenience:
  ``is_vulnerable_pms_version("1.41.7.9100")`` returns True.
"""

from __future__ import annotations


def parse_version_tuple(ver: str) -> tuple[int, int, int, int]:
    """Return a 4-int tuple for PMS versions like ``'1.41.7.9100'``.

    Any ``-suffix`` (e.g. ``'1.42.0.9700-abc123'``) is trimmed.
    Missing components default to 0; non-integer components also
    default to 0 (defensive against malformed input in log lines).
    """
    ver = ver.split("-", 1)[0].strip()
    parts = ver.split(".")
    nums = []
    for i in range(4):
        try:
            nums.append(int(parts[i]))
        except Exception:
            nums.append(0)
    return tuple(nums[:4])


def version_in_inclusive_range(ver: str, low: tuple, high: tuple) -> bool:
    """Return True when *ver* parses into a tuple within ``[low, high]``."""
    return low <= parse_version_tuple(ver) <= high


# Currently-flagged vulnerable PMS version window.  When a new CVE
# needs flagging, update these two constants and the recommendation
# text in :func:`modules.logscan.LogscanAnalyzer.make_recommendations`.
VULNERABLE_RANGE_LOW: tuple[int, int, int, int] = (1, 41, 7, 0)  # 1.41.7.x
VULNERABLE_RANGE_HIGH: tuple[int, int, int, int] = (1, 42, 0, 99999)  # through 1.42.0.x


def is_vulnerable_pms_version(ver: str) -> bool:
    """Return True when *ver* falls inside the current vulnerable window."""
    return version_in_inclusive_range(ver, VULNERABLE_RANGE_LOW, VULNERABLE_RANGE_HIGH)


def format_version_tuple(version: tuple) -> str:
    """Render a version tuple as a dotted string.

    ``(1, 41, 7, 0) -> '1.41.7.0'``.  Used when the recommendation
    text needs to display the vulnerable range in a human-readable
    form.
    """
    return ".".join(str(component) for component in version)
