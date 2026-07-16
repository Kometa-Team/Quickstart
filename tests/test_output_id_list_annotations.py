import re

from modules.output_dump import dump_section
from modules.output_render import apply_final_transformations


def test_collection_id_lists_sort_and_emit_saved_lookup_comments(app):
    config_data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "franchise",
                        "template_variables": {
                            "exclude": ["893731", "230161", "125574"],
                        },
                        "__template_variable_comments": {
                            "exclude": {
                                "893731": "Zeta Franchise",
                                "230161": "Beta Franchise",
                                "125574": "Alpha Franchise",
                            }
                        },
                    }
                ]
            }
        }
    }

    with app.app_context():
        transformed = apply_final_transformations(config_data, {"Movies": "movie"})
        yaml_content = dump_section("", "libraries", transformed["libraries"], "none", None)

    alpha_index = yaml_content.index("- '125574'")
    beta_index = yaml_content.index("- '230161'")
    zeta_index = yaml_content.index("- '893731'")

    assert alpha_index < beta_index < zeta_index
    assert re.search(r"- '125574'\s+# Alpha Franchise", yaml_content)
    assert re.search(r"- '230161'\s+# Beta Franchise", yaml_content)
    assert re.search(r"- '893731'\s+# Zeta Franchise", yaml_content)
    assert "__template_variable_comments" not in yaml_content


def test_collection_ignore_ids_emit_as_commented_sorted_rows(app):
    config_data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "franchise",
                        "template_variables": {
                            "ignore_ids": ["893731", "230161", "125574"],
                        },
                        "__template_variable_comments": {
                            "ignore_ids": {
                                "893731": "Zeta Franchise",
                                "230161": "Beta Franchise",
                                "125574": "Alpha Franchise",
                            }
                        },
                    }
                ]
            }
        }
    }

    with app.app_context():
        transformed = apply_final_transformations(config_data, {"Movies": "movie"})
        yaml_content = dump_section("", "libraries", transformed["libraries"], "none", None)

    assert yaml_content.index("- '125574'") < yaml_content.index("- '230161'") < yaml_content.index("- '893731'")
    assert re.search(r"- '125574'\s+# Alpha Franchise", yaml_content)
    assert re.search(r"- '230161'\s+# Beta Franchise", yaml_content)
    assert re.search(r"- '893731'\s+# Zeta Franchise", yaml_content)


def test_settings_ignore_ids_emit_as_commented_sorted_rows(app):
    settings = {
        "settings": {
            "ignore_ids": '["893731", "230161", "125574"]',
            "ignore_ids__lookup_labels": '{"893731":"Zeta Franchise","230161":"Beta Franchise","125574":"Alpha Franchise"}',
        }
    }

    with app.app_context():
        yaml_content = dump_section("", "settings", settings, "none", None)

    assert yaml_content.index("- 125574") < yaml_content.index("- 230161") < yaml_content.index("- 893731")
    assert re.search(r"- 125574\s+# Alpha Franchise", yaml_content)
    assert re.search(r"- 230161\s+# Beta Franchise", yaml_content)
    assert re.search(r"- 893731\s+# Zeta Franchise", yaml_content)
    assert "__lookup_labels" not in yaml_content


def test_library_placeholder_id_emits_saved_lookup_comment(app):
    config_data = {
        "libraries": {
            "Movies": {
                "template_variables": {
                    "use_separator": True,
                    "placeholder_imdb_id": "tt0108052",
                },
                "__template_variable_comments": {
                    "placeholder_imdb_id": {
                        "tt0108052": "Schindler's List",
                    }
                },
            }
        }
    }

    with app.app_context():
        yaml_content = dump_section("", "libraries", config_data["libraries"], "none", None)

    assert re.search(r"placeholder_imdb_id: tt0108052\s+# Schindler's List", yaml_content)
    assert "__template_variable_comments" not in yaml_content
