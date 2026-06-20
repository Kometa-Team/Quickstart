import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"


def _build_qs_collection_map():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    mapping = {}
    for group in data:
        for collection in group.get("collections", []):
            alias = collection["id"].replace("collection_", "", 1)
            mapping.setdefault(alias, []).append(collection)
    return mapping


def _expected_title_format_aliases():
    qs_map = _build_qs_collection_map()
    aliases = set()
    for bucket in ("award", "both", "movie", "show"):
        for path in sorted((DEFAULTS_ROOT / bucket).glob("*.yml")):
            alias = path.stem
            if alias not in qs_map:
                continue
            text = path.read_text(encoding="utf-8")
            if "title_format:" in text:
                aliases.add(alias)
    return aliases


def test_title_format_exists_for_every_supported_collection_family():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_title_format_aliases()

    missing = []
    for alias in sorted(expected_aliases):
        for collection in qs_map[alias]:
            if collection.get("readonly"):
                continue
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            if "title_format" not in keys:
                missing.append(collection["id"])

    assert missing == []


def test_title_format_uses_text_input_contract():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_title_format_aliases()

    for alias in sorted(expected_aliases):
        for collection in qs_map[alias]:
            if collection.get("readonly"):
                continue
            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "title_format")
            assert field["type"] == "text_input"
            assert "default" not in field
