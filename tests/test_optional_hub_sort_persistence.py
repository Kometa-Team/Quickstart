"""Issue #1944: optional hub sorting must not block unrelated settings saves."""

import json
import os
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from werkzeug.datastructures import MultiDict

from modules.hub_sort import SETTINGS_AUTO_SORT_HUBS_VALUES


class HubForm(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.fields = {}
        self.clear_buttons = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden" and "auto_sort_hubs" in attrs.get("name", ""):
            self.fields[attrs["name"]] = attrs.get("value", "")
        if tag == "button" and "data-clear-auto-sort-hubs" in attrs:
            self.clear_buttons.append(attrs["data-clear-auto-sort-hubs"])


def select_config(client, name="issue1944"):
    with client.session_transaction() as sess:
        sess["config_name"] = name
    return name


def save_settings(client, name, value, paths=None, *, autosave=True):
    data = MultiDict({"configSelector": name})
    if value is not ...:
        data.add("auto_sort_hubs", value)
    for group, values in (paths or {"movies": ["/assets/movies"], "shows": ["/assets/shows"]}).items():
        for path in values:
            data.add(f"asset_directory[{group}]", path)
    headers = {"Referer": "http://localhost/step/150-settings"}
    if autosave:
        headers["X-QS-Autosave-Only"] = "1"
    return client.post("/step/150-settings", data=data, headers=headers)


def stored_settings(name):
    from modules import database

    return database.retrieve_section_data(name, "settings")[2]["settings"]


@pytest.mark.parametrize("value", [None, "", "  ", "None", " none ", *sorted(SETTINGS_AUTO_SORT_HUBS_VALUES)])
def test_optional_and_valid_hub_sort_values(qs_module, value):
    assert qs_module._is_valid_auto_sort_hubs_value(value)


@pytest.mark.parametrize("value", ["bogus", "null", "false", "alpha.invalid", False, 0, [], {}])
def test_explicit_invalid_hub_sort_values_remain_invalid(qs_module, value):
    assert not qs_module._is_valid_auto_sort_hubs_value(value)


@pytest.mark.parametrize("value", [..., None, "", "None", "alpha", "configured.desc"])
def test_imported_optional_values_render_and_export_consistently(client, isolated_config_dir, app, value):
    from modules import database, importer
    from modules.output_dump import dump_section

    name = select_config(client)
    settings = {"asset_directory": ["/assets/shared"]}
    if value is not ...:
        settings["auto_sort_hubs"] = value
    with app.test_request_context():
        payload, _report = importer.prepare_import_payload({"settings": settings}, set(), set())
    database.save_section_data("settings", False, True, payload["settings"], name=name)
    html = client.get("/step/150-settings").get_data(as_text=True)
    expected = value if value in SETTINGS_AUTO_SORT_HUBS_VALUES else ""
    form = HubForm(html)
    assert form.fields["auto_sort_hubs"] == expected
    assert form.clear_buttons == ["auto_sort_hubs"]
    assert 'disabled aria-disabled="true"' in html
    with app.app_context():
        output = dump_section("", "settings", payload["settings"], "none", name)
    assert YAML().load(output)["settings"]["auto_sort_hubs"] == (expected or None)
    response = save_settings(client, name, form.fields["auto_sort_hubs"])
    assert response.status_code == 200, response.get_json()
    assert stored_settings(name)["asset_directory"]["movies"] == ["/assets/movies"]


@pytest.mark.parametrize(
    "paths",
    [
        {"movies": ["/assets/movies", "/assets/more"], "shows": ["/assets/tv"]},
        {"movies": ["config/assets/movies"], "shows": ["/config/assets/tv"]},
        {"movies": [r"C:\Assets\Movies", r"D:\Artwork"], "shows": [r"\\nas\Assets\TV"]},
    ],
)
def test_fresh_settings_save_navigate_reload_and_export(client, isolated_config_dir, app, paths):
    from modules.output_dump import dump_section

    name = select_config(client)
    form = HubForm(client.get("/step/150-settings").get_data(as_text=True))
    assert form.fields["auto_sort_hubs"] == ""
    assert save_settings(client, name, "", {"movies": ["/assets/original"]}).status_code == 200
    form = HubForm(client.get("/step/150-settings").get_data(as_text=True))
    assert form.fields["auto_sort_hubs"] == ""  # Previously became the literal "None".
    assert save_settings(client, name, form.fields["auto_sort_hubs"], paths).get_json()["success"] is True
    assert stored_settings(name)["asset_directory"] == paths
    assert client.get("/step/020-tmdb").status_code == 200
    for _ in range(2):
        html = client.get("/step/150-settings").get_data(as_text=True)
        assert HubForm(html).fields["auto_sort_hubs"] == ""
        assert stored_settings(name)["asset_directory"] == paths
    with app.app_context():
        output = dump_section("", "settings", {"settings": stored_settings(name)}, "none", name)
    parsed = YAML().load(output)["settings"]
    assert parsed["asset_directory"] == paths
    assert parsed["auto_sort_hubs"] is None


@pytest.mark.parametrize("value", [..., "", "None", "alpha", "random"])
def test_autosave_accepts_optional_and_valid_values(client, isolated_config_dir, value):
    name = select_config(client)
    response = save_settings(client, name, value)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["success"] is True
    assert stored_settings(name)["asset_directory"] == {"movies": ["/assets/movies"], "shows": ["/assets/shows"]}


@pytest.mark.parametrize("autosave", [True, False])
def test_rejected_save_reports_error_and_preserves_previous_assets(client, isolated_config_dir, autosave):
    name = select_config(client)
    assert save_settings(client, name, "alpha", {"movies": ["/assets/original"]}).status_code == 200
    response = save_settings(client, name, "bogus", autosave=autosave)
    if autosave:
        assert response.status_code == 400
        assert response.get_json()["success"] is False
        assert "auto_sort_hubs must be one of" in response.get_json()["error"]
    else:
        assert b'id="qs-save-error"' in response.data
        assert b"auto_sort_hubs must be one of" in response.data
    assert stored_settings(name)["asset_directory"] == {"movies": ["/assets/original"]}
    assert stored_settings(name)["auto_sort_hubs"] == "alpha"


@pytest.mark.parametrize("value", [None, "None", "", "configured.desc", "bogus"])
def test_library_hub_sort_and_assets_remain_independent(client, isolated_config_dir, app, value):
    from modules import database, output

    name = select_config(client)
    for lib, title in [("mov-library_movies", "Movies"), ("sho-library_tv", "TV Shows")]:
        response = client.post(
            f"/autosave_library/{lib}",
            json={
                "config_name": name,
                f"{lib}-library": title,
                f"{lib}-top_level_auto_sort_hubs": value,
                f"{lib}-attribute_asset_directory[movies]": ["/assets/movies"],
                f"{lib}-attribute_asset_directory[shows]": ["/assets/shows"],
            },
        )
        assert response.status_code == (400 if value == "bogus" else 200), response.get_json()
    if value == "bogus":
        assert database.retrieve_section_data(name, "libraries")[2] is None
        return
    data = database.retrieve_section_data(name, "libraries")[2]["libraries"]
    for lib in ("mov-library_movies", "sho-library_tv"):
        assert data[f"{lib}-attribute_asset_directory"]["shows"] == ["/assets/shows"]
    with app.app_context():
        section = output.build_libraries_section(
            movie_libraries={"mov-library_movies-library": "Movies"},
            show_libraries={"sho-library_tv-library": "TV Shows"},
            movie_top_level={"movies": data},
            show_top_level={"tv": data},
        )
    for title in ("Movies", "TV Shows"):
        if value == "configured.desc":
            assert section["libraries"][title]["auto_sort_hubs"] == value
        else:
            assert "auto_sort_hubs" not in section["libraries"][title]


def test_restart_loads_assets_and_unset_hub_sort_from_disk(client, isolated_config_dir, app):
    name = select_config(client)
    assert save_settings(client, name, "None").status_code == 200
    # A separate interpreter starts the actual Flask app against the same SQLite file.
    script = """
import json, sys
sys.path.insert(0, "tests")
from conftest import _load_app
from modules import database
app = _load_app(sys.argv[1], sys.argv[2])
client = app.test_client()
with client.session_transaction() as sess:
    sess["config_name"] = "issue1944"
response = client.get("/step/150-settings")
assert response.status_code == 200
assert 'name="auto_sort_hubs" value=""' in response.get_data(as_text=True)
print("RESTART_DATA=" + json.dumps(database.retrieve_section_data("issue1944", "settings")[2]["settings"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(isolated_config_dir), app.config["KOMETA_ROOT"]],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    line = next(line for line in result.stdout.splitlines() if line.startswith("RESTART_DATA="))
    assert json.loads(line.partition("=")[2]) == stored_settings(name)


@pytest.mark.parametrize("value,expected", [(None, ""), ("None", ""), ("alpha", "alpha"), ("bogus", "bogus"), (False, "False"), (0, "0")])
def test_library_fragment_renders_optional_preserved_and_clearable_values(client, monkeypatch, qs_module, library_routes_module, value, expected):
    lib = "mov-library_movies"
    monkeypatch.setattr(library_routes_module, "_build_library_lists", lambda: ([{"id": lib, "name": "Movies", "type": "movie"}], [], {"plex_pass": False}))
    monkeypatch.setattr(library_routes_module, "_migrate_legacy_playlist_libraries_to_library_toggles", lambda *_: set())
    monkeypatch.setattr(library_routes_module, "_build_preview_image_data", lambda: {"movie": {}, "show": {}})
    original = qs_module.persistence.retrieve_settings

    def retrieve(target):
        if target == "025-libraries":
            return {"libraries": {f"{lib}-top_level_auto_sort_hubs": value}}
        return original(target)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", retrieve)
    response = client.get(f"/library_fragment/{lib}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    form = HubForm(html)
    assert form.fields[f"{lib}-top_level_auto_sort_hubs"] == expected
    assert form.clear_buttons == [f"{lib}-top_level_auto_sort_hubs"]
    if value == "bogus":
        assert "Invalid saved value: bogus" in html


def test_clearing_movie_sort_preserves_global_and_tv_settings(client, isolated_config_dir, app):
    from modules import database, output

    name = select_config(client)
    assert save_settings(client, name, "alpha").status_code == 200
    for lib, title, mode in [("mov-library_movies", "Movies", "configured"), ("sho-library_tv", "TV Shows", "random")]:
        response = client.post(
            f"/autosave_library/{lib}",
            json={
                "config_name": name,
                f"{lib}-library": title,
                f"{lib}-top_level_auto_sort_hubs": mode,
                f"{lib}-attribute_asset_directory[shows]": ["/assets/retained"],
            },
        )
        assert response.status_code == 200, response.get_json()
    response = client.post(
        "/autosave_library/mov-library_movies",
        json={
            "config_name": name,
            "mov-library_movies-library": "Movies",
            "mov-library_movies-top_level_auto_sort_hubs": "",
            "mov-library_movies-attribute_asset_directory[shows]": ["/assets/edited"],
        },
    )
    assert response.status_code == 200, response.get_json()
    assert stored_settings(name)["auto_sort_hubs"] == "alpha"
    data = database.retrieve_section_data(name, "libraries")[2]["libraries"]
    assert data["mov-library_movies-top_level_auto_sort_hubs"] is None
    assert data["sho-library_tv-top_level_auto_sort_hubs"] == "random"
    assert data["mov-library_movies-attribute_asset_directory"]["shows"] == ["/assets/edited"]
    assert data["sho-library_tv-attribute_asset_directory"]["shows"] == ["/assets/retained"]
    with app.app_context():
        section = output.build_libraries_section(
            movie_libraries={"mov-library_movies-library": "Movies"},
            show_libraries={"sho-library_tv-library": "TV Shows"},
            movie_top_level={"movies": data},
            show_top_level={"tv": data},
        )
    assert "auto_sort_hubs" not in section["libraries"]["Movies"]
    assert section["libraries"]["TV Shows"]["auto_sort_hubs"] == "random"
