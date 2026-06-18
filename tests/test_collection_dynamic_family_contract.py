import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"

FIELD_TYPES = {
    "include": "string_list",
    "append_include": "string_list",
    "addons": "mapping_list",
    "append_addons": "mapping_list",
    "remove_suffix": "string_list",
}


def _build_qs_collection_map():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    mapping = {}
    for group in data:
        for collection in group.get("collections", []):
            alias = collection["id"].replace("collection_", "", 1)
            mapping.setdefault(alias, []).append(collection)
    return mapping


def _expected_dynamic_family_defaults():
    expected = {}
    bucket_media_types = {
        "both": {"movie", "show"},
        "movie": {"movie"},
        "show": {"show"},
    }

    for bucket, media_types in bucket_media_types.items():
        for path in sorted((DEFAULTS_ROOT / bucket).glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            keys = set()
            if re.search(r"(?m)^\s*include\s*:", text):
                keys.update({"include", "append_include"})
            if re.search(r"(?m)^\s*addons\s*:", text):
                keys.update({"addons", "append_addons"})
            if re.search(r"(?m)^\s*remove_suffix\s*:", text):
                keys.add("remove_suffix")
            if not keys:
                continue

            alias = path.stem
            media_key_map = expected.setdefault(alias, {})
            for media_type in media_types:
                media_key_map.setdefault(media_type, set()).update(keys)

    return expected


def test_dynamic_family_keys_exist_for_every_yaml_backed_collection_family():
    qs_map = _build_qs_collection_map()
    expected = _expected_dynamic_family_defaults()

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


def test_dynamic_family_key_types_match_the_defaults_contract():
    qs_map = _build_qs_collection_map()
    expected = _expected_dynamic_family_defaults()

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
                if key in {"addons", "append_addons"}:
                    assert field.get("key_placeholder")
                    assert field.get("value_placeholder")
