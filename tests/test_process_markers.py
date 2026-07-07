def test_write_quickstart_run_marker_falls_back_to_pending_journal(monkeypatch, tmp_path, qs_module):
    import modules.process_markers as process_markers

    with qs_module.app.app_context():
        monkeypatch.setattr(process_markers, "append_quickstart_meta_log_line", lambda *_args, **_kwargs: False)

        ok = process_markers.write_quickstart_run_marker(tmp_path, config_name="demo", start_mode="current")

    assert ok is True
    pending_path = qs_module._get_kometa_pending_marker_path(tmp_path)
    assert pending_path.exists()
    pending_text = pending_path.read_text(encoding="utf-8")
    assert "[Quickstart] Run marker:" in pending_text
    assert "config=demo" in pending_text


def test_write_quickstart_stop_marker_falls_back_to_pending_journal(monkeypatch, tmp_path):
    import modules.process_markers as process_markers

    monkeypatch.setattr(process_markers, "append_quickstart_meta_log_line", lambda *_args, **_kwargs: False)

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
