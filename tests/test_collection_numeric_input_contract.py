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


def test_collection_child_limit_labels_are_specific():
    path = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_collections.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    generic_child_labels = []
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
                if isinstance(key, str) and key.startswith("limit_") and item.get("label") == "Limit":
                    generic_child_labels.append(key)

    assert generic_child_labels == []


def test_collection_child_numeric_inputs_use_wider_default_label_width_rule():
    path = Path(__file__).resolve().parents[1] / "templates" / "partials" / "_macros.html"
    template = path.read_text(encoding="utf-8")

    expected_rule = "item.key.startswith('limit_') or item.key.startswith('list_days_') or item.key.startswith('list_size_')"
    assert template.count(expected_rule) >= 2
    assert "320 if item.label|length > 24 else 240" in template
    assert "qs-template-variable-label" in template
