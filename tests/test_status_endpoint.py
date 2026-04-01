def test_kometa_status_has_expected_fields(client):
    resp = client.get("/kometa-status")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in [
        "status",
        "maintenance_active",
        "maintenance_paused",
        "maintenance_window",
        "maintenance_paused_since",
        "queued_started_at",
        "window_unavailable",
        "window_unavailable_since",
        "pending_start",
        "pending_requested_at",
    ]:
        assert key in data
