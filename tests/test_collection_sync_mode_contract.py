import json
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"
YAML = YAML(typ="safe", pure=True)
SYNC_TEMPLATES = {"custom", "filter", "mdb_smart"}


def _build_qs_collection_map():
    data = json.loads(QS_COLLECTIONS_PATH.read_text(encoding="utf-8"))
    mapping = {}
    for group in data:
        for collection in group.get("collections", []):
            alias = collection["id"].replace("collection_", "", 1)
            mapping.setdefault(alias, set()).update(item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key"))
    return mapping


def _iter_collection_default_files():
    for bucket in ("award", "both", "movie", "show", "chart"):
        yield from sorted((DEFAULTS_ROOT / bucket).glob("*.yml"))


def _template_names_for_default(path: Path):
    data = YAML.load(path.read_text(encoding="utf-8")) or {}
    names = set()
    for section_name in ("collections", "dynamic_collections"):
        section = data.get(section_name) or {}
        if not isinstance(section, dict):
            continue
        for cfg in section.values():
            if not isinstance(cfg, dict):
                continue
            template = cfg.get("template")
            if isinstance(template, list):
                for entry in template:
                    if isinstance(entry, str):
                        names.add(entry)
                    elif isinstance(entry, dict) and entry.get("name"):
                        names.add(str(entry["name"]))
            elif isinstance(template, dict) and template.get("name"):
                names.add(str(template["name"]))
            elif isinstance(template, str):
                names.add(template)
    return names


def _expected_sync_mode_aliases():
    qs_map = _build_qs_collection_map()
    aliases = set()
    for path in _iter_collection_default_files():
        alias = path.stem
        if alias not in qs_map:
            continue
        text = path.read_text(encoding="utf-8")
        has_direct_sync = "sync_mode:" in text or "sync_mode_<<key>>:" in text
        inherits_sync = bool(_template_names_for_default(path) & SYNC_TEMPLATES)
        if has_direct_sync or inherits_sync:
            aliases.add(alias)
    return aliases


def test_sync_mode_exists_for_every_sync_capable_collection_family():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_sync_mode_aliases()

    missing = sorted(alias for alias in expected_aliases if "sync_mode" not in qs_map[alias])

    assert missing == []


def test_sync_mode_is_not_inferred_for_genre_or_network():
    qs_map = _build_qs_collection_map()
    expected_aliases = _expected_sync_mode_aliases()

    assert "genre" not in expected_aliases
    assert "network" not in expected_aliases
    assert "sync_mode" not in qs_map["genre"]
    assert "sync_mode" not in qs_map["network"]
