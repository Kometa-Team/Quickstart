class _FakeProcDone:
    def __init__(self, pid, cmdline=None):
        self.pid = pid
        self._cmdline = cmdline or ["python", "kometa.py"]
        self._wait_called = False

    def cmdline(self):
        return self._cmdline

    def is_running(self):
        return False

    def status(self):
        return "stopped"

    def wait(self, timeout=0.1):
        self._wait_called = True
        return 0


class _FakeNoSuchProcess(Exception):
    pass


class _FakeProcAlive:
    def __init__(self, pid):
        self.pid = pid

    def cmdline(self):
        return ["python", "kometa.py"]

    def is_running(self):
        return True

    def status(self):
        return "running"


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


def test_maintenance_window_unavailable_state(monkeypatch, qs_module):
    _reset_maintenance_state(qs_module)
    qs_module._clear_pending_kometa_start()

    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (None, None, None))
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda: (None, None, None))
    qs_module._set_pending_kometa_start("python kometa.py", None)

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

    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["window_unavailable"] is True
        assert qs_module.MAINTENANCE_STATE["window_unavailable_since"] is not None


def test_kometa_status_done_cleans_pid(tmp_path, client, monkeypatch, qs_module):
    pid_file = tmp_path / "kometa.pid"
    pid_file.write_text("9999")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: 9999)
    monkeypatch.setattr(qs_module.psutil, "Process", lambda pid: _FakeProcDone(pid))

    resp = client.get("/kometa-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "done"
    assert data["return_code"] == 0
    assert not pid_file.exists()


def test_kometa_status_no_such_process_cleans_pid(tmp_path, client, monkeypatch, qs_module):
    pid_file = tmp_path / "kometa.pid"
    pid_file.write_text("8888")
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: 8888)

    def raise_no_such_process(_pid):
        raise qs_module.psutil.NoSuchProcess(_pid)

    monkeypatch.setattr(qs_module.psutil, "Process", raise_no_such_process)

    resp = client.get("/kometa-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "not started"
    assert not pid_file.exists()
