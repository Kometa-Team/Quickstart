import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"

FIELD_TYPES = {
    "sort_prefix": "text_input",
    "sort_title": "text_input",
    "name_format": "text_input",
    "summary_format": "text_input",
}


def _build_qs_collection_map():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    mapping = {}
    for group in data:
        for collection in group.get("collections", []):
            alias = collection["id"].replace("collection_", "", 1)
            mapping.setdefault(alias, []).append(collection)
    return mapping


def _expected_shared_naming_defaults():
    expected = {}
    bucket_media_types = {
        "award": {"movie", "show"},
        "both": {"movie", "show"},
        "chart": {"movie", "show"},
        "movie": {"movie"},
        "show": {"show"},
    }

    for bucket, media_types in bucket_media_types.items():
        for path in sorted((DEFAULTS_ROOT / bucket).glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            alias = path.stem
            keys = set()

            if "- shared" in text or "name: shared" in text:
                keys.update({"sort_prefix", "sort_title", "name_format", "summary_format"})
            elif re.search(r"(?m)^\s*sort_title\b", text):
                keys.add("sort_title")

            if not keys:
                continue

            media_key_map = expected.setdefault(alias, {})
            for media_type in media_types:
                media_key_map.setdefault(media_type, set()).update(keys)

    return expected


def test_shared_naming_keys_exist_for_every_supported_collection_family():
    qs_map = _build_qs_collection_map()
    expected = _expected_shared_naming_defaults()

    missing = []
    for alias, collections in qs_map.items():
        alias_expected = expected.get(alias)
        if not alias_expected:
            continue
        for collection in collections:
            if collection.get("readonly"):
                continue
            media_types = set(collection.get("media_types") or [])
            expected_keys = set()
            for media_type in media_types:
                expected_keys.update(alias_expected.get(media_type, set()))
            if not expected_keys:
                continue

            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            for key in sorted(expected_keys - keys):
                missing.append(f"{collection['id']}:{','.join(sorted(media_types))}:{key}")

    assert missing == []


def test_shared_naming_key_types_match_the_defaults_contract():
    qs_map = _build_qs_collection_map()
    expected = _expected_shared_naming_defaults()

    for alias, collections in qs_map.items():
        alias_expected = expected.get(alias)
        if not alias_expected:
            continue
        for collection in collections:
            if collection.get("readonly"):
                continue
            media_types = set(collection.get("media_types") or [])
            expected_keys = set()
            for media_type in media_types:
                expected_keys.update(alias_expected.get(media_type, set()))
            if not expected_keys:
                continue

            for key in sorted(expected_keys):
                field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == key)
                assert field["type"] == FIELD_TYPES[key]
