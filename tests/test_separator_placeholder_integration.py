"""Separator selections across the browser form, persistence, validation and YAML."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest

from blueprints import library_routes
from modules import database, output, persistence, validations
from modules.helpers import _plex
from modules.output_dump import dump_section

SOURCES = [
    ("mov", "movie", "Movies", "imdb_id", "tt0133093", "The Matrix"),
    ("mov", "movie", "Movies", "tmdb_movie", "603", "The Matrix"),
    ("sho", "show", "TV Shows", "imdb_id", "tt0944947", "Game of Thrones"),
    ("sho", "show", "TV Shows", "tvdb_show", "121361", "Game of Thrones"),
]


class _Controls(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.by_name = {}
        self.by_id = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"select", "input"} and attrs.get("name"):
            self.by_name[attrs["name"]] = attrs
            if attrs.get("id"):
                self.by_id[attrs["id"]] = attrs


def _render_separator(app, prefix, data):
    with app.test_request_context():
        macro = app.jinja_env.get_template("partials/_macros.html").module.select_section
        return str(
            macro(
                library={"id": prefix, "name": "TV Shows" if prefix.startswith("sho-") else "Movies"},
                data={"libraries": data},
                prefix="use_separator",
                title="Separator",
                description="Separator style",
                wiki="https://kometa.wiki/en/develop/defaults/separators/",
                options=[("", "None"), ("gray", "Gray")],
                yml_location="template_variables",
            )
        )


def _render_separator_collections(app, prefix, data):
    definitions = json.loads(Path("static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    separators = [collection for group in definitions for collection in group["collections"] if collection["id"] in {"collection_separator_award", "collection_separator_chart"}]
    with app.test_request_context():
        macro = app.jinja_env.get_template("partials/_macros.html").module.collection_group_section
        return str(
            macro(
                library={"id": prefix, "name": "Library", "type": "movie" if prefix.startswith("mov-") else "show"},
                data={"libraries": data},
                version_info={},
                group={"accordion": "Separators", "collections": separators},
                telemetry={},
            )
        )


@pytest.mark.parametrize("kind,media_type,library_name,source,value,title", SOURCES)
def test_separator_template_preserves_selected_id_and_title(app, kind, media_type, library_name, source, value, title):
    prefix = f"{kind}-library_test"
    field = f"{prefix}-attribute_template_variables[placeholder_{source}]"
    labels = json.dumps({value: title})
    html = _render_separator(app, prefix, {field: value, f"{field}__lookup_labels": labels})
    controls = _Controls(html).by_name

    assert f'data-library-type="{media_type}"' in html
    assert f'data-library-id="{library_name}"' in html
    assert controls[field]["data-separator-placeholder-value"] == value
    assert controls[f"{field}__lookup_labels"]["value"] == labels
    assert controls[f"{field}__lookup_labels"]["id"] == f'{controls[field]["id"]}__lookup_labels'


@pytest.mark.parametrize("kind,media_type,library_name,source,value,title", SOURCES)
@pytest.mark.parametrize("award,chart", [(False, False), (True, False), (False, True), (True, True)])
def test_separator_selection_survives_lookup_save_validation_and_yaml(
    client, app, isolated_config_dir, monkeypatch, kind, media_type, library_name, source, value, title, award, chart
):
    prefix = f"{kind}-library_test"
    config_name = f"separator_{kind}_{source}"
    with client.session_transaction() as session:
        session["config_name"] = config_name
    with app.test_request_context():
        from flask import session

        session["config_name"] = config_name
        database.save_section_data(
            name=config_name,
            section="plex",
            validated=True,
            user_entered=True,
            data={
                "plex": {
                    "url": "http://plex.test",
                    "token": "test-only-token",
                    "tmp_movie_libraries": "1",
                    "tmp_show_libraries": "2",
                    "tmp_library_names": json.dumps({"1": "Movies", "2": "TV Shows"}),
                }
            },
        )

    # Exercise the real GUID extractor and stored numeric-library-ID resolution.
    guid_source = {"imdb_id": "imdb", "tmdb_movie": "tmdb", "tvdb_show": "tvdb"}[source]
    guids = [f"{guid_source}://{value}"]
    item = SimpleNamespace(title=title, guids=[SimpleNamespace(id=guid) for guid in guids])
    searches = []

    def search(**kwargs):
        searches.append(kwargs)
        return [item]

    section = SimpleNamespace(key="1" if kind == "mov" else "2", title=library_name, search=search)
    monkeypatch.setattr(_plex, "PlexServer", lambda *_args: SimpleNamespace(library=SimpleNamespace(sections=lambda: [section])))
    monkeypatch.setattr(validations, "validate_plex_server", lambda _payload: {"validated": True})
    monkeypatch.setattr(library_routes, "_top_placeholder_cache", {})
    response = client.get(f"/get_top_imdb_items/{library_name}", query_string={"type": media_type})
    assert response.status_code == 200
    assert response.json["status"] == "success"
    assert response.json["items"][0][source] == value
    assert response.json["items"][0]["title"] == title
    assert searches == [{"sort": "audienceRating:desc", "maxresults": 50}]

    field = f"{prefix}-attribute_template_variables[placeholder_{source}]"
    # The browser submits the empty inactive select as well as the chosen source.
    secondary = "tmdb_movie" if kind == "mov" else "tvdb_show"
    form = {
        f"{prefix}-library": library_name,
        f"{prefix}-template_variables[use_separator]": "gray",
        f"{prefix}-attribute_template_variables[placeholder_imdb_id]": "",
        f"{prefix}-attribute_template_variables[placeholder_{secondary}]": "",
        field: value,
        f"{field}__lookup_labels": json.dumps({value: title}),
        f"{prefix}-collection_separator_award": award,
        f"{prefix}-collection_separator_chart": chart,
    }
    saved = client.post(f"/autosave_library/{prefix}", json=form)
    assert saved.status_code == 200, saved.json
    assert saved.json["success"] is True
    _, _, stored = database.retrieve_section_data(config_name, "libraries")
    assert str(stored["libraries"][field]) == value
    assert json.loads(stored["libraries"][f"{field}__lookup_labels"]) == {value: title}
    assert stored["libraries"][f"{prefix}-collection_separator_award"] is award
    assert stored["libraries"][f"{prefix}-collection_separator_chart"] is chart

    validated = client.post("/validate_all_services")
    assert validated.status_code == 200
    result = validated.json["results"]["025-libraries"]
    assert result["status"] == "validated", result

    with app.test_request_context():
        from flask import session

        session["config_name"] = config_name
        restored = persistence.retrieve_settings("025-libraries")["libraries"]
        controls = _Controls(_render_separator(app, prefix, restored)).by_name
        assert controls[field]["data-separator-placeholder-value"] == value
        assert json.loads(controls[f"{field}__lookup_labels"]["value"]) == {value: title}
        toggles = _Controls(_render_separator_collections(app, prefix, restored)).by_id
        assert ("checked" in toggles[f"{prefix}-collection_separator_award"]) is award
        assert ("checked" in toggles[f"{prefix}-collection_separator_chart"]) is chart
        arguments = {
            f'{"movie" if kind == "mov" else "show"}_libraries': {f"{prefix}-library": library_name},
            f'{"movie" if kind == "mov" else "show"}_templates': {"test": restored},
            f'{"movie" if kind == "mov" else "show"}_collections': {"test": {key: restored[key] for key in form if "-collection_" in key}},
        }
        libraries = output.build_libraries_section(**arguments)["libraries"]
        yaml_text = dump_section("", "libraries", libraries, "none", None)
    assert str(libraries[library_name]["template_variables"][f"placeholder_{source}"]) == value
    assert re.search(rf"placeholder_{source}: ['\"]?{value}['\"]?\s+# {re.escape(title)}", yaml_text), yaml_text
    assert "__lookup_labels" not in yaml_text
    assert "__template_variable_comments" not in yaml_text
    assert {key for key in libraries[library_name]["template_variables"] if key.startswith("placeholder_")} == {f"placeholder_{source}"}
    defaults = {entry["default"] for entry in libraries[library_name].get("collection_files", [])}
    assert ("separator_award" in defaults) is award
    assert ("separator_chart" in defaults) is chart


@pytest.mark.parametrize("kind,wrong_source", [("mov", "tvdb_show"), ("sho", "tmdb_movie")])
def test_separator_validation_rejects_empty_or_wrong_media_source(client, qs_module, monkeypatch, kind, wrong_source):
    prefix = f"{kind}-library_test"
    settings = {
        "010-plex": {"validated": True, "plex": {}},
        "025-libraries": {
            "libraries": {
                f"{prefix}-library": "Library",
                f"{prefix}-template_variables[use_separator]": "gray",
                f"{prefix}-attribute_template_variables[placeholder_imdb_id]": "",
                f"{prefix}-attribute_template_variables[placeholder_{wrong_source}]": "123",
            }
        },
    }
    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", lambda section: settings.get(section, {}))
    response = client.post("/validate_all_services")
    assert response.status_code == 200
    result = response.json["results"]["025-libraries"]
    assert result["status"] == "failed"
    assert result["reason"] == "missing_separator_placeholder"


@pytest.mark.parametrize("kind,media_type,library_name,source,value,title", SOURCES)
def test_mirror_separator_selection_ignores_blank_inactive_source(kind, media_type, library_name, source, value, title):
    prefix = f"{kind}-library_test"
    secondary = "tmdb_movie" if kind == "mov" else "tvdb_show"
    data = {
        f"{prefix}-template_variables[use_separator]": "gray",
        f"{prefix}-attribute_template_variables[placeholder_imdb_id]": "",
        f"{prefix}-attribute_template_variables[placeholder_{secondary}]": "",
    }
    data[f"{prefix}-attribute_template_variables[placeholder_{source}]"] = value
    verified = {"valid": True, "verified": True, "label": title, "result_type": media_type}
    quickstart = SimpleNamespace(
        _lookup_tmdb_numeric_id=lambda *_args, **_kwargs: verified,
        _lookup_tmdb_by_imdb_id=lambda *_args, **_kwargs: verified,
        helpers=SimpleNamespace(
            find_item_by_title=lambda *_args, **_kwargs: {"title": title},
            find_item_by_imdb_id=lambda *_args, **_kwargs: {"title": title},
        ),
    )
    issues = library_routes._mirror_separator_placeholder_issues(data, prefix, library_name, kind, quickstart)
    if source == "tvdb_show":
        # Keep the existing manual-review policy for copied TVDb placeholders.
        assert len(issues) == 1
        assert f"TVDb placeholder {value} cannot be verified automatically" in issues[0]
    else:
        assert issues == []
