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


def test_library_runtime_does_not_become_finished_run_total():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-22 06:50:18,000] [metadata.py:100] [INFO] |                                      Finished Movies                                      |",
            "[2026-04-22 06:50:20,000] [metadata.py:100] [INFO] |                                      Run Time: 0:00:02                                     |",
        ]
    )

    analyzer.extract_last_lines(content)

    assert analyzer.run_time is None


def test_extract_progress_playlist_runtime_from_continuation_line():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-18 10:00:00,000] [kometa.py:803] [INFO] |                                            Playlists                                             |",
            "[2026-04-18 10:00:01,000] [kometa.py:1226] [INFO] |                               Finished Demo Playlist                                |",
            "Playlist Run Time: 0:00:05",
            "[2026-04-18 10:00:02,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
        ]
    )

    progress = analyzer.extract_progress(content, library_list=[{"name": "Movies", "type": "movie"}])
    assert progress.get("playlist_total_seconds") == 5
    assert progress.get("playlists_detected") is True


def test_extract_progress_playlist_runtime_when_logged_from_playlists_module():
    analyzer = LogscanAnalyzer()
    content = "\n".join(
        [
            "[2026-04-18 10:00:00,000] [playlists.py:100] [INFO] |                                            Playlists                                             |",
            "[2026-04-18 10:00:01,000] [playlists.py:222] [INFO] |                               Finished Demo Playlist                                |",
            "[2026-04-18 10:00:01,000] [playlists.py:222] [INFO] |                                    Playlist Run Time: 0:00:07                                    |",
            "[2026-04-18 10:00:02,000] [kometa.py:522] [INFO] |                                            Finished Run                                            |",
        ]
    )

    progress = analyzer.extract_progress(content, library_list=[{"name": "Movies", "type": "movie"}])
    assert progress.get("playlist_total_seconds") == 7
    assert progress.get("playlists_detected") is True
