"""Tests for the extracted ``modules.logscan_people`` helpers."""

import json
from unittest.mock import MagicMock, patch

import pytest

from modules import logscan_people

# ---------------------------------------------------------------------------
# extract_filename_from_url
# ---------------------------------------------------------------------------


def test_extract_filename_url_decodes_and_drops_extension():
    url = "https://example.com/path/to/Foo%20Bar.jpg"
    assert logscan_people.extract_filename_from_url(url) == "Foo Bar"


def test_extract_filename_handles_basename_with_no_ext():
    assert logscan_people.extract_filename_from_url("https://example.com/just-a-name") == "just-a-name"


# ---------------------------------------------------------------------------
# get_people_cache_path / load_people_cache / save_people_cache
# ---------------------------------------------------------------------------


def test_load_people_cache_returns_empty_when_path_missing(tmp_path):
    missing = tmp_path / "definitely_not_here.json"
    assert logscan_people.load_people_cache(missing) == {}


def test_load_people_cache_returns_empty_on_none():
    assert logscan_people.load_people_cache(None) == {}


def test_load_people_cache_returns_empty_on_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json {")
    assert logscan_people.load_people_cache(bad) == {}


def test_save_then_load_people_cache_roundtrip(tmp_path):
    path = tmp_path / "cache.json"
    payload = {"url": "https://x", "content": "hi", "etag": "abc"}
    logscan_people.save_people_cache(path, payload)
    loaded = logscan_people.load_people_cache(path)
    assert loaded == payload


def test_save_people_cache_with_none_path_is_a_noop():
    # Should not raise; nothing to assert other than \"does not crash\".
    logscan_people.save_people_cache(None, {"x": 1})


# ---------------------------------------------------------------------------
# build_people_index
# ---------------------------------------------------------------------------


def test_build_people_index_extracts_lowercased_names():
    readme = """
    Some preamble.
    ![image](https://x/people/Pamela%20Anderson.jpg)
    ![other](https://x/people/Bob_Marley.png)
    not an image link: https://x/people/file.gif
    """
    index = logscan_people.build_people_index(readme)
    # Note: extract_filename_from_url does NOT url-decode the regex output
    # because the regex captures the raw URL substring. Match the actual
    # behavior: the regex picks up the raw \"Pamela%20Anderson\" filename.
    assert "pamela anderson" in index
    assert "bob_marley" in index


def test_build_people_index_returns_empty_on_blank_input():
    assert logscan_people.build_people_index("") == set()
    assert logscan_people.build_people_index(None) == set()


# ---------------------------------------------------------------------------
# is_blank_log_line / is_divider_log_line / is_section_break
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, expected",
    [
        ("", True),
        ("   ", True),
        ("\t\n", True),
        ("non-blank", False),
    ],
)
def test_is_blank_log_line(line, expected):
    assert logscan_people.is_blank_log_line(line) is expected


@pytest.mark.parametrize(
    "line, expected",
    [
        ("========", True),
        ("============", True),
        ("= = = = = = = =", True),
        ("=", False),  # too short (compact length < 8)
        ("=======", False),  # 7 chars, just under the threshold
        ("==!==!==", False),  # mixed chars
        ("", False),
        ("real text", False),
    ],
)
def test_is_divider_log_line(line, expected):
    assert logscan_people.is_divider_log_line(line) is expected


def test_is_section_break_combines_blank_and_divider():
    assert logscan_people.is_section_break("")
    assert logscan_people.is_section_break("============")
    assert not logscan_people.is_section_break("Validating Foo Attributes")


# ---------------------------------------------------------------------------
# matches_any_pattern
# ---------------------------------------------------------------------------


def test_matches_any_pattern_returns_true_on_first_hit():
    patterns = (r"^foo", r"^bar")
    assert logscan_people.matches_any_pattern("bar baz", patterns)


def test_matches_any_pattern_returns_false_on_no_hit():
    patterns = (r"^foo", r"^bar")
    assert not logscan_people.matches_any_pattern("baz", patterns)


# ---------------------------------------------------------------------------
# normalize_name_line
# ---------------------------------------------------------------------------


def test_normalize_name_line_strips_dividers_and_whitespace():
    assert logscan_people.normalize_name_line("==  Foo Bar  ==") == "Foo Bar"
    assert logscan_people.normalize_name_line("") == ""
    assert logscan_people.normalize_name_line(None) == ""


# ---------------------------------------------------------------------------
# extract_key_name_from_block
# ---------------------------------------------------------------------------


def test_extract_key_name_prefers_validating_method_key_name():
    block = [
        "Some unrelated line",
        "Validating Method: key_name",
        "Value: Pamela Anderson",
        "more noise",
    ]
    assert logscan_people.extract_key_name_from_block(block, 0, len(block) - 1) == "Pamela Anderson"


def test_extract_key_name_falls_back_to_collection_pattern():
    block = [
        "noise",
        "Running Tom Hanks Collection",
        "more",
    ]
    assert logscan_people.extract_key_name_from_block(block, 0, len(block) - 1) == "Tom Hanks"


def test_extract_key_name_returns_none_when_no_match():
    block = ["nothing", "useful", "here"]
    assert logscan_people.extract_key_name_from_block(block, 0, len(block) - 1) is None


# ---------------------------------------------------------------------------
# extract_missing_people_names
# ---------------------------------------------------------------------------


def test_extract_missing_people_names_basic():
    lines = [
        "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/P/Pamela%20Anderson.jpg",
        "unrelated line",
    ]
    names = logscan_people.extract_missing_people_names(lines, available=set())
    assert names == {"pamela anderson"}


def test_extract_missing_people_names_respects_available():
    lines = [
        "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/P/Pamela%20Anderson.jpg",
    ]
    # If the name is already in the available index, it is NOT considered missing.
    names = logscan_people.extract_missing_people_names(lines, available={"pamela anderson"})
    assert names == set()


def test_extract_missing_people_names_uses_name_hint_when_provided():
    lines = [
        "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/P/some-random-filename.jpg",
    ]
    names = logscan_people.extract_missing_people_names(lines, available=set(), name_hint="Tom Hanks")
    # Hint overrides the URL-derived name; it gets lowercased.
    assert names == {"tom hanks"}


def test_extract_missing_people_names_ignores_unrelated_warnings():
    lines = [
        "Collection Warning: No Poster Found at https://example.com/not-people/foo.jpg",
        "Some other line",
    ]
    assert logscan_people.extract_missing_people_names(lines, available=set()) == set()


# ---------------------------------------------------------------------------
# collect_missing_people_lines (integration)
# ---------------------------------------------------------------------------


def test_collect_missing_people_lines_handles_empty_input():
    assert logscan_people.collect_missing_people_lines("") == []


def test_collect_missing_people_lines_returns_block_per_match():
    content = "\n".join(
        [
            "Running Pamela Anderson Collection",
            "stuff",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/P/Pamela%20Anderson.jpg",
            "Finished Pamela Anderson Collection",
        ]
    )
    items = logscan_people.collect_missing_people_lines(content, available_index=set())
    assert len(items) == 1
    assert "pamela anderson" in items[0]["names"]
    assert "Pamela Anderson Collection" in items[0]["block"]


def test_collect_missing_people_lines_dedupes_identical_blocks():
    # Same exact block appearing twice should only produce one entry.
    block = "\n".join(
        [
            "Running Pamela Anderson Collection",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/P/Pamela%20Anderson.jpg",
            "Finished Pamela Anderson Collection",
        ]
    )
    content = block + "\n" + block
    items = logscan_people.collect_missing_people_lines(content, available_index=set())
    # Both occurrences map to identical blocks => dedupe.
    assert len(items) == 1


def test_collect_missing_people_lines_invokes_cleanup_fn():
    # When a cleanup_fn is provided, it should be called with the content.
    cleanup = MagicMock(
        return_value="\n".join(
            [
                "Running Bob Collection",
                "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/B/Bob.jpg",
                "Finished Bob Collection",
            ]
        )
    )
    content = "\n".join(
        [
            "Running Bob Collection",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images/master/B/Bob.jpg",
            "Finished Bob Collection",
        ]
    )
    items = logscan_people.collect_missing_people_lines(content, available_index=set(), cleanup_fn=cleanup)
    cleanup.assert_called_once_with(content)
    assert len(items) == 1


# ---------------------------------------------------------------------------
# fetch_people_readme (network mocked)
# ---------------------------------------------------------------------------


def _mock_response(status_code, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    return resp


def test_fetch_people_readme_uses_cache_on_304(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "url": logscan_people.PEOPLE_README_URLS[0],
                "content": "cached body",
                "etag": "etag-1",
            }
        )
    )
    with patch("modules.logscan_people.requests.get", return_value=_mock_response(304)):
        text, used_cache = logscan_people.fetch_people_readme(cache_path)
    assert text == "cached body"
    assert used_cache is True


def test_fetch_people_readme_writes_cache_on_200(tmp_path):
    cache_path = tmp_path / "cache.json"
    fresh = _mock_response(200, "fresh body", {"ETag": "etag-2"})
    with patch("modules.logscan_people.requests.get", return_value=fresh):
        text, used_cache = logscan_people.fetch_people_readme(cache_path)
    assert text == "fresh body"
    assert used_cache is False
    # Verify the cache file got written with the fresh payload.
    written = json.loads(cache_path.read_text())
    assert written["content"] == "fresh body"
    assert written["etag"] == "etag-2"


def test_fetch_people_readme_falls_back_to_cache_on_network_error(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "url": logscan_people.PEOPLE_README_URLS[0],
                "content": "stale body",
            }
        )
    )
    with patch("modules.logscan_people.requests.get", side_effect=ConnectionError("offline")):
        text, used_cache = logscan_people.fetch_people_readme(cache_path)
    assert text == "stale body"
    assert used_cache is True


def test_fetch_people_readme_returns_none_when_no_cache_and_network_dead(tmp_path):
    cache_path = tmp_path / "nothing.json"
    with patch("modules.logscan_people.requests.get", side_effect=ConnectionError("offline")):
        text, used_cache = logscan_people.fetch_people_readme(cache_path)
    assert text is None
    assert used_cache is False
