def test_start_kometa_queues_during_maintenance(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "is_kometa_running", lambda: False)
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_process", lambda: None)
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
    monkeypatch.setattr(qs_module, "_get_maintenance_window_live", lambda: (60, 120, "01:00-02:00"))
    monkeypatch.setattr(qs_module, "_is_within_maintenance_window", lambda *_: False)
    monkeypatch.setattr(qs_module, "_launch_kometa_command", lambda *_: (True, 4321))

    resp = client.post("/start-kometa", json={"command": "python kometa.py"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "Kometa started"
    assert data["pid"] == 4321


def test_stop_kometa_no_pid(client, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "get_kometa_pid", lambda: None)
    monkeypatch.setattr(qs_module, "_find_running_kometa_processes", lambda: [])

    resp = client.post("/stop-kometa")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "warning" in data
