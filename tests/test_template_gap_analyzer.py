import importlib.util
import tarfile
import zipfile
from gzip import open as gzip_open
from pathlib import Path


def _load_gap_analyzer_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "analyze_uploaded_template_gaps.py"
    spec = importlib.util.spec_from_file_location("analyze_uploaded_template_gaps", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _kometa_defaults_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    real = root / "config" / "kometa" / "defaults"
    # `config/kometa/defaults` is a gitignored local cache populated by a real Kometa
    # install. On a fresh checkout it won't exist, so fall back to the checked-in fixtures.
    if real.exists():
        return real
    return root / "tests" / "fixtures" / "kometa" / "defaults"


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


def test_build_qs_overlay_map_includes_source_override_types_for_repo_file():
    module = _load_gap_analyzer_module()
    qs_overlays = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_overlays.json"

    overlay_map = module.build_qs_overlay_map(qs_overlays)

    assert {"file", "url", "git", "repo"} <= overlay_map["resolution"]
    assert {"file", "url", "git", "repo"} <= overlay_map["audio_codec"]
    assert {"file", "url", "git", "repo"} <= overlay_map["network"]


def test_build_qs_overlay_map_exposes_fixed_key_overlay_aliases_for_repo_file():
    module = _load_gap_analyzer_module()
    qs_overlays = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_overlays.json"

    overlay_map = module.build_qs_overlay_map(qs_overlays)

    assert "commonsense" in overlay_map
    assert {"horizontal_align", "vertical_align", "horizontal_offset", "vertical_offset", "back_width", "back_color"} <= overlay_map["commonsense"]


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


def test_overlay_key_supported_in_quickstart_is_case_insensitive_for_overlay_aliases():
    module = _load_gap_analyzer_module()

    qs_overlays = {
        "status": {"horizontal_align", "vertical_align", "horizontal_offset", "vertical_offset"},
    }

    assert module.overlay_key_supported_in_quickstart("Status", "horizontal_align", qs_overlays) is True
    assert module.overlay_key_supported_in_quickstart("STATUS", "vertical_offset", qs_overlays) is True


def test_overlay_key_supported_in_quickstart_accepts_prefixed_source_override_keys():
    module = _load_gap_analyzer_module()

    qs_overlays = {
        "resolution": {"file", "url", "git", "repo"},
    }

    assert module.overlay_key_supported_in_quickstart("resolution", "file_4k", qs_overlays) is True
    assert module.overlay_key_supported_in_quickstart("resolution", "url_4k", qs_overlays) is True
    assert module.overlay_key_supported_in_quickstart("resolution", "git_4k", qs_overlays) is True
    assert module.overlay_key_supported_in_quickstart("resolution", "repo_4k", qs_overlays) is True


def test_quickstart_recommendation_summary_skips_runtime_supported_overlay_keys():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "overlay",
            "default": "status",
            "key": "back_width",
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

    assert ranked == []


def test_quickstart_recommendation_summary_excludes_legacy_or_not_recommended_library_keys():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "library",
            "default": None,
            "key": "metadata_path",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "path",
        },
        {
            "kind": "library",
            "default": None,
            "key": "library_name",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "library",
            "default": None,
            "key": "library_type",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": False,
            "validation_level": "importer_metadata_only",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "library",
            "default": None,
            "key": "sort_by",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "library",
            "default": None,
            "key": "exclude",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "list",
        },
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
        },
    ]

    summary = module.build_quickstart_recommendation_summary(rows)
    ranked = module.serialize_ranked_summary(summary)

    assert [item["key"] for item in ranked] == ["library_name"]


def test_quickstart_recommendation_exclusion_summary_tracks_legacy_library_keys():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "library",
            "default": None,
            "key": "metadata_path",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "path",
        },
        {
            "kind": "library",
            "default": None,
            "key": "reapply_overlays",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "boolean",
        },
        {
            "kind": "library",
            "default": None,
            "key": "library_type",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": False,
            "validation_level": "importer_metadata_only",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "library",
            "default": None,
            "key": "sort_by",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "library",
            "default": None,
            "key": "exclude",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "list",
        },
        {
            "kind": "overlay",
            "default": "status",
            "key": "vertical_align",
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
        },
    ]

    excluded = sorted(
        module.build_quickstart_recommendation_exclusion_summary(rows).values(),
        key=lambda item: str(item["key"]),
    )

    assert [item["key"] for item in excluded] == ["exclude", "library_type", "metadata_path", "reapply_overlays", "sort_by"]
    reasons = {item["key"]: item["reason"] for item in excluded}
    assert reasons["library_type"] == "internal_importer_or_analyzer_metadata"
    assert reasons["metadata_path"] == "legacy_library_path_key_not_recommended"
    assert reasons["reapply_overlays"] == "valid_but_not_recommended_for_quickstart"
    assert reasons["sort_by"] == "library_template_variable_not_documented_for_quickstart"
    assert reasons["exclude"] == "library_template_variable_not_documented_for_quickstart"


def test_build_qs_collection_map_preserves_dynamic_family_edge_cases_for_repo_file():
    module = _load_gap_analyzer_module()
    qs_collections = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_collections.json"

    collection_map = module.build_qs_collection_map(qs_collections)

    assert "data_limit" in collection_map["actor"]
    assert "data_limit" in collection_map["writer"]
    assert "data_limit" not in collection_map["studio"]
    assert "data_limit" not in collection_map["network"]


def test_build_qs_library_template_keys_includes_separator_placeholder_keys_for_repo_file():
    module = _load_gap_analyzer_module()
    qs_attributes = Path(__file__).resolve().parents[1] / "static" / "json" / "quickstart_attributes.json"

    keys = module.build_qs_library_template_keys(qs_attributes)

    assert "placeholder_imdb_id" in keys
    assert "placeholder_tmdb_movie" in keys
    assert "placeholder_tvdb_show" in keys


def test_key_is_valid_for_default_understands_dynamic_data_limit_from_repo_defaults():
    module = _load_gap_analyzer_module()
    kometa_defaults = _kometa_defaults_root()
    actor_default = kometa_defaults / "both" / "actor.yml"
    writer_default = kometa_defaults / "movie" / "writer.yml"

    actor_valid, actor_matches = module.key_is_valid_for_default("data_limit", [actor_default])
    writer_valid, writer_matches = module.key_is_valid_for_default("data_limit", [writer_default])

    assert actor_valid is True
    assert actor_matches == [actor_default]
    assert writer_valid is True
    assert writer_matches == [writer_default]


def test_key_is_valid_for_default_does_not_infer_data_limit_for_studio_or_network_repo_defaults():
    module = _load_gap_analyzer_module()
    kometa_defaults = _kometa_defaults_root()
    studio_default = kometa_defaults / "both" / "studio.yml"
    network_default = kometa_defaults / "show" / "network.yml"

    studio_valid, studio_matches = module.key_is_valid_for_default("data_limit", [studio_default])
    network_valid, network_matches = module.key_is_valid_for_default("data_limit", [network_default])

    assert studio_valid is False
    assert studio_matches == []
    assert network_valid is False
    assert network_matches == []


def test_key_is_valid_for_default_uses_repo_yaml_for_streaming_and_letterboxd_cases():
    module = _load_gap_analyzer_module()
    kometa_defaults = _kometa_defaults_root()
    streaming_defaults = module.resolve_default_paths("streaming", "collection", kometa_defaults)
    letterboxd_defaults = module.resolve_default_paths("letterboxd", "collection", kometa_defaults)

    streaming_valid, _streaming_matches = module.key_is_valid_for_default("discover_limit", streaming_defaults)
    # "Letterboxd Top 500" has no use_top_500 toggle in the real default (unlike the
    # neighboring "IMDb Top 250" entry, which does define use_imdb_top_250).
    letterboxd_valid, _letterboxd_matches = module.key_is_valid_for_default("use_top_500", letterboxd_defaults)
    imdb_top_250_valid, _imdb_top_250_matches = module.key_is_valid_for_default("use_imdb_top_250", letterboxd_defaults)

    assert streaming_valid is True
    assert letterboxd_valid is False
    assert imdb_top_250_valid is True


def test_resolve_default_paths_for_collection_does_not_cross_into_overlay_defaults():
    module = _load_gap_analyzer_module()
    kometa_defaults = _kometa_defaults_root()

    network_defaults = module.resolve_default_paths("network", "collection", kometa_defaults)

    assert all("overlays" not in str(path).lower() for path in network_defaults)
    assert any(path.parts[-2:] == ("show", "network.yml") for path in network_defaults)
    assert module.key_is_valid_for_default("horizontal_align", network_defaults)[0] is False
    assert module.key_is_valid_for_default("vertical_align", network_defaults)[0] is False


def test_resolve_default_paths_for_overlays_is_case_insensitive():
    module = _load_gap_analyzer_module()
    kometa_defaults = _kometa_defaults_root()

    status_defaults = module.resolve_default_paths("Status", "overlay", kometa_defaults)

    assert any(path.name.lower() == "status.yml" for path in status_defaults)


def test_classify_yaml_document_type_distinguishes_config_and_external_yaml():
    module = _load_gap_analyzer_module()

    assert module.classify_yaml_document_type({"libraries": {}}) == "config"
    assert module.classify_yaml_document_type({"collections": {}}) == "external_collection"
    assert module.classify_yaml_document_type({"dynamic_collections": {}}) == "external_collection"
    assert module.classify_yaml_document_type({"overlays": {}}) == "external_overlay"
    assert module.classify_yaml_document_type({"metadata": {}}) == "external_metadata"
    assert module.classify_yaml_document_type({"playlists": {}}) == "external_playlist"
    assert module.classify_yaml_document_type({"templates": {}}) == "external_template_bundle"
    assert module.classify_yaml_document_type(["not", "a", "mapping"]) == "unknown"


def test_prefilter_yaml_files_skips_external_yaml_early_when_focus_is_config(tmp_path):
    module = _load_gap_analyzer_module()
    overlay_file = tmp_path / "overlay.yml"
    overlay_file.write_text(
        """
overlays:
  Resolution:
    overlay:
      name: text(4K)
""".strip(),
        encoding="utf-8",
    )

    candidates, skipped, stats = module.prefilter_yaml_files([overlay_file], yaml_type_focus="config")

    assert candidates == []
    assert len(skipped) == 1
    assert skipped[0]["error_type"] == "NotKometaConfig"
    assert stats["non_kometa_skips"] == 1


def test_prefilter_yaml_files_does_not_skip_real_config_just_because_filename_looks_like_artifact(tmp_path):
    module = _load_gap_analyzer_module()
    config_file = tmp_path / "parsed_message.txt_config_Mel-46174d489990d66d.yml"
    config_file.write_text(
        """
libraries:
  Movies:
    collection_files:
      - pmm: basic
settings:
  cache: true
""".strip(),
        encoding="utf-8",
    )

    candidates, skipped, stats = module.prefilter_yaml_files([config_file], yaml_type_focus="config")

    assert candidates == [config_file]
    assert skipped == []
    assert stats["artifact_skips"] == 0


def test_prefilter_yaml_files_skips_quickstart_schema_sample_configs_when_focus_is_config(tmp_path):
    module = _load_gap_analyzer_module()
    sample_file = tmp_path / "json-schema" / "prototype_comprehensive.yml"
    sample_file.parent.mkdir(parents=True, exist_ok=True)
    sample_file.write_text(
        """
libraries:
  Movies:
    collection_files:
      - pmm: basic
settings:
  cache: true
""".strip(),
        encoding="utf-8",
    )

    candidates, skipped, stats = module.prefilter_yaml_files([sample_file], yaml_type_focus="config")

    assert candidates == []
    assert len(skipped) == 1
    assert skipped[0]["error_type"] == "IgnoredSampleConfig"
    assert skipped[0]["noise_reason"] == "quickstart_sample_config"
    assert stats["artifact_skips"] == 1


def test_scan_uploaded_configs_excludes_external_yaml_when_focus_is_config(tmp_path):
    module = _load_gap_analyzer_module()
    overlay_file = tmp_path / "overlay.yml"
    overlay_file.write_text(
        """
overlays:
  Resolution:
    overlay:
      name: text(4K)
""".strip(),
        encoding="utf-8",
    )

    findings, importer_findings, skipped, parsed_paths, stats = module.scan_uploaded_configs(
        [overlay_file],
        yaml_type_focus="config",
    )

    assert findings == []
    assert importer_findings == []
    assert parsed_paths == []
    assert stats["type_excluded"] == 1
    assert skipped[0]["error_type"] == "YamlTypeExcluded"
    assert skipped[0]["yaml_document_type"] == "external_overlay"
    assert skipped[0]["noise_reason"] == "yaml_type_excluded"


def test_prefilter_yaml_files_skips_template_variable_only_external_yaml_when_focus_is_config(tmp_path):
    module = _load_gap_analyzer_module()
    external_file = tmp_path / "collection.yml"
    external_file.write_text(
        """
collections:
  Test:
    template:
      name: test
    template_variables:
      visible_home: true
""".strip(),
        encoding="utf-8",
    )

    candidates, skipped, stats = module.prefilter_yaml_files([external_file], yaml_type_focus="config")

    assert candidates == []
    assert len(skipped) == 1
    assert skipped[0]["error_type"] == "NotKometaConfig"
    assert stats["non_kometa_skips"] == 1


def test_collect_yaml_files_recurses_into_nested_zip_archives(tmp_path):
    module = _load_gap_analyzer_module()
    inner_yaml = "libraries:\n  Movies:\n    collection_files:\n      - pmm: basic\n"
    inner_zip = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner_zip, "w") as inner_handle:
        inner_handle.writestr("config.yml", inner_yaml)

    outer_zip = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer_zip, "w") as outer_handle:
        outer_handle.write(inner_zip, arcname="nested/inner.zip")

    yaml_files, temp_dirs = module.collect_yaml_files([outer_zip], include_archives=True)

    try:
        assert len(yaml_files) == 1
        assert yaml_files[0].name == "config.yml"
        assert yaml_files[0].read_text(encoding="utf-8") == inner_yaml
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()


def test_collect_yaml_files_reuses_persistent_archive_cache_without_reopening_zip(tmp_path):
    module = _load_gap_analyzer_module()
    archive_cache_dir = tmp_path / "archive_cache"
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as handle:
        handle.writestr("config.yml", "libraries:\n  Movies:\n    collection_files:\n      - pmm: basic\n")

    yaml_files, temp_dirs = module.collect_yaml_files([zip_path], include_archives=True, archive_cache_dir=archive_cache_dir)
    try:
        assert len(yaml_files) == 1
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()

    original_zipfile = module.zipfile.ZipFile

    class FailIfOpenedZipFile:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("zip should not be reopened when archive cache is warm")

    module.zipfile.ZipFile = FailIfOpenedZipFile
    try:
        yaml_files_second, temp_dirs_second = module.collect_yaml_files([zip_path], include_archives=True, archive_cache_dir=archive_cache_dir)
        try:
            assert len(yaml_files_second) == 1
            assert yaml_files_second[0].read_text(encoding="utf-8").startswith("libraries:")
        finally:
            for temp_dir in temp_dirs_second:
                temp_dir.cleanup()
    finally:
        module.zipfile.ZipFile = original_zipfile


def test_collect_yaml_files_archive_cache_falls_back_when_move_fails(tmp_path):
    module = _load_gap_analyzer_module()
    archive_cache_dir = tmp_path / "archive_cache"
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as handle:
        handle.writestr("config.yml", "libraries:\n  Movies:\n    collection_files:\n      - pmm: basic\n")

    original_move = module.shutil.move
    move_calls = {"count": 0}

    def flaky_move(src, dst, *args, **kwargs):
        move_calls["count"] += 1
        raise PermissionError("simulated windows directory move failure")

    module.shutil.move = flaky_move
    try:
        yaml_files, temp_dirs = module.collect_yaml_files([zip_path], include_archives=True, archive_cache_dir=archive_cache_dir)
        try:
            assert len(yaml_files) == 1
            assert yaml_files[0].read_text(encoding="utf-8").startswith("libraries:")
            assert move_calls["count"] >= 1
            cache_entries = [path for path in archive_cache_dir.iterdir() if path.is_dir() and not path.name.startswith(".")]
            assert cache_entries
        finally:
            for temp_dir in temp_dirs:
                temp_dir.cleanup()
    finally:
        module.shutil.move = original_move


def test_collect_yaml_files_reads_yaml_from_tar_gz_archive(tmp_path):
    module = _load_gap_analyzer_module()
    source_yaml = tmp_path / "config.yml"
    source_yaml.write_text("libraries:\n  Movies:\n    collection_files:\n      - pmm: basic\n", encoding="utf-8")
    tar_gz = tmp_path / "bundle.tar.gz"

    with tarfile.open(tar_gz, "w:gz") as tf:
        tf.add(source_yaml, arcname="bundle/config.yml")

    yaml_files, temp_dirs = module.collect_yaml_files([tar_gz], include_archives=True)

    try:
        assert len(yaml_files) == 1
        assert yaml_files[0].name == "config.yml"
        assert "libraries:" in yaml_files[0].read_text(encoding="utf-8")
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()


def test_collect_yaml_files_reads_yaml_from_plain_gz_archive(tmp_path):
    module = _load_gap_analyzer_module()
    gz_path = tmp_path / "config.yml.gz"
    with gzip_open(gz_path, "wt", encoding="utf-8") as handle:
        handle.write("libraries:\n  Movies:\n    collection_files:\n      - pmm: basic\n")

    yaml_files, temp_dirs = module.collect_yaml_files([gz_path], include_archives=True)

    try:
        assert len(yaml_files) == 1
        assert yaml_files[0].name == "config.yml"
        assert "libraries:" in yaml_files[0].read_text(encoding="utf-8")
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()


def test_collect_yaml_files_ignores_plain_gz_that_expands_to_non_yaml_file(tmp_path):
    module = _load_gap_analyzer_module()
    gz_path = tmp_path / "meta.log.gz"
    with gzip_open(gz_path, "wt", encoding="utf-8") as handle:
        handle.write("this is not yaml\njust a plain log file\n")

    yaml_files, temp_dirs = module.collect_yaml_files([gz_path], include_archives=True)

    try:
        assert yaml_files == []
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()


def test_collect_yaml_files_skips_7z_when_optional_dependency_is_unavailable(tmp_path):
    module = _load_gap_analyzer_module()
    archive_path = tmp_path / "bundle.7z"
    archive_path.write_bytes(b"not-a-real-7z")
    original_py7zr = module.py7zr
    module.py7zr = None

    try:
        yaml_files, temp_dirs = module.collect_yaml_files([archive_path], include_archives=True)
        assert yaml_files == []
        assert temp_dirs == []
    finally:
        module.py7zr = original_py7zr


def test_collect_yaml_files_skips_archives_by_default(tmp_path):
    module = _load_gap_analyzer_module()
    zip_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as handle:
        handle.writestr("config.yml", "libraries:\n  Movies:\n    collection_files:\n      - pmm: basic\n")

    yaml_files, temp_dirs = module.collect_yaml_files([zip_path])

    try:
        assert yaml_files == []
        assert temp_dirs == []
    finally:
        for temp_dir in temp_dirs:
            temp_dir.cleanup()


def test_should_exclude_directory_skips_analyzer_runtime_cache_dirs(tmp_path):
    module = _load_gap_analyzer_module()
    root = tmp_path / "scan-root"
    archive_cache_dir = root / "repo" / "artifacts" / "template_gap_archive_cache"
    verify_dir = root / "repo" / "artifacts" / "template_gap_verify_checkpoint"

    assert module.should_exclude_directory(archive_cache_dir, root, enabled=True) is True
    assert module.should_exclude_directory(verify_dir, root, enabled=True) is True


def test_extract_importer_findings_from_data_maps_collection_template_var_miss_to_alias():
    module = _load_gap_analyzer_module()

    data = {
        "libraries": {
            "Movies": {
                "collection_files": [
                    {
                        "default": "streaming",
                        "template_variables": {
                            "not_a_real_qs_key": True,
                        },
                    }
                ]
            }
        }
    }

    findings = module.extract_importer_findings_from_data(data, Path("sample.yml"))

    assert any(
        row["kind"] == "collection" and row["default"] == "streaming" and row["key"] == "not_a_real_qs_key" and row["reason_class"] == "missing_template_variable_support"
        for row in findings
    )


def test_extract_importer_findings_from_data_captures_unsupported_top_level_section():
    module = _load_gap_analyzer_module()

    data = {
        "bogus_section": {
            "enabled": True,
        }
    }

    findings = module.extract_importer_findings_from_data(data, Path("sample.yml"))

    assert any(row["kind"] == "section" and row["key"] == "bogus_section" and row["reason_class"] == "unsupported_section" for row in findings)


def test_serialize_importer_ranked_summary_groups_by_status_key_and_reason():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "file": "a.yml",
            "library": "Movies",
            "section": "collection_files",
            "default": "streaming",
            "kind": "collection",
            "key": "not_a_real_qs_key",
            "detail_key": "template_variables.not_a_real_qs_key",
            "import_status": "unmapped",
            "import_reason": "Template variable not available in Quickstart.",
            "reason_class": "missing_template_variable_support",
            "raw_path": "libraries.Movies.collection_files[0].template_variables.not_a_real_qs_key",
            "source": "importer",
        },
        {
            "file": "b.yml",
            "library": "Movies",
            "section": "collection_files",
            "default": "streaming",
            "kind": "collection",
            "key": "not_a_real_qs_key",
            "detail_key": "template_variables.not_a_real_qs_key",
            "import_status": "unmapped",
            "import_reason": "Template variable not available in Quickstart.",
            "reason_class": "missing_template_variable_support",
            "raw_path": "libraries.Movies.collection_files[0].template_variables.not_a_real_qs_key",
            "source": "importer",
        },
    ]

    ranked = module.serialize_importer_ranked_summary(module.build_importer_summary(rows))

    assert len(ranked) == 1
    assert ranked[0]["kind"] == "collection"
    assert ranked[0]["default"] == "streaming"
    assert ranked[0]["key"] == "not_a_real_qs_key"
    assert ranked[0]["import_status"] == "unmapped"
    assert ranked[0]["reason_class"] == "missing_template_variable_support"
    assert ranked[0]["occurrences"] == 2


def test_build_merged_fix_queue_combines_schema_quickstart_and_importer_actions():
    module = _load_gap_analyzer_module()

    verified_rows = [
        {
            "kind": "collection",
            "default": "streaming",
            "key": "discover_limit",
            "occurrences": 3,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["both/streaming.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
        }
    ]
    importer_rows = [
        {
            "kind": "collection",
            "default": "streaming",
            "key": "discover_limit",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 2,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        }
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert len(ranked) == 1
    assert ranked[0]["key"] == "discover_limit"
    assert ranked[0]["action_targets"] == ["schema", "quickstart", "importer"]
    assert ranked[0]["total_occurrences"] == 5
    assert ranked[0]["importer_reason_classes"] == ["missing_template_variable_support"]


def test_build_merged_fix_queue_suppresses_excluded_quickstart_only_keys():
    module = _load_gap_analyzer_module()

    verified_rows = [
        {
            "kind": "overlay",
            "default": "status",
            "key": "horizontal_align",
            "occurrences": 4,
            "files": ["config.yml"],
            "libraries": ["Shows"],
            "matched_default_files": ["overlays/status.yml"],
            "supported_in_quickstart": True,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
        }
    ]
    importer_rows = [
        {
            "kind": "overlay",
            "default": "status",
            "key": "horizontal_align",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 1,
            "files": ["config.yml"],
            "libraries": ["Shows"],
            "reasons": ["Template variable not available in Quickstart."],
        }
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert len(ranked) == 1
    assert ranked[0]["key"] == "horizontal_align"
    assert ranked[0]["action_targets"] == ["importer"]


def test_build_merged_fix_queue_suppresses_importer_only_rows_without_verified_default_support():
    module = _load_gap_analyzer_module()

    verified_rows = []
    importer_rows = [
        {
            "kind": "overlay",
            "default": "ratings",
            "key": "horizontal_align",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 3,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        }
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert ranked == []


def test_quickstart_recommendation_summary_excludes_overlay_style_keys_misclassified_as_library_scope():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "library",
            "default": None,
            "key": "horizontal_align",
            "file": "config.yml",
            "library": "Shows",
            "matched_default_files": [],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "library",
            "default": None,
            "key": "back_width",
            "file": "config.yml",
            "library": "Shows",
            "matched_default_files": [],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "number",
        },
    ]

    summary = module.build_quickstart_recommendation_summary(rows)
    ranked = module.serialize_ranked_summary(summary)
    excluded = module.build_quickstart_recommendation_exclusion_summary(rows)

    assert ranked == []
    assert excluded[("library", "", "horizontal_align")]["reason"] == "overlay_rendering_key_misclassified_at_library_scope"
    assert excluded[("library", "", "back_width")]["reason"] == "overlay_rendering_key_misclassified_at_library_scope"


def test_build_merged_fix_queue_excludes_overlay_style_keys_misclassified_as_library_scope():
    module = _load_gap_analyzer_module()

    verified_rows = [
        {
            "kind": "library",
            "default": None,
            "key": "horizontal_align",
            "occurrences": 10,
            "files": ["config.yml"],
            "libraries": ["Shows"],
            "matched_default_files": [],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
        }
    ]
    importer_rows = [
        {
            "kind": "library",
            "default": None,
            "key": "horizontal_align",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 10,
            "files": ["config.yml"],
            "libraries": ["Shows"],
            "reasons": ["Template variable not available in Quickstart."],
        }
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert ranked == []


def test_quickstart_recommendation_summary_excludes_internal_overlay_finalizer_keys():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "overlay",
            "default": "resolution",
            "key": "final_horizontal_offset",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["overlays/resolution.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "number",
        }
    ]

    summary = module.build_quickstart_recommendation_summary(rows)
    excluded = module.build_quickstart_recommendation_exclusion_summary(rows)

    assert summary == {}
    assert excluded[("overlay", "resolution", "final_horizontal_offset")]["reason"] == "internal_overlay_finalizer_key_not_user_facing"


def test_quickstart_recommendation_summary_excludes_dynamic_collection_child_instance_keys_but_keeps_real_family_keys():
    module = _load_gap_analyzer_module()

    rows = [
        {
            "kind": "collection",
            "default": "seasonal",
            "key": "trakt_list_christmas",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["movie/seasonal.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "string",
        },
        {
            "kind": "collection",
            "default": "franchise",
            "key": "movie_645",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["movie/franchise.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "dynamic",
        },
        {
            "kind": "collection",
            "default": "franchise",
            "key": "title_override",
            "file": "config.yml",
            "library": "Movies",
            "matched_default_files": ["movie/franchise.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
            "name_verified": True,
            "value_shape_verified": True,
            "value_shape_rule": "dynamic",
        },
    ]

    summary = module.build_quickstart_recommendation_summary(rows)
    ranked = module.serialize_ranked_summary(summary)
    excluded = module.build_quickstart_recommendation_exclusion_summary(rows)

    assert [item["key"] for item in ranked] == ["title_override"]
    assert excluded[("collection", "seasonal", "trakt_list_christmas")]["reason"] == "dynamic_collection_child_instance_key_not_ranked"
    assert excluded[("collection", "franchise", "movie_645")]["reason"] == "dynamic_collection_child_instance_key_not_ranked"


def test_build_merged_fix_queue_excludes_internal_and_dynamic_instance_false_positives():
    module = _load_gap_analyzer_module()

    verified_rows = [
        {
            "kind": "overlay",
            "default": "resolution",
            "key": "final_vertical_offset",
            "occurrences": 8,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["overlays/resolution.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
        },
        {
            "kind": "collection",
            "default": "seasonal",
            "key": "trakt_list_halloween",
            "occurrences": 5,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["movie/seasonal.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
        },
        {
            "kind": "collection",
            "default": "franchise",
            "key": "build_collection",
            "occurrences": 4,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["movie/franchise.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": False,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart_and_schema",
        },
    ]
    importer_rows = [
        {
            "kind": "overlay",
            "default": "resolution",
            "key": "final_vertical_offset",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 8,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        },
        {
            "kind": "collection",
            "default": "seasonal",
            "key": "trakt_list_halloween",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 5,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        },
        {
            "kind": "collection",
            "default": "franchise",
            "key": "build_collection",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 4,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        },
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert [item["key"] for item in ranked] == ["build_collection"]
    assert ranked[0]["action_targets"] == ["schema", "quickstart", "importer"]


def test_build_merged_fix_queue_excludes_internal_library_type_metadata():
    module = _load_gap_analyzer_module()

    verified_rows = [
        {
            "kind": "library",
            "default": None,
            "key": "library_name",
            "occurrences": 4,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
        }
    ]
    importer_rows = [
        {
            "kind": "library",
            "default": None,
            "key": "library_type",
            "import_status": "unmapped",
            "reason_class": "library_type_unknown",
            "occurrences": 9,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Library type could not be determined."],
        },
        {
            "kind": "library",
            "default": None,
            "key": "library_name",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 2,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        },
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert len(ranked) == 1
    assert ranked[0]["key"] == "library_name"
    assert ranked[0]["action_targets"] == ["quickstart", "importer"]


def test_build_merged_fix_queue_excludes_undocumented_library_template_variables():
    module = _load_gap_analyzer_module()

    verified_rows = [
        {
            "kind": "library",
            "default": None,
            "key": "sort_by",
            "occurrences": 4,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
        },
        {
            "kind": "library",
            "default": None,
            "key": "exclude",
            "occurrences": 4,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "matched_default_files": ["config/config.yml"],
            "supported_in_quickstart": False,
            "quickstart_declared": False,
            "schema_declared": True,
            "kometa_declared": True,
            "validation_level": "works_in_kometa_missing_from_quickstart",
        },
    ]
    importer_rows = [
        {
            "kind": "library",
            "default": None,
            "key": "sort_by",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 1,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        },
        {
            "kind": "library",
            "default": None,
            "key": "exclude",
            "import_status": "unmapped",
            "reason_class": "missing_template_variable_support",
            "occurrences": 1,
            "files": ["config.yml"],
            "libraries": ["Movies"],
            "reasons": ["Template variable not available in Quickstart."],
        },
    ]

    ranked = module.build_merged_fix_queue(verified_rows, importer_rows)

    assert ranked == []


def test_extract_importer_findings_from_data_ignores_bare_library_container_status():
    module = _load_gap_analyzer_module()

    original_prepare = module.importer.prepare_import_payload
    original_parse = module.importer._parse_report_details

    class _DummyReport:
        lines = []

    def _fake_prepare_import_payload(*_args, **_kwargs):
        return {}, _DummyReport()

    def _fake_parse_report_details(_lines):
        return {"libraries.Movies": "unmapped"}, {"libraries.Movies": "Library type could not be determined."}

    module.importer.prepare_import_payload = _fake_prepare_import_payload
    module.importer._parse_report_details = _fake_parse_report_details
    try:
        findings = module.extract_importer_findings_from_data({"libraries": {"Movies": {}}}, Path("sample.yml"))
    finally:
        module.importer.prepare_import_payload = original_prepare
        module.importer._parse_report_details = original_parse

    assert findings == []


def test_looks_like_kometa_config_text_accepts_non_template_variable_configs():
    module = _load_gap_analyzer_module()

    raw_text = """
libraries:
  Movies:
    operations:
      mass_genre_update:
        - source: trakt_list
"""

    assert module.looks_like_kometa_config_text(raw_text) is True


def test_is_probable_non_config_artifact_flags_parsed_log_extract_name():
    module = _load_gap_analyzer_module()

    path = Path(r"C:\temp\fromDownloads\parsed_meta.log_config-371b30add732f96d.yml")

    assert module.is_probable_non_config_artifact(path) is True


def test_read_text_with_fallbacks_accepts_cp1252_file(tmp_path):
    module = _load_gap_analyzer_module()

    path = tmp_path / "config.yml"
    path.write_bytes("libraries:\n  Movies:\n    note: smart’quote\n".encode("cp1252"))

    text, encoding = module.read_text_with_fallbacks(path)

    assert "smart’quote" in text
    assert encoding in {"cp1252", "latin-1"}


def test_key_is_valid_for_default_only_uses_referenced_template_chain():
    module = _load_gap_analyzer_module()
    kometa_defaults = _kometa_defaults_root()

    based_defaults = module.resolve_default_paths("based", "collection", kometa_defaults)
    genre_defaults = module.resolve_default_paths("genre", "collection", kometa_defaults)
    network_defaults = module.resolve_default_paths("network", "collection", kometa_defaults)
    streaming_defaults = module.resolve_default_paths("streaming", "collection", kometa_defaults)
    seasonal_defaults = module.resolve_default_paths("seasonal", "collection", kometa_defaults)
    collectionless_defaults = module.resolve_default_paths("collectionless", "collection", kometa_defaults)
    movie_franchise_defaults = module.resolve_default_paths("franchise", "collection", kometa_defaults)
    show_franchise_default = [kometa_defaults / "show" / "franchise.yml"]

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
