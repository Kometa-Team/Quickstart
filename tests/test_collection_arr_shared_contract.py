import json
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
QS_COLLECTIONS_PATH = ROOT / "static" / "json" / "quickstart_collections.json"
DEFAULTS_ROOT = ROOT / "config" / "kometa" / "defaults"
YAML_LOADER = YAML(typ="safe", pure=True)

MOVIE_ARR_KEYS = {
    "radarr_add_missing",
    "radarr_folder",
    "radarr_tag",
    "item_radarr_tag",
    "radarr_monitor",
    "radarr_upgrade_existing",
    "radarr_monitor_existing",
    "radarr_search",
}
SHOW_ARR_KEYS = {
    "sonarr_add_missing",
    "sonarr_folder",
    "sonarr_tag",
    "item_sonarr_tag",
    "sonarr_monitor",
    "sonarr_upgrade_existing",
    "sonarr_monitor_existing",
    "sonarr_search",
}
TOGGLE_KEYS = {
    "radarr_add_missing",
    "sonarr_add_missing",
    "radarr_monitor",
    "radarr_upgrade_existing",
    "radarr_monitor_existing",
    "sonarr_upgrade_existing",
    "sonarr_monitor_existing",
    "radarr_search",
    "sonarr_search",
}
STRING_LIST_KEYS = {"radarr_tag", "sonarr_tag", "item_radarr_tag", "item_sonarr_tag"}
TEXT_INPUT_KEYS = {"radarr_folder", "sonarr_folder"}
SONARR_MONITOR_OPTIONS = ["all", "none", "future", "missing", "existing", "pilot", "first", "latest"]


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


def _template_names(path: Path):
    data = YAML_LOADER.load(path.read_text(encoding="utf-8")) or {}
    names = set()
    for section_name in ("collections", "dynamic_collections"):
        section = data.get(section_name) or {}
        if not isinstance(section, dict):
            continue
        for cfg in section.values():
            if not isinstance(cfg, dict):
                continue
            for template_key in ("template", "other_template"):
                template = cfg.get(template_key)
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


def _expected_arr_shared_defaults():
    expected = {}
    all_keys = MOVIE_ARR_KEYS | SHOW_ARR_KEYS
    for path in _iter_collection_default_files():
        alias = path.stem
        text = path.read_text(encoding="utf-8")
        names = _template_names(path)
        supported = expected.setdefault(alias, set())
        for key in all_keys:
            if key.startswith("item_"):
                if "shared" in names or f"{key}:" in text or f"{key}_<<key>>:" in text:
                    supported.add(key)
                continue
            if "arr" in names or f"{key}:" in text or f"{key}_<<key>>:" in text:
                supported.add(key)
    return expected


def test_arr_shared_keys_exist_for_every_supported_non_readonly_collection_family():
    qs_map = _build_qs_collection_map()
    expected = _expected_arr_shared_defaults()

    missing = []
    for alias, collections in qs_map.items():
        supported = expected.get(alias, set())
        if not supported:
            continue
        for collection in collections:
            if collection.get("readonly"):
                continue
            keys = {item["key"] for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key")}
            media_types = set(collection.get("media_types") or [])
            expected_keys = set()
            if "movie" in media_types:
                expected_keys |= supported & MOVIE_ARR_KEYS
            if "show" in media_types:
                expected_keys |= supported & SHOW_ARR_KEYS
            for key in sorted(expected_keys - keys):
                missing.append(f"{collection['id']}:{key}")

    assert missing == []


def test_arr_shared_key_types_match_the_defaults_contract():
    qs_map = _build_qs_collection_map()
    expected = _expected_arr_shared_defaults()

    for alias, collections in qs_map.items():
        supported = expected.get(alias, set())
        if not supported:
            continue
        for collection in collections:
            if collection.get("readonly"):
                continue
            media_types = set(collection.get("media_types") or [])
            expected_keys = set()
            if "movie" in media_types:
                expected_keys |= supported & MOVIE_ARR_KEYS
            if "show" in media_types:
                expected_keys |= supported & SHOW_ARR_KEYS

            for key in expected_keys:
                field = next(item for item in collection.get("template_variables", []) if isinstance(item, dict) and item.get("key") == key)
                if key in TOGGLE_KEYS:
                    assert field["type"] == "toggle"
                elif key in STRING_LIST_KEYS:
                    assert field["type"] == "string_list"
                    assert "default" not in field
                elif key in TEXT_INPUT_KEYS:
                    assert field["type"] == "text_input"
                elif key == "sonarr_monitor":
                    assert field["type"] == "select"
                    assert [option["value"] for option in field["options"]] == SONARR_MONITOR_OPTIONS
                else:
                    raise AssertionError(f"Unhandled ARR/shared contract key {key}")
