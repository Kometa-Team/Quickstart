import os

from flask import has_request_context, session

from modules import helpers

UPLOAD_FOLDER = os.path.join(helpers.CONFIG_DIR, "uploads")
UPLOAD_FOLDERS = {
    "movie": os.path.join(UPLOAD_FOLDER, "movies"),
    "show": os.path.join(UPLOAD_FOLDER, "shows"),
    "season": os.path.join(UPLOAD_FOLDER, "seasons"),
    "episode": os.path.join(UPLOAD_FOLDER, "episodes"),
}
# Ensure all upload subdirectories exist
for _folder in UPLOAD_FOLDERS.values():
    os.makedirs(_folder, exist_ok=True)

IMAGES_FOLDER = os.path.join(helpers.MEIPASS_DIR, "static", "images")
OVERLAY_FOLDER = os.path.join(IMAGES_FOLDER, "overlays")
FONTS_FOLDER = os.path.join(helpers.MEIPASS_DIR, "static", "fonts")
DEFAULT_IMAGE_MAP = {
    "movie": os.path.join(IMAGES_FOLDER, "default.png"),
    "show": os.path.join(IMAGES_FOLDER, "default-sho_preview.png"),
    "season": os.path.join(IMAGES_FOLDER, "default-season_preview.png"),
    "episode": os.path.join(IMAGES_FOLDER, "default-episode_preview.png"),
}
BUILTIN_PREVIEW_IMAGES = (
    "overlay_alignment_guide.png",
    "overlay_alignment_guide_episodes.png",
)
BUILTIN_PREVIEW_IMAGES_BY_TYPE = {
    "movie": ("overlay_alignment_guide.png",),
    "show": ("overlay_alignment_guide.png",),
    "season": ("overlay_alignment_guide.png",),
    "episode": ("overlay_alignment_guide_episodes.png",),
}
PREVIEW_FOLDER = os.path.join(helpers.CONFIG_DIR, "previews")
os.makedirs(PREVIEW_FOLDER, exist_ok=True)
OVERLAY_CACHE_FOLDER = os.path.join(helpers.CONFIG_DIR, "cache", "overlays")
os.makedirs(OVERLAY_CACHE_FOLDER, exist_ok=True)
OVERLAY_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30

_FONT_CACHE: dict[str, list[str]] = {}


def clear_font_cache():
    global _FONT_CACHE
    _FONT_CACHE = {}


def list_overlay_fonts() -> list[str]:
    """Font discovery (TTF/OTF) across common static dirs."""
    config_name = session.get("config_name") if has_request_context() else None
    if config_name:
        migration = helpers.migrate_legacy_custom_fonts_to_config(config_name)
        if migration.get("copied"):
            clear_font_cache()
    cache_key = helpers.normalize_config_name_for_storage(config_name) if config_name else "__default__"
    cached = _FONT_CACHE.get(cache_key)
    if cached:
        return cached
    fonts: list[str] = []
    font_dirs = helpers.get_font_dirs(include_static=True, include_custom=True, config_name=config_name)
    for fdir in font_dirs:
        try:
            if os.path.isdir(fdir):
                for fname in os.listdir(fdir):
                    if fname.lower().endswith((".ttf", ".otf")) and fname not in fonts:
                        fonts.append(fname)
        except Exception:
            continue
    _FONT_CACHE[cache_key] = fonts
    return fonts


def list_preview_images_for_type(image_type: str) -> list[str]:
    """Return built-in guide images plus uploaded images for a preview image type."""
    builtin_candidates = BUILTIN_PREVIEW_IMAGES_BY_TYPE.get(image_type, ())
    builtins = [name for name in builtin_candidates if os.path.exists(os.path.join(IMAGES_FOLDER, name))]
    uploads_dir = UPLOAD_FOLDERS.get(image_type)
    uploads: list[str] = []
    if uploads_dir and os.path.exists(uploads_dir):
        uploads = sorted(
            [img for img in os.listdir(uploads_dir) if any(img.lower().endswith(f".{ext}") for ext in helpers.ALLOWED_EXTENSIONS)],
            key=str.casefold,
        )
    return builtins + [img for img in uploads if img not in builtins]


def build_preview_image_data() -> dict[str, list[str]]:
    return {img_type: list_preview_images_for_type(img_type) for img_type in UPLOAD_FOLDERS}


def resolve_preview_base_image_path(img_type: str, selected_image: str) -> str:
    if not selected_image or selected_image == "default":
        return DEFAULT_IMAGE_MAP.get(img_type, DEFAULT_IMAGE_MAP["movie"])

    if selected_image in BUILTIN_PREVIEW_IMAGES and selected_image not in BUILTIN_PREVIEW_IMAGES_BY_TYPE.get(img_type, ()):
        return DEFAULT_IMAGE_MAP.get(img_type, DEFAULT_IMAGE_MAP["movie"])

    static_candidate = helpers.safe_join(IMAGES_FOLDER, selected_image)
    if static_candidate and static_candidate.exists():
        return str(static_candidate)

    upload_candidate = helpers.safe_join(UPLOAD_FOLDERS[img_type], selected_image)
    if upload_candidate and upload_candidate.exists():
        return str(upload_candidate)

    return DEFAULT_IMAGE_MAP.get(img_type, DEFAULT_IMAGE_MAP["movie"])
