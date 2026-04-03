import time


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
                "active": False,
                "window": None,
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
            }
        )


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

    def fake_launch(command, config_name):
        called["count"] += 1
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
