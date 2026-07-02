import os
import sys

STRING_FIELDS = {"apikey", "token", "username", "password"}
GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/Kometa"
IMAGEMAID_GITHUB_BASE_URL = "https://raw.githubusercontent.com/Kometa-Team/ImageMaid"

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
FONT_EXTENSIONS = {".ttf", ".otf"}

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
WORKING_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
MEIPASS_DIR = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR  # noqa

JSON_SETTINGS = os.path.join(MEIPASS_DIR, "static", "json")

CONFIG_DIR = os.path.join(WORKING_DIR, "config")
os.makedirs(CONFIG_DIR, exist_ok=True)

VERSION_FILE = os.path.join(MEIPASS_DIR, "VERSION")
BUILDNUM_FILE = os.path.join(MEIPASS_DIR, "BUILDNUM")

RESTART_NOTICE_FILE = os.path.join(CONFIG_DIR, ".restart_notice.json")
PLEX_DISCOVERY_CACHE_TTL_SECONDS = int(os.environ.get("QS_PLEX_DISCOVERY_CACHE_TTL_SECONDS", "300"))
QS_UPDATE_CACHE_TTL_SECONDS = int(os.environ.get("QS_UPDATE_CACHE_TTL_SECONDS", "600"))
_QS_UPDATE_CACHE = {}
KOMETA_UPDATE_CACHE_TTL_SECONDS = int(os.environ.get("QS_KOMETA_UPDATE_CACHE_TTL_SECONDS", "600"))
_KOMETA_UPDATE_CACHE = {}
KOMETA_BRANCH_OVERRIDES = {"master", "develop", "nightly"}
IMAGEMAID_UPDATE_CACHE_TTL_SECONDS = int(os.environ.get("QS_IMAGEMAID_UPDATE_CACHE_TTL_SECONDS", "600"))
_IMAGEMAID_UPDATE_CACHE = {}
IMAGEMAID_BRANCH_OVERRIDES = {"master", "develop"}
