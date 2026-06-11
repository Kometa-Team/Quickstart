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
    assert "rating_alignment" in overlay_map["ratings"]
