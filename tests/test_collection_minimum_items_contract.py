import json
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"
YAML = YAML(typ="safe", pure=True)
MINIMUM_ITEM_TEMPLATES = {"shared", "separator", "collection", "tmdbshow"}


def _build_qs_collection_map():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    mapping = {}
    for group in data:
        for collection in group.get("collections", []):
            alias = collection["id"].replace("collection_", "", 1)
            mapping.setdefault(alias, []).append(collection)
    return mapping


def _iter_collection_default_files():
    for bucket in ("award", "both", "movie", "show", "chart"):
        yield from sorted((DEFAULTS_ROOT / bucket).glob("*.yml"))


def _iter_template_entries(path: Path):
    data = YAML.load(path.read_text(encoding="utf-8")) or {}
    for section_name in ("collections", "dynamic_collections"):
        section = data.get(section_name) or {}
        if not isinstance(section, dict):
            continue
        for cfg in section.values():
            if not isinstance(cfg, dict):
                continue
            template = cfg.get("template")
            if isinstance(template, list):
                yield from template
            elif template is not None:
                yield template


def _expected_minimum_items_defaults():
    qs_map = _build_qs_collection_map()
    defaults = {}
    for path in _iter_collection_default_files():
        alias = path.stem
        if alias not in qs_map:
            continue
        text = path.read_text(encoding="utf-8")
        has_support = False
        default_value = None
        for entry in _iter_template_entries(path):
            if isinstance(entry, str):
                if entry in MINIMUM_ITEM_TEMPLATES:
                    has_support = True
                if entry in {"collection", "tmdbshow"}:
                    default_value = default_value or 2
            elif isinstance(entry, dict):
                template_name = entry.get("name")
                if template_name in MINIMUM_ITEM_TEMPLATES:
                    has_support = True
                if template_name in {"collection", "tmdbshow"}:
                    default_value = default_value or 2
        if "minimum_items:" in text or "minimum_items_<<key>>:" in text:
            has_support = True
            if "minimum_items: 2" in text and default_value is None:
                default_value = 2
        if has_support:
            defaults[alias] = default_value
    return defaults


def test_minimum_items_exists_for_every_supported_non_readonly_collection_family():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_minimum_items_defaults()

    missing = []
    for alias, collections in qs_map.items():
        if alias not in expected_defaults:
            continue
        for collection in collections:
            if collection.get("readonly"):
                continue
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            if "minimum_items" not in keys:
                missing.append(collection["id"])

    assert missing == []


def test_minimum_items_defaults_and_numeric_contract_match_repo_defaults():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_minimum_items_defaults()

    for alias, expected_default in expected_defaults.items():
        for collection in qs_map[alias]:
            if collection.get("readonly"):
                continue
            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "minimum_items")
            assert field["type"] == "text_input"
            assert field["input_type"] == "number"
            assert field["min"] == 1
            assert field["step"] == 1
            if expected_default is None:
                assert "default" not in field
            else:
                assert field["default"] == expected_default


def test_minimum_items_is_not_added_to_readonly_separator_cards():
    qs_map = _build_qs_collection_map()

    for alias in ("separator_award", "separator_chart"):
        for collection in qs_map[alias]:
            assert collection.get("readonly") is True
            assert "template_variables" not in collection
