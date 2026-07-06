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

* The line-detector block that used to live here has been
  extracted to :mod:`modules.logscan_line_scan`.  A future PR
  could take it data-driven with a list of (predicate, bucket)
  tuples to shrink its if/elif chain.

* The advisory-builder module (:mod:`modules.logscan_advisory_messages`,
  ~900 lines) mostly follows a shared template shape (icon +
  title + body + url + count line) and could collapse to a data
  table with a dozen inline exceptions.  Would take that file
  from ~900 lines down to ~200.
"""

from __future__ import annotations

import logging
import re

from modules.logscan_advisory_messages import build_advisory_messages
from modules.logscan_issue_counts import build_issue_counts
from modules.logscan_line_scan import scan_content

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
    # PHASE 1+2 -- initialize state, then line-scan the content into buckets
    # (Phase 1 used to declare ~57 empty accumulators inline; Phase 2 was the
    # detector loop that populated them.  Both now live inside scan_content.)
    # ------------------------------------------------------------------
    analyzer.checkfiles_flg = None
    special_check_lines = []
    buckets = scan_content(analyzer, content)

    # ------------------------------------------------------------------
    # PHASE 3 -- build advisory messages from the populated buckets
    # ------------------------------------------------------------------
    platform_recs = _build_advisory_messages(
        analyzer=analyzer,
        content=content,
        incomplete_message=incomplete_message,
        special_check_lines=special_check_lines,
        **buckets,
    )

    # ------------------------------------------------------------------
    # PHASE 4 -- side-effect: flip the checkfiles flag
    # ------------------------------------------------------------------
    if buckets["checkFiles"]:
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
        buckets=buckets,
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
