"""Foundational constants shared across the helpers package.

Owns the small pieces of shared state that many submodules read at
import time:

- Filesystem layout: ``BASE_DIR``, ``WORKING_DIR``, ``MEIPASS_DIR``,
  ``CONFIG_DIR``, ``JSON_SETTINGS``, ``VERSION_FILE``, ``BUILDNUM_FILE``,
  ``RESTART_NOTICE_FILE``
- Upstream URLs: ``GITHUB_BASE_URL``, ``IMAGEMAID_GITHUB_BASE_URL``
- Redaction hint: ``STRING_FIELDS``
- File type sets: ``ALLOWED_EXTENSIONS``, ``FONT_EXTENSIONS``
- Update-cache TTLs and in-memory dicts for Quickstart, Kometa, and ImageMaid
- Branch-override sets: ``KOMETA_BRANCH_OVERRIDES``, ``IMAGEMAID_BRANCH_OVERRIDES``

Historically named ``_legacy.py`` — this module was the last surviving
chunk of the original monolithic ``helpers.py``. All functions have been
extracted into dedicated submodules; what remains here is pure constants.
"""

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
