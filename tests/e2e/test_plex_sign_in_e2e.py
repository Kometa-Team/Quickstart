from pathlib import Path
import re
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
@pytest.mark.parametrize("mode", ["existing", "manual"])
def test_plex_browser_approval_and_server_validation(page, live_server, app, monkeypatch, viewport, label, mode):
    approved = False
    config_name = f"plex_sign_in_{label}_{mode}"
    server_url = "http://192.168.1.20:32400"
    auth_requests = []
    page.on("request", lambda request: auth_requests.append(request.url) if "/plex-auth/" in request.url else None)
    page.set_viewport_size(viewport)
    database.save_section_data("start", True, True, {"start": {"config_name": config_name}}, name=config_name)

    def plex_get(url, **kwargs):
        if "/pins/" in url:
            return PlexResponse({"authToken": "approved-token" if approved else None})
        assert url.endswith("/user")
        assert kwargs["headers"]["X-Plex-Token"] == "approved-token"
        return PlexResponse({"username": "plex-owner"})

    monkeypatch.setattr(auth, "requests", SimpleNamespace(post=lambda *args, **kwargs: PlexResponse({"id": 123, "code": "test-pin", "expiresIn": 60}), get=plex_get))

    def validate(data):
        assert data == {"plex_url": server_url, "plex_token": "approved-token"}
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
    guidance = page.locator(".qs-validation-callout")
    expect(guidance).to_contain_text("Choose either option:")
    expect(guidance).to_contain_text("Quickstart fills only the token")
    expect(guidance).to_contain_text("An existing URL is kept")
    expect(guidance).to_contain_text("Manual entry:")
    expect(guidance).to_contain_text("Docker host's LAN address and published Plex port")
    expect(guidance).to_contain_text("Sign-in does not change your server address")
    expect(guidance).not_to_contain_text("discovery")
    expect(guidance.locator("a")).to_have_attribute("rel", "noopener noreferrer")
    expect(page.locator("#plex_url_text [data-bs-toggle='tooltip']")).to_have_attribute("data-bs-original-title", re.compile("Enter the address Kometa.*", re.DOTALL))
    expect(page.locator("#plexServerPicker, #plexServerSelect")).to_have_count(0)
    page.locator("#plex_url").fill(server_url if mode == "existing" else "")
    artifacts = Path(__file__).resolve().parents[2] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    page.screenshot(path=str(artifacts / f"plex-sign-in-{label}-{mode}.png"), full_page=True)

    page.locator("#plexSignIn").click()
    page.bring_to_front()
    expect(page.locator("#plexAuthStatus")).to_have_text("Waiting for Plex approval...", timeout=15000)
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
    page.screenshot(path=str(artifacts / f"plex-sign-in-{label}-{mode}-pending.png"), full_page=True)

    approved = True
    page.bring_to_front()
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    if mode == "manual":
        expect(page.locator("#plexAuthStatus")).to_have_text("Signed in as plex-owner. Enter your Plex server URL, then validate.", timeout=15000)
        expect(page.locator("#plex_token")).to_have_value("approved-token")
        expect(page.locator("#plex_url")).to_have_value("")
        expect(page.locator("#plexSignIn")).to_be_enabled()
        expect(page.locator("#plex_token")).not_to_have_attribute("readonly", "")
        expect(page.locator("#plex_validated")).to_have_value("false")
        expect(page.locator("#statusMessage")).not_to_have_text("Plex server validated successfully!")
        assert not any(url.endswith(("/servers", "/connect")) for url in auth_requests)
        page.locator("#plex_url").fill(server_url)
        expect(page.locator("#validateButton")).to_be_enabled()
        page.locator("#validateButton").click()
    else:
        expect(page.locator("#plexAuthStatus")).to_have_text("Signed in as plex-owner.", timeout=15000)
    expect(page.locator("#plex_url")).to_have_value(server_url)
    expect(page.locator("#plexAuthStatus")).to_be_visible()
    expect(page.locator("#statusMessage")).to_have_text("Plex server validated successfully!", timeout=15000)
    expect(page.locator("#plex_token")).to_have_value("approved-token")
    expect(page.locator("#plex_token")).to_have_attribute("type", "password")
    expect(page.locator("#tmp_movie_libraries")).to_have_value("1")
    expect(page.locator("#plex-pass-status-success")).to_be_visible()
    assert all(url.rsplit("/", 1)[-1] in ("start", "check", "cancel") for url in auth_requests)
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    page.screenshot(path=str(artifacts / f"plex-sign-in-{label}-{mode}-approved.png"), full_page=True)
    with app.app_context():
        assert database.retrieve_section_data(config_name, "plex")[2]["plex"]["token"] == "approved-token"
