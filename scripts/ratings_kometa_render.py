import argparse
import json
import sys
import tempfile
import types
from pathlib import Path

from PIL import Image

ICON_MAP = {
    "anidb": "AniDB.png",
    "imdb": "IMDb.png",
    "letterboxd": "Letterboxd.png",
    "mdb": "MDBList.png",
    "metacritic": "Metacritic.png",
    "rt_popcorn": "RT-Aud-Fresh.png",
    "rt_tomato": "RT-Crit-Fresh.png",
    "tmdb": "TMDb.png",
    "trakt": "Trakt.png",
    "mal": "MAL.png",
    "star": "Star.png",
}

RATING_TEXT_MAP = {
    "critic": "9.0",
    "audience": "85%",
    "user": "85%",
}
RATING_SAMPLE_BASE = {
    "critic": {"decimal10": 9.0, "decimal5": 4.5, "percent": 90, "score100": 90},
    "audience": {"decimal10": 8.5, "decimal5": 4.3, "percent": 85, "score100": 85},
    "user": {"decimal10": 7.5, "decimal5": 3.3, "percent": 75, "score100": 75},
}
RATING_SAMPLE_JITTER = {
    "decimal10": 1.2,
    "decimal5": 0.6,
    "percent": 12,
    "score100": 12,
}
RATING_SAMPLE_LIMITS = {
    "decimal10": {"min": 1.0, "max": 9.8},
    "decimal5": {"min": 0.5, "max": 4.5},
    "percent": {"min": 10, "max": 95},
    "score100": {"min": 10, "max": 95},
}
RATING_SAMPLE_OVERRIDES = {
    "rt_tomato": {"min": 10, "max": 95, "scale": "percent"},
    "rt_popcorn": {"min": 10, "max": 95, "scale": "percent"},
}
RATING_VALUE_FORMAT_MAP = {
    "anidb": {"scale": "decimal10", "decimals": 1},
    "imdb": {"scale": "decimal10", "decimals": 1},
    "letterboxd": {"scale": "decimal5", "decimals": 1},
    "tmdb": {"scale": "decimal10", "decimals": 1},
    "metacritic": {"scale": "score100", "decimals": 0},
    "rt_popcorn": {"scale": "percent", "decimals": 0},
    "rt_tomato": {"scale": "percent", "decimals": 0},
    "trakt": {"scale": "percent", "decimals": 0},
    "mal": {"scale": "decimal10", "decimals": 2},
    "mdb": {"scale": "score100", "decimals": 0},
    "mdblist": {"scale": "score100", "decimals": 0},
    "star": {"scale": "decimal10", "decimals": 1},
    "plex_star": {"scale": "decimal10", "decimals": 1},
}
RT_ROTTEN_THRESHOLD = 60
RATING_FONT_MAP = {
    "anidb": "Arimo-Medium.ttf",
    "imdb": "Roboto-Medium.ttf",
    "tmdb": "Consensus-SemiBold.otf",
    "metacritic": "Montserrat-SemiBold.ttf",
    "letterboxd": "Montserrat-Bold.ttf",
    "trakt": "Figtree-Medium.ttf",
    "rt_tomato": "LibreFranklin-Bold.ttf",
    "rt_popcorn": "LibreFranklin-Bold.ttf",
    "myanimelist": "Lato-Regular.ttf",
    "mal": "Lato-Regular.ttf",
    "mdblist": "Lato-Regular.ttf",
    "mdb": "Lato-Regular.ttf",
    "star": "Roboto-Medium.ttf",
    "plex_star": "Roboto-Medium.ttf",
}


def _str(v, default=""):
    if v is None:
        return default
    return str(v)


def _int(v, default):
    try:
        return int(float(str(v)))
    except Exception:
        return int(default)


def _normalize_rating_image_key(value):
    raw = _str(value, "").strip().lower()
    if not raw:
        return ""
    normalized = " ".join(raw.split())
    mapped = {
        "rt tomato": "rt_tomato",
        "rt tomatoes": "rt_tomato",
        "rt popcorn": "rt_popcorn",
        "myanimelist": "mal",
        "mdb": "mdb",
    }.get(normalized)
    if mapped:
        return mapped
    return normalized.replace(" ", "_")


def _hash_string(value):
    h = 2166136261
    for ch in _str(value, ""):
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def _seeded_random(seed):
    t = (seed + 0x6D2B79F5) & 0xFFFFFFFF
    t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
    t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0


def _clamp_number(value, min_value, max_value):
    return min(max(value, min_value), max_value)


def _is_enabled(tv, slot):
    value = _str(tv.get(slot, "none"), "none").strip().lower()
    return value not in {"", "none", "null"}


def _alignment_vars(tv):
    alignment = _str(tv.get("rating_alignment", "vertical"), "vertical").strip().lower()
    if alignment not in {"vertical", "horizontal"}:
        alignment = "vertical"
    hp = _str(tv.get("horizontal_position", "left"), "left").strip().lower()
    if hp not in {"left", "center", "right"}:
        hp = "left"
    vp = _str(tv.get("vertical_position", "center"), "center").strip().lower()
    if vp not in {"top", "center", "bottom"}:
        vp = "center"
    return alignment, hp, vp


def _default_offsets(tv, slot):
    alignment, hp, vp = _alignment_vars(tv)
    r1 = _is_enabled(tv, "rating1")
    r2 = _is_enabled(tv, "rating2")
    r3 = _is_enabled(tv, "rating3")
    standard = _int(tv.get("standard_offset", 30), 30)
    center = _int(tv.get("center_offset", 0), 0)
    v2 = _int(tv.get("v2_offset", 235), 235)
    v3 = _int(tv.get("v3_offset", 440), 440)
    cv2 = _int(tv.get("cv2_offset", 105), 105)
    cv3 = _int(tv.get("cv3_offset", 205), 205)
    h2 = _int(tv.get("h2_offset", 345), 345)
    h3 = _int(tv.get("h3_offset", 660), 660)
    ch2 = _int(tv.get("ch2_offset", 160), 160)
    ch3 = _int(tv.get("ch3_offset", 335), 335)

    def h_for():
        if slot == "rating1":
            if alignment == "vertical" and hp == "center":
                return center
            if alignment == "horizontal":
                if hp == "center":
                    if not r2 and not r3:
                        return center
                    if not r2 or not r3:
                        return -ch2
                    return -ch3
                if hp == "right":
                    if not r2 and not r3:
                        return standard
                    if not r2 or not r3:
                        return h2
                    return h3
            return standard

        if slot == "rating2":
            if alignment == "vertical" and hp == "center":
                return center
            if alignment == "horizontal":
                if hp == "center":
                    if not r1 and not r3:
                        return center
                    if not r1:
                        return -ch2
                    if not r3:
                        return ch2
                    return center
                if hp == "right":
                    if not r1 and not r3:
                        return standard
                    if not r3:
                        return standard
                    return h2
                if hp == "left":
                    if not r1:
                        return standard
                    return h2
            return standard

        # rating3
        if alignment == "vertical" and hp == "center":
            return center
        if alignment == "horizontal":
            if hp == "center":
                if not r1 and not r2:
                    return center
                if not r1 or not r2:
                    return ch2
                return ch3
            if hp == "left":
                if not r1 and not r2:
                    return standard
                if not r1 or not r2:
                    return h2
                return h3
        return standard

    def v_for():
        if slot == "rating1":
            if alignment == "horizontal" and vp == "center":
                return center
            if alignment == "vertical":
                if vp == "center":
                    if not r2 and not r3:
                        return center
                    if not r2 or not r3:
                        return -cv2
                    return -cv3
                if vp == "bottom":
                    if not r2 and not r3:
                        return standard
                    if not r2 or not r3:
                        return v2
                    return v3
            return standard

        if slot == "rating2":
            if alignment == "horizontal" and vp == "center":
                return center
            if alignment == "vertical":
                if vp == "center":
                    if not r1 and not r3:
                        return center
                    if not r1:
                        return -cv2
                    if not r3:
                        return cv2
                    return center
                if vp == "bottom":
                    if not r1 and not r3:
                        return standard
                    if not r1:
                        return v2
                    if not r3:
                        return standard
                    return v2
                if vp == "top":
                    if not r1:
                        return standard
                    return v2
            return standard

        # rating3
        if alignment == "horizontal" and vp == "center":
            return center
        if alignment == "vertical":
            if vp == "center":
                if not r1 and not r2:
                    return center
                if not r1 or not r2:
                    return cv2
                return cv3
            if vp == "top":
                if not r1 and not r2:
                    return standard
                if not r1 or not r2:
                    return v2
                return v3
        return standard

    return h_for(), v_for()


def _effective_offset(tv, slot):
    h_key = f"{slot}_horizontal_offset"
    v_key = f"{slot}_vertical_offset"
    if h_key in tv and tv[h_key] is not None and str(tv[h_key]).strip() != "":
        h = _int(tv[h_key], 0)
    else:
        h, _ = _default_offsets(tv, slot)
    if v_key in tv and tv[v_key] is not None and str(tv[v_key]).strip() != "":
        v = _int(tv[v_key], 0)
    else:
        _, v = _default_offsets(tv, slot)
    return h, v


def _resolve_font(repo_root, font_value):
    font_value = _str(font_value, "").strip()
    candidates = []
    if font_value:
        candidates.extend(
            [
                repo_root / font_value,
                repo_root / "config" / "kometa" / font_value,
                repo_root / "config" / "kometa" / "fonts" / Path(font_value).name,
                repo_root / "config" / "fonts" / Path(font_value).name,
            ]
        )
    candidates.append(repo_root / "config" / "kometa" / "fonts" / "Roboto-Medium.ttf")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[-1])


def _resolve_icon_path(repo_root, image_key):
    icon_name = ICON_MAP.get(_str(image_key, "").strip().lower())
    if not icon_name:
        icon_name = "IMDb.png"
    return repo_root / "config" / "kometa" / "defaults" / "overlays" / "images" / "rating" / icon_name


def _base_image_path(repo_root, board_type):
    board_type = _str(board_type, "movie").strip().lower()
    if board_type == "episode":
        preferred = [
            repo_root / "static" / "images" / "overlay_alignment_guide_episodes.png",
            repo_root / "config" / "uploads" / "episodes" / "overlay_alignment_guide_episodes.png",
        ]
    elif board_type == "show":
        preferred = [
            repo_root / "static" / "images" / "overlay_alignment_guide.png",
            repo_root / "config" / "uploads" / "shows" / "overlay_alignment_guide.png",
            repo_root / "config" / "uploads" / "movies" / "overlay_alignment_guide.png",
        ]
    else:
        preferred = [
            repo_root / "static" / "images" / "overlay_alignment_guide.png",
            repo_root / "config" / "uploads" / "movies" / "overlay_alignment_guide.png",
            repo_root / "config" / "uploads" / "shows" / "overlay_alignment_guide.png",
        ]
    for candidate in preferred:
        if candidate.exists():
            return candidate
    return preferred[0]


def _sample_text(rating_type, image_key, variant=None):
    type_key = _str(rating_type, "").strip().lower()
    normalized_image = _normalize_rating_image_key(image_key)
    format_info = RATING_VALUE_FORMAT_MAP.get(normalized_image)
    base_map = RATING_SAMPLE_BASE.get(type_key)
    fallback = RATING_TEXT_MAP.get(type_key, "NR")
    if not format_info or not base_map:
        return fallback

    scale = _str(format_info.get("scale"), "decimal10") or "decimal10"
    base_value = base_map.get(scale)
    if base_value is None:
        return fallback

    overrides = RATING_SAMPLE_OVERRIDES.get(normalized_image)
    scale_key = overrides.get("scale") if isinstance(overrides, dict) and overrides.get("scale") else scale
    limits = overrides if overrides else RATING_SAMPLE_LIMITS.get(scale_key)
    seed = _hash_string(f"{normalized_image}|{type_key}|{_str(variant, 'base') or 'base'}")
    rand = _seeded_random(seed)
    jitter = float(RATING_SAMPLE_JITTER.get(scale_key, 0))
    value = float(base_value) + ((rand - 0.5) * 2 * jitter)

    if isinstance(limits, dict):
        min_value = float(limits.get("min", value))
        max_value = float(limits.get("max", value))
        if normalized_image in {"rt_tomato", "rt_popcorn"} and scale_key == "percent":
            if variant == "fresh":
                min_value = max(RT_ROTTEN_THRESHOLD, min_value)
            elif variant == "rotten":
                max_value = min(RT_ROTTEN_THRESHOLD - 1, max_value)
        value = _clamp_number(value, min_value, max_value)
    elif scale_key == "decimal10":
        value = _clamp_number(value, 0.1, 9.9)
    elif scale_key == "decimal5":
        value = _clamp_number(value, 0.1, 4.9)
    else:
        value = _clamp_number(value, 1.0, 99.0)

    if scale_key == "percent":
        return f"{round(value)}%"

    decimals = int(format_info.get("decimals", 0))
    if decimals == 0:
        return f"{round(value)}"
    return f"{value:.{max(0, decimals)}f}"


def _build_overlay_data(repo_root, tv, slot):
    alignment, hp, vp = _alignment_vars(tv)
    h_offset, v_offset = _effective_offset(tv, slot)
    image_key = _str(tv.get(f"{slot}_image", "imdb"), "imdb").strip().lower()
    normalized_image_key = _normalize_rating_image_key(image_key)
    rating_type = _str(tv.get(slot, "critic"), "critic").strip().lower()
    text = _sample_text(rating_type, image_key)
    font_value = _str(tv.get(f"{slot}_font", ""), "").strip()
    if not font_value:
        font_value = RATING_FONT_MAP.get(normalized_image_key, "Inter-Medium.ttf")

    default_back_w = 270 if alignment == "horizontal" else 160
    default_back_h = 80 if alignment == "horizontal" else 160
    default_addon = "left" if alignment == "horizontal" else "top"

    return {
        "text": text,
        "overlay_data": {
            "name": f"text({text})",
            "file": str(_resolve_icon_path(repo_root, image_key)),
            "horizontal_align": hp,
            "vertical_align": vp,
            "horizontal_offset": h_offset,
            "vertical_offset": v_offset,
            "font": _resolve_font(repo_root, font_value),
            "font_size": _int(tv.get(f"{slot}_font_size", 63), 63),
            "font_color": _str(tv.get(f"{slot}_font_color", "#FFFFFFFF"), "#FFFFFFFF"),
            "stroke_width": _int(tv.get(f"{slot}_stroke_width", 1), 1),
            "stroke_color": _str(tv.get(f"{slot}_stroke_color", "#00000000"), "#00000000"),
            "back_color": _str(tv.get(f"{slot}_back_color", tv.get("back_color", "#00000099")), "#00000099"),
            "back_width": _int(tv.get(f"{slot}_back_width", tv.get("back_width", default_back_w)), default_back_w),
            "back_height": _int(tv.get(f"{slot}_back_height", tv.get("back_height", default_back_h)), default_back_h),
            "back_align": _str(tv.get(f"{slot}_back_align", tv.get("back_align", "center")), "center"),
            "back_padding": _int(tv.get(f"{slot}_back_padding", tv.get("back_padding", 15)), 15),
            "back_radius": _int(tv.get(f"{slot}_back_radius", tv.get("back_radius", 30)), 30),
            "addon_offset": _int(tv.get(f"{slot}_addon_offset", tv.get("addon_offset", 15)), 15),
            "addon_position": _str(tv.get(f"{slot}_addon_position", tv.get("addon_position", default_addon)), default_addon),
            "weight": 100,
        },
    }


def _render_case(repo_root, out_dir, overlay_cls, job):
    case_id = job["case_id"]
    tv = dict(job.get("template_vars") or {})
    board_type = _str(job.get("board_type", "movie"), "movie").strip().lower()
    builder_level = _str(job.get("builder_level", "movie"), "movie").strip().lower()

    canvas_size = (1920, 1080) if builder_level == "episode" else (1000, 1500)
    base_path = _base_image_path(repo_root, board_type)
    if not base_path.exists():
        raise FileNotFoundError(f"Missing base image: {base_path}")

    with Image.open(base_path).convert("RGBA") as src:
        out_img = src.resize(canvas_size, Image.Resampling.LANCZOS)

    class _DummyConfig:
        Requests = None
        Cache = None
        GitHub = type("GitHub", (), {"configs_url": ""})()
        custom_repo = ""

    class _DummyOverlayFile:
        file_num = 1
        queue_names = {}

    with tempfile.TemporaryDirectory(prefix="ratings-kometa-overlay-") as tmp_overlay:

        class _DummyLibrary:
            overlay_folder = tmp_overlay
            image_table_name = "ratings_matrix"

        slots = [slot for slot in ("rating1", "rating2", "rating3") if _is_enabled(tv, slot)]
        for idx, slot in enumerate(slots, start=1):
            built = _build_overlay_data(repo_root, tv, slot)
            overlay_obj = overlay_cls(
                _DummyConfig(),
                _DummyLibrary(),
                _DummyOverlayFile(),
                f"{case_id}-{slot}-{idx}",
                built["overlay_data"],
                suppress=[],
                level=builder_level,
            )
            overlay_layer, addon_box = overlay_obj.get_backdrop(
                canvas_size,
                box=overlay_obj.image.size if overlay_obj.image else None,
                text=built["text"],
            )
            if overlay_layer is not None:
                # Use alpha compositing so semi-transparent backdrops are flattened
                # consistently against the base guide image (matches canvas export).
                out_img.alpha_composite(overlay_layer.convert("RGBA"), (0, 0))
            if overlay_obj.image:
                icon_layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
                icon_layer.paste(overlay_obj.image, addon_box, overlay_obj.image)
                out_img.alpha_composite(icon_layer, (0, 0))

    out_path = out_dir / f"{case_id}.png"
    # Force opaque output to match how the canvas export is flattened.
    out_img.convert("RGB").save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Render ratings overlays using Kometa overlay classes.")
    parser.add_argument("--jobs", required=True, help="Path to JSON jobs file.")
    parser.add_argument("--out", required=True, help="Output directory for rendered images.")
    parser.add_argument("--results", required=True, help="Path to write JSON results.")
    parser.add_argument("--repo-root", required=True, help="Repository root path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    kometa_root = repo_root / "config" / "kometa"
    if not kometa_root.exists():
        raise FileNotFoundError(f"Missing Kometa root at {kometa_root}")

    # Kometa util imports optional runtime deps that are not required for this renderer path.
    if "num2words" not in sys.modules:
        mod = types.ModuleType("num2words")
        mod.num2words = lambda value, *args, **kwargs: str(value)
        sys.modules["num2words"] = mod
    if "pathvalidate" not in sys.modules:
        mod = types.ModuleType("pathvalidate")
        mod.is_valid_filename = lambda value, *args, **kwargs: True
        mod.sanitize_filename = lambda value, *args, **kwargs: str(value)
        sys.modules["pathvalidate"] = mod
    if "plexapi" not in sys.modules:
        plexapi_mod = types.ModuleType("plexapi")
        audio_mod = types.ModuleType("plexapi.audio")
        video_mod = types.ModuleType("plexapi.video")

        class _Album:  # noqa: D401
            pass

        class _Track:  # noqa: D401
            pass

        class _Season:  # noqa: D401
            pass

        class _Episode:  # noqa: D401
            pass

        class _Movie:  # noqa: D401
            pass

        audio_mod.Album = _Album
        audio_mod.Track = _Track
        video_mod.Season = _Season
        video_mod.Episode = _Episode
        video_mod.Movie = _Movie
        plexapi_mod.audio = audio_mod
        plexapi_mod.video = video_mod
        sys.modules["plexapi"] = plexapi_mod
        sys.modules["plexapi.audio"] = audio_mod
        sys.modules["plexapi.video"] = video_mod
    if "tenacity" not in sys.modules:
        tenacity_mod = types.ModuleType("tenacity")
        wait_mod = types.ModuleType("tenacity.wait")

        class _RetryIfException:  # noqa: D401
            def __init__(self, predicate=None):
                self.predicate = predicate

        class _WaitBase:  # noqa: D401
            pass

        tenacity_mod.retry_if_exception = _RetryIfException
        wait_mod.wait_base = _WaitBase
        sys.modules["tenacity"] = tenacity_mod
        sys.modules["tenacity.wait"] = wait_mod

    sys.path.insert(0, str(kometa_root))
    from modules import util as kometa_util  # pylint: disable=import-error,import-outside-toplevel
    from modules import overlay as kometa_overlay  # pylint: disable=import-error,import-outside-toplevel

    class _NullLogger:
        def debug(self, *args, **kwargs):
            return None

        def info(self, *args, **kwargs):
            return None

        def warning(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

        def trace(self, *args, **kwargs):
            return None

        def ghost(self, *args, **kwargs):
            return None

    if kometa_util.logger is None:
        kometa_util.logger = _NullLogger()
    if getattr(kometa_overlay, "logger", None) is None:
        kometa_overlay.logger = kometa_util.logger
    KometaOverlay = kometa_overlay.Overlay

    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("Jobs file must contain a list")
    results = []
    for job in jobs:
        case_id = job.get("case_id")
        if not case_id:
            continue
        try:
            output_path = _render_case(repo_root, out_dir, KometaOverlay, job)
            results.append({"case_id": case_id, "ok": True, "output_path": str(output_path)})
        except Exception as e:  # noqa: BLE001
            results.append({"case_id": case_id, "ok": False, "error": f"{type(e).__name__}: {e}"})

    Path(args.results).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
