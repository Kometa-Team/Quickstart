import json
from pathlib import Path


EXACT_KEYS = {
    "data_depth",
    "data_limit",
    "discover_limit",
    "limit",
    "list_days",
    "list_size",
}
PREFIXES = (
    "limit_",
    "list_days_",
    "list_size_",
)


def _is_numeric_key(key):
    if key in EXACT_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in PREFIXES)


def test_collection_numeric_template_inputs_use_number_metadata():
    path = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_collections.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    matched = 0
    for group in payload:
        if not isinstance(group, dict):
            continue
        for collection in group.get("collections", []):
            if not isinstance(collection, dict):
                continue
            for item in collection.get("template_variables", []):
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                if not isinstance(key, str) or not _is_numeric_key(key):
                    continue
                matched += 1
                assert item.get("type") == "text_input", key
                assert item.get("input_type") == "number", key
                assert item.get("step") == 1, key
                expected_min = 0 if key == "discover_limit" else 1
                assert item.get("min") == expected_min, key

    assert matched > 0
