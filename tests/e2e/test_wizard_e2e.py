import re
from pathlib import Path

import pytest
from playwright.sync_api import expect


def _ordered_stems():
    repo_root = Path(__file__).resolve().parents[2]
    templates_dir = repo_root / "templates"
    files = sorted(p.name for p in templates_dir.iterdir() if p.is_file())
    included = []
    for file in files:
        if not file.endswith(".html"):
            continue
        if file in {"000-base.html", "001-navigation.html"}:
            continue
        if file.startswith("999-"):
            continue
        if not file[:3].isdigit():
            continue
        included.append(Path(file).stem)
    return included


@pytest.mark.e2e
def test_wizard_happy_path_all_steps(page, live_server):
    stems = _ordered_stems()
    assert stems

    for stem in stems:
        page.goto(f"{live_server}/step/{stem}", wait_until="domcontentloaded")
        heading = page.locator("h2").first
        expect(heading).to_be_visible()


@pytest.mark.e2e
def test_back_forward_navigation(page, live_server):
    stems = _ordered_stems()
    assert len(stems) >= 2

    first, second = stems[0], stems[1]
    page.goto(f"{live_server}/step/{first}", wait_until="domcontentloaded")
    page.goto(f"{live_server}/step/{second}", wait_until="domcontentloaded")

    page.go_back()
    expect(page).to_have_url(re.compile(f"/step/{re.escape(first)}$"))
    expect(page.locator("h2").first).to_be_visible()

    page.go_forward()
    expect(page).to_have_url(re.compile(f"/step/{re.escape(second)}$"))
    expect(page.locator("h2").first).to_be_visible()


@pytest.mark.e2e
def test_maintenance_badge_visible_on_any_page(page, live_server):
    def handle_status(route):
        route.fulfill(
            status=200,
            json={
                "status": "running",
                "elapsed_seconds": 90,
                "maintenance_active": True,
                "maintenance_paused": True,
                "maintenance_window": "01:00-02:00",
                "maintenance_paused_since": "2026-03-31T00:00:00Z",
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": False,
                "pending_requested_at": None,
            },
        )

    page.route("**/kometa-status", handle_status)
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.wait_for_timeout(1600)
    badge = page.locator("#qs-maintenance-badge")
    expect(badge).not_to_have_class(re.compile(r"\bd-none\b"))


@pytest.mark.e2e
def test_running_pill_visible(page, live_server):
    def handle_status(route):
        route.fulfill(
            status=200,
            json={
                "status": "running",
                "elapsed_seconds": 75,
                "maintenance_active": False,
                "maintenance_paused": False,
                "maintenance_window": None,
                "maintenance_paused_since": None,
                "queued_started_at": None,
                "window_unavailable": False,
                "window_unavailable_since": None,
                "pending_start": False,
                "pending_requested_at": None,
            },
        )

    page.route("**/kometa-status", handle_status)
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.wait_for_timeout(1600)
    badge = page.locator("#qs-running-badge")
    expect(badge).not_to_have_class(re.compile(r"\bd-none\b"))
    expect(badge).to_contain_text("Kometa running")
