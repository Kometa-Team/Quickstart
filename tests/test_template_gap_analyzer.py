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


def test_build_qs_collection_map_preserves_dynamic_family_edge_cases_for_repo_file():
    module = _load_gap_analyzer_module()
    qs_collections = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_collections.json"

    collection_map = module.build_qs_collection_map(qs_collections)

    assert "data_limit" in collection_map["actor"]
    assert "data_limit" in collection_map["writer"]
    assert "data_limit" not in collection_map["studio"]
    assert "data_limit" not in collection_map["network"]


def test_key_is_valid_for_default_understands_dynamic_data_limit_from_repo_defaults():
    module = _load_gap_analyzer_module()
    root = Path(__file__).resolve().parents[1]
    actor_default = root / "config" / "kometa" / "defaults" / "both" / "actor.yml"
    writer_default = root / "config" / "kometa" / "defaults" / "movie" / "writer.yml"

    actor_valid, actor_matches = module.key_is_valid_for_default("data_limit", [actor_default])
    writer_valid, writer_matches = module.key_is_valid_for_default("data_limit", [writer_default])

    assert actor_valid is True
    assert actor_matches == [actor_default]
    assert writer_valid is True
    assert writer_matches == [writer_default]


def test_key_is_valid_for_default_does_not_infer_data_limit_for_studio_or_network_repo_defaults():
    module = _load_gap_analyzer_module()
    root = Path(__file__).resolve().parents[1]
    studio_default = root / "config" / "kometa" / "defaults" / "both" / "studio.yml"
    network_default = root / "config" / "kometa" / "defaults" / "show" / "network.yml"

    studio_valid, studio_matches = module.key_is_valid_for_default("data_limit", [studio_default])
    network_valid, network_matches = module.key_is_valid_for_default("data_limit", [network_default])

    assert studio_valid is False
    assert studio_matches == []
    assert network_valid is False
    assert network_matches == []


def test_key_is_valid_for_default_uses_repo_yaml_for_streaming_and_letterboxd_cases():
    module = _load_gap_analyzer_module()
    root = Path(__file__).resolve().parents[1]
    kometa_defaults = root / "config" / "kometa" / "defaults"
    streaming_defaults = module.resolve_default_paths("streaming", "collection", kometa_defaults)
    letterboxd_defaults = module.resolve_default_paths("letterboxd", "collection", kometa_defaults)

    streaming_valid, _streaming_matches = module.key_is_valid_for_default("discover_limit", streaming_defaults)
    letterboxd_valid, _letterboxd_matches = module.key_is_valid_for_default("use_top_500", letterboxd_defaults)
    imdb_top_250_valid, _imdb_top_250_matches = module.key_is_valid_for_default("use_imdb_top_250", letterboxd_defaults)

    assert streaming_valid is True
    assert letterboxd_valid is True
    assert imdb_top_250_valid is True


def test_key_is_valid_for_default_only_uses_referenced_template_chain():
    module = _load_gap_analyzer_module()
    root = Path(__file__).resolve().parents[1]
    kometa_defaults = root / "config" / "kometa" / "defaults"

    based_defaults = module.resolve_default_paths("based", "collection", kometa_defaults)
    genre_defaults = module.resolve_default_paths("genre", "collection", kometa_defaults)
    network_defaults = module.resolve_default_paths("network", "collection", kometa_defaults)
    streaming_defaults = module.resolve_default_paths("streaming", "collection", kometa_defaults)
    seasonal_defaults = module.resolve_default_paths("seasonal", "collection", kometa_defaults)
    collectionless_defaults = module.resolve_default_paths("collectionless", "collection", kometa_defaults)
    movie_franchise_defaults = module.resolve_default_paths("franchise", "collection", kometa_defaults)
    show_franchise_default = [root / "config" / "kometa" / "defaults" / "show" / "franchise.yml"]

    assert module.key_is_valid_for_default("collection_order", based_defaults)[0] is False
    assert module.key_is_valid_for_default("collection_order", genre_defaults)[0] is False
    assert module.key_is_valid_for_default("collection_order", streaming_defaults)[0] is False
    assert module.key_is_valid_for_default("sync_mode", genre_defaults)[0] is False
    assert module.key_is_valid_for_default("sync_mode", network_defaults)[0] is False

    assert module.key_is_valid_for_default("sync_mode", streaming_defaults)[0] is True
    assert module.key_is_valid_for_default("sync_mode", seasonal_defaults)[0] is True
    assert module.key_is_valid_for_default("collection_order", collectionless_defaults)[0] is True
    assert module.key_is_valid_for_default("collection_order", movie_franchise_defaults)[0] is True
    assert module.key_is_valid_for_default("sync_mode", movie_franchise_defaults)[0] is True
    assert module.key_is_valid_for_default("collection_order", show_franchise_default)[0] is True
    assert module.key_is_valid_for_default("sync_mode", show_franchise_default)[0] is True


def test_quickstart_recommendation_summary_uses_yaml_verified_collection_edges():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "collection",
            "default": "actor",
            "key": "data_limit",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["both/actor.yml"],
            "supported_in_quickstart": True,
            "quickstart_declared": True,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "supported_in_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "number",
        },
        {
            "kind": "collection",
            "default": "studio",
            "key": "data_limit",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": [],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": False,
            "validation_level": "unverified",
            "name_verified": False,
            "value_shape_verified": True,
            "value_shape_rule": "number",
        },
        {
            "kind": "collection",
            "default": "streaming",
            "key": "discover_limit",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["both/streaming.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "number",
        },
    ]

    summary = module.build_quickstart_recommendation_summary(rows)
    ranked = module.serialize_ranked_summary(summary)

    assert [item["key"] for item in ranked] == ["discover_limit"]
