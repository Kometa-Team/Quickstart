"""Unit tests for the log-scan advisory data table.

Guards the :class:`modules._logscan_advisory_table.Advisory` records and
:func:`~modules._logscan_advisory_table.render_advisory` helper introduced
in the data-table refactor of :mod:`modules.logscan_advisory_messages`.

Byte-identical output was the acceptance criterion for that refactor.
These tests lock in the structural invariants so future edits to the
table (adding rows, tweaking wording) can't silently break the render
contract.
"""

from __future__ import annotations

import pytest

from modules._logscan_advisory_table import (
    STANDARD_ADVISORIES,
    Advisory,
    render_advisory,
)
from modules.logscan_advisory_messages import _ADVISORY


class _FakeAnalyzer:
    """Minimal analyzer stub -- only ``format_contiguous_lines`` is used."""

    def format_contiguous_lines(self, bucket):
        # Deterministic fixture so assertions can pin the exact rendering.
        return "L45-48, L92"


# ---------------------------------------------------------------------------
# Table shape
# ---------------------------------------------------------------------------


class TestStandardAdvisoriesTable:
    def test_table_is_non_empty(self):
        assert len(STANDARD_ADVISORIES) > 0

    def test_every_entry_is_frozen_advisory(self):
        for advisory in STANDARD_ADVISORIES:
            assert isinstance(advisory, Advisory)
            with pytest.raises((AttributeError, Exception)):
                advisory.bucket_key = "mutated"  # type: ignore[misc]

    def test_bucket_keys_are_unique(self):
        keys = [a.bucket_key for a in STANDARD_ADVISORIES]
        assert len(keys) == len(set(keys)), "duplicate bucket_key entries"

    def test_lookup_dict_covers_every_advisory(self):
        assert set(_ADVISORY) == {a.bucket_key for a in STANDARD_ADVISORIES}

    def test_every_body_ends_with_newline(self):
        # The render function relies on this so the count line lands on
        # its own line without an extra join character.
        for advisory in STANDARD_ADVISORIES:
            assert advisory.body.endswith("\n"), f"Advisory {advisory.bucket_key!r} body must end with '\\n' so the count line renders on its own line."

    def test_url_placeholder_matches_url_presence(self):
        # If body references {url_line}, url must be non-empty.
        # (The reverse doesn't hold: at least one legacy bucket --
        # ``traceback_errors`` -- carried a url_line assignment that
        # never rendered in the original message, and we preserve
        # that quirk byte-for-byte.)
        for advisory in STANDARD_ADVISORIES:
            if "{url_line}" in advisory.body:
                assert advisory.url, f"Advisory {advisory.bucket_key!r} references {{url_line}} but has an empty url field."


# ---------------------------------------------------------------------------
# render_advisory
# ---------------------------------------------------------------------------


class TestRenderAdvisory:
    def test_substitutes_url_and_count(self):
        advisory = Advisory(
            bucket_key="demo",
            body=" **DEMO**\nSomething went sideways.\nMore info at {url_line}\n",
            url="[https://example.com]",
            count_label="demo issues",
        )
        rendered = render_advisory(advisory, [1, 2, 3], _FakeAnalyzer())
        assert rendered == (" **DEMO**\nSomething went sideways.\nMore info at [https://example.com]\n3 line(s) with demo issues. Line number(s): L45-48, L92")

    def test_no_url_body_renders_unchanged(self):
        # Buckets like ``checkFiles`` have no {url_line} placeholder.
        advisory = Advisory(
            bucket_key="demo",
            body=" **DEMO**\nNo url here.\n",
            url="",
            count_label="demo items",
        )
        rendered = render_advisory(advisory, [1, 2], _FakeAnalyzer())
        assert rendered == (" **DEMO**\nNo url here.\n2 line(s) with demo items. Line number(s): L45-48, L92")

    def test_bucket_length_is_from_len(self):
        advisory = Advisory(
            bucket_key="demo",
            body="**X**\nbody\n",
            url="",
            count_label="X",
        )
        rendered = render_advisory(advisory, list(range(7)), _FakeAnalyzer())
        assert rendered.startswith("**X**\nbody\n7 line(s) with X.")

    def test_every_table_advisory_renders_without_error(self):
        analyzer = _FakeAnalyzer()
        fake_bucket = [1, 2, 3]
        for advisory in STANDARD_ADVISORIES:
            rendered = render_advisory(advisory, fake_bucket, analyzer)
            # Every rendering should be a non-empty markdown string that
            # ends with the count-line suffix.
            assert rendered
            assert "line(s) with" in rendered
            assert "Line number(s): L45-48, L92" in rendered
            # No placeholder should leak through -- either the url was
            # substituted or the body never contained one.
            assert "{url_line}" not in rendered
