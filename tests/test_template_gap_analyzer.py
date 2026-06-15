import importlib.util
from pathlib import Path


def _load_gap_analyzer_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "analyze_uploaded_template_gaps.py"
    spec = importlib.util.spec_from_file_location("analyze_uploaded_template_gaps", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_qs_overlay_map_merges_duplicate_overlay_aliases(tmp_path):
    module = _load_gap_analyzer_module()
    qs_overlays = tmp_path / "quickstart_overlays.json"
    qs_overlays.write_text(
        """
[
  {
    "overlays": [
      {
        "id": "overlay_ratings",
        "template_variables": {
          "rating1": {},
          "rating3": {},
          "rating3_image": {}
        }
      },
      {
        "id": "overlay_ratings",
        "template_variables": {
          "rating1": {},
          "rating2": {},
          "rating_alignment": {}
        }
      }
    ]
  }
]
""".strip(),
        encoding="utf-8",
    )

    overlay_map = module.build_qs_overlay_map(qs_overlays)

    assert overlay_map["ratings"] >= {"rating1", "rating2", "rating3", "rating3_image", "rating_alignment"}


def test_build_qs_overlay_map_includes_rating3_for_repo_quickstart_file():
    module = _load_gap_analyzer_module()
    qs_overlays = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_overlays.json"

    overlay_map = module.build_qs_overlay_map(qs_overlays)

    assert "rating3" in overlay_map["ratings"]
    assert "rating3_image" in overlay_map["ratings"]
    assert "rating3_font" in overlay_map["ratings"]
    assert "rating3_font_size" in overlay_map["ratings"]
    assert "rating3_font_color" in overlay_map["ratings"]
    assert "rating3_vertical_offset" in overlay_map["ratings"]
    assert "rating_alignment" in overlay_map["ratings"]


def test_build_qs_overlay_map_adds_runtime_offset_and_alignment_keys(tmp_path):
    module = _load_gap_analyzer_module()
    qs_overlays = tmp_path / "quickstart_overlays.json"
    qs_overlays.write_text(
        """
[
  {
    "overlays": [
      {
        "id": "overlay_status",
        "default_offsets": {
          "horizontal": 15,
          "vertical": 15,
          "origin": "top_left"
        },
        "template_variables": [
          {
            "key": "use_airing"
          }
        ]
      }
    ]
  }
]
""".strip(),
        encoding="utf-8",
    )

    overlay_map = module.build_qs_overlay_map(qs_overlays)

    assert overlay_map["status"] >= {
        "use_airing",
        "horizontal_offset",
        "vertical_offset",
        "horizontal_align",
        "vertical_align",
    }


def test_build_qs_overlay_map_includes_runtime_offset_and_alignment_keys_for_repo_file():
    module = _load_gap_analyzer_module()
    qs_overlays = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_overlays.json"

    overlay_map = module.build_qs_overlay_map(qs_overlays)

    assert "horizontal_offset" in overlay_map["resolution"]
    assert "vertical_offset" in overlay_map["resolution"]
    assert "horizontal_align" in overlay_map["resolution"]
    assert "vertical_align" in overlay_map["resolution"]
    assert "horizontal_offset" in overlay_map["status"]
    assert "vertical_offset" in overlay_map["status"]


def test_build_qs_overlay_map_can_skip_runtime_support_enrichment(tmp_path):
    module = _load_gap_analyzer_module()
    qs_overlays = tmp_path / "quickstart_overlays.json"
    qs_overlays.write_text(
        """
[
  {
    "overlays": [
      {
        "id": "overlay_status",
        "default_offsets": {
          "horizontal": 15,
          "vertical": 15,
          "origin": "top_left"
        },
        "template_variables": [
          {
            "key": "use_airing"
          }
        ]
      }
    ]
  }
]
""".strip(),
        encoding="utf-8",
    )

    overlay_map = module.build_qs_overlay_map(qs_overlays, enrich_runtime_support=False)

    assert overlay_map["status"] == {"use_airing"}


def test_overlay_key_supported_in_quickstart_accepts_languages_use_subtitles_alias():
    module = _load_gap_analyzer_module()

    qs_overlays = {
        "languages": {"style", "languages"},
        "languages_subtitles": {"style", "languages", "use_subtitles"},
    }

    assert module.overlay_key_supported_in_quickstart("languages", "use_subtitles", qs_overlays) is True


def test_overlay_key_supported_in_quickstart_uses_direct_alias_match_when_available():
    module = _load_gap_analyzer_module()

    qs_overlays = {
        "ratings": {"rating1", "rating2", "rating3", "rating3_image"},
    }

    assert module.overlay_key_supported_in_quickstart("ratings", "rating3", qs_overlays) is True
    assert module.overlay_key_supported_in_quickstart("ratings", "rating3_image", qs_overlays) is True


def test_quickstart_recommendation_summary_includes_runtime_supported_overlay_keys():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "overlay",
            "default": "status",
            "key": "horizontal_align",
            "file": "config.yml",
            "library": "Shows",
            "matched_default_files": ["overlays/status.yml"],
            "supported_in_quickstart": True,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "supported_in_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        }
    ]

    summary = module.build_quickstart_recommendation_summary(rows)
    ranked = module.serialize_ranked_summary(summary)

    assert len(ranked) == 1
    assert ranked[0]["key"] == "horizontal_align"
    assert ranked[0]["supported_in_quickstart"] is True
    assert ranked[0]["quickstart_declared"] is False
