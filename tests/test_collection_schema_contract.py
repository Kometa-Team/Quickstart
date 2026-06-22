import json
from pathlib import Path

import jsonschema
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = ROOT / "tests" / "fixtures"

# `config/.schema` and `config/kometa/defaults` are gitignored local caches that the app
# populates at runtime (schema downloads, a real Kometa install). On a fresh checkout
# neither exists, so fall back to the checked-in fixtures to keep this test reproducible.
SCHEMA_PATH = ROOT / "config" / ".schema" / "collection-schema.json"
if not SCHEMA_PATH.exists():
    SCHEMA_PATH = FIXTURES_ROOT / "schema" / "collection-schema.json"

_DEFAULTS_BASE = ROOT / "config" / "kometa" / "defaults"
if not _DEFAULTS_BASE.exists():
    _DEFAULTS_BASE = FIXTURES_ROOT / "kometa" / "defaults"

DEFAULTS_ROOTS = [
    _DEFAULTS_BASE / "award",
    _DEFAULTS_BASE / "both",
    _DEFAULTS_BASE / "chart",
    _DEFAULTS_BASE / "movie",
    _DEFAULTS_BASE / "show",
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
                formatted = [f"{'.'.join(str(part) for part in err.absolute_path) or '<root>'}: {err.message}" for err in errors[:10]]
                failures.append(f"{path.relative_to(ROOT)}: " + " | ".join(formatted))

    assert not failures, "\n".join(failures)
