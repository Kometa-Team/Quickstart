"""Tests for the extracted ``modules.logscan_command`` helpers."""

import hashlib
from pathlib import Path

from modules import logscan_command

# ---------------------------------------------------------------------------
# extract_plex_config_section
# ---------------------------------------------------------------------------


def test_extract_plex_config_section_stops_at_end_marker():
    # Note: end markers are matched after .strip(), so leading-space markers
    # like " Scanning " only work when the log line itself has additional
    # content past the strip. We use "Library Connection Failed" here because
    # it survives stripping intact.
    lines = [
        "Connected to server MyPlex version 1.40.0.7998-c29d4c0c8",
        "Some other line",
        "Library Connection Failed: thing",  # end marker
        "should not appear",
    ]
    result = logscan_command.extract_plex_config_section(lines, 0, ("Library Connection Failed",))
    assert "Connected to server MyPlex" in result
    assert "Some other line" in result
    assert "should not appear" not in result


def test_extract_plex_config_section_skips_blank_lines():
    lines = ["alpha", "", "   ", "beta"]
    result = logscan_command.extract_plex_config_section(lines, 0, ("nope",))
    assert result == "alpha\nbeta"


def test_extract_plex_config_section_returns_none_when_empty():
    assert logscan_command.extract_plex_config_section([], 0, ("x",)) is None


def test_extract_plex_config_section_strips_traceback_middle():
    lines = [
        "header line",
        "Traceback (most recent call last):",
        "  File noisy",
        "  more noise",
        "still noise",
        "keep1",
        "final-1",
        "final",
    ]
    result = logscan_command.extract_plex_config_section(lines, 0, ("nope",))
    # Keeps everything up through the traceback marker, plus the LAST line
    # ("final"). Lines in between are dropped to suppress traceback noise
    # while preserving the closing context.
    assert "header line" in result
    assert "Traceback" in result
    assert "noisy" not in result
    assert "still noise" not in result
    assert "keep1" not in result
    assert "final-1" not in result
    assert result.endswith("final")


# ---------------------------------------------------------------------------
# parse_server_info
# ---------------------------------------------------------------------------


def test_parse_server_info_extracts_name_and_version():
    section = "Connected to server MyPlex version 1.40.3.8555-fef15d30c"
    info, lines = logscan_command.parse_server_info(section)
    assert info == {"server_name": "MyPlex", "version": "1.40.3.8555-fef15d30c"}
    assert lines == [section]


def test_parse_server_info_returns_empty_when_no_match():
    info, lines = logscan_command.parse_server_info("nothing to see here")
    assert info == {}
    assert lines == ["nothing to see here"]


# ---------------------------------------------------------------------------
# extract_plex_config (integration of the two above)
# ---------------------------------------------------------------------------


def test_extract_plex_config_collects_flagged_versions_only():
    # Use "Library Connection Failed" as the end marker so test sections
    # actually terminate (the production " Scanning " marker has a known
    # quirk where it can be eaten by .strip() on short lines).
    content = "\n".join(
        [
            "Plex Configuration",
            "Connected to server A version 1.40.2.0000-aaaabbbb",  # in flagged range
            "Library Connection Failed: stop here",
            "noise",
            "Plex Configuration",
            "Connected to server B version 1.40.3.8555-fef15d30c",  # NOT flagged (>= good)
            "Library Connection Failed: stop here",
        ]
    )
    result = logscan_command.extract_plex_config(content)
    assert result["plex_config_content"] is not None
    assert len(result["plex_config_content"]) == 2
    # Only the middle-range server should be in server_versions.
    assert result["server_versions"] == [("A", "1.40.2.0000-aaaabbbb")]


def test_extract_plex_config_returns_none_content_when_absent():
    result = logscan_command.extract_plex_config("nothing relevant")
    assert result == {"plex_config_content": None, "server_versions": []}


# ---------------------------------------------------------------------------
# extract_header_lines
# ---------------------------------------------------------------------------


def test_extract_header_lines_captures_versions_and_strips_redacted():
    content = "\n".join(
        [
            "preamble",
            "Version: 1.20.0",
            "Newest Version: 1.21.0",
            "Run Command: kometa --config=/tmp/test_config.yml (redacted)",
            "stuff after",
        ]
    )
    header, current, newest = logscan_command.extract_header_lines(content)
    assert current == "1.20.0"
    assert newest == "1.21.0"
    assert "(redacted)" not in header
    assert "Run Command:" in header
    assert "stuff after" not in header


def test_extract_header_lines_handles_missing_newest_version():
    content = "Version: 1.20.0\nRun Command: kometa"
    header, current, newest = logscan_command.extract_header_lines(content)
    assert current == "1.20.0"
    assert newest is None
    assert header.endswith("Run Command: kometa")


def test_extract_header_lines_no_version_returns_none_versions():
    header, current, newest = logscan_command.extract_header_lines("")
    assert header == ""
    assert current is None
    assert newest is None


# ---------------------------------------------------------------------------
# extract_run_command / split_command
# ---------------------------------------------------------------------------


def test_extract_run_command_returns_first_match():
    content = "noise\nRun Command: kometa --run\nRun Command: should-not-win"
    assert logscan_command.extract_run_command(content) == "kometa --run"


def test_extract_run_command_returns_none_on_empty_input():
    assert logscan_command.extract_run_command("") is None
    assert logscan_command.extract_run_command(None) is None


def test_split_command_returns_empty_list_for_empty_input():
    assert logscan_command.split_command("") == []
    assert logscan_command.split_command(None) == []


def test_split_command_uses_shlex_for_normal_commands():
    assert logscan_command.split_command("kometa --config=/tmp/x.yml --run") == [
        "kometa",
        "--config=/tmp/x.yml",
        "--run",
    ]


# ---------------------------------------------------------------------------
# compute_command_signature
# ---------------------------------------------------------------------------


def test_compute_command_signature_keeps_only_flags():
    sig = logscan_command.compute_command_signature("kometa --config=/x --run -v")
    assert sig == "--config --run -v"


def test_compute_command_signature_returns_none_for_empty():
    assert logscan_command.compute_command_signature("") is None
    assert logscan_command.compute_command_signature(None) is None


# ---------------------------------------------------------------------------
# extract_config_path_from_command
# ---------------------------------------------------------------------------


def test_extract_config_path_equals_syntax():
    assert logscan_command.extract_config_path_from_command("kometa --config=/tmp/foo.yml --run") == "/tmp/foo.yml"


def test_extract_config_path_space_syntax():
    assert logscan_command.extract_config_path_from_command("kometa --config /tmp/foo.yml --run") == "/tmp/foo.yml"


def test_extract_config_path_quoted_value_without_spaces():
    # Quoted values without internal spaces still get their quotes stripped.
    assert logscan_command.extract_config_path_from_command('kometa --config="/tmp/foo.yml"') == "/tmp/foo.yml"
    # Known limitation: shlex with posix=False does not honor quoted values
    # that contain spaces. This documents the current behavior rather than
    # endorses it.
    assert logscan_command.extract_config_path_from_command('kometa --config="/tmp/foo bar.yml"') == "/tmp/foo"


def test_extract_config_path_returns_none_when_absent():
    assert logscan_command.extract_config_path_from_command("kometa --run") is None
    assert logscan_command.extract_config_path_from_command("") is None
    assert logscan_command.extract_config_path_from_command(None) is None


# ---------------------------------------------------------------------------
# derive_config_name_from_path
# ---------------------------------------------------------------------------


def test_derive_config_name_strips_config_suffix():
    assert logscan_command.derive_config_name_from_path("/tmp/movies_config.yml") == "movies"


def test_derive_config_name_without_suffix():
    assert logscan_command.derive_config_name_from_path("/tmp/movies.yml") == "movies"


def test_derive_config_name_handles_path_objects():
    assert logscan_command.derive_config_name_from_path(Path("/tmp/shows_config.yml")) == "shows"


# ---------------------------------------------------------------------------
# sanitize_run_command
# ---------------------------------------------------------------------------


def test_sanitize_run_command_replaces_config_path():
    cleaned = logscan_command.sanitize_run_command("kometa --config=/etc/secrets/mine.yml --run", config_path="/etc/secrets/mine.yml")
    assert "/etc/secrets/mine.yml" not in cleaned
    assert "<config>" in cleaned


def test_sanitize_run_command_redacts_secret_flags():
    cleaned = logscan_command.sanitize_run_command("kometa --apikey=ABCDEF1234567 --run")
    assert "ABCDEF1234567" not in cleaned
    assert "<redacted>" in cleaned


def test_sanitize_run_command_replaces_path_with_alt_separators():
    cleaned = logscan_command.sanitize_run_command("kometa --config C:\\Users\\test\\config.yml", config_path="C:/Users/test/config.yml")
    assert "config.yml" not in cleaned
    assert "<config>" in cleaned


def test_sanitize_run_command_returns_none_for_empty():
    assert logscan_command.sanitize_run_command("") is None
    assert logscan_command.sanitize_run_command(None) is None


# ---------------------------------------------------------------------------
# hash_file
# ---------------------------------------------------------------------------


def test_hash_file_returns_sha256_hex_digest(tmp_path):
    payload = b"hello logscan world"
    target = tmp_path / "sample.txt"
    target.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert logscan_command.hash_file(target) == expected


def test_hash_file_handles_missing_paths():
    assert logscan_command.hash_file(None) is None
    assert logscan_command.hash_file("") is None
    assert logscan_command.hash_file("/definitely/not/a/real/path.xyz") is None


def test_hash_file_accepts_string_paths(tmp_path):
    target = tmp_path / "another.txt"
    target.write_text("data")
    assert isinstance(logscan_command.hash_file(str(target)), str)
