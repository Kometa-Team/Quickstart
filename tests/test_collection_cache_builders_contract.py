import json
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"
YAML = YAML(typ="safe", pure=True)
CACHE_TEMPLATES = {"custom", "mdb_smart"}


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


def _expected_cache_builders_defaults():
    qs_map = _build_qs_collection_map()
    defaults = {}
    for path in _iter_collection_default_files():
        alias = path.stem
        if alias not in qs_map:
            continue
        text = path.read_text(encoding="utf-8")
        has_support = False
        alias_default = None
        for entry in _iter_template_entries(path):
            if isinstance(entry, str) and entry in CACHE_TEMPLATES:
                has_support = True
                alias_default = 1 if alias_default is None else alias_default
            elif isinstance(entry, dict) and entry.get("name") in CACHE_TEMPLATES:
                has_support = True
                value = entry.get("cache_builders")
                if value is None:
                    value = 1
                alias_default = int(value)
        if "cache_builders:" in text or "cache_builders_<<key>>:" in text:
            has_support = True
            if alias_default is None:
                if "cache_builders: 0" in text:
                    alias_default = 0
                else:
                    alias_default = 1
        if has_support:
            defaults[alias] = alias_default if alias_default is not None else 1
    return defaults


def test_cache_builders_exists_for_every_cache_capable_collection_family():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_cache_builders_defaults()

    missing = []
    for alias, collections in qs_map.items():
        if alias not in expected_defaults:
            continue
        for collection in collections:
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            if "cache_builders" not in keys:
                missing.append(collection["id"])

    assert missing == []


def test_cache_builders_defaults_match_repo_defaults():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_cache_builders_defaults()

    for alias, expected_default in expected_defaults.items():
        for collection in qs_map[alias]:
            cache_field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "cache_builders")
            assert cache_field["type"] == "text_input"
            assert cache_field["input_type"] == "number"
            assert cache_field["default"] == expected_default
            assert cache_field["min"] == 0
            assert cache_field["step"] == 1


def test_cache_builders_is_not_inferred_for_basic_genre_or_network():
    qs_map = _build_qs_collection_map()
    expected_defaults = _expected_cache_builders_defaults()

    for alias in ("basic", "genre", "network"):
        assert alias not in expected_defaults
        for collection in qs_map[alias]:
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            assert "cache_builders" not in keys
