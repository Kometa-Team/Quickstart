import json
from pathlib import Path

from modules.output_collections import build_collection_files


def _defaults(entries):
    return [entry.get("default") or next(iter(entry.keys())) for entry in entries]


def test_collectionless_default_section_is_final_value():
    data = json.loads(Path("static/json/quickstart_collections.json").read_text(encoding="utf-8"))
    collectionless = next(collection for group in data for collection in group.get("collections", []) if collection.get("id") == "collection_collectionless")
    section = next(item for item in collectionless["template_variables"] if item.get("key") == "collection_section")
    assert section["default"] == "999"


def test_build_collection_files_uses_quickstart_json_order_not_saved_key_order():
    collections = {
        "movies": {
            "mov-library_movies-collection_studio": True,
            "mov-library_movies-collection_folder": True,
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-collection_basic": True,
            "mov-library_movies-collection_oscars": True,
            "mov-library_movies-collection_separator_award": True,
        }
    }
    raw_collection_entries = json.dumps(
        [
            {
                "type": "file",
                "location": "config/custom_collections.yml",
            }
        ]
    )

    collection_files, has_collectionless = build_collection_files(
        "mov-library_movies-library",
        "mov",
        collections,
        {},
        {"movies": {"mov-library_movies-collection_files": raw_collection_entries}},
        {},
    )

    assert has_collectionless is True
    assert _defaults(collection_files) == [
        "separator_award",
        "oscars",
        "basic",
        "studio",
        "folder",
        "file",
        "collectionless",
    ]


def test_collectionless_is_absolute_last_entry_after_raw_collection_files():
    collections = {
        "movies": {
            "mov-library_movies-collection_collectionless": True,
            "mov-library_movies-collection_basic": True,
        }
    }
    raw_collection_entries = json.dumps(
        [
            {"type": "file", "location": "config/advanced_custom.yml"},
        ]
    )

    collection_files, has_collectionless = build_collection_files(
        "mov-library_movies-library",
        "mov",
        collections,
        {},
        {"movies": {"mov-library_movies-collection_files": raw_collection_entries}},
        {},
    )

    assert has_collectionless is True
    assert _defaults(collection_files) == ["basic", "file", "collectionless"]
