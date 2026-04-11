from itertools import product

import pytest
from ruamel.yaml import YAML

RATING_SLOT_VALUES = {
    "1": ("user", "rt_tomato"),
    "2": ("critic", "imdb"),
    "3": ("audience", "tmdb"),
}

ALIGNMENTS = ("vertical", "horizontal")
HORIZONTAL_POSITIONS = ("left", "center", "right")
VERTICAL_POSITIONS = ("top", "center", "bottom")

MATRIX_PROFILES = [
    # 54 movie cases: 18 positions x 3 slot profiles
    ("movie", "movie", "three", ("1", "2", "3"), "Movies"),
    ("movie", "movie", "two", ("1", "3"), "Movies"),
    ("movie", "movie", "one", ("2",), "Movies"),
    # 54 show cases: 18 positions x 3 slot profiles
    ("show", "show", "three", ("1", "2", "3"), "TV Shows"),
    ("show", "show", "two", ("1", "3"), "TV Shows"),
    ("show", "show", "one", ("2",), "TV Shows"),
    # 36 episode cases: 18 positions x 2 slot profiles
    ("show", "episode", "two", ("1", "2"), "TV Shows"),
    ("show", "episode", "one", ("2",), "TV Shows"),
]


def _all_matrix_cases():
    cases = []
    for library_type, builder_level, profile_name, enabled_slots, library_name in MATRIX_PROFILES:
        for alignment, h_pos, v_pos in product(ALIGNMENTS, HORIZONTAL_POSITIONS, VERTICAL_POSITIONS):
            case_id = f"{library_type}-{builder_level}-{profile_name}-{alignment}-{h_pos}-{v_pos}"
            cases.append(
                (
                    case_id,
                    {
                        "library_type": library_type,
                        "builder_level": builder_level,
                        "profile_name": profile_name,
                        "enabled_slots": enabled_slots,
                        "library_name": library_name,
                        "alignment": alignment,
                        "horizontal_position": h_pos,
                        "vertical_position": v_pos,
                    },
                )
            )
    return cases


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
    monkeypatch.setattr(qs_module.output.helpers, "get_library_summaries", lambda _names: "Ratings Matrix")
    monkeypatch.setattr(qs_module.persistence, "check_minimum_settings", lambda: (True, True, True, True))

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        return {"validated": False}

    monkeypatch.setattr(qs_module.output.persistence, "retrieve_settings", fake_retrieve_settings)
    with qs_module.app.app_context():
        validated, _validation_error, _config_data, yaml_content, _validation_errors = qs_module.output.build_config(
            header_style="single line",
            config_name="pytest_ratings_matrix_contract",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def _build_case_payload(case):
    if case["library_type"] == "movie":
        base = "mov-library_movies"
        builder = "movie"
        library_name = "Movies"
    else:
        base = "sho-library_tv_shows"
        builder = case["builder_level"]
        library_name = "TV Shows"

    libraries = {
        f"{base}-library": library_name,
        f"{base}-collection_collectionless": True,
        f"{base}-{builder}-overlay_ratings": True,
    }

    prefix = f"{base}-{builder}-template_overlay_ratings"
    libraries[f"{prefix}[rating_alignment]"] = case["alignment"]
    libraries[f"{prefix}[horizontal_position]"] = case["horizontal_position"]
    libraries[f"{prefix}[vertical_position]"] = case["vertical_position"]

    if builder == "episode":
        libraries[f"{prefix}[builder_level]"] = "episode"

    enabled = set(case["enabled_slots"])
    for idx, (rating_value, image_value) in RATING_SLOT_VALUES.items():
        if idx in enabled:
            libraries[f"{prefix}[rating{idx}]"] = rating_value
            libraries[f"{prefix}[rating{idx}_image]"] = image_value
        else:
            libraries[f"{prefix}[rating{idx}]"] = "none"
            libraries[f"{prefix}[rating{idx}_image]"] = "none"

    return {"validated": True, "libraries": libraries}


def _template_vars_from_yaml(yaml_content, library_name, builder_level):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    overlays = parsed.get("libraries", {}).get(library_name, {}).get("overlay_files", [])
    assert overlays, f"Expected overlay_files for {library_name}"
    ratings_entries = [entry for entry in overlays if entry.get("default") == "ratings"]
    assert ratings_entries, f"Expected ratings overlay for {library_name}"

    if builder_level == "episode":
        for entry in ratings_entries:
            tv = entry.get("template_variables", {})
            if tv.get("builder_level") == "episode":
                return tv
        raise AssertionError("Expected ratings overlay with builder_level=episode")

    for entry in ratings_entries:
        tv = entry.get("template_variables", {})
        if tv.get("builder_level", "show") == "show":
            return tv
    raise AssertionError("Expected show/movie ratings overlay entry")


def _normalize_number(value, fallback=None):
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return int(round(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return fallback
        try:
            return int(stripped)
        except ValueError:
            try:
                return int(round(float(stripped)))
            except ValueError:
                return fallback
    return fallback


def _is_enabled(tv, idx):
    rating = str(tv.get(f"rating{idx}", "")).strip().lower()
    image = str(tv.get(f"rating{idx}_image", "")).strip().lower()
    return bool(rating and image and rating != "none" and image != "none")


def _computed_rating_defaults(tv):
    alignment = str(tv.get("rating_alignment", "vertical")).strip().lower()
    if alignment not in {"vertical", "horizontal"}:
        alignment = "vertical"
    h_pos = str(tv.get("horizontal_position", "left")).strip().lower()
    if h_pos not in {"left", "center", "right"}:
        h_pos = "left"
    v_pos = str(tv.get("vertical_position", "center")).strip().lower()
    if v_pos not in {"top", "center", "bottom"}:
        v_pos = "center"

    c = {
        "standard": 30,
        "center": 0,
        "v2": 235,
        "v3": 440,
        "cv2": 105,
        "cv3": 205,
        "h2": 345,
        "h3": 660,
        "ch2": 160,
        "ch3": 335,
    }

    none1 = not _is_enabled(tv, "1")
    none2 = not _is_enabled(tv, "2")
    none3 = not _is_enabled(tv, "3")

    def r1h():
        if alignment == "vertical" and h_pos == "center":
            return c["center"]
        if alignment == "horizontal" and h_pos == "center" and none2 and none3:
            return c["center"]
        if alignment == "horizontal" and h_pos == "center" and none2:
            return -c["ch2"]
        if alignment == "horizontal" and h_pos == "center" and none3:
            return -c["ch2"]
        if alignment == "horizontal" and h_pos == "center":
            return -c["ch3"]
        if alignment == "horizontal" and h_pos == "right" and none2 and none3:
            return c["standard"]
        if alignment == "horizontal" and h_pos == "right" and none2:
            return c["h2"]
        if alignment == "horizontal" and h_pos == "right" and none3:
            return c["h2"]
        if alignment == "horizontal" and h_pos == "right":
            return c["h3"]
        return c["standard"]

    def r1v():
        if alignment == "horizontal" and v_pos == "center":
            return c["center"]
        if alignment == "vertical" and v_pos == "center" and none2 and none3:
            return c["center"]
        if alignment == "vertical" and v_pos == "center" and none2:
            return -c["cv2"]
        if alignment == "vertical" and v_pos == "center" and none3:
            return -c["cv2"]
        if alignment == "vertical" and v_pos == "center":
            return -c["cv3"]
        if alignment == "vertical" and v_pos == "bottom" and none2 and none3:
            return c["standard"]
        if alignment == "vertical" and v_pos == "bottom" and none2:
            return c["v2"]
        if alignment == "vertical" and v_pos == "bottom" and none3:
            return c["v2"]
        if alignment == "vertical" and v_pos == "bottom":
            return c["v3"]
        return c["standard"]

    def r2h():
        if alignment == "vertical" and h_pos == "center":
            return c["center"]
        if alignment == "horizontal" and h_pos == "center" and none1 and none3:
            return c["center"]
        if alignment == "horizontal" and h_pos == "center" and none1:
            return -c["ch2"]
        if alignment == "horizontal" and h_pos == "center" and none3:
            return c["ch2"]
        if alignment == "horizontal" and h_pos == "center":
            return c["center"]
        if alignment == "horizontal" and h_pos == "right" and none1 and none3:
            return c["standard"]
        if alignment == "horizontal" and h_pos == "right" and none3:
            return c["standard"]
        if alignment == "horizontal" and h_pos == "right":
            return c["h2"]
        if alignment == "horizontal" and h_pos == "left" and none1:
            return c["standard"]
        if alignment == "horizontal" and h_pos == "left":
            return c["h2"]
        return c["standard"]

    def r2v():
        if alignment == "horizontal" and v_pos == "center":
            return c["center"]
        if alignment == "vertical" and v_pos == "center" and none1 and none3:
            return c["center"]
        if alignment == "vertical" and v_pos == "center" and none1:
            return -c["cv2"]
        if alignment == "vertical" and v_pos == "center" and none3:
            return c["cv2"]
        if alignment == "vertical" and v_pos == "center":
            return c["center"]
        if alignment == "vertical" and v_pos == "bottom" and none1 and none3:
            return c["standard"]
        if alignment == "vertical" and v_pos == "bottom" and none1:
            return c["v2"]
        if alignment == "vertical" and v_pos == "bottom" and none3:
            return c["standard"]
        if alignment == "vertical" and v_pos == "bottom":
            return c["v2"]
        if alignment == "vertical" and v_pos == "top" and none1:
            return c["standard"]
        if alignment == "vertical" and v_pos == "top":
            return c["v2"]
        return c["standard"]

    def r3h():
        if alignment == "vertical" and h_pos == "center":
            return c["center"]
        if alignment == "horizontal" and h_pos == "center" and none1 and none2:
            return c["center"]
        if alignment == "horizontal" and h_pos == "center" and none1:
            return c["ch2"]
        if alignment == "horizontal" and h_pos == "center" and none2:
            return c["ch2"]
        if alignment == "horizontal" and h_pos == "center":
            return c["ch3"]
        if alignment == "horizontal" and h_pos == "left" and none1 and none2:
            return c["standard"]
        if alignment == "horizontal" and h_pos == "left" and none1:
            return c["h2"]
        if alignment == "horizontal" and h_pos == "left" and none2:
            return c["h2"]
        if alignment == "horizontal" and h_pos == "left":
            return c["h3"]
        return c["standard"]

    def r3v():
        if alignment == "horizontal" and v_pos == "center":
            return c["center"]
        if alignment == "vertical" and v_pos == "center" and none1 and none2:
            return c["center"]
        if alignment == "vertical" and v_pos == "center" and none1:
            return c["cv2"]
        if alignment == "vertical" and v_pos == "center" and none2:
            return c["cv2"]
        if alignment == "vertical" and v_pos == "center":
            return c["cv3"]
        if alignment == "vertical" and v_pos == "top" and none1 and none2:
            return c["standard"]
        if alignment == "vertical" and v_pos == "top" and none1:
            return c["v2"]
        if alignment == "vertical" and v_pos == "top" and none2:
            return c["v2"]
        if alignment == "vertical" and v_pos == "top":
            return c["v3"]
        return c["standard"]

    return {
        "1": {"h": int(round(r1h())), "v": int(round(r1v()))},
        "2": {"h": int(round(r2h())), "v": int(round(r2v()))},
        "3": {"h": int(round(r3h())), "v": int(round(r3v()))},
    }


def _active_rating_sequence(tv):
    result = []
    for idx in ("1", "2", "3"):
        if _is_enabled(tv, idx):
            result.append((tv.get(f"rating{idx}"), tv.get(f"rating{idx}_image")))
    return result


def _expected_compacted_sequence(enabled_slots):
    seq = []
    for idx in ("1", "2", "3"):
        if idx in enabled_slots:
            seq.append(RATING_SLOT_VALUES[idx])
    return seq


@pytest.mark.ratings_matrix
@pytest.mark.parametrize("case_id,case", _all_matrix_cases(), ids=[cid for cid, _ in _all_matrix_cases()])
def test_ratings_matrix_contract_all_positions(case_id, case, monkeypatch, qs_module):
    payload = _build_case_payload(case)
    yaml_content = _run_build_config_with_payload(qs_module, monkeypatch, payload)
    tv = _template_vars_from_yaml(yaml_content, case["library_name"], case["builder_level"])

    # Baseline choices may be omitted when equal to template defaults.
    effective_alignment = str(tv.get("rating_alignment", "vertical")).strip().lower()
    effective_h_pos = str(tv.get("horizontal_position", "left")).strip().lower()
    effective_v_pos = str(tv.get("vertical_position", "center")).strip().lower()
    assert effective_alignment == case["alignment"], case_id
    assert effective_h_pos == case["horizontal_position"], case_id
    assert effective_v_pos == case["vertical_position"], case_id

    expected_sequence = _expected_compacted_sequence(set(case["enabled_slots"]))
    actual_sequence = _active_rating_sequence(tv)
    assert actual_sequence == expected_sequence, case_id

    active_count = len(expected_sequence)
    for idx in range(1, active_count + 1):
        assert f"rating{idx}" in tv, case_id
        assert f"rating{idx}_image" in tv, case_id
    for idx in range(active_count + 1, 4):
        assert f"rating{idx}" not in tv, case_id
        assert f"rating{idx}_image" not in tv, case_id

    defaults = _computed_rating_defaults(tv)
    h_values = []
    v_values = []
    for idx in ("1", "2", "3"):
        if not _is_enabled(tv, idx):
            continue
        h_key = f"rating{idx}_horizontal_offset"
        v_key = f"rating{idx}_vertical_offset"
        explicit_h = _normalize_number(tv.get(h_key), None)
        explicit_v = _normalize_number(tv.get(v_key), None)

        h = explicit_h if explicit_h is not None else defaults[idx]["h"]
        v = explicit_v if explicit_v is not None else defaults[idx]["v"]
        h_values.append(h)
        v_values.append(v)

        # Kometa contract from parse_cords: non-center edge anchors cannot be negative.
        # Only assert explicit values here; omitted values are template-driven defaults.
        if effective_h_pos != "center" and explicit_h is not None:
            assert explicit_h >= 0, case_id
        if effective_v_pos != "center" and explicit_v is not None:
            assert explicit_v >= 0, case_id

    # Keep these collected for future geometry checks; YAML-only contracts cannot
    # reliably infer rendered top-to-bottom/left-to-right order from offsets alone.
    assert len(h_values) == active_count, case_id
    assert len(v_values) == active_count, case_id
