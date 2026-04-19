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
