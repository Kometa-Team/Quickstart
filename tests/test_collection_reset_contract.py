from pathlib import Path

MACROS_PATH = Path(__file__).resolve().parents[1] / "templates" / "partials" / "_macros.html"


def test_collection_template_variables_include_reset_button():
    text = MACROS_PATH.read_text(encoding="utf-8")

    assert 'data-toggle-parent="{{ library.id }}-{{ collection.id }}"' in text
    assert 'class="btn btn-sm btn-outline-secondary btn-overlay reset-offset-btn"' in text
    assert "Reset to Defaults" in text


def test_collection_reset_contract_exposes_defaults_for_supported_field_types():
    text = MACROS_PATH.read_text(encoding="utf-8")

    assert "data-default=\"{{ item.default | default('false', true) }}\"" in text
    assert "data-default=\"{{ item.default | default('', true) }}\"" in text
    assert "data-default='{{ list_default_json }}'" in text
