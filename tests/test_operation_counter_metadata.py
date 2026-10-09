from html.parser import HTMLParser
import json

from flask import render_template_string
import pytest


class InputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []

    def handle_starttag(self, tag, attrs):
        if tag == "input":
            self.inputs.append(dict(attrs))


@pytest.mark.parametrize(
    "prefix",
    [
        "mass_user_rating_update",
        "mass_critic_rating_update",
        "mass_audience_rating_update",
        "mass_genre_update",
    ],
)
def test_source_order_is_saved_metadata_not_an_extra_modification(app, prefix):
    field_prefix = f"mov-library_1-attribute_{prefix}"
    saved_order = json.dumps(["tmdb", "imdb"])
    with app.app_context():
        html = render_template_string(
            """{% from 'partials/_macros.html' import mass_update_section %}
            {{ mass_update_section(library, data, {}, prefix, 'Update', '', '',
               sources=[('imdb', 'IMDb', ''), ('tmdb', 'TMDb', '')], container_class='accordion') }}""",
            library={"id": "mov-library_1"},
            data={
                "libraries": {
                    f"{field_prefix}_imdb": "true",
                    f"{field_prefix}_tmdb": "true",
                    f"{field_prefix}_order": saved_order,
                }
            },
            prefix=prefix,
        )
    parser = InputParser()
    parser.feed(html)
    order = next(field for field in parser.inputs if field.get("name") == f"{field_prefix}_order")
    assert order["type"] == "hidden"
    assert order["value"] == saved_order
    assert order["data-default"] == "[]"
    assert order["data-skip-override-count"] == "true"
    assert "data-skip-yaml" not in order
    sources = [field for field in parser.inputs if field.get("type") == "checkbox"]
    assert len(sources) == 2
    assert all("checked" in field and "data-skip-override-count" not in field for field in sources)
