from modules.logscan import LogscanAnalyzer


def test_parse_run_time_with_days():
    analyzer = LogscanAnalyzer()
    delta = analyzer._parse_run_time_from_line("Run Time: 1 day, 2:20:31")
    assert delta is not None
    assert int(delta.total_seconds()) == (1 * 24 * 3600) + (2 * 3600) + (20 * 60) + 31


def test_analyze_content_marks_complete_for_day_runtime():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |====================================================================================================|",
            "[2026-04-14 09:37:06,901] [kometa.py:522]             [INFO]     |                                            Finished Run                                            |",
            "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |   Start Time: 07:16:22 2026-04-13     Finished: 09:36:53 2026-04-14     Run Time: 1 day, 2:20:31   |",
            "[2026-04-14 09:37:06,902] [kometa.py:522]             [INFO]     |====================================================================================================|",
        ]
    )
    result = analyzer.analyze_content(content, include_people_scan=False)
    summary = result.get("summary")
    assert isinstance(summary, dict)
    assert summary.get("run_complete") is True
    assert summary.get("run_time_seconds") == (1 * 24 * 3600) + (2 * 3600) + (20 * 60) + 31
