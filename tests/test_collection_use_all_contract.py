import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"

EXCLUDED_USE_KEYS = {"use_separator", "use_year_collections", "use_all"}


def _build_qs_collection_map():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    mapping = {}
    for group in data:
        for collection in group.get("collections", []):
            alias = collection["id"].replace("collection_", "", 1)
            mapping.setdefault(alias, []).append(collection)
    return mapping


def _expected_shared_family_defaults():
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
            if "- shared" not in text and "name: shared" not in text:
                continue
            alias = path.stem
            media_key_map = expected.setdefault(alias, {})
            for media_type in media_types:
                media_key_map.setdefault(media_type, set()).add("use_all")

    return expected


def test_use_all_exists_for_every_shared_collection_family_with_child_use_toggles():
    qs_map = _build_qs_collection_map()
    expected = _expected_shared_family_defaults()

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
            if "use_all" not in expected_keys:
                continue

            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            child_use_keys = {key for key in keys if key.startswith("use_") and key not in EXCLUDED_USE_KEYS}
            if not child_use_keys:
                continue
            if "use_all" not in keys:
                missing.append(f"{collection['id']}:{','.join(sorted(media_types))}")

    assert missing == []


def test_use_all_field_matches_the_shared_collection_contract():
    qs_map = _build_qs_collection_map()
    expected = _expected_shared_family_defaults()

    for alias, collections in qs_map.items():
        alias_expected = expected.get(alias)
        if not alias_expected:
            continue
        for collection in collections:
            if collection.get("readonly"):
                continue
            keys = [item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")]
            child_use_keys = [key for key in keys if key.startswith("use_") and key not in EXCLUDED_USE_KEYS]
            if not child_use_keys or "use_all" not in keys:
                continue

            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "use_all")
            assert field["type"] == "toggle"
            assert field["default"] is True
            assert "override" in field["tooltip"].lower()
