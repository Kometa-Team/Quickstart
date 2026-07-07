def test_write_quickstart_run_marker_writes_pending_journal_without_touching_meta_log(monkeypatch, tmp_path, qs_module):
    import modules.process_markers as process_markers

    with qs_module.app.app_context():
        monkeypatch.setattr(
            process_markers,
            "append_quickstart_meta_log_line",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("meta.log should not be written during runtime")),
        )

        ok = process_markers.write_quickstart_run_marker(tmp_path, config_name="demo", start_mode="current")

    assert ok is True
    pending_path = qs_module._get_kometa_pending_marker_path(tmp_path)
    assert pending_path.exists()
    pending_text = pending_path.read_text(encoding="utf-8")
    assert "[Quickstart] Run marker:" in pending_text
    assert "config=demo" in pending_text


def test_schedule_quickstart_run_marker_preserves_version_outside_app_context(monkeypatch, tmp_path, qs_module):
    import modules.process_markers as process_markers

    captured = {}

    class FakeThread:
        def __init__(self, target, daemon=False):
            captured["target"] = target
            captured["daemon"] = daemon

        def start(self):
            captured["started"] = True

    monkeypatch.setattr(process_markers.threading, "Thread", FakeThread)
    qs_module.app.config["VERSION_CHECK"] = {"local_version": "0.10.4-build236", "branch": "develop"}

    with qs_module.app.app_context():
        process_markers.schedule_quickstart_run_marker(tmp_path, config_name="demo", start_mode="current")

    assert captured["started"] is True
    assert captured["daemon"] is True
    captured["target"]()

    pending_text = process_markers.get_kometa_pending_marker_path(tmp_path).read_text(encoding="utf-8")
    assert "quickstart=0.10.4-build236" in pending_text
    assert "branch=develop" in pending_text


def test_write_quickstart_stop_marker_writes_pending_journal_without_touching_meta_log(monkeypatch, tmp_path):
    import modules.process_markers as process_markers

    monkeypatch.setattr(
        process_markers,
        "append_quickstart_meta_log_line",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("meta.log should not be written during runtime")),
    )

    ok = process_markers.write_quickstart_stop_marker(tmp_path, config_name="demo", reason="user_stop")

    assert ok is True
    pending_path = process_markers.get_kometa_pending_marker_path(tmp_path)
    assert pending_path.exists()
    pending_text = pending_path.read_text(encoding="utf-8")
    assert "[Quickstart] Run event:" in pending_text
    assert "reason=user_stop" in pending_text


def test_flush_quickstart_pending_markers_falls_back_to_first_quickstart_line(monkeypatch, tmp_path, qs_module):
    log_dir = tmp_path / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    meta_path = log_dir / "meta.log"
    pending_path = log_dir / "meta.quickstart-pending.log"
    meta_path.write_text(
        "\n".join(
            [
                "[Quickstart] Run marker: started=2026-05-05T01:00:00Z config=demo quickstart=1.0.0 branch=develop",
                "[2026-05-05 01:01:00,000] [kometa.py:1] [INFO] | Continue",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    pending_path.write_text(
        "[Quickstart] Maintenance marker: event=paused at=2026-05-05T02:00:00Z local_at=2026-05-05T22:00:00\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    result = qs_module._flush_quickstart_pending_markers(tmp_path, require_process_stopped=True)

    assert result["flushed"] is True
    assert result["anchor"] == "quickstart_line"
    saved_text = meta_path.read_text(encoding="utf-8")
    run_marker_index = saved_text.index("[Quickstart] Run marker:")
    replay_index = saved_text.index("# [Quickstart] Marker replay start")
    continue_index = saved_text.index("[2026-05-05 01:01:00,000]")
    assert run_marker_index < replay_index < continue_index
    assert not pending_path.exists()


def test_flush_quickstart_pending_markers_inserts_after_wrapped_config_marker(monkeypatch, tmp_path, qs_module):
    log_dir = tmp_path / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    meta_path = log_dir / "meta.log"
    pending_path = log_dir / "meta.quickstart-pending.log"
    run_marker_line = (
        "[2026-07-07 16:48:11,436] [config.py:296]             [DEBUG]    | " "# [Quickstart] Run marker: started=2026-07-07T20:48:08.128590+00:00                                |"
    )
    marker_continuation_line = (
        "[2026-07-07 16:48:11,436] [config.py:296]             [DEBUG]    | " "  config=docker_unraid_bullmoose20_prod quickstart=0.10.4-build236 branch=develop                  |"
    )
    warning_line = (
        "[2026-07-07 16:48:12,093] [config.py:625]             [WARNING]  | " "Config Warning: settings sub-attribute auto_sort_hubs not found using None as default              |"
    )
    meta_path.write_text(
        "\n".join([run_marker_line, marker_continuation_line, warning_line]) + "\n",
        encoding="utf-8",
    )
    pending_path.write_text(
        "[Quickstart] Maintenance marker: event=paused at=2026-07-07T20:49:15Z local_at=2026-07-07T16:49:15 window=02:00-19:00\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    result = qs_module._flush_quickstart_pending_markers(tmp_path, require_process_stopped=True)

    assert result["flushed"] is True
    assert result["anchor"] == "config_marker"
    saved_text = meta_path.read_text(encoding="utf-8")
    run_marker_index = saved_text.index("# [Quickstart] Run marker:")
    continuation_index = saved_text.index("config=docker_unraid_bullmoose20_prod")
    replay_index = saved_text.index("# [Quickstart] Marker replay start")
    warning_index = saved_text.index("Config Warning: settings sub-attribute auto_sort_hubs")
    assert run_marker_index < continuation_index < replay_index < warning_index


def test_stamp_quickstart_config_marker_replaces_legacy_prefix(tmp_path):
    import modules.process_markers as process_markers

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "libraries:\n  Movies:\n    metadata_path: []\n\n# Quickstart run marker: started=2026-01-01T00:00:00+00:00 config=demo quickstart=old branch=develop\n",
        encoding="utf-8",
    )

    ok = process_markers.stamp_quickstart_config_marker(config_path, config_name="demo")

    assert ok is True
    saved_text = config_path.read_text(encoding="utf-8")
    assert "# Quickstart run marker:" not in saved_text
    assert "# [Quickstart] Run marker:" in saved_text
