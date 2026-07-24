import time

from modules import process_maintenance


class _FakeProc:
    def __init__(self, pid, cmdline):
        self.pid = pid
        self._cmdline = cmdline

    def cmdline(self):
        return self._cmdline


class _FakeAlive:
    def __init__(self, pid):
        self.pid = pid


def _reset_maintenance_state(qs_module):
    with qs_module.MAINTENANCE_STATE_LOCK:
        qs_module.MAINTENANCE_STATE.update(
            {
                "paused": False,
                "paused_since": None,
                "imagemaid_paused": False,
                "imagemaid_paused_since": None,
                "active": False,
                "window": None,
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
            }
        )


def test_maintenance_window_db_lookup_skips_request_settings_outside_request(monkeypatch):
    calls = {"legacy": 0}

    def fake_retrieve_section_data(name, section):
        assert name == "bad_plex_cfg"
        assert section == "plex_telemetry"
        return False, True, {"plex_telemetry": {}}

    def fail_legacy_lookup(section):
        calls["legacy"] += 1
        raise RuntimeError("Working outside of request context.")

    monkeypatch.setattr(process_maintenance.database, "retrieve_section_data", fake_retrieve_section_data)
    monkeypatch.setattr(process_maintenance.persistence, "retrieve_settings", fail_legacy_lookup)

    assert process_maintenance.get_maintenance_window_from_db("bad_plex_cfg") == (None, None, None)
    assert calls["legacy"] == 0


def test_maintenance_live_lookup_skips_unvalidated_plex_credentials(monkeypatch):
    calls = {"plex": 0}

    def fake_retrieve_section_data(name, section):
        assert name == "bad_plex_cfg"
        assert section == "plex"
        return False, True, {"plex": {"url": "http://192.168.2.242:32400", "token": "bad"}}

    def fail_live_lookup(*_args, **_kwargs):
        calls["plex"] += 1
        raise AssertionError("invalid Plex credentials should not be polled by maintenance refresh")

    monkeypatch.setattr(process_maintenance.database, "retrieve_section_data", fake_retrieve_section_data)
    monkeypatch.setattr(process_maintenance.helpers, "get_plex_maintenance_hours", fail_live_lookup)

    assert process_maintenance.get_plex_credentials_from_db("bad_plex_cfg") == (None, None)
    assert process_maintenance.get_maintenance_window_live("bad_plex_cfg") == (None, None, None)
    assert calls["plex"] == 0


def test_stop_kometa_non_kometa_pid_warning(tmp_path, client, monkeypatch, qs_module):
    pid_file = tmp_path / "kometa.pid"
    pid_file.write_text("1234")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module, "_find_running_kometa_processes", lambda: [_FakeProc(1234, ["python", "other.py"])])

    resp = client.post("/stop-kometa")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "warning" in data
    assert not pid_file.exists()


def test_stop_kometa_warns_if_processes_still_alive(tmp_path, client, monkeypatch, qs_module):
    pid_file = tmp_path / "kometa.pid"
    pid_file.write_text("2222")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module, "_find_running_kometa_processes", lambda: [_FakeProc(2222, ["python", "kometa.py"])])
    monkeypatch.setattr(qs_module, "_stop_process_tree", lambda *_: [_FakeAlive(9999)])

    resp = client.post("/stop-kometa")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "warning" in data
    assert not pid_file.exists()


def test_maintenance_guard_starts_queued_run(monkeypatch, qs_module):
    _reset_maintenance_state(qs_module)
    qs_module._clear_pending_kometa_start()

    qs_module._set_pending_kometa_start("python kometa.py", "ConfigName")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)

    called = {"count": 0}

    def fake_launch(command, config_name, start_mode="current"):
        called["count"] += 1
        assert start_mode == "current"
        return True, 7777

    monkeypatch.setattr(qs_module, "_launch_kometa_command", fake_launch)

    ticks = {"count": 0}

    def fake_sleep(_):
        ticks["count"] += 1
        if ticks["count"] > 1:
            raise StopIteration()
        return None

    monkeypatch.setattr(qs_module.time, "sleep", fake_sleep)

    try:
        qs_module._maintenance_guard_loop(qs_module.app)
    except StopIteration:
        pass

    assert called["count"] == 1
    assert qs_module._peek_pending_kometa_start() is None
    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["queued_started_at"] is not None


def test_maintenance_guard_pauses_running_imagemaid(monkeypatch, qs_module, tmp_path):
    _reset_maintenance_state(qs_module)

    imagemaid_log = tmp_path / "imagemaid.log"
    imagemaid_log.write_text("ImageMaid running\n", encoding="utf-8")

    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: 5555)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: True)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: tmp_path)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module, "_get_latest_imagemaid_log_path", lambda: imagemaid_log)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (120, 300, "02:00-05:00"))
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda: (120, 300, "02:00-05:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: True)
    monkeypatch.setattr(qs_module, "_get_imagemaid_run_context", lambda: {"mode": "report", "config_name": "demo"})

    class _FakePsutilProc:
        pid = 5555

    monkeypatch.setattr(qs_module.psutil, "Process", lambda pid: _FakePsutilProc())

    calls = {"suspend": 0, "marker": 0}

    monkeypatch.setattr(qs_module, "_suspend_process_tree", lambda proc: calls.__setitem__("suspend", calls["suspend"] + 1) or True)

    def fake_marker(root, event, **kwargs):
        calls["marker"] += 1
        assert event == "paused"
        assert kwargs["mode"] == "report"
        assert kwargs["config_name"] == "demo"
        assert kwargs["window"] == "02:00-05:00"
        assert kwargs["mirror_to_live_log"] is True
        return True

    monkeypatch.setattr(qs_module, "_write_quickstart_imagemaid_maintenance_marker", fake_marker)

    ticks = {"count": 0}

    def fake_sleep(_):
        ticks["count"] += 1
        if ticks["count"] > 1:
            raise StopIteration()

    monkeypatch.setattr(qs_module.time, "sleep", fake_sleep)

    try:
        qs_module._maintenance_guard_loop(qs_module.app)
    except StopIteration:
        pass

    assert calls["suspend"] == 1
    assert calls["marker"] == 1
    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["imagemaid_paused"] is True
        assert qs_module.MAINTENANCE_STATE["imagemaid_paused_since"] is not None


def test_refresh_maintenance_window_availability_prefers_active_imagemaid_config(monkeypatch, qs_module):
    _reset_maintenance_state(qs_module)

    seen = {"config_name": None}

    monkeypatch.setattr(qs_module, "_get_run_context", lambda: {})
    monkeypatch.setattr(qs_module, "_get_imagemaid_run_context", lambda: {"config_name": "imagemaid_cfg"})
    monkeypatch.setattr(qs_module, "_peek_pending_kometa_start", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: 5555)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: True)

    def fake_live(config_name=None):
        seen["config_name"] = config_name
        return 120, 300, "02:00 – 05:00"

    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", fake_live)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda config_name=None: (None, None, None))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)

    qs_module._refresh_maintenance_window_availability()

    assert seen["config_name"] == "imagemaid_cfg"
    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["window"] == "02:00 – 05:00"
        assert qs_module.MAINTENANCE_STATE["window_unavailable"] is False


def test_refresh_maintenance_window_availability_ignores_stale_kometa_context(monkeypatch, qs_module):
    _reset_maintenance_state(qs_module)

    seen = {"config_name": None}

    monkeypatch.setattr(qs_module, "_get_run_context", lambda: {"config_name": "stale_kometa_cfg"})
    monkeypatch.setattr(qs_module, "_get_imagemaid_run_context", lambda: {"config_name": "imagemaid_cfg"})
    monkeypatch.setattr(qs_module, "_peek_pending_kometa_start", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: 5555)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: True)

    def fake_live(config_name=None):
        seen["config_name"] = config_name
        return 120, 300, "02:00 – 05:00"

    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", fake_live)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda config_name=None: (None, None, None))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)

    qs_module._refresh_maintenance_window_availability()

    assert seen["config_name"] == "imagemaid_cfg"
    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["window"] == "02:00 – 05:00"
        assert qs_module.MAINTENANCE_STATE["window_unavailable"] is False


def test_maintenance_guard_resumes_paused_imagemaid(monkeypatch, qs_module, tmp_path):
    _reset_maintenance_state(qs_module)
    paused_at = time.time() - 90
    with qs_module.MAINTENANCE_STATE_LOCK:
        qs_module.MAINTENANCE_STATE["imagemaid_paused"] = True
        qs_module.MAINTENANCE_STATE["imagemaid_paused_since"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(paused_at))

    imagemaid_log = tmp_path / "imagemaid.log"
    imagemaid_log.write_text("ImageMaid paused\n", encoding="utf-8")

    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: 5555)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: True)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: tmp_path)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module, "_get_latest_imagemaid_log_path", lambda: imagemaid_log)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (120, 300, "02:00-05:00"))
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda: (120, 300, "02:00-05:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)
    monkeypatch.setattr(qs_module, "_get_imagemaid_run_context", lambda: {"mode": "move", "config_name": "demo"})

    class _FakePsutilProc:
        pid = 5555

    monkeypatch.setattr(qs_module.psutil, "Process", lambda pid: _FakePsutilProc())
    monkeypatch.setattr(qs_module, "_resume_process_tree", lambda proc: True)

    calls = {"marker": 0}

    def fake_marker(root, event, **kwargs):
        calls["marker"] += 1
        assert event == "resumed"
        assert kwargs["mode"] == "move"
        assert kwargs["config_name"] == "demo"
        assert kwargs["window"] == "02:00-05:00"
        assert isinstance(kwargs["paused_seconds"], int)
        assert kwargs["paused_seconds"] >= 60
        assert kwargs["mirror_to_live_log"] is True
        return True

    monkeypatch.setattr(qs_module, "_write_quickstart_imagemaid_maintenance_marker", fake_marker)

    ticks = {"count": 0}

    def fake_sleep(_):
        ticks["count"] += 1
        if ticks["count"] > 1:
            raise StopIteration()

    monkeypatch.setattr(qs_module.time, "sleep", fake_sleep)

    try:
        qs_module._maintenance_guard_loop(qs_module.app)
    except StopIteration:
        pass

    assert calls["marker"] == 1
    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["imagemaid_paused"] is False
        assert qs_module.MAINTENANCE_STATE["imagemaid_paused_since"] is None
