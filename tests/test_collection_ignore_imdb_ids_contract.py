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


def _expected_ignore_imdb_ids_aliases():
    qs_map = _build_qs_collection_map()
    aliases = set()
    for path in _iter_collection_default_files():
        alias = path.stem
        if alias not in qs_map:
            continue
        for entry in _iter_template_entries(path):
            if isinstance(entry, str) and entry == "shared":
                aliases.add(alias)
                break
            if isinstance(entry, dict) and entry.get("name") == "shared":
                aliases.add(alias)
                break
    return aliases


def test_ignore_imdb_ids_exists_for_every_shared_collection_family():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_ignore_imdb_ids_aliases()

    missing = []
    for alias in expected_aliases:
        for collection in qs_map[alias]:
            if collection.get("readonly"):
                continue
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            if "ignore_imdb_ids" not in keys:
                missing.append(collection["id"])

    assert missing == []


def test_ignore_imdb_ids_uses_string_list_with_imdb_preset():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_ignore_imdb_ids_aliases()

    for alias in expected_aliases:
        for collection in qs_map[alias]:
            if collection.get("readonly"):
                continue
            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "ignore_imdb_ids")
            assert field["type"] == "string_list"
            assert field["validation_preset"] == "imdb_id_plex"
            assert "default" not in field


def test_ignore_ids_uses_string_list_with_numeric_preset():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_ignore_imdb_ids_aliases()

    for alias in expected_aliases:
        for collection in qs_map[alias]:
            if collection.get("readonly"):
                continue
            field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == "ignore_ids")
            assert field["type"] == "string_list"
            assert field["validation_preset"] == "numeric_id"
            assert "default" not in field
