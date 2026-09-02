from unittest.mock import patch

from modules.logscan import LogscanAnalyzer, PEOPLE_MISSING_WARNING_RE


def test_people_warning_regex_matches_signature_repo():
    line = "Collection Warning: No Poster Found at " "https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/P/Images/Pamela%20Anderson.jpg"
    assert PEOPLE_MISSING_WARNING_RE.search(line)


def test_extract_missing_people_names_from_signature_repo_warning():
    analyzer = LogscanAnalyzer()
    line = (
        "[2026-04-13 13:19:15,251] [builder.py:1725] [WARNING]  | Collection Warning: No Poster Found at "
        "https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/P/Images/Pamela%20Anderson.jpg |"
    )
    names = analyzer._extract_missing_people_names([line], available=set(), name_hint=None)
    assert names == {"pamela anderson"}


def test_collect_missing_people_lines_with_signature_repo_warning():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-13 13:19:14,900] [builder.py:1495] [DEBUG] | Validating Method: key_name |",
            "[2026-04-13 13:19:14,901] [builder.py:1496] [DEBUG] | Value: Pamela Anderson |",
            "[2026-04-13 13:19:15,251] [builder.py:1725] [WARNING] | Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/P/Images/Pamela%20Anderson.jpg |",
            "[2026-04-13 13:19:15,252] [builder.py:1496] [DEBUG] | Value: hide |",
        ]
    )
    items = analyzer.collect_missing_people_lines(content, available_index=set(), max_block_lines=30)
    assert items
    assert "pamela anderson" in items[0].get("names", set())


def test_scan_uses_styled_people_poster_index_for_signature_warnings(tmp_path):
    readme = """
    [Alex Rudzinski](https://raw.githubusercontent.com/Kometa-Team/People-Images-bw/master/A/Images/Alex%20Rudzinski.jpg)
    """
    content = "\n".join(
        [
            "Running Alex Rudzinski (Director) Collection",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/A/Images/Alex%20Rudzinski.jpg",
            "Finished Alex Rudzinski (Director) Collection",
            "Running Jon Hurwitz (Director) Collection",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/J/Images/Jon%20Hurwitz.jpg",
            "Finished Jon Hurwitz (Director) Collection",
            "Running Hayden Schlossberg (Director) Collection",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/H/Images/Hayden%20Schlossberg.jpg",
            "Finished Hayden Schlossberg (Director) Collection",
            "Running Kenny Leon (Director) Collection",
            "Collection Warning: No Poster Found at https://raw.githubusercontent.com/Kometa-Team/People-Images-signature/master/K/Images/Kenny%20Leon.jpg",
            "Finished Kenny Leon (Director) Collection",
        ]
    )
    analyzer = LogscanAnalyzer()

    with patch("modules.logscan_people.fetch_people_poster_readme", return_value=(readme, False)):
        names = analyzer.scan_file_for_people_posters(content, log_path=tmp_path / "meta.log")

    assert names == ["hayden schlossberg", "jon hurwitz", "kenny leon"]


def test_collect_missing_people_lines_detects_tmdb_poster_update_candidates():
    content = "\n".join(
        [
            "Running Missing Person (Director) Collection",
            "Metadata: tmdb_person updated poster to [URL] https://image.tmdb.org/t/p/original/example.jpg",
            "Finished Missing Person (Director) Collection",
        ]
    )

    items = LogscanAnalyzer().collect_missing_people_lines(content, available_index=set(), max_block_lines=30)

    assert items
    assert items[0]["names"] == {"missing person"}
