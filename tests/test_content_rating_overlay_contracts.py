from ruamel.yaml import YAML

from modules import importer

OVERLAY_CASES = [
    {
        "id": "us_movie",
        "default_name": "content_rating_us_movie",
        "overlay_key": "content_rating_us_movie",
        "radio_value": "us_movie",
        "library_name": "Movies",
        "library_type": "movie",
        "builder": "movie",
        "template_vars": {
            "use_g": False,
            "use_pg": False,
            "use_pg-13": False,
            "use_r": False,
            "use_nc-17": False,
            "use_nr": False,
        },
    },
    {
        "id": "us_show",
        "default_name": "content_rating_us_show",
        "overlay_key": "content_rating_us_show",
        "radio_value": "us_show",
        "library_name": "Shows",
        "library_type": "show",
        "builder": "show",
        "template_vars": {
            "use_tv-g": False,
            "use_tv-y": False,
            "use_tv-pg": False,
            "use_tv-14": False,
            "use_tv-ma": False,
            "use_nr": False,
        },
    },
    {
        "id": "uk",
        "default_name": "content_rating_uk",
        "overlay_key": "content_rating_uk",
        "radio_value": "uk",
        "library_name": "Movies",
        "library_type": "movie",
        "builder": "movie",
        "template_vars": {
            "use_u": False,
            "use_pg": False,
            "use_12": False,
            "use_12a": False,
            "use_15": False,
            "use_18": False,
            "use_r18": False,
            "use_nr": False,
        },
    },
    {
        "id": "de",
        "default_name": "content_rating_de",
        "overlay_key": "content_rating_de",
        "radio_value": "de",
        "library_name": "Movies",
        "library_type": "movie",
        "builder": "movie",
        "template_vars": {
            "use_0": False,
            "use_6": False,
            "use_12": False,
            "use_16": False,
            "use_18": False,
            "use_bpjm": False,
            "use_nr": False,
        },
    },
    {
        "id": "au",
        "default_name": "content_rating_au",
        "overlay_key": "content_rating_au",
        "radio_value": "au",
        "library_name": "Movies",
        "library_type": "movie",
        "builder": "movie",
        "template_vars": {
            "use_g": False,
            "use_pg": False,
            "use_m": False,
            "use_ma": False,
            "use_r": False,
            "use_x": False,
            "use_nr": False,
        },
    },
    {
        "id": "nz",
        "default_name": "content_rating_nz",
        "overlay_key": "content_rating_nz",
        "radio_value": "nz",
        "library_name": "Movies",
        "library_type": "movie",
        "builder": "movie",
        "template_vars": {
            "use_g": False,
            "use_pg": False,
            "use_m": False,
            "use_r13": False,
            "use_rp13": False,
            "use_r15": False,
            "use_r16": False,
            "use_rp16": False,
            "use_R18": False,
            "use_rp18": False,
            "use_r": False,
            "use_nr": False,
        },
    },
    {
        "id": "commonsense",
        "default_name": "commonsense",
        "overlay_key": "content_rating_commonsense",
        "radio_value": "commonsense",
        "library_name": "Movies",
        "library_type": "movie",
        "builder": "movie",
        "template_vars": {
            "use_1": False,
            "use_2": False,
            "use_3": False,
            "use_4": False,
            "use_5": False,
            "use_6": False,
            "use_7": False,
            "use_8": False,
            "use_9": False,
            "use_10": False,
            "use_11": False,
            "use_12": False,
            "use_13": False,
            "use_14": False,
            "use_15": False,
            "use_16": False,
            "use_17": False,
            "use_18": False,
            "use_nr": False,
        },
    },
]


def _base_parts(case):
    if case["library_type"] == "movie":
        return "mov-library_movies", "Movies"
    return "sho-library_shows", "Shows"


def _build_form_payload(case):
    base, library_name = _base_parts(case)
    builder = case["builder"]
    overlay_key = case["overlay_key"]
    data = {
        f"{base}-library": library_name,
        f"{base}-collection_collectionless": True,
        f"{base}-{builder}-overlay_content_rating": case["radio_value"],
    }
    prefix = f"{base}-{builder}-template_overlay_{overlay_key}"
    for key, value in case["template_vars"].items():
        data[f"{prefix}[{key}]"] = value
    return {"validated": True, "libraries": data}


def _run_build_config_with_payload(qs_module, monkeypatch, payload):
    monkeypatch.setattr(
        qs_module.output.helpers,
        "get_template_list",
        lambda: {
            "libraries": {
                "name": "Libraries",
                "stem": "025-libraries",
                "raw_name": "libraries",
            }
        },
    )
    monkeypatch.setattr(qs_module.output.helpers, "get_plex_summary", lambda: "Plex summary unavailable")
    monkeypatch.setattr(qs_module.output.helpers, "get_quickstart_settings_summary", lambda: [])
    monkeypatch.setattr(qs_module.output.helpers, "get_library_summaries", lambda _names: "Content Ratings")

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        return {"validated": False}

    monkeypatch.setattr(qs_module.output.persistence, "retrieve_settings", fake_retrieve_settings)
    with qs_module.app.app_context():
        validated, _validation_error, _config_data, yaml_content, _validation_errors = qs_module.output.build_config(
            header_style="single line",
            config_name="pytest_content_rating_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def _template_vars_from_yaml(yaml_content, case):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    overlays = parsed.get("libraries", {}).get(case["library_name"], {}).get("overlay_files", [])
    assert overlays, f"Expected overlay_files for {case['library_name']}"
    matching = [entry for entry in overlays if entry.get("default") == case["default_name"]]
    assert matching, f"Expected {case['default_name']} overlay entry"
    if case["builder"] == "show":
        for entry in matching:
            tv = entry.get("template_variables", {})
            if tv.get("builder_level", "show") == "show":
                return tv
        raise AssertionError(f"Expected show-level template variables for {case['default_name']}")
    return matching[0].get("template_variables", {})


def test_prepare_import_payload_accepts_content_rating_use_key_template_variables():
    for case in OVERLAY_CASES:
        payload, report = importer.prepare_import_payload(
            {
                "libraries": {
                    case["library_name"]: {
                        "overlay_files": [
                            {
                                "default": case["default_name"],
                                "template_variables": case["template_vars"],
                            }
                        ]
                    }
                }
            },
            {"Movies"} if case["library_type"] == "movie" else set(),
            {"Shows"} if case["library_type"] == "show" else set(),
            set(),
        )

        libraries_payload = payload["libraries"]["libraries"]
        base, _ = _base_parts(case)
        enabled_key = f"{base}-{case['builder']}-overlay_content_rating"
        template_prefix = f"{base}-{case['builder']}-template_overlay_{case['overlay_key']}"
        assert libraries_payload[enabled_key] == case["radio_value"]
        for key in case["template_vars"]:
            field_key = f"{template_prefix}[{key}]"
            assert libraries_payload[field_key] is False
            assert any(f"template_variables.{key}" in line for line in report.lines)


def test_content_rating_yaml_contract_keeps_use_key_toggles(monkeypatch, qs_module):
    for case in OVERLAY_CASES:
        yaml_content = _run_build_config_with_payload(qs_module, monkeypatch, _build_form_payload(case))
        template_vars = _template_vars_from_yaml(yaml_content, case)
        for key in case["template_vars"]:
            assert template_vars[key] is False
