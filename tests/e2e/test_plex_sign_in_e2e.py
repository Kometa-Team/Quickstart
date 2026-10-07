from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import jsonify
from playwright.sync_api import expect

from blueprints import plex_auth_routes as auth
from blueprints import validation_routes
from modules import database


class PlexResponse:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.mark.e2e
@pytest.mark.parametrize("viewport,label", [({"width": 1440, "height": 1000}, "desktop"), ({"width": 390, "height": 844}, "mobile")])
def test_plex_browser_approval_and_server_validation(page, live_server, app, monkeypatch, viewport, label):
    approved = False
    config_name = f"plex_sign_in_{label}"
    page.set_viewport_size(viewport)
    database.save_section_data("start", True, True, {"start": {"config_name": config_name}}, name=config_name)

    def plex_get(url, **kwargs):
        if "/pins/" in url:
            return PlexResponse({"authToken": "approved-token" if approved else None})
        assert kwargs["headers"]["X-Plex-Token"] == "approved-token"
        return PlexResponse({"username": "plex-owner"})

    monkeypatch.setattr(auth, "requests", SimpleNamespace(post=lambda *args, **kwargs: PlexResponse({"id": 123, "code": "test-pin", "expiresIn": 60}), get=plex_get))

    def validate(data):
        assert data == {"plex_url": "http://plex:32400", "plex_token": "approved-token"}
        return jsonify(
            {
                "validated": True,
                "db_cache": 40,
                "has_plex_pass": True,
                "user_list": ["plex-owner"],
                "movie_libraries": [{"id": 1, "name": "Movies"}],
                "show_libraries": [],
                "music_libraries": [],
            }
        )

    monkeypatch.setattr(validation_routes.validations, "validate_plex_server", validate)
    monkeypatch.setattr(validation_routes.helpers, "get_plex_metadata", lambda **kwargs: {})
    page.context.route("https://app.plex.tv/**", lambda route: route.fulfill(status=200, content_type="text/html", body="<title>Plex approval fixture</title>"))
    page.goto(f"{live_server}/step/001-start", wait_until="domcontentloaded")
    page.evaluate(
        """async name => {
      const response = await fetch('/switch-config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name}) })
      if (!response.ok) throw new Error('Unable to select test config')
    }""",
        config_name,
    )
    page.goto(f"{live_server}/step/010-plex", wait_until="networkidle")
    page.locator("#plex_url").fill("http://plex:32400")
    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    page.screenshot(path=str(artifacts / f"plex-sign-in-{label}.png"), full_page=True)

    page.locator("#plexSignIn").click()
    expect(page.locator("#plexAuthStatus")).to_have_text("Waiting for Plex approval...")
    expect(page.locator("#plexAuthStatus")).to_be_visible()
    expect(page.locator("#plexSignInCancel")).to_be_visible()
    expect(page.locator("#plexSignInOpen")).to_be_visible()
    expect(page.locator("#plex_token")).to_have_attribute("readonly", "")
    expect(page.locator("#validateButton")).to_be_disabled()
    boxes = [page.locator(selector).bounding_box() for selector in ("#plexSignIn", "#plexSignInCancel", "#plexSignInOpen")]
    for box in boxes:
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= viewport["width"] + 1
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            assert (
                box["x"] + box["width"] <= other["x"] + 1
                or other["x"] + other["width"] <= box["x"] + 1
                or box["y"] + box["height"] <= other["y"] + 1
                or other["y"] + other["height"] <= box["y"] + 1
            )
    page.screenshot(path=str(artifacts / f"plex-sign-in-{label}-pending.png"), full_page=True)

    approved = True
    expect(page.locator("#plexAuthStatus")).to_have_text("Signed in as plex-owner.")
    expect(page.locator("#plexAuthStatus")).to_be_visible()
    expect(page.locator("#statusMessage")).to_have_text("Plex server validated successfully!")
    expect(page.locator("#plex_token")).to_have_value("approved-token")
    expect(page.locator("#plex_token")).to_have_attribute("type", "password")
    expect(page.locator("#tmp_movie_libraries")).to_have_value("1")
    expect(page.locator("#plex-pass-status-success")).to_be_visible()
    page.screenshot(path=str(artifacts / f"plex-sign-in-{label}-approved.png"), full_page=True)
    with app.app_context():
        assert database.retrieve_section_data(config_name, "plex")[2]["plex"]["token"] == "approved-token"
