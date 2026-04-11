import base64
import csv
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from itertools import product
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
import modules.helpers as helpers
from PIL import Image, ImageChops
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from ruamel.yaml import YAML

RATING_SLOT_VALUES_MOVIE_SHOW = {
    "1": ("user", "rt_tomato"),
    "2": ("critic", "imdb"),
    "3": ("audience", "tmdb"),
}
RATING_SLOT_VALUES_EPISODE = {
    "1": ("critic", "imdb"),
    "2": ("audience", "tmdb"),
}
RATING_FONT_BY_IMAGE = {
    "anidb": "Arimo-Medium.ttf",
    "imdb": "Roboto-Medium.ttf",
    "letterboxd": "Montserrat-Bold.ttf",
    "tmdb": "Consensus-SemiBold.otf",
    "metacritic": "Montserrat-SemiBold.ttf",
    "rt_popcorn": "LibreFranklin-Bold.ttf",
    "rt_tomato": "LibreFranklin-Bold.ttf",
    "trakt": "Figtree-Medium.ttf",
    "myanimelist": "Lato-Regular.ttf",
    "mal": "Lato-Regular.ttf",
    "mdblist": "Lato-Regular.ttf",
    "mdb": "Lato-Regular.ttf",
    "star": "Roboto-Medium.ttf",
    "plex_star": "Roboto-Medium.ttf",
}

CASE_SETTLE_MS = max(50, int(os.environ.get("RATINGS_MATRIX_SETTLE_MS", "120")))
LAYER_READY_TIMEOUT_MS = max(500, int(os.environ.get("RATINGS_LAYER_READY_TIMEOUT_MS", "1500")))
SHOW_LAYER_READY_TIMEOUT_MS = max(
    LAYER_READY_TIMEOUT_MS,
    int(os.environ.get("RATINGS_SHOW_LAYER_READY_TIMEOUT_MS", str(LAYER_READY_TIMEOUT_MS * 2))),
)
LIBRARY_LOAD_TIMEOUT_MS = max(2000, int(os.environ.get("RATINGS_LIBRARY_LOAD_TIMEOUT_MS", "20000")))
SHOW_LIBRARY_LOAD_TIMEOUT_MS = max(
    LIBRARY_LOAD_TIMEOUT_MS,
    int(os.environ.get("RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS", str(LIBRARY_LOAD_TIMEOUT_MS * 2))),
)
LIBRARY_LOAD_RETRIES = max(1, int(os.environ.get("RATINGS_LIBRARY_LOAD_RETRIES", "3")))
CASE_OFFSET = max(0, int(os.environ.get("RATINGS_MATRIX_CASE_OFFSET", "0")))
CASE_LIMIT = max(0, int(os.environ.get("RATINGS_MATRIX_CASE_LIMIT", "0")))
CASE_IDS_RAW = (os.environ.get("RATINGS_MATRIX_CASE_IDS", "") or "").strip()
CASE_IDS_FILE = (os.environ.get("RATINGS_MATRIX_CASE_IDS_FILE", "") or "").strip()
RANDOM_COUNT = max(0, int(os.environ.get("RATINGS_MATRIX_RANDOM_COUNT", "0")))
PROGRESS_WRITE_INTERVAL = max(1, int(os.environ.get("RATINGS_PROGRESS_WRITE_INTERVAL", "10")))
RANDOM_SEED_RAW = (os.environ.get("RATINGS_MATRIX_RANDOM_SEED", "") or "").strip()
EXECUTION_MODE = (os.environ.get("RATINGS_MATRIX_EXECUTION_MODE", "batch") or "batch").strip().lower()
CHUNK_SIZE = max(1, int(os.environ.get("RATINGS_MATRIX_CHUNK_SIZE", "12")))
WITH_KOMETA_RENDER = str(os.environ.get("RATINGS_MATRIX_WITH_KOMETA", "1")).strip().lower() not in {"0", "false", "no"}
FAIL_ON_DIFF = str(os.environ.get("RATINGS_MATRIX_FAIL_ON_DIFF", "0")).strip().lower() in {"1", "true", "yes"}
DIFF_THRESHOLD_PERCENT = max(0.0, float(os.environ.get("RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT", "0.0")))
DIFF_IGNORE_ALPHA = str(os.environ.get("RATINGS_MATRIX_DIFF_IGNORE_ALPHA", "1")).strip().lower() in {"1", "true", "yes"}
DIFF_USE_SLOT_THRESHOLDS = str(os.environ.get("RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS", "1")).strip().lower() in {
    "1",
    "true",
    "yes",
}
DIFF_THRESHOLD_ONE_SLOT_PERCENT = max(0.0, float(os.environ.get("RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT", "0.80")))
DIFF_THRESHOLD_TWO_SLOT_PERCENT = max(0.0, float(os.environ.get("RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT", "1.50")))
DIFF_THRESHOLD_THREE_SLOT_PERCENT = max(0.0, float(os.environ.get("RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT", "2.80")))
INCLUDE_NUDGES = str(os.environ.get("RATINGS_MATRIX_INCLUDE_NUDGES", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
}
NUDGE_PROFILES_RAW = (os.environ.get("RATINGS_MATRIX_NUDGE_PROFILES", "none") or "none").strip()
NUDGE_APPLY_TO = (os.environ.get("RATINGS_MATRIX_NUDGE_APPLY_TO", "enabled_slots") or "enabled_slots").strip().lower()
FAILED_PROFILE = object()

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


def _profile_group_key(profile):
    return profile[0], profile[1]


def _slugify_nudge_name(value):
    return (value or "none").replace("+", "p").replace("-", "m").replace(" ", "")


def _parse_nudge_token(token):
    raw = (token or "").strip().lower().replace(" ", "")
    if not raw or raw == "none":
        return {"name": "none", "dx": 0, "dy": 0}
    if raw.startswith("hv") and len(raw) > 2:
        delta = int(raw[2:])
        return {"name": f"hv{delta:+d}", "dx": delta, "dy": delta}
    if raw.startswith("h") and "v" in raw[1:]:
        v_index = raw.index("v", 1)
        dx = int(raw[1:v_index])
        dy = int(raw[v_index + 1 :])
        return {"name": f"h{dx:+d}v{dy:+d}", "dx": dx, "dy": dy}
    if raw.startswith("v") and "h" in raw[1:]:
        h_index = raw.index("h", 1)
        dy = int(raw[1:h_index])
        dx = int(raw[h_index + 1 :])
        return {"name": f"h{dx:+d}v{dy:+d}", "dx": dx, "dy": dy}
    if raw.startswith("h") and len(raw) > 1:
        dx = int(raw[1:])
        return {"name": f"h{dx:+d}", "dx": dx, "dy": 0}
    if raw.startswith("v") and len(raw) > 1:
        dy = int(raw[1:])
        return {"name": f"v{dy:+d}", "dx": 0, "dy": dy}
    raise ValueError(f"Unsupported nudge profile token: {token}")


def _format_eta(seconds):
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "unknown"
    total = int(round(seconds))
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}h{mins:02d}m{secs:02d}s"
    if mins:
        return f"{mins}m{secs:02d}s"
    return f"{secs}s"


def _nudge_profiles():
    if not INCLUDE_NUDGES:
        return [{"name": "none", "dx": 0, "dy": 0}]
    parsed = []
    for token in [part.strip() for part in NUDGE_PROFILES_RAW.split(",") if part.strip()]:
        try:
            parsed.append(_parse_nudge_token(token))
        except ValueError:
            continue
    if not parsed:
        return [{"name": "none", "dx": 0, "dy": 0}]
    deduped = []
    seen = set()
    for profile in parsed:
        key = (profile["dx"], profile["dy"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(profile)
    return deduped


def _ordered_matrix_profiles():
    raw = (os.environ.get("RATINGS_MATRIX_PROFILE_ORDER", "") or "").strip().lower()
    if not raw:
        return MATRIX_PROFILES

    alias_map = {
        "movie": ("movie", "movie"),
        "show": ("show", "show"),
        "episode": ("show", "episode"),
        "movie:movie": ("movie", "movie"),
        "show:show": ("show", "show"),
        "show:episode": ("show", "episode"),
    }

    requested_keys = []
    for token in [t.strip() for t in raw.split(",") if t.strip()]:
        key = alias_map.get(token)
        if key and key not in requested_keys:
            requested_keys.append(key)

    if not requested_keys:
        return MATRIX_PROFILES

    grouped = {}
    for profile in MATRIX_PROFILES:
        grouped.setdefault(_profile_group_key(profile), []).append(profile)

    ordered = []
    used = set()
    for key in requested_keys:
        for profile in grouped.get(key, []):
            ordered.append(profile)
            used.add(profile)

    for profile in MATRIX_PROFILES:
        if profile not in used:
            ordered.append(profile)
    return ordered


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
    nudge_profiles = _nudge_profiles()
    for library_type, builder_level, profile_name, enabled_slots, context_level, board_type in _ordered_matrix_profiles():
        for alignment, h_pos, v_pos, nudge in product(ALIGNMENTS, HORIZONTAL_POSITIONS, VERTICAL_POSITIONS, nudge_profiles):
            nudge_name = nudge["name"]
            case_id = f"{library_type}-{builder_level}-{profile_name}-{alignment}-{h_pos}-{v_pos}" f"-nudge_{_slugify_nudge_name(nudge_name)}"
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
                    "nudge_profile": nudge_name,
                    "nudge_dx": int(nudge["dx"]),
                    "nudge_dy": int(nudge["dy"]),
                }
            )
    return cases


def _execution_mode():
    if EXECUTION_MODE in {"stream", "chunked"}:
        return EXECUTION_MODE
    return "batch"


def _random_sample_cases(cases):
    if RANDOM_COUNT <= 0:
        return list(cases)
    if not cases:
        return []

    families = ("movie", "show", "episode")
    by_family = {family: [c for c in cases if c.get("board_type") == family] for family in families}
    required_families = [family for family in families if by_family[family]]
    min_required = len(required_families)
    target_count = min(max(RANDOM_COUNT, min_required), len(cases))

    seed_value = None
    if RANDOM_SEED_RAW:
        try:
            seed_value = int(RANDOM_SEED_RAW)
        except ValueError:
            seed_value = sum(ord(ch) for ch in RANDOM_SEED_RAW)
    else:
        seed_value = random.SystemRandom().randint(1, 2**31 - 1)

    rng = random.Random(seed_value)
    selected = []
    used_ids = set()

    for family in required_families:
        pick = rng.choice(by_family[family])
        selected.append(pick)
        used_ids.add(pick["case_id"])

    remaining = [c for c in cases if c["case_id"] not in used_ids]
    needed = target_count - len(selected)
    if needed > 0:
        selected.extend(rng.sample(remaining, needed))

    rng.shuffle(selected)
    print(
        f"[ratings-artifacts] random mode enabled count={target_count} seed={seed_value} " f"required_families={','.join(required_families)}",
        flush=True,
    )
    return selected


def _select_matrix_cases():
    all_cases = _all_matrix_cases()
    requested_case_ids = _requested_case_ids()
    if requested_case_ids:
        by_id = {case["case_id"]: case for case in all_cases}
        selected = []
        missing = []
        for case_id in requested_case_ids:
            match = by_id.get(case_id)
            if match:
                selected.append(match)
            else:
                missing.append(case_id)
        if missing:
            sample = ", ".join(missing[:5])
            suffix = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
            raise AssertionError("RATINGS_MATRIX_CASE_IDS filter contains unknown case id(s): " f"{sample}{suffix}. Check nudge/profile settings and case id spelling.")
        print(
            f"[ratings-artifacts] case-id filter enabled count={len(selected)} " "(offset/limit/random ignored)",
            flush=True,
        )
        return selected

    if CASE_LIMIT > 0:
        sliced = all_cases[CASE_OFFSET : CASE_OFFSET + CASE_LIMIT]
    elif CASE_OFFSET > 0:
        sliced = all_cases[CASE_OFFSET:]
    else:
        sliced = all_cases
    return _random_sample_cases(sliced)


def _parse_case_id_tokens(raw_text):
    if not raw_text:
        return []
    tokens = []
    seen = set()
    for part in re.split(r"[\r\n,;|]+", raw_text):
        token = part.strip()
        if not token or token.startswith("#"):
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _requested_case_ids():
    selected = []
    seen = set()

    def _append_unique(values):
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            selected.append(value)

    _append_unique(_parse_case_id_tokens(CASE_IDS_RAW))

    if CASE_IDS_FILE:
        file_path = Path(CASE_IDS_FILE)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        if not file_path.exists():
            raise AssertionError(f"RATINGS_MATRIX_CASE_IDS_FILE not found: {file_path}")
        _append_unique(_parse_case_id_tokens(file_path.read_text(encoding="utf-8")))

    return selected


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
        f"{show_base}-episode-template_overlay_ratings[rating1]": "critic",
        f"{show_base}-episode-template_overlay_ratings[rating1_image]": "imdb",
        f"{show_base}-episode-template_overlay_ratings[rating2]": "audience",
        f"{show_base}-episode-template_overlay_ratings[rating2_image]": "tmdb",
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
    timeout_ms = SHOW_LIBRARY_LOAD_TIMEOUT_MS if str(library_type or "").lower() == "show" else LIBRARY_LOAD_TIMEOUT_MS
    per_attempt_timeout_ms = max(1500, timeout_ms // max(1, LIBRARY_LOAD_RETRIES))
    for library_id in library_ids:
        for attempt in range(1, LIBRARY_LOAD_RETRIES + 1):
            try:
                page.select_option("#libraryPicker", library_id)
                page.wait_for_function(
                    """(libraryId) => {
                      return !!document.querySelector(
                        `#library-form-container .library-settings-card[data-library-id="${libraryId}"]`
                      );
                    }""",
                    arg=library_id,
                    timeout=per_attempt_timeout_ms,
                )
                page.wait_for_timeout(200)
                ctx = _ratings_context(page, library_id, builder_level)
                if ctx:
                    ctx["libraryId"] = library_id
                    return ctx
            except PlaywrightTimeoutError:
                # Intermittent library fragment/render lag is expected on some hosts.
                # Retry the same library before failing profile bootstrap.
                if attempt < LIBRARY_LOAD_RETRIES:
                    page.wait_for_timeout(400)
                    continue
            # Context can still be missing right after the card appears; brief settle before retry.
            if attempt < LIBRARY_LOAD_RETRIES:
                page.wait_for_timeout(250)
    return None


def _ensure_library_card_loaded(page, library_id, library_type=None):
    timeout_ms = SHOW_LIBRARY_LOAD_TIMEOUT_MS if str(library_type or "").lower() == "show" else LIBRARY_LOAD_TIMEOUT_MS
    per_attempt_timeout_ms = max(1500, timeout_ms // max(1, LIBRARY_LOAD_RETRIES))
    for attempt in range(1, LIBRARY_LOAD_RETRIES + 1):
        try:
            page.select_option("#libraryPicker", library_id)
            page.wait_for_function(
                """(id) => !!document.querySelector(
                  `#library-form-container .library-settings-card[data-library-id="${id}"]`
                )""",
                arg=library_id,
                timeout=per_attempt_timeout_ms,
            )
            page.wait_for_timeout(120)
            return True
        except PlaywrightTimeoutError:
            if attempt < LIBRARY_LOAD_RETRIES:
                page.wait_for_timeout(350)
                continue
    return False


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


def _slot_values_for_builder(builder_level):
    return RATING_SLOT_VALUES_EPISODE if str(builder_level or "").lower() == "episode" else RATING_SLOT_VALUES_MOVIE_SHOW


def _configure_rating_slots(page, template, enabled, builder_level="show"):
    slot_values = _slot_values_for_builder(builder_level)
    for idx, (rating_value, image_value) in slot_values.items():
        slot = f"rating{idx}"
        use_slot = slot in enabled
        _set_if_exists(page, f"{template}[{slot}]", rating_value if use_slot else "")
        _set_if_exists(page, f"{template}[{slot}_image]", image_value if use_slot else "")


def _apply_nudge_offsets(page, board_selector, library_id, board_type, template, case):
    dx = int(case.get("nudge_dx", 0) or 0)
    dy = int(case.get("nudge_dy", 0) or 0)
    if dx == 0 and dy == 0:
        return True, ""

    result = page.evaluate(
        """([selector, libId, type, templateName, dx, dy]) => {
          const board = document.querySelector(selector);
          if (!board) return { ok: false, error: 'board missing' };

          // Ratings overlay is rendered as a composite layer; select it so board nudge
          // path uses the same clamp/math as real user interactions.
          let selected = false;
          if (typeof board._overlaySelectById === 'function') {
            try {
              selected = !!board._overlaySelectById(templateName);
            } catch (_err) {
              selected = false;
            }
          }
          if (!selected) {
            const fallbackLayer = board.querySelector('.overlay-board-layer[data-overlay-type="overlay_ratings"]');
            if (fallbackLayer) {
              fallbackLayer.click();
              selected = true;
            }
          }
          if (!selected) return { ok: false, error: `ratings layer not selectable for ${templateName}` };

          const root = board.closest('.library-settings-card') || document;
          const stepSelectId = `${libId}-${type}-nudge-step`;
          const stepSelect = root.querySelector(`#${stepSelectId}`) || root.querySelector('[data-overlay-board-nudge-step]');
          if (!stepSelect) return { ok: false, error: `nudge step select missing (${stepSelectId})` };

          const hasStep = (val) => Array.from(stepSelect.options || []).some(opt => String(opt.value) === String(val));
          const clickDir = (dir, amount) => {
            if (!amount) return true;
            const btn = root.querySelector(`[data-overlay-board-nudge="${dir}"]`);
            if (!btn) return false;
            let remaining = Math.abs(Number(amount) || 0);
            while (remaining > 0) {
              const step = (remaining >= 5 && hasStep(5)) ? 5 : 1;
              stepSelect.value = String(step);
              stepSelect.dispatchEvent(new Event('change', { bubbles: true }));
              btn.click();
              remaining -= step;
            }
            return true;
          };

          const okX = dx > 0 ? clickDir('right', dx) : clickDir('left', -dx);
          const okY = dy > 0 ? clickDir('down', dy) : clickDir('up', -dy);
          return (okX && okY) ? { ok: true } : { ok: false, error: 'nudge button missing' };
        }""",
        [board_selector, library_id, board_type, template, dx, dy],
    )
    if not result or not result.get("ok"):
        reason = (result or {}).get("error", "unknown nudge error")
        return False, f"Nudge via board controls failed ({NUDGE_APPLY_TO}): {reason}"
    return True, ""


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


def _mock_remote_rating_assets(page):
    repo_root = Path(__file__).resolve().parents[2]
    rating_dir = repo_root / "config" / "kometa" / "defaults" / "overlays" / "images" / "rating"
    fallback_path = str((repo_root / "static" / "favicon.png").resolve())

    file_map = {}
    if rating_dir.exists():
        for fp in rating_dir.glob("*.png"):
            file_map[fp.name.lower()] = str(fp.resolve())

    alias_map = {
        "imdb.png": "imdb.png",
        "tmdb.png": "tmdb.png",
        "mdblist.png": "mdblist.png",
        "mal.png": "mal.png",
        "anidb.png": "anidb.png",
        "metacritic.png": "metacritic.png",
        "letterboxd.png": "letterboxd.png",
        "trakt.png": "trakt.png",
        "star.png": "star.png",
        "rt-crit-fresh.png": "rt-crit-fresh.png",
        "rt-crit-rotten.png": "rt-crit-rotten.png",
        "rt-aud-fresh.png": "rt-aud-fresh.png",
        "rt-aud-rotten.png": "rt-aud-rotten.png",
    }

    def _resolve_local_rating_path(url):
        parsed = urlparse(url)
        basename = unquote(Path(parsed.path).name).strip()
        if not basename:
            return fallback_path
        key = basename.lower()
        direct = file_map.get(key)
        if direct:
            return direct
        alias = alias_map.get(key)
        if alias:
            return file_map.get(alias, fallback_path)
        compact = key.replace(" ", "").replace("_", "").replace("-", "")
        for fname, full_path in file_map.items():
            normalized = fname.replace(" ", "").replace("_", "").replace("-", "")
            if normalized == compact:
                return full_path
        return fallback_path

    def _fulfill(route):
        try:
            target = _resolve_local_rating_path(route.request.url)
            route.fulfill(path=target, content_type="image/png")
        except Exception:
            route.fulfill(path=fallback_path, content_type="image/png")

    page.route("**://raw.githubusercontent.com/Kometa-Team/Kometa/**/overlays/images/rating/*.png", _fulfill)
    page.route("**://kometa.wiki/**/assets/images/defaults/overlays/ratings.png", _fulfill)


def _mock_generate_preview_requests(page):
    page.route(
        "**/generate_preview",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"status":"success","message":"mocked by ratings artifact test"}',
        ),
    )


def _set_board_alignment_guide(page, library_id, board_type):
    image_name = "overlay_alignment_guide_episodes.png" if board_type == "episode" else "overlay_alignment_guide.png"
    page.evaluate(
        """([libraryId, type, imageName]) => {
          const dropdown = document.getElementById(`${libraryId}-${type}-image-dropdown`);
          const hidden = document.getElementById(`${libraryId}-${type}_selected_image`);
          if (dropdown) {
            const options = Array.from(dropdown.options || []);
            if (!options.some(opt => opt.value === imageName)) {
              const opt = document.createElement('option');
              opt.value = imageName;
              opt.textContent = imageName;
              dropdown.appendChild(opt);
            }
            dropdown.value = imageName;
            dropdown.dispatchEvent(new Event('change', { bubbles: true }));
          }
          if (hidden) hidden.value = imageName;
          if (window.ImageHandler?.updateOverlayBoardBackground) {
            window.ImageHandler.updateOverlayBoardBackground(libraryId, type, imageName);
          }
        }""",
        [library_id, board_type, image_name],
    )


def _wait_for_rating_layer_ready(page, board_selector, board_type=None):
    timeout_ms = SHOW_LAYER_READY_TIMEOUT_MS if str(board_type or "").lower() == "show" else LAYER_READY_TIMEOUT_MS
    return page.wait_for_function(
        """(selector) => {
          const board = document.querySelector(selector);
          if (!board) return false;
          const canvas = board.querySelector('.overlay-board-canvas');
          if (!canvas) return false;
          const layers = Array.from(canvas.querySelectorAll('.overlay-board-layer[data-overlay-type="overlay_ratings"]'));
          if (!layers.length) return false;
          return layers.some(layer => {
            const style = window.getComputedStyle(layer);
            return (
              style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              layer.complete === true &&
              Number(layer.naturalWidth || 0) > 0 &&
              Number(layer.naturalHeight || 0) > 0
            );
          });
        }""",
        arg=board_selector,
        timeout=timeout_ms,
    )


def _find_default_ratings_layer_sources(page, board_selector):
    return page.evaluate(
        """(selector) => {
          const board = document.querySelector(selector);
          if (!board) return [];
          const canvas = board.querySelector('.overlay-board-canvas');
          if (!canvas) return [];
          const layers = Array.from(canvas.querySelectorAll('.overlay-board-layer[data-overlay-type="overlay_ratings"]'));
          const defaults = [];
          for (const layer of layers) {
            const src = String(layer.currentSrc || layer.src || '');
            if (!src) continue;
            if (src.includes('/defaults/overlays/ratings.png')) defaults.push(src);
          }
          return defaults;
        }""",
        board_selector,
    )


def _hide_global_nav_for_capture(page):
    page.evaluate("""() => {
          const selectors = [
            '.page-nav',
            '.navbar.page-nav',
            '.jump-to-button',
            '.overlay-jump-button'
          ];
          selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(node => {
              node.style.setProperty('visibility', 'hidden', 'important');
            });
          });
        }""")


def _capture_board_png(page, board_selector, png_path):
    try:
        exported = page.evaluate(
            """async (selector) => {
              const loadImage = (src) => new Promise((resolve, reject) => {
                const img = new Image();
                img.crossOrigin = 'anonymous';
                img.onload = () => resolve(img);
                img.onerror = () => reject(new Error(`Failed to load image: ${src}`));
                img.src = src;
              });

              const board = document.querySelector(selector);
              if (!board) return { ok: false, error: `Missing board: ${selector}` };
              const canvas = board.querySelector('.overlay-board-canvas');
              if (!canvas) return { ok: false, error: `Missing board canvas: ${selector}` };

              const baseWidth = Number(board.dataset.baseWidth) || 1000;
              const baseHeight = Number(board.dataset.baseHeight) || 1500;
              const out = document.createElement('canvas');
              out.width = Math.round(baseWidth);
              out.height = Math.round(baseHeight);
              const ctx = out.getContext('2d');
              if (!ctx) return { ok: false, error: 'Failed to create export canvas context' };

              ctx.fillStyle = '#0f0f0f';
              ctx.fillRect(0, 0, out.width, out.height);

              try {
                const style = window.getComputedStyle(canvas);
                const bg = style.backgroundImage || '';
                const match = bg.match(/url\\(["']?(.*?)["']?\\)/i);
                if (match && match[1]) {
                  const bgImg = await loadImage(match[1]);
                  const scale = Math.max(out.width / bgImg.width, out.height / bgImg.height);
                  const drawW = bgImg.width * scale;
                  const drawH = bgImg.height * scale;
                  const drawX = (out.width - drawW) / 2;
                  const drawY = (out.height - drawH) / 2;
                  ctx.drawImage(bgImg, drawX, drawY, drawW, drawH);
                }
              } catch (e) {
                return { ok: false, error: `Background render failed: ${e?.message || e}` };
              }

              const rect = canvas.getBoundingClientRect();
              const scaleX = rect.width > 0 ? (rect.width / out.width) : 1;
              const scaleY = rect.height > 0 ? (rect.height / out.height) : 1;

              const layers = Array.from(canvas.querySelectorAll('.overlay-board-layer'));
              for (const layer of layers) {
                const style = window.getComputedStyle(layer);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
                const src = layer.currentSrc || layer.src;
                if (!src) continue;
                const img = await loadImage(src);
                const leftPx = parseFloat(layer.style.left) || 0;
                const topPx = parseFloat(layer.style.top) || 0;
                const widthPx = parseFloat(layer.style.width) || img.width;
                const heightPx = parseFloat(layer.style.height) || img.height;
                const x = leftPx / scaleX;
                const y = topPx / scaleY;
                const w = widthPx / scaleX;
                const h = heightPx / scaleY;
                ctx.drawImage(img, x, y, w, h);
              }

              return {
                ok: true,
                dataUrl: out.toDataURL('image/png'),
                width: out.width,
                height: out.height
              };
            }""",
            board_selector,
        )
        if exported and exported.get("ok") and exported.get("dataUrl"):
            data_url = exported["dataUrl"]
            if data_url.startswith("data:image/png;base64,"):
                raw = data_url.split(",", 1)[1]
                png_path.write_bytes(base64.b64decode(raw))
                width = int(exported.get("width") or 0)
                height = int(exported.get("height") or 0)
                if width > 0 and height > 0:
                    with Image.open(png_path) as img:
                        if img.size != (width, height):
                            return (
                                False,
                                f"Exported image size mismatch: expected {width}x{height}, got {img.size[0]}x{img.size[1]}",
                            )
                return True, ""
            return False, "Canvas export returned unexpected data URL format"
        if exported and exported.get("error"):
            return False, f"Canvas export error: {exported['error']}"
        else:
            return False, "Canvas export error: unknown export failure"
    except Exception as e:
        return False, f"Canvas export error: {type(e).__name__}: {e}"


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
    libraries[f"{prefix}[back_align]"] = "center"
    libraries[f"{prefix}[back_color]"] = "#00000099"
    libraries[f"{prefix}[back_padding]"] = 15
    libraries[f"{prefix}[back_radius]"] = 30
    libraries[f"{prefix}[addon_offset]"] = 15
    if case["alignment"] == "horizontal":
        libraries[f"{prefix}[back_height]"] = 80
        libraries[f"{prefix}[back_width]"] = 270
        libraries[f"{prefix}[addon_position]"] = "left"
    else:
        libraries[f"{prefix}[back_height]"] = 160
        libraries[f"{prefix}[back_width]"] = 160
        libraries[f"{prefix}[addon_position]"] = "top"

    if builder == "episode":
        libraries[f"{prefix}[builder_level]"] = "episode"

    enabled = set(case["enabled_slots"])
    slot_values = _slot_values_for_builder(case["builder_level"])
    for idx, (rating_value, image_value) in slot_values.items():
        if idx in enabled:
            libraries[f"{prefix}[rating{idx}]"] = rating_value
            libraries[f"{prefix}[rating{idx}_image]"] = image_value
            libraries[f"{prefix}[rating{idx}_font]"] = RATING_FONT_BY_IMAGE.get(image_value, "Inter-Medium.ttf")
            libraries[f"{prefix}[rating{idx}_font_size]"] = 63
            libraries[f"{prefix}[rating{idx}_font_color]"] = "#FFFFFFFF"
            libraries[f"{prefix}[rating{idx}_stroke_width]"] = 1
            libraries[f"{prefix}[rating{idx}_stroke_color]"] = "#00000000"
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

    original_retrieve_settings = qs_module.output.persistence.retrieve_settings

    def fake_retrieve_settings(section):
        if section == "025-libraries":
            return payload
        # Preserve seeded runtime context (010-plex, telemetry, etc.) so later UI
        # interactions in the same test run do not lose library picker options.
        return original_retrieve_settings(section)

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


def _run_kometa_render_batch(output_dir, jobs, kometa_dir):
    if not jobs:
        return {}

    jobs_path = output_dir / "_kometa_jobs_work.json"
    jobs_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

    results_path = output_dir / "_kometa_results_work.json"
    if results_path.exists():
        results_path.unlink()
    script_path = Path("scripts") / "ratings_kometa_render.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--jobs",
        str(jobs_path),
        "--out",
        str(kometa_dir),
        "--results",
        str(results_path),
        "--repo-root",
        str(Path.cwd()),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 and not results_path.exists():
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        reason = stderr or stdout or f"kometa renderer exited with code {proc.returncode}"
        return {job["case_id"]: {"ok": False, "error": reason} for job in jobs}

    if not results_path.exists():
        reason = "kometa renderer did not write results file"
        return {job["case_id"]: {"ok": False, "error": reason} for job in jobs}

    raw = json.loads(results_path.read_text(encoding="utf-8"))
    by_case = {}
    for item in raw:
        case_id = item.get("case_id")
        if not case_id:
            continue
        by_case[case_id] = item
    return by_case


def _write_kometa_manifests(output_dir, all_jobs, results_by_case):
    jobs_path = output_dir / "kometa_jobs.json"
    jobs_path.write_text(json.dumps(all_jobs, indent=2), encoding="utf-8")

    results = list(results_by_case.values())
    results.sort(key=lambda item: str(item.get("case_id", "")))
    results_path = output_dir / "kometa_results.json"
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")


def _image_diff_stats(canvas_path, kometa_path, diff_path):
    with Image.open(canvas_path).convert("RGBA") as canvas_img, Image.open(kometa_path).convert("RGBA") as kometa_img:
        if canvas_img.size != kometa_img.size:
            target_w = max(canvas_img.width, kometa_img.width)
            target_h = max(canvas_img.height, kometa_img.height)
            c_bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            k_bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
            c_bg.paste(canvas_img, (0, 0), canvas_img)
            k_bg.paste(kometa_img, (0, 0), kometa_img)
            canvas_img = c_bg
            kometa_img = k_bg

        if DIFF_IGNORE_ALPHA:
            c_flat = Image.new("RGBA", canvas_img.size, (255, 255, 255, 255))
            k_flat = Image.new("RGBA", kometa_img.size, (255, 255, 255, 255))
            c_flat.alpha_composite(canvas_img)
            k_flat.alpha_composite(kometa_img)
            diff = ImageChops.difference(c_flat.convert("RGB"), k_flat.convert("RGB"))
        else:
            diff = ImageChops.difference(canvas_img, kometa_img)

        gray = diff.convert("L")
        hist = gray.histogram()
        total_pixels = gray.width * gray.height
        changed_pixels = total_pixels - hist[0]
        diff_percent = (changed_pixels / total_pixels) * 100 if total_pixels else 0.0
        if changed_pixels > 0:
            diff.save(diff_path)
        return changed_pixels, diff_percent


def _effective_diff_threshold_for_row(row):
    # Explicit global threshold always wins when > 0.
    if DIFF_THRESHOLD_PERCENT > 0:
        return DIFF_THRESHOLD_PERCENT
    if not DIFF_USE_SLOT_THRESHOLDS:
        return DIFF_THRESHOLD_PERCENT

    enabled_raw = str(row.get("enabled_slots", "") or "")
    enabled_count = len([token for token in enabled_raw.split("|") if token.strip()])
    if enabled_count <= 1:
        return DIFF_THRESHOLD_ONE_SLOT_PERCENT
    if enabled_count == 2:
        return DIFF_THRESHOLD_TWO_SLOT_PERCENT
    return DIFF_THRESHOLD_THREE_SLOT_PERCENT


def _apply_kometa_result_to_row(row, result, diff_dir, failures):
    case_id = row.get("case_id", "")
    if not result:
        row["status"] = "FAIL"
        row["notes"] = f"{row.get('notes', '')}; Kometa render failed: missing result".strip("; ").strip()
        failures.append(f"{case_id}: Kometa render failed: missing result")
        return

    if result.get("ok"):
        kometa_png = result.get("output_path", "")
        if kometa_png:
            row["kometa_png"] = str(kometa_png).replace("\\", "/")
        canvas_png = row.get("canvas_png")
        if canvas_png and kometa_png and Path(canvas_png).exists() and Path(kometa_png).exists():
            diff_png = diff_dir / f"{case_id}.png"
            changed_pixels, diff_percent = _image_diff_stats(Path(canvas_png), Path(kometa_png), diff_png)
            row["diff_pixels"] = int(changed_pixels)
            row["diff_percent"] = round(diff_percent, 6)
            row["diff_threshold_percent"] = round(_effective_diff_threshold_for_row(row), 6)
            if changed_pixels > 0 and diff_png.exists():
                row["diff_png"] = str(diff_png).replace("\\", "/")
            effective_threshold = row["diff_threshold_percent"]
            if FAIL_ON_DIFF and diff_percent > effective_threshold:
                row["status"] = "FAIL"
                extra = f"Diff {diff_percent:.4f}% exceeds threshold {effective_threshold:.4f}%"
                row["notes"] = f"{row.get('notes', '')}; {extra}".strip("; ").strip()
                failures.append(f"{case_id}: {extra}")
        return

    error = result.get("error", "Unknown kometa render error")
    row["status"] = "FAIL"
    row["notes"] = f"{row.get('notes', '')}; Kometa render failed: {error}".strip("; ").strip()
    failures.append(f"{case_id}: Kometa render failed: {error}")


def _flush_chunked_kometa_jobs(output_dir, pending_jobs, row_by_case_id, diff_dir, failures, kometa_dir, all_jobs, all_results_by_case):
    if not pending_jobs:
        return {"case_ids": [], "passed": 0, "failed": 0}
    chunk_snapshot = list(pending_jobs)
    all_jobs.extend(chunk_snapshot)
    chunk_ids = [job["case_id"] for job in pending_jobs]
    print(f"[ratings-artifacts] chunk render start size={len(pending_jobs)} first={chunk_ids[0]} last={chunk_ids[-1]}", flush=True)
    results = _run_kometa_render_batch(output_dir, pending_jobs, kometa_dir)
    all_results_by_case.update(results)
    passed = 0
    failed = 0
    for case_id in chunk_ids:
        row = row_by_case_id.get(case_id)
        if not row:
            continue
        _apply_kometa_result_to_row(row, results.get(case_id), diff_dir, failures)
        if row.get("status") == "FAIL":
            failed += 1
        else:
            passed += 1
    pending_jobs.clear()
    print(f"[ratings-artifacts] chunk render done size={len(chunk_ids)}", flush=True)
    return {"case_ids": chunk_ids, "passed": passed, "failed": failed}


def _is_locked_file_error(exc):
    return (
        isinstance(exc, PermissionError)
        or getattr(exc, "errno", None) == 13
        or getattr(exc, "winerror", None)
        in {
            32,
            33,
        }
    )


def _write_reports(output_dir, rows):
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "summary.json"
    json_written = json_path
    try:
        json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    except OSError as e:
        if not _is_locked_file_error(e):
            raise
        json_written = output_dir / "summary.live.json"
        try:
            json_written.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print(
                f"[ratings-artifacts] warning: summary.json is locked; wrote {json_written.name} instead",
                flush=True,
            )
        except OSError as e2:
            if not _is_locked_file_error(e2):
                raise
            json_written = None
            print(
                "[ratings-artifacts] warning: summary.json is locked and summary.live.json is also locked; skipping JSON write",
                flush=True,
            )

    csv_path = output_dir / "summary.csv"
    fieldnames = [
        "case_id",
        "library_type",
        "builder_level",
        "enabled_slots",
        "alignment",
        "horizontal_position",
        "vertical_position",
        "nudge_profile",
        "nudge_dx",
        "nudge_dy",
        "canvas_png",
        "kometa_png",
        "diff_png",
        "diff_pixels",
        "diff_percent",
        "diff_threshold_percent",
        "yaml_file",
        "status",
        "notes",
    ]
    csv_written = csv_path
    try:
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
    except OSError as e:
        if not _is_locked_file_error(e):
            raise
        csv_written = output_dir / "summary.live.csv"
        try:
            with csv_written.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow({k: row.get(k, "") for k in fieldnames})
            print(
                f"[ratings-artifacts] warning: summary.csv is locked; wrote {csv_written.name} instead",
                flush=True,
            )
        except OSError as e2:
            if not _is_locked_file_error(e2):
                raise
            csv_written = None
            print(
                "[ratings-artifacts] warning: summary.csv is locked and summary.live.csv is also locked; skipping CSV write",
                flush=True,
            )

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
        f"- `{json_written.name}`" if json_written else "- `summary.json` (write skipped: locked)",
        f"- `{csv_written.name}`" if csv_written else "- `summary.csv` (write skipped: locked)",
        "- `canvas/*.png`",
        "- `kometa/*.png`",
        "- `diff/*.png` (only when differences exist)",
        "- `yaml/*.yml`",
        "",
    ]

    if failed:
        md_lines.append("## Failed Cases")
        md_lines.append("")
        for row in rows:
            if row.get("status") == "FAIL":
                md_lines.append(f"- `{row['case_id']}`: {row.get('notes', '')}")

    readme_path = output_dir / "README.md"
    try:
        readme_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    except OSError as e:
        if not _is_locked_file_error(e):
            raise
        fallback_readme = output_dir / "README.live.md"
        try:
            fallback_readme.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
            print(
                f"[ratings-artifacts] warning: README.md is locked; wrote {fallback_readme.name} instead",
                flush=True,
            )
        except OSError as e2:
            if not _is_locked_file_error(e2):
                raise
            print(
                "[ratings-artifacts] warning: README.md is locked and README.live.md is also locked; skipping README write",
                flush=True,
            )


@pytest.mark.e2e
@pytest.mark.ratings_artifacts
def test_generate_ratings_matrix_artifacts(page, live_server, monkeypatch, qs_module):
    output_dir = _artifact_root()
    canvas_dir = output_dir / "canvas"
    kometa_dir = output_dir / "kometa"
    diff_dir = output_dir / "diff"
    yaml_dir = output_dir / "yaml"
    canvas_dir.mkdir(parents=True, exist_ok=True)
    kometa_dir.mkdir(parents=True, exist_ok=True)
    diff_dir.mkdir(parents=True, exist_ok=True)
    yaml_dir.mkdir(parents=True, exist_ok=True)

    cases = _select_matrix_cases()
    rows = []
    row_by_case_id = {}
    failures = []
    kometa_jobs = []
    chunk_jobs = []
    all_kometa_jobs = []
    all_kometa_results_by_case = {}
    mode = _execution_mode()
    chunk_index = 0
    pending_rows_since_report = 0
    if mode == "chunked":
        print(f"[ratings-artifacts] execution_mode=chunked chunk_size={CHUNK_SIZE}", flush=True)
    else:
        print(f"[ratings-artifacts] execution_mode={mode}", flush=True)

    report_write_interval = CHUNK_SIZE if (WITH_KOMETA_RENDER and mode == "chunked") else PROGRESS_WRITE_INTERVAL

    def maybe_write_reports(force=False):
        nonlocal pending_rows_since_report
        if force or pending_rows_since_report >= report_write_interval:
            try:
                _write_reports(output_dir, rows)
                pending_rows_since_report = 0
            except OSError as e:
                if _is_locked_file_error(e):
                    print(
                        "[ratings-artifacts] warning: report write skipped due to file lock; close Excel and run can continue",
                        flush=True,
                    )
                else:
                    raise

    _seed_library_settings_for_artifacts(monkeypatch, qs_module)
    _mock_remote_rating_assets(page)
    _mock_generate_preview_requests(page)

    page.goto(f"{live_server}/step/025-libraries", wait_until="domcontentloaded")
    page.wait_for_selector("#libraryPicker", timeout=10000)

    total_cases = len(cases)
    total_chunk_target = math.ceil(total_cases / CHUNK_SIZE) if (WITH_KOMETA_RENDER and mode == "chunked" and total_cases > 0) else 0
    profile_context = {}
    run_started = time.monotonic()
    for index, case in enumerate(cases, start=1):
        case_id = case["case_id"]
        processed = index - 1
        if processed > 0:
            elapsed = time.monotonic() - run_started
            avg = elapsed / processed
            remaining = (total_cases - processed) * avg
            eta = _format_eta(remaining)
            elapsed_fmt = _format_eta(elapsed)
            print(
                f"[ratings-artifacts] {index}/{total_cases} {case_id} " f"elapsed={elapsed_fmt} avg={avg:.2f}s/test eta={eta}",
                flush=True,
            )
        else:
            print(
                f"[ratings-artifacts] {index}/{total_cases} {case_id} " "elapsed=0s avg=n/a eta=estimating...",
                flush=True,
            )
        png_path = canvas_dir / f"{case_id}.png"
        yaml_path = yaml_dir / f"{case_id}.yml"

        try:
            profile_key = (case["library_type"], case["builder_level"], case["profile_name"])
            context = profile_context.get(profile_key)
            if context is FAILED_PROFILE:
                row = {
                    "case_id": case_id,
                    "library_type": case["library_type"],
                    "builder_level": case["builder_level"],
                    "enabled_slots": "|".join(case["enabled_slots"]),
                    "alignment": case["alignment"],
                    "horizontal_position": case["horizontal_position"],
                    "vertical_position": case["vertical_position"],
                    "nudge_profile": case.get("nudge_profile", "none"),
                    "nudge_dx": int(case.get("nudge_dx", 0) or 0),
                    "nudge_dy": int(case.get("nudge_dy", 0) or 0),
                    "canvas_png": str(png_path).replace("\\", "/"),
                    "kometa_png": "",
                    "diff_png": "",
                    "diff_pixels": "",
                    "diff_percent": "",
                    "diff_threshold_percent": "",
                    "yaml_file": str(yaml_path).replace("\\", "/"),
                    "status": "FAIL",
                    "notes": f"Skipped after profile bootstrap failure: {profile_key}",
                }
                rows.append(row)
                pending_rows_since_report += 1
                failures.append(f"{case_id}: {row['notes']}")
                print(f"[ratings-artifacts] skipped {case_id} (profile failed)", flush=True)
                maybe_write_reports()
                continue
            if context is None:
                ctx = _load_library_with_ratings(
                    page,
                    builder_level=case["context_level"],
                    library_type=case["library_type"],
                )
                if not ctx:
                    failures.append(f"No ratings context found for profile {profile_key}")
                    profile_context[profile_key] = FAILED_PROFILE
                    continue
                template = ctx["templateName"]
                library_id = ctx.get("libraryId")
                if not library_id:
                    failures.append(f"No active library card found for profile {profile_key}")
                    profile_context[profile_key] = FAILED_PROFILE
                    continue
                _enable_overlay_group(page, template)
                _set_if_exists(page, f"{template}[builder_level]", case["builder_level"])
                enabled_names = {f"rating{idx}" for idx in case["enabled_slots"]}
                _configure_rating_slots(page, template, enabled_names, case["builder_level"])
                context = {"template": template, "library_id": library_id}
                profile_context[profile_key] = context

            if context is None:
                continue

            template = context["template"]
            library_id = context["library_id"]
            if not _ensure_library_card_loaded(page, library_id, case["library_type"]):
                raise RuntimeError(f"Failed to activate library card: {library_id}")
            _enable_overlay_group(page, template)
            enabled_names = {f"rating{idx}" for idx in case["enabled_slots"]}
            _configure_rating_slots(page, template, enabled_names, case["builder_level"])

            _set_by_name(page, f"{template}[rating_alignment]", case["alignment"])
            _set_by_name(page, f"{template}[horizontal_position]", case["horizontal_position"])
            _set_by_name(page, f"{template}[vertical_position]", case["vertical_position"])
            _set_if_exists(page, f"{template}[builder_level]", case["builder_level"])
            _set_board_alignment_guide(page, library_id, case["board_type"])
            page.wait_for_timeout(CASE_SETTLE_MS)

            board_selector = f'#library-form-container .library-settings-card[data-library-id="{library_id}"] ' f".overlay-board[data-overlay-type=\"{case['board_type']}\"]"
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
                        _wait_for_rating_layer_ready(page, board_selector, case["board_type"])
                    except Exception as e:
                        notes.append(f"Rating layer wait warning: {type(e).__name__}: {e}")
                    nudge_ok, nudge_warning = _apply_nudge_offsets(page, board_selector, library_id, case["board_type"], template, case)
                    if nudge_warning:
                        notes.append(nudge_warning)
                    if not nudge_ok:
                        status = "FAIL"
                    page.wait_for_timeout(CASE_SETTLE_MS)

                    default_layer_srcs = _find_default_ratings_layer_sources(page, board_selector)
                    if default_layer_srcs:
                        status = "FAIL"
                        notes.append(f"Ratings layer used default ratings.png instead of slot icons ({len(default_layer_srcs)} layer(s))")

                    _hide_global_nav_for_capture(page)
                    saved, warning = _capture_board_png(page, board_selector, png_path)
                    if not saved:
                        status = "FAIL"
                        notes.append(warning)
                    elif warning:
                        notes.append(warning)

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

            active_yaml_slots = []
            for idx in ("1", "2", "3"):
                rating_val = str(tv.get(f"rating{idx}", "") or "").strip().lower()
                if rating_val and rating_val != "none":
                    active_yaml_slots.append(idx)
            if len(active_yaml_slots) != len(case["enabled_slots"]):
                status = "FAIL"
                notes.append(f"YAML enabled slot count mismatch (ui={len(case['enabled_slots'])}, yaml={len(active_yaml_slots)})")

            for idx in active_yaml_slots:
                slot = f"rating{idx}"
                y_h = tv.get(f"{slot}_horizontal_offset")
                y_v = tv.get(f"{slot}_vertical_offset")
                if y_h is not None:
                    try:
                        int(y_h)
                    except (TypeError, ValueError):
                        status = "FAIL"
                        notes.append(f"{slot} horizontal offset is not numeric: {y_h}")
                if y_v is not None:
                    try:
                        int(y_v)
                    except (TypeError, ValueError):
                        status = "FAIL"
                        notes.append(f"{slot} vertical offset is not numeric: {y_v}")

            if case["horizontal_position"] == "right":
                for idx in active_yaml_slots:
                    slot = f"rating{idx}"
                    y_h = tv.get(f"{slot}_horizontal_offset")
                    if y_h is not None and int(y_h) < 0:
                        status = "FAIL"
                        notes.append(f"{slot} horizontal offset is negative for right anchor")
            if case["vertical_position"] == "bottom":
                for idx in active_yaml_slots:
                    slot = f"rating{idx}"
                    y_v = tv.get(f"{slot}_vertical_offset")
                    if y_v is not None and int(y_v) < 0:
                        status = "FAIL"
                        notes.append(f"{slot} vertical offset is negative for bottom anchor")

            row = {
                "case_id": case_id,
                "library_type": case["library_type"],
                "builder_level": case["builder_level"],
                "enabled_slots": "|".join(case["enabled_slots"]),
                "alignment": case["alignment"],
                "horizontal_position": case["horizontal_position"],
                "vertical_position": case["vertical_position"],
                "nudge_profile": case.get("nudge_profile", "none"),
                "nudge_dx": int(case.get("nudge_dx", 0) or 0),
                "nudge_dy": int(case.get("nudge_dy", 0) or 0),
                "canvas_png": str(png_path).replace("\\", "/"),
                "kometa_png": "",
                "diff_png": "",
                "diff_pixels": "",
                "diff_percent": "",
                "diff_threshold_percent": "",
                "yaml_file": str(yaml_path).replace("\\", "/"),
                "status": status,
                "notes": "; ".join(notes),
            }
            rows.append(row)
            pending_rows_since_report += 1
            row_by_case_id[case_id] = row
            job = {
                "case_id": case_id,
                "builder_level": case["builder_level"],
                "library_type": case["library_type"],
                "board_type": case["board_type"],
                "template_vars": tv,
                "canvas_png": str(png_path),
            }
            if WITH_KOMETA_RENDER:
                if mode == "stream":
                    all_kometa_jobs.append(job)
                    stream_results = _run_kometa_render_batch(output_dir, [job], kometa_dir)
                    all_kometa_results_by_case.update(stream_results)
                    _apply_kometa_result_to_row(row, stream_results.get(case_id), diff_dir, failures)
                elif mode == "chunked":
                    chunk_jobs.append(job)
                    if len(chunk_jobs) >= CHUNK_SIZE:
                        result = _flush_chunked_kometa_jobs(
                            output_dir=output_dir,
                            pending_jobs=chunk_jobs,
                            row_by_case_id=row_by_case_id,
                            diff_dir=diff_dir,
                            failures=failures,
                            kometa_dir=kometa_dir,
                            all_jobs=all_kometa_jobs,
                            all_results_by_case=all_kometa_results_by_case,
                        )
                        chunk_index += 1
                        cum_pass = sum(1 for r in rows if r.get("status") == "PASS")
                        cum_fail = sum(1 for r in rows if r.get("status") == "FAIL")
                        print(
                            f"[ratings-artifacts] chunk {chunk_index}/{total_chunk_target} "
                            f"pass={result['passed']} fail={result['failed']} "
                            f"cumulative_pass={cum_pass} cumulative_fail={cum_fail}",
                            flush=True,
                        )
                        maybe_write_reports(force=True)
                else:
                    kometa_jobs.append(job)
            if status == "FAIL":
                failures.append(f"{case_id}: {row['notes']}")
            print(f"[ratings-artifacts] done {case_id} status={row['status']}", flush=True)
            maybe_write_reports()
        except Exception as e:
            if "profile_key" in locals() and "context" in locals() and context is None:
                profile_context[profile_key] = FAILED_PROFILE
            row = {
                "case_id": case_id,
                "library_type": case["library_type"],
                "builder_level": case["builder_level"],
                "enabled_slots": "|".join(case["enabled_slots"]),
                "alignment": case["alignment"],
                "horizontal_position": case["horizontal_position"],
                "vertical_position": case["vertical_position"],
                "nudge_profile": case.get("nudge_profile", "none"),
                "nudge_dx": int(case.get("nudge_dx", 0) or 0),
                "nudge_dy": int(case.get("nudge_dy", 0) or 0),
                "canvas_png": str(png_path).replace("\\", "/"),
                "kometa_png": "",
                "diff_png": "",
                "diff_pixels": "",
                "diff_percent": "",
                "diff_threshold_percent": "",
                "yaml_file": str(yaml_path).replace("\\", "/"),
                "status": "FAIL",
                "notes": f"Unhandled case exception: {type(e).__name__}: {e}",
            }
            rows.append(row)
            pending_rows_since_report += 1
            row_by_case_id[case_id] = row
            failures.append(f"{case_id}: {row['notes']}")
            print(f"[ratings-artifacts] error {case_id}: {row['notes']}", flush=True)
            maybe_write_reports()

    if WITH_KOMETA_RENDER and mode == "chunked" and chunk_jobs:
        result = _flush_chunked_kometa_jobs(
            output_dir=output_dir,
            pending_jobs=chunk_jobs,
            row_by_case_id=row_by_case_id,
            diff_dir=diff_dir,
            failures=failures,
            kometa_dir=kometa_dir,
            all_jobs=all_kometa_jobs,
            all_results_by_case=all_kometa_results_by_case,
        )
        chunk_index += 1
        cum_pass = sum(1 for r in rows if r.get("status") == "PASS")
        cum_fail = sum(1 for r in rows if r.get("status") == "FAIL")
        print(
            f"[ratings-artifacts] chunk {chunk_index}/{total_chunk_target} "
            f"pass={result['passed']} fail={result['failed']} "
            f"cumulative_pass={cum_pass} cumulative_fail={cum_fail}",
            flush=True,
        )
        maybe_write_reports(force=True)

    if WITH_KOMETA_RENDER and mode == "batch" and kometa_jobs:
        all_kometa_jobs.extend(kometa_jobs)
        kometa_results = _run_kometa_render_batch(output_dir, kometa_jobs, kometa_dir)
        all_kometa_results_by_case.update(kometa_results)
        for row in rows:
            case_id = row.get("case_id")
            if not case_id:
                continue
            _apply_kometa_result_to_row(row, kometa_results.get(case_id), diff_dir, failures)
        maybe_write_reports(force=True)

    if WITH_KOMETA_RENDER:
        _write_kometa_manifests(output_dir, all_kometa_jobs, all_kometa_results_by_case)

    _write_reports(output_dir, rows)

    if failures:
        preview = "\n".join(failures[:25])
        pytest.fail(f"Ratings artifact matrix found {len(failures)} issue(s). " f"See {output_dir} for details.\n{preview}")
