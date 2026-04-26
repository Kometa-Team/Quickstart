import time


class _FakeMem:
    def __init__(self, rss):
        self.rss = rss


class _FakeCpuTimes:
    def __init__(self, user=0.1, system=0.1):
        self.user = user
        self.system = system


class _FakePsutilProc:
    def __init__(self, pid, cmdline=None, started_at=None):
        self.pid = pid
        self._cmdline = cmdline or ["python", "kometa.py"]
        self._started_at = started_at or (time.time() - 5)

    def create_time(self):
        return self._started_at

    def cmdline(self):
        return self._cmdline

    def is_running(self):
        return True

    def status(self):
        return "running"

    def children(self, recursive=True):
        return []

    def memory_info(self):
        return _FakeMem(50 * 1024 * 1024)

    def cpu_times(self):
        return _FakeCpuTimes()


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


def test_start_kometa_already_running(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: True)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: 1111)
    monkeypatch.setattr(qs_module.psutil, "Process", lambda pid: _FakePsutilProc(pid))

    resp = client.post("/start-kometa", json={"command": "python kometa.py"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "running"
    assert data["pid"] == 1111


def test_kometa_status_reconnects_pid_file(tmp_path, client, monkeypatch, qs_module):
    pid_file = tmp_path / "kometa.pid"
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: _FakePsutilProc(2222))
    monkeypatch.setattr(qs_module.psutil, "Process", lambda pid: _FakePsutilProc(pid))

    resp = client.get("/kometa-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "running"
    assert data["pid"] == 2222
    assert pid_file.exists()
    assert pid_file.read_text().strip() == "2222"


def test_maintenance_guard_pause_and_resume(tmp_path, monkeypatch, qs_module):
    _reset_maintenance_state(qs_module)
    qs_module._clear_pending_kometa_start()

    active_flag = {"value": True}
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: 3333)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: True)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_get_maintenance_window_from_db", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: active_flag["value"])
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: tmp_path)
    monkeypatch.setattr(qs_module.psutil, "Process", lambda pid: _FakePsutilProc(pid))
    monkeypatch.setattr(qs_module, "_suspend_process_tree", lambda *_: True)
    monkeypatch.setattr(qs_module, "_resume_process_tree", lambda *_: True)

    calls = {"count": 0}

    def fake_sleep(_):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        if calls["count"] == 2:
            active_flag["value"] = False
            return None
        raise StopIteration()

    monkeypatch.setattr(qs_module.time, "sleep", fake_sleep)

    try:
        qs_module._maintenance_guard_loop(qs_module.app)
    except StopIteration:
        pass

    with qs_module.MAINTENANCE_STATE_LOCK:
        assert qs_module.MAINTENANCE_STATE["active"] is False
        assert qs_module.MAINTENANCE_STATE["paused"] is False
        assert qs_module.MAINTENANCE_STATE["paused_since"] is None
        assert qs_module.MAINTENANCE_STATE["window"] == "01:00-02:00"

    meta_log = tmp_path / "config" / "logs" / "meta.log"
    assert meta_log.exists()
    marker_lines = meta_log.read_text(encoding="utf-8").splitlines()
    assert any("[Quickstart] Maintenance marker: event=paused" in line for line in marker_lines)
    assert any("[Quickstart] Maintenance marker: event=resumed" in line for line in marker_lines)
