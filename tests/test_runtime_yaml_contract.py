from ruamel.yaml import YAML

from modules.output_dump import dump_section


def test_runtime_overlay_emits_explicit_empty_prefix():
    data = {
        "libraries": {
            "Movies": {
                "overlay_files": [
                    {
                        "default": "runtimes",
                        "template_variables": {
                            "text": "",
                            "format": "<<runtimeH>>h <<runtimeM>>m",
                        },
                    }
                ]
            }
        }
    }

    yaml_content = dump_section("", "libraries", data, "none", None)
    parsed = YAML(typ="safe", pure=True).load(yaml_content)
    runtime_entry = parsed["libraries"]["Movies"]["overlay_files"][0]

    assert runtime_entry["template_variables"]["text"] == ""
    assert "text: ''" in yaml_content


def test_other_empty_template_variables_are_still_pruned():
    data = {
        "libraries": {
            "Movies": {
                "overlay_files": [
                    {
                        "default": "resolution",
                        "template_variables": {
                            "style": "",
                            "horizontal_position": "left",
                        },
                    }
                ]
            }
        }
    }

    yaml_content = dump_section("", "libraries", data, "none", None)
    parsed = YAML(typ="safe", pure=True).load(yaml_content)
    template_vars = parsed["libraries"]["Movies"]["overlay_files"][0]["template_variables"]

    assert "style" not in template_vars
    assert template_vars["horizontal_position"] == "left"
