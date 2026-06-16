import json
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"
YAML = YAML(typ="safe", pure=True)


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


def _expected_collection_order_defaults():
    qs_map = _build_qs_collection_map()
    defaults = {}
    release_templates = {"collection", "tmdbshow"}
    for path in _iter_collection_default_files():
        alias = path.stem
        if alias not in qs_map:
            continue
        text = path.read_text(encoding="utf-8")
        has_support = False
        default_value = None
        for entry in _iter_template_entries(path):
            if isinstance(entry, str):
                if entry == "custom":
                    has_support = True
                    default_value = default_value or "custom"
                elif entry in release_templates:
                    has_support = True
                    default_value = default_value or "release"
            elif isinstance(entry, dict):
                template_name = entry.get("name")
                if template_name == "custom":
                    has_support = True
                    default_value = str(entry.get("collection_order", "custom"))
                elif template_name in release_templates:
                    has_support = True
                    default_value = str(entry.get("collection_order", "release"))
        if alias == "collectionless":
            has_support = True
            default_value = "alpha"
        elif "collection_order:" in text or "collection_order_<<key>>:" in text:
            has_support = True
            default_value = default_value or "custom"
        if has_support:
            if alias in defaults and defaults[alias] == "release":
                continue
            defaults[alias] = default_value or defaults.get(alias) or "custom"
    return defaults


def test_collection_order_exists_for_every_supported_collection_family():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_collection_order_defaults()

    missing = []
    for alias, collections in qs_map.items():
        if alias not in expected_defaults:
            continue
        for collection in collections:
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            if "collection_order" not in keys:
                missing.append(collection["id"])

    assert missing == []


def test_collection_order_defaults_match_repo_defaults():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_collection_order_defaults()

    for alias, expected_default in expected_defaults.items():
        for collection in qs_map[alias]:
            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "collection_order")
            assert field["type"] == "select"
            assert field["default"] == expected_default


def test_collection_order_is_not_inferred_for_streaming_seasonal_genre_or_network():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_collection_order_defaults()

    for alias in ("streaming", "seasonal", "genre", "network", "basic"):
        assert alias not in expected_defaults
        for collection in qs_map[alias]:
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            assert "collection_order" not in keys
