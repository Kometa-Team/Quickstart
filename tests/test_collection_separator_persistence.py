"""Collection separator overrides must survive the library save pipeline."""

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from werkzeug.datastructures import MultiDict

from modules import database, output, persistence
from modules.output_dump import dump_section
from modules.output_optimize import optimize_template_variables

FAMILIES = ("resolution", "audio_language", "subtitle_language", "actor", "universe", "based", "decade")


class _Checkboxes(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.checked = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "checkbox" and attrs.get("name"):
            self.checked[attrs["name"]] = "checked" in attrs


@pytest.mark.parametrize("kind", ["mov", "sho"])
@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("raw,expected", [("false", False), ("true", True), (False, False), (True, True)])
def test_collection_separator_fields_keep_their_scope(kind, family, raw, expected):
    prefix = f"{kind}-library_1-template_collection_{family}"
    cleaned = persistence.clean_form_data(MultiDict({f"{prefix}_use_separator": raw, f"{prefix}_sep_style": " blue "}))
    assert cleaned == {f"{prefix}_use_separator": expected, f"{prefix}_sep_style": "blue"}


@pytest.mark.parametrize("kind", ["mov", "sho"])
@pytest.mark.parametrize("checked", [False, True])
def test_collection_separator_form_checkbox_and_hidden_fallback(kind, checked):
    key = f"{kind}-library_1-template_collection_resolution_use_separator"
    fields = [(key, "true")] if checked else []
    fields.append((key, "false"))
    assert persistence.clean_form_data(MultiDict(fields)) == {key: checked}


@pytest.mark.parametrize("kind", ["mov", "sho"])
@pytest.mark.parametrize("selection,expected", [("gray", "gray"), ("none", None)])
def test_legacy_global_separator_selection_still_migrates(kind, selection, expected):
    cleaned = persistence.clean_form_data(MultiDict({f"{kind}-use_separator": selection}))
    assert cleaned == {f"{kind}-template_variables": {"use_separator": expected}}


@pytest.mark.parametrize("kind", ["mov", "sho"])
def test_legacy_global_separator_style_still_migrates(kind):
    cleaned = persistence.clean_form_data(MultiDict({f"{kind}-sep_style": " gray "}))
    assert cleaned == {f"{kind}-template_variables": {"sep_style": "gray"}}


@pytest.mark.parametrize("kind,media_type,library_name", [("mov", "movie", "Movies"), ("sho", "show", "TV Shows")])
@pytest.mark.parametrize("transport", ["json", "form"])
def test_separator_overrides_survive_autosave_reload_and_yaml(client, app, isolated_config_dir, kind, media_type, library_name, transport):
    config_name = f"separator_overrides_{kind}_{transport}"
    prefix = f"{kind}-library_test"
    other_prefix = f"{kind}-library_other"
    other_settings = {f"{other_prefix}-library": "Other Library", f"{other_prefix}-template_collection_resolution_use_separator": False}
    database.save_section_data("libraries", False, True, {"libraries": other_settings}, name=config_name)
    with client.session_transaction() as session:
        session["config_name"] = config_name

    definitions = json.loads(Path("static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    collections = [
        collection
        for group in definitions
        for collection in group["collections"]
        if collection["id"].removeprefix("collection_") in FAMILIES and media_type in collection["media_types"]
    ]
    assert {collection["id"].removeprefix("collection_") for collection in collections} == set(FAMILIES)

    # Start with every separator disabled, then reset alternating families to the
    # UI default. Default-valued checkboxes are omitted by the browser payload.
    for enabled_families in (set(), set(FAMILIES[::2])):
        form = {
            "__loaded_sections": ["collections"],
            f"{prefix}-library": library_name,
            f"{prefix}-template_variables[use_separator]": "gray",
            f"{prefix}-template_variables[sep_style]": "gray",
        }
        for family in FAMILIES:
            form[f"{prefix}-collection_{family}"] = "true"
            form[f"{prefix}-template_collection_{family}_sep_style"] = "blue"
            if family not in enabled_families:
                form[f"{prefix}-template_collection_{family}_use_separator"] = "false"

        response = client.post(f"/autosave_library/{prefix}", **({"json": form} if transport == "json" else {"data": form}))
        assert response.status_code == 200, response.json
        assert response.json["success"] is True
        stored = database.retrieve_section_data(config_name, "libraries")[2]["libraries"]
        assert all(stored[key] == value for key, value in other_settings.items())
        assert stored[f"{prefix}-template_variables[use_separator]"] == "gray"
        assert stored[f"{prefix}-template_variables[sep_style]"] == "gray"
        assert not stored.get("mov-template_variables")
        assert not stored.get("sho-template_variables")
        for family in FAMILIES:
            key = f"{prefix}-template_collection_{family}_use_separator"
            if family in enabled_families:
                assert key not in stored
            else:
                assert stored[key] is False
            assert stored[f"{prefix}-template_collection_{family}_sep_style"] == "blue"

        with app.test_request_context():
            macros = app.jinja_env.get_template("partials/_macros.html").module
            html = str(
                macros.collection_group_section(
                    {"id": prefix, "name": library_name, "type": media_type},
                    {"libraries": stored},
                    {},
                    {"accordion": "Collections", "collections": collections},
                    {},
                )
            )
            controls = _Checkboxes(html)
            for family in FAMILIES:
                assert controls.checked[f"{prefix}-template_collection_{family}_use_separator"] is (family in enabled_families)

            config = output.build_libraries_section(
                **{
                    f"{media_type}_libraries": {f"{prefix}-library": library_name},
                    f"{media_type}_templates": {"test": stored},
                    f"{media_type}_collections": {"test": stored},
                }
            )
            optimize_template_variables(config, {library_name: media_type})
            yaml_text = dump_section("", "libraries", config["libraries"], "none", None)
        exported = YAML(typ="safe", pure=True).load(yaml_text)["libraries"][library_name]
        entries = {entry["default"]: entry.get("template_variables", {}) for entry in exported["collection_files"]}
        assert set(entries) == set(FAMILIES)
        for family in FAMILIES:
            assert entries[family].get("use_separator", True) is (family in enabled_families)
            assert entries[family]["sep_style"] == "blue"
        assert exported["template_variables"].get("use_separator", True) is True
        assert exported["template_variables"]["sep_style"] == "gray"
