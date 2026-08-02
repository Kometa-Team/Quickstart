from ruamel.yaml import YAML

from modules.output_render import _validate_yaml_content


def test_validate_yaml_content_handles_non_string_mapping_keys():
    yaml_parser = YAML(typ="safe", pure=True)
    schema = {
        "type": "object",
        "patternProperties": {
            "^.+$": {"type": "object"},
        },
        "additionalProperties": False,
    }

    validated, first_error, errors = _validate_yaml_content("false: {}\n", yaml_parser, schema)

    assert validated is True
    assert first_error is None
    assert errors == []
