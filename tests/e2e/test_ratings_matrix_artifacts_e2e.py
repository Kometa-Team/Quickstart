import csv
import json
import os
from datetime import datetime
from itertools import product
from pathlib import Path

import pytest
import modules.helpers as helpers
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
    ("movie", "movie", "three", ("1", "2", "3"), None, "movie"),
    ("movie", "movie", "two", ("1", "3"), None, "movie"),
    ("movie", "movie", "one", ("2",), None, "movie"),
    # 54 show cases: 18 positions x 3 slot profiles
    ("show", "show", "three", ("1", "2", "3"), "show", "show"),
    ("show", "show", "two", ("1", "3"), "show", "show"),
    ("show", "show", "one", ("2",), "show", "show"),
    # 36 episode cases: 18 positions x 2 slot profiles
    ("show", "episode", "two", ("1", "2"), "episode", "episode"),
    ("show", "episode", "one", ("2",), "episode", "episode"),
]


def _movie_library_name():
    return (os.environ.get("RATINGS_MATRIX_MOVIE_LIBRARY", "Movies") or "Movies").strip() or "Movies"


def _show_library_name():
    return (os.environ.get("RATINGS_MATRIX_SHOW_LIBRARY", "TV Shows") or "TV Shows").strip() or "TV Shows"


def _library_bases():
    existing_ids = set()
    movie_base = f"mov-library_{helpers.normalize_id(_movie_library_name(), existing_ids)}"
    show_base = f"sho-library_{helpers.normalize_id(_show_library_name(), existing_ids)}"
    return movie_base, show_base


def _all_matrix_cases():
    cases = []
    for library_type, builder_level, profile_name, enabled_slots, context_level, board_type in MATRIX_PROFILES:
        for alignment, h_pos, v_pos in product(ALIGNMENTS, HORIZONTAL_POSITIONS, VERTICAL_POSITIONS):
            case_id = f"{library_type}-{builder_level}-{profile_name}-{alignment}-{h_pos}-{v_pos}"
            cases.append(
                {
                    "case_id": case_id,
                    "library_type": library_type,
                    "builder_level": builder_level,
                    "profile_name": profile_name,
                    "enabled_slots": enabled_slots,
                    "library_name": _movie_library_name() if library_type == "movie" else _show_library_name(),
                    "alignment": alignment,
                    "horizontal_position": h_pos,
                    "vertical_position": v_pos,
                    "context_level": context_level,
                    "board_type": board_type,
                }
            )
    return cases


def _seed_library_settings_for_artifacts(monkeypatch, qs_module):
    movie_name = _movie_library_name()
    show_name = _show_library_name()
    movie_base, show_base = _library_bases()

    plex_settings = {
        "validated": False,
        "user_entered": True,
        "validated_at": None,
        "plex": {
            "tmp_movie_libraries": movie_name,
            "tmp_show_libraries": show_name,
            "tmp_music_libraries": "",
            "tmp_user_list": "",
        },
    }

    libraries = {
        f"{movie_base}-library": movie_name,
        f"{movie_base}-collection_collectionless": True,
        f"{movie_base}-movie-overlay_ratings": True,
        f"{movie_base}-movie-template_overlay_ratings[rating1]": "user",
        f"{movie_base}-movie-template_overlay_ratings[rating1_image]": "rt_tomato",
        f"{movie_base}-movie-template_overlay_ratings[rating2]": "critic",
        f"{movie_base}-movie-template_overlay_ratings[rating2_image]": "imdb",
        f"{movie_base}-movie-template_overlay_ratings[rating3]": "audience",
        f"{movie_base}-movie-template_overlay_ratings[rating3_image]": "tmdb",
        f"{show_base}-library": show_name,
        f"{show_base}-collection_collectionless": True,
        f"{show_base}-show-overlay_ratings": True,
        f"{show_base}-show-template_overlay_ratings[builder_level]": "show",
        f"{show_base}-show-template_overlay_ratings[rating1]": "user",
        f"{show_base}-show-template_overlay_ratings[rating1_image]": "rt_tomato",
        f"{show_base}-show-template_overlay_ratings[rating2]": "critic",
        f"{show_base}-show-template_overlay_ratings[rating2_image]": "imdb",
        f"{show_base}-show-template_overlay_ratings[rating3]": "audience",
        f"{show_base}-show-template_overlay_ratings[rating3_image]": "tmdb",
        f"{show_base}-episode-overlay_ratings": True,
        f"{show_base}-episode-template_overlay_ratings[builder_level]": "episode",
        f"{show_base}-episode-template_overlay_ratings[rating1]": "user",
        f"{show_base}-episode-template_overlay_ratings[rating1_image]": "rt_tomato",
        f"{show_base}-episode-template_overlay_ratings[rating2]": "critic",
        f"{show_base}-episode-template_overlay_ratings[rating2_image]": "imdb",
    }
    libraries_settings = {
        "validated": True,
        "user_entered": True,
        "validated_at": None,
        "libraries": libraries,
    }

    original_retrieve = qs_module.persistence.retrieve_settings

    def fake_retrieve_settings(section):
        if section in ("010-plex", "plex"):
            return json.loads(json.dumps(plex_settings))
        if section in ("025-libraries", "libraries"):
            return json.loads(json.dumps(libraries_settings))
        return original_retrieve(section)

    monkeypatch.setattr(qs_module.persistence, "retrieve_settings", fake_retrieve_settings)


def _ratings_context(page, library_id=None, builder_level=None):
    return page.evaluate(
        """([libraryId, builderLevel]) => {
          const cards = Array.from(document.querySelectorAll('#library-form-container .library-settings-card'));
          const card = libraryId
            ? cards.find(c => String(c.dataset.libraryId || '') === String(libraryId)) || null
            : null;
          const root = card || document;
          const groups = Array.from(root.querySelectorAll('.template-toggle-group[data-overlay-id="overlay_ratings"]'));
          if (!groups.length) return null;
          const wantedLevel = (builderLevel || '').toString().toLowerCase();
          const pick = groups.find(group => {
            const builder = group.querySelector('[name$="[builder_level]"]');
            if (!wantedLevel) return !builder;
            if (!builder) return false;
            const raw = (builder.value || builder.dataset.default || '').toString().toLowerCase();
            return raw === wantedLevel;
          }) || groups[0];
          const templateName = pick?.dataset?.overlayTemplate || null;
          if (!templateName) return null;
          return { templateName };
        }""",
        [library_id, builder_level],
    )


def _load_library_with_ratings(page, builder_level=None, library_type=None):
    library_ids = page.evaluate(
        """(wantedType) => Array.from(document.querySelectorAll('#libraryPicker option[value]'))
          .filter(opt => !!opt.value && (!wantedType || (opt.dataset.libraryType || '') === wantedType))
          .map(opt => opt.value)""",
        library_type,
    )
    for library_id in library_ids:
        page.select_option("#libraryPicker", library_id)
        page.wait_for_function(
            """(libraryId) => {
              const card = document.querySelector('#library-form-container .library-settings-card');
              return !!card && card.dataset.libraryId === libraryId;
            }""",
            arg=library_id,
            timeout=10000,
        )
        page.wait_for_timeout(200)
        ctx = _ratings_context(page, library_id, builder_level)
        if ctx:
            ctx["libraryId"] = library_id
            return ctx
    return None


def _set_by_name(page, name, value):
    ok = page.evaluate(
        """([name, value]) => {
          const el = document.querySelector(`[name="${name}"]`);
          if (!el) return false;
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }""",
        [name, value],
    )
    assert ok, f"Missing input/select: {name}"


def _set_if_exists(page, name, value):
    return page.evaluate(
        """([name, value]) => {
          const el = document.querySelector(`[name="${name}"]`);
          if (!el) return false;
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }""",
        [name, value],
    )


def _configure_rating_slots(page, template, enabled):
    slot_values = {
        "rating1": ("user", "rt_tomato"),
        "rating2": ("critic", "imdb"),
        "rating3": ("audience", "tmdb"),
    }
    for slot, (rating_value, image_value) in slot_values.items():
        use_slot = slot in enabled
        _set_if_exists(page, f"{template}[{slot}]", rating_value if use_slot else "")
        _set_if_exists(page, f"{template}[{slot}_image]", image_value if use_slot else "")


def _enable_overlay_group(page, template):
    return page.evaluate(
        """(template) => {
          const group = document.querySelector(`[data-overlay-template="${template}"]`);
          if (!group) return false;
          const toggle = group.querySelector('.overlay-toggle');
          if (!toggle) return false;
          if (!toggle.checked) {
            toggle.checked = true;
            toggle.dispatchEvent(new Event('change', { bubbles: true }));
          }
          return true;
        }""",
        template,
    )


def _get_number_or_none(page, name):
    return page.evaluate(
        """(name) => {
          const el = document.querySelector(`[name="${name}"]`);
          if (!el) return null;
          return Number(el.value);
        }""",
        name,
    )


def _slot_offsets(page, template):
    return {
        "rating1": {
            "h": _get_number_or_none(page, f"{template}[rating1_horizontal_offset]"),
            "v": _get_number_or_none(page, f"{template}[rating1_vertical_offset]"),
        },
        "rating2": {
            "h": _get_number_or_none(page, f"{template}[rating2_horizontal_offset]"),
            "v": _get_number_or_none(page, f"{template}[rating2_vertical_offset]"),
        },
        "rating3": {
            "h": _get_number_or_none(page, f"{template}[rating3_horizontal_offset]"),
            "v": _get_number_or_none(page, f"{template}[rating3_vertical_offset]"),
        },
    }


def _force_visible_for_screenshot(page, selector):
    return page.evaluate(
        """(selector) => {
          const target = document.querySelector(selector);
          if (!target) return false;

          let node = target;
          while (node) {
            if (node.classList && node.classList.contains('collapse') && !node.classList.contains('show')) {
              node.classList.add('show');
            }
            const style = window.getComputedStyle(node);
            if (style.display === 'none') node.style.display = 'block';
            if (style.visibility === 'hidden') node.style.visibility = 'visible';
            if (style.opacity === '0') node.style.opacity = '1';
            node = node.parentElement;
          }

          target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
          const rect = target.getBoundingClientRect();
          const finalStyle = window.getComputedStyle(target);
          return (
            rect.width > 0 &&
            rect.height > 0 &&
            finalStyle.display !== 'none' &&
            finalStyle.visibility !== 'hidden' &&
            finalStyle.opacity !== '0'
          );
        }""",
        selector,
    )


def _build_case_payload(case, ui_offsets):
    movie_name = _movie_library_name()
    show_name = _show_library_name()
    movie_base, show_base = _library_bases()

    if case["library_type"] == "movie":
        base = movie_base
        builder = "movie"
        library_name = movie_name
    else:
        base = show_base
        builder = case["builder_level"]
        library_name = show_name

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
            libraries[f"{prefix}[rating{idx}_horizontal_offset]"] = int(ui_offsets[f"rating{idx}"]["h"])
            libraries[f"{prefix}[rating{idx}_vertical_offset]"] = int(ui_offsets[f"rating{idx}"]["v"])
        else:
            libraries[f"{prefix}[rating{idx}]"] = "none"
            libraries[f"{prefix}[rating{idx}_image]"] = "none"

    return {"validated": True, "libraries": libraries}


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
            config_name="pytest_ratings_matrix_artifacts",
        )
    assert isinstance(validated, bool)
    assert yaml_content
    return yaml_content


def _template_vars_from_yaml(yaml_content, library_name, builder_level):
    parser = YAML(typ="safe", pure=True)
    parsed = parser.load(yaml_content)
    overlays = parsed.get("libraries", {}).get(library_name, {}).get("overlay_files", [])
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


def _artifact_root():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    custom = os.environ.get("RATINGS_MATRIX_ARTIFACT_DIR", "").strip()
    if custom:
        if "{timestamp}" in custom:
            return Path(custom.replace("{timestamp}", stamp))
        return Path(custom) / stamp
    return Path("artifacts") / "ratings-matrix" / stamp


def _write_reports(output_dir, rows):
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "summary.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    csv_path = output_dir / "summary.csv"
    fieldnames = [
        "case_id",
        "library_type",
        "builder_level",
        "enabled_slots",
        "alignment",
        "horizontal_position",
        "vertical_position",
        "canvas_png",
        "yaml_file",
        "status",
        "notes",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    passed = sum(1 for r in rows if r.get("status") == "PASS")
    failed = sum(1 for r in rows if r.get("status") == "FAIL")

    md_lines = [
        "# Ratings Matrix Artifact Report",
        "",
        f"- Total cases: {len(rows)}",
        f"- Passed: {passed}",
        f"- Failed: {failed}",
        "",
        "## Files",
        "",
        "- `summary.json`",
        "- `summary.csv`",
        "- `canvas/*.png`",
        "- `yaml/*.yml`",
        "",
    ]

    if failed:
        md_lines.append("## Failed Cases")
        md_lines.append("")
        for row in rows:
            if row.get("status") == "FAIL":
                md_lines.append(f"- `{row['case_id']}`: {row.get('notes', '')}")

    (output_dir / "README.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


@pytest.mark.e2e
@pytest.mark.ratings_artifacts
def test_generate_ratings_matrix_artifacts(page, live_server, monkeypatch, qs_module):
    output_dir = _artifact_root()
    canvas_dir = output_dir / "canvas"
    yaml_dir = output_dir / "yaml"
    canvas_dir.mkdir(parents=True, exist_ok=True)
    yaml_dir.mkdir(parents=True, exist_ok=True)

    cases = _all_matrix_cases()
    rows = []
    failures = []

    _seed_library_settings_for_artifacts(monkeypatch, qs_module)

    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    profile_context = {}
    for case in cases:
        case_id = case["case_id"]
        png_path = canvas_dir / f"{case_id}.png"
        yaml_path = yaml_dir / f"{case_id}.yml"

        try:
            profile_key = (case["library_type"], case["builder_level"], case["profile_name"])
            context = profile_context.get(profile_key)
            if context is None:
                ctx = _load_library_with_ratings(
                    page,
                    builder_level=case["context_level"],
                    library_type=case["library_type"],
                )
                if not ctx:
                    failures.append(f"No ratings context found for profile {profile_key}")
                    profile_context[profile_key] = None
                    continue
                template = ctx["templateName"]
                library_id = ctx.get("libraryId")
                if not library_id:
                    failures.append(f"No active library card found for profile {profile_key}")
                    profile_context[profile_key] = None
                    continue
                _enable_overlay_group(page, template)
                _set_if_exists(page, f"{template}[builder_level]", case["builder_level"])
                enabled_names = {f"rating{idx}" for idx in case["enabled_slots"]}
                _configure_rating_slots(page, template, enabled_names)
                context = {"template": template, "library_id": library_id}
                profile_context[profile_key] = context

            if context is None:
                continue

            template = context["template"]
            library_id = context["library_id"]
            enabled_names = {f"rating{idx}" for idx in case["enabled_slots"]}
            _configure_rating_slots(page, template, enabled_names)

            _set_by_name(page, f"{template}[rating_alignment]", case["alignment"])
            _set_by_name(page, f"{template}[horizontal_position]", case["horizontal_position"])
            _set_by_name(page, f"{template}[vertical_position]", case["vertical_position"])
            _set_if_exists(page, f"{template}[builder_level]", case["builder_level"])
            page.wait_for_timeout(220)

            board_selector = (
                f"#library-form-container .library-settings-card[data-library-id=\"{library_id}\"] "
                f".overlay-board[data-overlay-type=\"{case['board_type']}\"] .overlay-board-canvas"
            )
            board = page.locator(board_selector).first

            notes = []
            status = "PASS"

            if board.count() == 0:
                status = "FAIL"
                notes.append(f"Missing canvas selector: {board_selector}")
            else:
                visible = _force_visible_for_screenshot(page, board_selector)
                if not visible:
                    status = "FAIL"
                    notes.append(f"Canvas not visible for screenshot: {board_selector}")
                else:
                    try:
                        board.screenshot(path=str(png_path), timeout=8000)
                    except Exception as e:
                        status = "FAIL"
                        notes.append(f"Canvas screenshot error: {type(e).__name__}: {e}")

            ui_offsets = _slot_offsets(page, template)
            payload = _build_case_payload(case, ui_offsets)
            yaml_content = _run_build_config_with_payload(qs_module, monkeypatch, payload)
            yaml_path.write_text(yaml_content, encoding="utf-8")

            tv = _template_vars_from_yaml(yaml_content, case["library_name"], case["builder_level"])

            if str(tv.get("rating_alignment", "vertical")).lower() != case["alignment"]:
                status = "FAIL"
                notes.append("YAML rating_alignment mismatch")
            if str(tv.get("horizontal_position", "left")).lower() != case["horizontal_position"]:
                status = "FAIL"
                notes.append("YAML horizontal_position mismatch")
            if str(tv.get("vertical_position", "center")).lower() != case["vertical_position"]:
                status = "FAIL"
                notes.append("YAML vertical_position mismatch")

            for idx in case["enabled_slots"]:
                slot = f"rating{idx}"
                y_h = tv.get(f"{slot}_horizontal_offset")
                y_v = tv.get(f"{slot}_vertical_offset")
                if y_h is not None and int(y_h) != int(ui_offsets[slot]["h"]):
                    status = "FAIL"
                    notes.append(f"{slot} horizontal offset differs UI({ui_offsets[slot]['h']}) vs YAML({y_h})")
                if y_v is not None and int(y_v) != int(ui_offsets[slot]["v"]):
                    status = "FAIL"
                    notes.append(f"{slot} vertical offset differs UI({ui_offsets[slot]['v']}) vs YAML({y_v})")

            if case["horizontal_position"] != "center":
                for idx in case["enabled_slots"]:
                    slot = f"rating{idx}"
                    y_h = tv.get(f"{slot}_horizontal_offset")
                    if y_h is not None and int(y_h) < 0:
                        status = "FAIL"
                        notes.append(f"{slot} horizontal offset is negative on edge anchor")
            if case["vertical_position"] != "center":
                for idx in case["enabled_slots"]:
                    slot = f"rating{idx}"
                    y_v = tv.get(f"{slot}_vertical_offset")
                    if y_v is not None and int(y_v) < 0:
                        status = "FAIL"
                        notes.append(f"{slot} vertical offset is negative on edge anchor")

            row = {
                "case_id": case_id,
                "library_type": case["library_type"],
                "builder_level": case["builder_level"],
                "enabled_slots": "|".join(case["enabled_slots"]),
                "alignment": case["alignment"],
                "horizontal_position": case["horizontal_position"],
                "vertical_position": case["vertical_position"],
                "canvas_png": str(png_path).replace("\\", "/"),
                "yaml_file": str(yaml_path).replace("\\", "/"),
                "status": status,
                "notes": "; ".join(notes),
            }
            rows.append(row)
            if status == "FAIL":
                failures.append(f"{case_id}: {row['notes']}")
        except Exception as e:
            row = {
                "case_id": case_id,
                "library_type": case["library_type"],
                "builder_level": case["builder_level"],
                "enabled_slots": "|".join(case["enabled_slots"]),
                "alignment": case["alignment"],
                "horizontal_position": case["horizontal_position"],
                "vertical_position": case["vertical_position"],
                "canvas_png": str(png_path).replace("\\", "/"),
                "yaml_file": str(yaml_path).replace("\\", "/"),
                "status": "FAIL",
                "notes": f"Unhandled case exception: {type(e).__name__}: {e}",
            }
            rows.append(row)
            failures.append(f"{case_id}: {row['notes']}")

    _write_reports(output_dir, rows)

    if failures:
        preview = "\n".join(failures[:25])
        pytest.fail(
            f"Ratings artifact matrix found {len(failures)} issue(s). "
            f"See {output_dir} for details.\n{preview}"
        )
