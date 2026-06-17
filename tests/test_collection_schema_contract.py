import json
from pathlib import Path

import jsonschema
from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "config" / ".schema" / "collection-schema.json"
DEFAULTS_ROOTS = [
    ROOT / "config" / "kometa" / "defaults" / "award",
    ROOT / "config" / "kometa" / "defaults" / "both",
    ROOT / "config" / "kometa" / "defaults" / "chart",
    ROOT / "config" / "kometa" / "defaults" / "movie",
    ROOT / "config" / "kometa" / "defaults" / "show",
]


def test_collection_schema_validates_all_top_level_collection_defaults():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft7Validator(schema)
    yaml = YAML(typ="safe", pure=True)

    failures = []
    for defaults_root in DEFAULTS_ROOTS:
        for path in sorted(defaults_root.glob("*.yml")):
            parsed = yaml.load(path.read_text(encoding="utf-8"))
            errors = sorted(
                validator.iter_errors(parsed),
                key=lambda err: (".".join(str(part) for part in err.absolute_path), err.validator, err.message),
            )
            if errors:
                formatted = [
                    f"{'.'.join(str(part) for part in err.absolute_path) or '<root>'}: {err.message}"
                    for err in errors[:10]
                ]
                failures.append(f"{path.relative_to(ROOT)}: " + " | ".join(formatted))

    assert not failures, "\n".join(failures)
