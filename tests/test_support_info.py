import pytest


@pytest.fixture
def support_info_log(tmp_path, monkeypatch, qs_module):
    log_path = tmp_path / "quickstart.log"
    log_path.write_text("Plex user: Jane Example\ntoken=private-token\n", encoding="utf-8")
    monkeypatch.setattr(qs_module.helpers, "LOG_FILE", str(log_path))
    monkeypatch.setattr(qs_module.helpers, "get_plex_summary", lambda: "Connected to Plex server Test")
    monkeypatch.setattr(qs_module.helpers, "get_quickstart_settings_summary", lambda: ["# Quickstart Settings: test"])
    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda section: {})
    monkeypatch.setattr(qs_module.persistence, "get_library_names", lambda section: {})
    return log_path


@pytest.mark.parametrize("query", ["", "?include_logs=0", "?include_logs=true", "?include_logs=invalid"])
def test_support_info_omits_logs_without_explicit_opt_in(client, support_info_log, query):
    response = client.get(f"/support-info{query}")

    assert response.status_code == 200
    payload = response.get_json()
    assert "# System Information" in payload["text"]
    assert "Connected to Plex server Test" in payload["text"]
    assert "No libraries configured." in payload["text"]
    assert "Quickstart log tail" not in payload["text"]
    assert "Jane Example" not in payload["text"]
    assert "private-token" not in payload["text"]
    assert payload["generated_at"]


def test_support_info_does_not_access_log_path_by_default(client, support_info_log, monkeypatch, qs_module):
    monkeypatch.setattr(qs_module.helpers, "LOG_FILE", None)

    response = client.get("/support-info")

    assert response.status_code == 200
    assert "Quickstart log tail" not in response.get_json()["text"]


def test_support_info_opt_in_includes_redacted_log_tail(client, support_info_log):
    support_info_log.write_text("".join(f"Log line {index}\n" for index in range(205)) + "token=private-token\n", encoding="utf-8")

    response = client.get("/support-info?include_logs=1")

    assert response.status_code == 200
    text = response.get_json()["text"]
    heading = "# Quickstart log tail (last 200 lines)\n\n"
    assert heading in text
    tail = text.split(heading, 1)[1].splitlines()
    assert len(tail) == 200
    assert tail[0] == "Log line 6"
    assert tail[-1] == "token=(redacted)"
    assert "private-token" not in text


@pytest.mark.parametrize("missing", [False, True], ids=["empty", "missing"])
def test_support_info_opt_in_handles_unavailable_logs(client, support_info_log, missing):
    if missing:
        support_info_log.unlink()
    else:
        support_info_log.write_text("", encoding="utf-8")

    response = client.get("/support-info?include_logs=1")

    assert response.status_code == 200
    expected = "Quickstart log unavailable." if missing else "Quickstart log is empty."
    assert response.get_json()["text"].endswith(expected)
