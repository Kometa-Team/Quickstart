def test_start_kometa_queues_during_maintenance(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: True)

    resp = client.post("/start-kometa", json={"command": "python kometa.py"})
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "queued"
    assert data["maintenance_window"] == "01:00-02:00"
    assert qs_module._peek_pending_kometa_start() is not None

    qs_module._clear_pending_kometa_start()


def test_start_kometa_starts_outside_maintenance(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)
    monkeypatch.setattr(qs_module, "_launch_kometa_command", lambda *_: (True, 4321))

    resp = client.post("/start-kometa", json={"command": "python kometa.py"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "Kometa started"
    assert data["pid"] == 4321


def test_start_kometa_blocked_when_kometa_update_running(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(
        qs_module,
        "_get_active_background_job",
        lambda job_type: {"job_id": "job-123", "job_type": job_type, "phase": "extract", "status": "running"} if job_type == "kometa_update" else None,
    )

    resp = client.post("/start-kometa", json={"command": "python kometa.py"})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["status"] == "blocked"
    assert data["blocked_by"] == "kometa_update"
    assert data["job_id"] == "job-123"
    assert data["phase"] == "extract"
    assert "Cannot start Kometa while a Kometa update is running." in data["error"]


def test_start_imagemaid_blocked_when_kometa_running(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: True)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: 9999)

    resp = client.post("/start-imagemaid", json={"plex_path": "C:\\Plex", "mode": "report"})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["status"] == "blocked"
    assert data["blocked_by"] == "kometa_run"
    assert data["pid"] == 9999
    assert "Cannot start ImageMaid while Kometa is running." in data["error"]


def test_start_imagemaid_starts_when_valid(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)
    monkeypatch.setattr(qs_module, "_validate_imagemaid_settings", lambda *_args, **_kwargs: (True, None, None))
    monkeypatch.setattr(qs_module, "_persist_imagemaid_validation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))
    monkeypatch.setattr(qs_module, "_build_imagemaid_command", lambda *_args, **_kwargs: "python imagemaid.py --mode report")
    seen = {}

    def fake_launch(command, mode=None, config_name=None):
        seen["command"] = command
        seen["mode"] = mode
        seen["config_name"] = config_name
        return True, 2468

    monkeypatch.setattr(qs_module, "_launch_imagemaid_command", fake_launch)

    resp = client.post("/start-imagemaid", json={"plex_path": "C:\\Plex", "mode": "report"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ImageMaid started"
    assert data["pid"] == 2468
    assert seen["config_name"]
    assert seen["mode"] == "report"


def test_start_imagemaid_surfaces_immediate_exit(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)
    monkeypatch.setattr(qs_module, "_validate_imagemaid_settings", lambda *_args, **_kwargs: (True, None, None))
    monkeypatch.setattr(qs_module, "_persist_imagemaid_validation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))
    monkeypatch.setattr(qs_module, "_build_imagemaid_command", lambda *_args, **_kwargs: "python imagemaid.py --mode report")
    monkeypatch.setattr(
        qs_module,
        "_launch_imagemaid_command",
        lambda *_args, **_kwargs: (False, "ImageMaid exited immediately with code 2. Review the run log for details."),
    )

    resp = client.post("/start-imagemaid", json={"plex_path": "C:\\Plex", "mode": "report"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "exited immediately" in data["error"]


def test_start_imagemaid_blocked_during_maintenance(client, tmp_path, monkeypatch, qs_module):
    imagemaid_root = tmp_path / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.helpers, "is_imagemaid_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_validate_imagemaid_settings", lambda *_args, **_kwargs: (True, None, None))
    monkeypatch.setattr(qs_module, "_persist_imagemaid_validation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: True)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module, "_get_latest_imagemaid_log_path", lambda: log_dir / "imagemaid.log")

    resp = client.post("/start-imagemaid", json={"plex_path": "C:\\Plex", "mode": "restore"})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["status"] == "maintenance_blocked"
    assert data["maintenance_window"] == "01:00-02:00"
    assert "Plex maintenance window" in data["error"]

    content = (log_dir / "imagemaid.log").read_text(encoding="utf-8")
    assert "[Quickstart] Maintenance marker: event=blocked_start" in content
    assert "config=" in content
    assert "tool=imagemaid" in content
    assert "mode=restore" in content
    assert "window=01:00-02:00" in content


def test_imagemaid_status_reports_starting_during_startup_grace(client, tmp_path, monkeypatch, qs_module):
    pid_file = tmp_path / "imagemaid.pid"
    pid_file.write_text("4321", encoding="utf-8")

    class FakeProc:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return qs_module.time.time() - 2

        def is_running(self):
            return True

        def status(self):
            return qs_module.psutil.STATUS_SLEEPING

        def cmdline(self):
            return []

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: 4321)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: None)
    monkeypatch.setattr(qs_module.psutil, "Process", FakeProc)

    resp = client.get("/imagemaid-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "starting"
    assert data["pid"] == 4321


def test_validate_imagemaid_restore_requires_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "restore",
        "photo_transcoder": False,
    })

    assert ok is False
    assert reason == "missing_restore_dir"
    assert "ImageMaid Restore" in details
    assert str(plex_root / "ImageMaid Restore") in details


def test_validate_imagemaid_clear_requires_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "clear",
        "photo_transcoder": False,
    })

    assert ok is False
    assert reason == "missing_restore_dir"
    assert "ImageMaid Restore" in details
    assert str(plex_root / "ImageMaid Restore") in details


def test_validate_imagemaid_report_rejects_existing_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)
    restore_dir = plex_root / "ImageMaid Restore"
    restore_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "report",
        "photo_transcoder": False,
    })

    assert ok is False
    assert reason == "restore_dir_blocks_mode"
    assert "Report mode is not allowed" in details
    assert str(restore_dir) in details


def test_validate_imagemaid_move_rejects_existing_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)
    restore_dir = plex_root / "ImageMaid Restore"
    restore_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "move",
        "photo_transcoder": False,
    })

    assert ok is False
    assert reason == "restore_dir_blocks_mode"
    assert "Move mode is not allowed" in details
    assert str(restore_dir) in details


def test_validate_imagemaid_remove_rejects_existing_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)
    restore_dir = plex_root / "ImageMaid Restore"
    restore_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "remove",
        "photo_transcoder": False,
    })

    assert ok is False
    assert reason == "restore_dir_blocks_mode"
    assert "Remove mode is not allowed" in details
    assert str(restore_dir) in details


def test_validate_imagemaid_restore_allows_existing_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)
    (plex_root / "ImageMaid Restore").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "restore",
        "photo_transcoder": False,
    })

    assert ok is True
    assert reason is None
    assert details is None


def test_validate_imagemaid_nothing_allows_existing_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)
    (plex_root / "ImageMaid Restore").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "nothing",
        "photo_transcoder": False,
    })

    assert ok is True
    assert reason is None
    assert details is None


def test_validate_imagemaid_clear_allows_existing_restore_dir(tmp_path, monkeypatch, qs_module):
    plex_root = tmp_path / "Plex"
    (plex_root / "Metadata").mkdir(parents=True)
    (plex_root / "Plug-in Support").mkdir(parents=True)
    (plex_root / "ImageMaid Restore").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda *_args, **_kwargs: {"validated": True})
    monkeypatch.setattr(qs_module.persistence, "get_stored_plex_credentials", lambda *_args, **_kwargs: ("http://plex:32400", "token"))

    ok, reason, details = qs_module._validate_imagemaid_settings({
        "plex_path": str(plex_root),
        "mode": "clear",
        "photo_transcoder": False,
    })

    assert ok is True
    assert reason is None
    assert details is None



def test_stop_kometa_no_pid(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_processes", lambda: [])

    resp = client.post("/stop-kometa")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "warning" in data


def test_stop_kometa_writes_stop_marker(tmp_path, client, monkeypatch, qs_module):
    class _FakeProc:
        pid = 2222

        def cmdline(self):
            return ["python", "kometa.py"]

    pid_file = tmp_path / "kometa.pid"
    pid_file.write_text("2222", encoding="utf-8")
    kometa_root = tmp_path / "kometa"
    log_dir = kometa_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: 2222)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module.helpers, "get_kometa_root_path", lambda: kometa_root)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: _FakeProc())
    monkeypatch.setattr(qs_module, "_stop_process_tree", lambda _proc: [])
    qs_module.app.config["VERSION_CHECK"] = {"local_version": "0.9.16-build18", "branch": "develop"}
    with client.session_transaction() as session_state:
        session_state["config_name"] = "bullmoose20_prod9"
    with qs_module.RUN_CONTEXT_LOCK:
        qs_module.RUN_CONTEXT["config_name"] = "bullmoose20_prod9"

    resp = client.post("/stop-kometa")
    assert resp.status_code == 200
    content = (log_dir / "meta.log").read_text(encoding="utf-8")
    assert "[Quickstart] Run event: event=stopped" in content
    assert "tool=kometa" in content
    assert "config=bullmoose20_prod9" in content


def test_imagemaid_page_renders(client):
    resp = client.get("/step/915-imagemaid")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Prepare ImageMaid" in body
    assert "Run ImageMaid" in body


def test_imagemaid_page_restores_persisted_validation_state(client, qs_module):
    config_name = "pytest_imagemaid_validation_restore"
    with client.session_transaction() as session_state:
        session_state["config_name"] = config_name

    qs_module.database.save_section_data(
        name=config_name,
        section="imagemaid",
        validated=True,
        user_entered=True,
        data={
            "imagemaid": {
                "plex_path": "C:\\PlexData",
                "mode": "report",
            },
            "validated_at": "2026-04-29T12:00:00Z",
            "validation_status": "validated",
        },
    )

    resp = client.get("/step/915-imagemaid")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-validated="true"' in body


def test_autosave_imagemaid_persists_settings(client):
    resp = client.post("/autosave-imagemaid", json={
        "plex_path": "C:\\PlexData",
        "mode": "restore",
        "trace": True,
        "photo_transcoder": True,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    import modules.database as database
    with client.session_transaction() as session_state:
        config_name = session_state.get("config_name")
    validated, user_entered, saved = database.retrieve_section_data(config_name, "imagemaid")
    assert user_entered is True
    assert saved["imagemaid"]["plex_path"] == "C:\\PlexData"
    assert saved["imagemaid"]["mode"] == "restore"
    assert saved["imagemaid"]["trace"] is True
    assert saved["imagemaid"]["photo_transcoder"] is True


def test_tail_imagemaid_log_reads_runtime_log_only(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    qs_module.app.config["IMAGEMAID_ROOT"] = str(imagemaid_root)

    regular_log = log_dir / "imagemaid.log"
    regular_log.write_text("[2026-04-28 20:17:00,274] [imagemaid.py:453] [INFO] runtime log line\n", encoding="utf-8")

    resp = client.get("/tail-imagemaid-log")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "runtime log line" in data["text"]
    assert data["path"].endswith("imagemaid.log")


def test_tail_imagemaid_log_returns_404_when_runtime_log_missing(client, isolated_config_dir, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    qs_module.app.config["IMAGEMAID_ROOT"] = str(imagemaid_root)

    resp = client.get("/tail-imagemaid-log")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "No ImageMaid log found." in data["error"]


def test_tail_imagemaid_log_hides_executor_shutdown_noise(client, isolated_config_dir, monkeypatch, qs_module):
    imagemaid_root = isolated_config_dir / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    qs_module.app.config["IMAGEMAID_ROOT"] = str(imagemaid_root)

    regular_log = log_dir / "imagemaid.log"
    regular_log.write_text(
        "ImageMaid Finished\n"
        "Exception ignored in: <function _ExecutorManagerThread.__init__.<locals>.weakref_cb at 0x000001F4C6F2C720>\n"
        "Traceback (most recent call last):\n"
        "  File \"C:\\\\Users\\\\nickz\\\\AppData\\\\Local\\\\Programs\\\\Python\\\\Python312\\\\Lib\\\\concurrent\\\\futures\\\\process.py\", line 310, in weakref_cb\n"
        "AttributeError: 'NoneType' object has no attribute 'debug'\n",
        encoding="utf-8",
    )
    resp = client.get("/tail-imagemaid-log")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "ImageMaid Finished" in data["text"]
    assert "Exception ignored in:" not in data["text"]
    assert "weakref_cb" not in data["text"]
    assert "AttributeError: 'NoneType' object has no attribute 'debug'" not in data["text"]


def test_stop_imagemaid_writes_stop_marker(tmp_path, client, monkeypatch, qs_module):
    class _FakeProc:
        pid = 3333

        def cmdline(self):
            return ["python", "imagemaid.py"]

    pid_file = tmp_path / "imagemaid.pid"
    pid_file.write_text("3333", encoding="utf-8")
    imagemaid_root = tmp_path / "imagemaid"
    log_dir = imagemaid_root / "config" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "imagemaid.log"
    log_path.write_text("ImageMaid starting...\n", encoding="utf-8")

    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid", lambda: 3333)
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_pid_file", lambda: str(pid_file))
    monkeypatch.setattr(qs_module.helpers, "get_imagemaid_root_path", lambda: imagemaid_root)
    monkeypatch.setattr(qs_module, "_find_running_imagemaid_process", lambda: _FakeProc())
    monkeypatch.setattr(qs_module, "_stop_process_tree", lambda _proc: [])
    monkeypatch.setattr(qs_module, "_get_latest_imagemaid_log_path", lambda: log_path)
    monkeypatch.setattr(qs_module, "_get_imagemaid_settings_section", lambda: ({}, {"mode": "restore"}))
    qs_module.app.config["VERSION_CHECK"] = {"local_version": "0.9.16-build18", "branch": "develop"}

    resp = client.post("/stop-imagemaid")
    assert resp.status_code == 200
    content = log_path.read_text(encoding="utf-8")
    assert "[Quickstart] Run event: event=stopped" in content
    assert "tool=imagemaid" in content
    assert "mode=restore" in content


def test_write_quickstart_imagemaid_run_marker_writes_runtime_log(tmp_path, qs_module):
    imagemaid_root = tmp_path / "imagemaid"
    log_path = imagemaid_root / "config" / "logs" / "imagemaid.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("ImageMaid starting...\n", encoding="utf-8")

    qs_module.app.config["VERSION_CHECK"] = {"local_version": "0.9.16-build18", "branch": "develop"}

    ok = qs_module._write_quickstart_imagemaid_run_marker(imagemaid_root, mode="restore", config_name="demo", log_path=log_path)
    assert ok is True

    content = log_path.read_text(encoding="utf-8")
    assert "[Quickstart] Run marker:" in content
    assert "config=demo" in content
    assert "tool=imagemaid" in content
    assert "mode=restore" in content


def test_get_imagemaid_supported_options_detects_optional_flags(tmp_path, qs_module):
    imagemaid_root = tmp_path / "imagemaid"
    imagemaid_root.mkdir(parents=True, exist_ok=True)
    (imagemaid_root / "imagemaid.py").write_text(
        '"env": "NO_VERIFY_SSL"\n'
        '"key": "overlays-only"\n',
        encoding="utf-8",
    )

    supported = qs_module._get_imagemaid_supported_options(imagemaid_root)
    assert supported["no_verify_ssl"] is True
    assert supported["overlays_only"] is True


def test_build_imagemaid_command_parts_only_adds_supported_optional_flags(tmp_path, qs_module):
    imagemaid_root = tmp_path / "imagemaid"
    scripts_dir = imagemaid_root / "imagemaid-venv" / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "python.exe").write_text("", encoding="utf-8")
    (imagemaid_root / "imagemaid.py").write_text(
        '"env": "NO_VERIFY_SSL"\n'
        '"key": "overlays-only"\n',
        encoding="utf-8",
    )

    parts = qs_module._build_imagemaid_command_parts(
        {
            "plex_path": "C:\\Plex",
            "mode": "report",
            "no_verify_ssl": True,
            "overlays_only": True,
        },
        "http://plex:32400",
        "token",
        imagemaid_root=imagemaid_root,
        redact=False,
    )

    assert "--no-verify-ssl" in parts
    assert "--overlays-only" in parts
import os
