"""Tests for modules/bundle_artifacts.py.

All 25 public functions are pure utilities (string transforms, path
mapping, ZIP building) -- no Flask client or monkeypatching needed for
the core cases.  We use a real temp directory for the handful of
functions that actually touch the filesystem.
"""

import io
import zipfile
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_config_dir(tmp_path, monkeypatch):
    """Point helpers.CONFIG_DIR at a temp dir so path-resolution helpers work."""
    import modules.helpers as helpers
    monkeypatch.setattr(helpers, "CONFIG_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# yaml_path_suffix
# ---------------------------------------------------------------------------

def test_yaml_path_suffix_accepts_yml():
    from modules.bundle_artifacts import yaml_path_suffix
    assert yaml_path_suffix("config.yml") is True


def test_yaml_path_suffix_accepts_yaml():
    from modules.bundle_artifacts import yaml_path_suffix
    assert yaml_path_suffix("config.yaml") is True


def test_yaml_path_suffix_case_insensitive():
    from modules.bundle_artifacts import yaml_path_suffix
    assert yaml_path_suffix("CONFIG.YML") is True
    assert yaml_path_suffix("UPPER.YAML") is True


def test_yaml_path_suffix_rejects_other_extensions():
    from modules.bundle_artifacts import yaml_path_suffix
    assert yaml_path_suffix("image.png") is False
    assert yaml_path_suffix("font.ttf") is False
    assert yaml_path_suffix("README.txt") is False


def test_yaml_path_suffix_rejects_empty_and_none():
    from modules.bundle_artifacts import yaml_path_suffix
    assert yaml_path_suffix("") is False
    assert yaml_path_suffix(None) is False


# ---------------------------------------------------------------------------
# normalize_bundle_member_name
# ---------------------------------------------------------------------------

def test_normalize_bundle_member_name_strips_leading_slashes():
    from modules.bundle_artifacts import normalize_bundle_member_name
    assert normalize_bundle_member_name("/foo/bar.yml") == "foo/bar.yml"
    assert normalize_bundle_member_name("///foo/bar") == "foo/bar"


def test_normalize_bundle_member_name_converts_backslashes():
    from modules.bundle_artifacts import normalize_bundle_member_name
    assert normalize_bundle_member_name("\\foo\\bar.yml") == "foo/bar.yml"


def test_normalize_bundle_member_name_collapses_double_slashes():
    from modules.bundle_artifacts import normalize_bundle_member_name
    assert normalize_bundle_member_name("foo//bar.yml") == "foo/bar.yml"


def test_normalize_bundle_member_name_empty_and_none():
    from modules.bundle_artifacts import normalize_bundle_member_name
    assert normalize_bundle_member_name("") == ""
    assert normalize_bundle_member_name(None) == ""


# ---------------------------------------------------------------------------
# is_allowed_bundle_member
# ---------------------------------------------------------------------------

def test_is_allowed_bundle_member_allows_yml():
    from modules.bundle_artifacts import is_allowed_bundle_member
    assert is_allowed_bundle_member("myconfig.yml") is True


def test_is_allowed_bundle_member_allows_font_extensions():
    from modules.bundle_artifacts import is_allowed_bundle_member
    assert is_allowed_bundle_member("fonts/custom.ttf") is True
    assert is_allowed_bundle_member("fonts/custom.otf") is True


def test_is_allowed_bundle_member_allows_readme():
    from modules.bundle_artifacts import is_allowed_bundle_member
    assert is_allowed_bundle_member("README.txt") is True
    assert is_allowed_bundle_member("readme.txt") is True


def test_is_allowed_bundle_member_rejects_executables():
    from modules.bundle_artifacts import is_allowed_bundle_member
    assert is_allowed_bundle_member("evil.exe") is False
    assert is_allowed_bundle_member("shell.sh") is False


def test_is_allowed_bundle_member_rejects_path_traversal():
    from modules.bundle_artifacts import is_allowed_bundle_member
    # Path traversal attempts should be rejected or safely normalized
    # ../../etc/passwd after normalize becomes etc/passwd which has no allowed ext
    assert is_allowed_bundle_member("../../etc/passwd") is False


def test_is_allowed_bundle_member_allows_empty_path():
    from modules.bundle_artifacts import is_allowed_bundle_member
    # Empty member name: normalize_bundle_member_name returns "" which triggers early True
    assert is_allowed_bundle_member("") is True


# ---------------------------------------------------------------------------
# normalize_config_name
# ---------------------------------------------------------------------------

def test_normalize_config_name_lowercases_and_replaces_spaces():
    from modules.bundle_artifacts import normalize_config_name
    assert normalize_config_name("My Config") == "my_config"


def test_normalize_config_name_strips_whitespace():
    from modules.bundle_artifacts import normalize_config_name
    assert normalize_config_name("  test  ") == "test"


def test_normalize_config_name_falls_back_to_default_on_empty():
    from modules.bundle_artifacts import normalize_config_name
    assert normalize_config_name("") == "default"
    assert normalize_config_name("   ") == "default"
    assert normalize_config_name(None) == "default"


# ---------------------------------------------------------------------------
# safe_bundle_name
# ---------------------------------------------------------------------------

def test_safe_bundle_name_sanitises_special_chars():
    from modules.bundle_artifacts import safe_bundle_name
    result = safe_bundle_name("My Config!")
    # werkzeug secure_filename drops punctuation, keeps alphanumerics and underscores
    assert result  # non-empty
    assert "!" not in result


def test_safe_bundle_name_falls_back_to_default():
    from modules.bundle_artifacts import safe_bundle_name
    assert safe_bundle_name(None) == "default"
    assert safe_bundle_name("") == "default"


# ---------------------------------------------------------------------------
# safe_overlay_bundle_slug
# ---------------------------------------------------------------------------

def test_safe_overlay_bundle_slug_replaces_special_chars_with_underscore():
    from modules.bundle_artifacts import safe_overlay_bundle_slug
    assert safe_overlay_bundle_slug("My Library!", "library") == "My_Library"


def test_safe_overlay_bundle_slug_uses_fallback_when_result_empty():
    from modules.bundle_artifacts import safe_overlay_bundle_slug
    assert safe_overlay_bundle_slug("", "fallback") == "fallback"
    assert safe_overlay_bundle_slug("!!!", "fallback") == "fallback"


def test_safe_overlay_bundle_slug_preserves_dots_and_dashes():
    from modules.bundle_artifacts import safe_overlay_bundle_slug
    assert safe_overlay_bundle_slug("my-lib.v2", "lib") == "my-lib.v2"


# ---------------------------------------------------------------------------
# is_overlay_source_override_file_key
# ---------------------------------------------------------------------------

def test_is_overlay_source_override_file_key_accepts_file():
    from modules.bundle_artifacts import is_overlay_source_override_file_key
    assert is_overlay_source_override_file_key("file") is True


def test_is_overlay_source_override_file_key_accepts_file_underscore_suffix():
    from modules.bundle_artifacts import is_overlay_source_override_file_key
    assert is_overlay_source_override_file_key("file_1") is True
    assert is_overlay_source_override_file_key("file_extra") is True


def test_is_overlay_source_override_file_key_rejects_unrelated_keys():
    from modules.bundle_artifacts import is_overlay_source_override_file_key
    assert is_overlay_source_override_file_key("url") is False
    assert is_overlay_source_override_file_key("") is False
    assert is_overlay_source_override_file_key(None) is False


# ---------------------------------------------------------------------------
# parse_managed_overlay_image_relative_path
# ---------------------------------------------------------------------------

def test_parse_managed_overlay_image_relative_path_config_root_layout():
    from modules.bundle_artifacts import parse_managed_overlay_image_relative_path
    import modules.helpers as helpers
    moid = helpers.MANAGED_OVERLAY_IMAGE_DIR
    result = parse_managed_overlay_image_relative_path(f"myconfig/{moid}/subdir/img.png")
    assert result is not None
    assert result["config_name"] == "myconfig"
    assert result["layout"] == "config_root"
    assert "img.png" in result["remainder"]


def test_parse_managed_overlay_image_relative_path_display_layout():
    from modules.bundle_artifacts import parse_managed_overlay_image_relative_path
    import modules.helpers as helpers
    moid = helpers.MANAGED_OVERLAY_IMAGE_DIR
    result = parse_managed_overlay_image_relative_path(f"config/myconfig/{moid}/img.png")
    assert result is not None
    assert result["config_name"] == "myconfig"
    assert result["layout"] == "display"


def test_parse_managed_overlay_image_relative_path_returns_none_for_unrelated():
    from modules.bundle_artifacts import parse_managed_overlay_image_relative_path
    assert parse_managed_overlay_image_relative_path("some/random/path.yml") is None
    assert parse_managed_overlay_image_relative_path("") is None
    assert parse_managed_overlay_image_relative_path(None) is None


# ---------------------------------------------------------------------------
# normalized_managed_overlay_image_relative_path
# ---------------------------------------------------------------------------

def test_normalized_managed_overlay_image_relative_path_round_trips():
    from modules.bundle_artifacts import normalized_managed_overlay_image_relative_path
    import modules.helpers as helpers
    moid = helpers.MANAGED_OVERLAY_IMAGE_DIR
    canonical = f"myconfig/{moid}/lib/overlay/img.png"
    # Both layouts should normalize to the same canonical form
    assert normalized_managed_overlay_image_relative_path(canonical) == canonical
    display = f"config/myconfig/{moid}/lib/overlay/img.png"
    assert normalized_managed_overlay_image_relative_path(display) == canonical


def test_normalized_managed_overlay_image_relative_path_returns_none_for_unrelated():
    from modules.bundle_artifacts import normalized_managed_overlay_image_relative_path
    assert normalized_managed_overlay_image_relative_path("random/path.png") is None


# ---------------------------------------------------------------------------
# display_managed_overlay_image_location
# ---------------------------------------------------------------------------

def test_display_managed_overlay_image_location_converts_to_display_form():
    from modules.bundle_artifacts import display_managed_overlay_image_location
    import modules.helpers as helpers
    moid = helpers.MANAGED_OVERLAY_IMAGE_DIR
    # config_root form should be converted to display form (config/...)
    canonical = f"myconfig/{moid}/lib/overlay/img.png"
    result = display_managed_overlay_image_location(canonical)
    assert result.startswith("config/myconfig/")


def test_display_managed_overlay_image_location_passthrough_for_unknown():
    from modules.bundle_artifacts import display_managed_overlay_image_location
    raw = "/absolute/some/path.png"
    assert display_managed_overlay_image_location(raw) == raw


def test_display_managed_overlay_image_location_empty_returns_empty():
    from modules.bundle_artifacts import display_managed_overlay_image_location
    assert display_managed_overlay_image_location("") == ""
    assert display_managed_overlay_image_location(None) == ""


# ---------------------------------------------------------------------------
# dump_yaml_text
# ---------------------------------------------------------------------------

def test_dump_yaml_text_produces_valid_yaml():
    from modules.bundle_artifacts import dump_yaml_text
    data = {"key": "value", "nested": {"a": 1}}
    result = dump_yaml_text(data)
    assert isinstance(result, str)
    assert "key: value" in result


def test_dump_yaml_text_round_trips_through_ruamel():
    from modules.bundle_artifacts import dump_yaml_text
    from ruamel.yaml import YAML
    data = {"plex": {"url": "http://localhost:32400", "token": "abc"}}
    text = dump_yaml_text(data)
    parsed = YAML().load(text)
    assert parsed["plex"]["token"] == "abc"


# ---------------------------------------------------------------------------
# build_config_bundle
# ---------------------------------------------------------------------------

def test_build_config_bundle_returns_none_when_no_fonts_or_artifacts():
    from modules.bundle_artifacts import build_config_bundle
    result = build_config_bundle("yaml: true\n", "config.yml", font_files=[], artifact_files=[])
    assert result is None


def test_build_config_bundle_returns_zip_when_fonts_present(tmp_path):
    from modules.bundle_artifacts import build_config_bundle
    font = tmp_path / "custom.ttf"
    font.write_bytes(b"fake font data")

    result = build_config_bundle(
        "yaml: true\n",
        "config.yml",
        font_files=[font],
        config_name="myconfig",
    )
    assert result is not None
    with zipfile.ZipFile(result) as zf:
        names = zf.namelist()
    assert "config.yml" in names
    assert "myconfig/fonts/custom.ttf" in names
    assert "README.txt" in names


def test_build_config_bundle_includes_artifact_files(tmp_path):
    from modules.bundle_artifacts import build_config_bundle
    artifact_file = tmp_path / "collections.yml"
    artifact_file.write_text("collections: []\n")

    artifact = {"source": artifact_file, "archive": "myconfig/collection_files/collections.yml"}
    result = build_config_bundle(
        "yaml: true\n",
        "config.yml",
        font_files=[],
        artifact_files=[artifact],
        config_name="myconfig",
    )
    assert result is not None
    with zipfile.ZipFile(result) as zf:
        names = zf.namelist()
    assert "myconfig/collection_files/collections.yml" in names


def test_build_config_bundle_redacted_flag_mentioned_in_readme(tmp_path):
    from modules.bundle_artifacts import build_config_bundle
    font = tmp_path / "f.ttf"
    font.write_bytes(b"data")

    result = build_config_bundle(
        "yaml: true\n", "config.yml", font_files=[font], redacted=True
    )
    assert result is not None
    with zipfile.ZipFile(result) as zf:
        readme = zf.read("README.txt").decode()
    assert "redacted" in readme.lower()


def test_build_config_bundle_returns_none_when_config_text_empty(tmp_path):
    from modules.bundle_artifacts import build_config_bundle
    font = tmp_path / "f.ttf"
    font.write_bytes(b"data")
    result = build_config_bundle("", "config.yml", font_files=[font])
    assert result is None


# ---------------------------------------------------------------------------
# get_custom_font_files
# ---------------------------------------------------------------------------

def test_get_custom_font_files_returns_empty_when_no_font_dir(tmp_path):
    from modules.bundle_artifacts import get_custom_font_files
    # CONFIG_DIR is tmp_path but no fonts/ subdirectory created
    result = get_custom_font_files(config_name="noconfig")
    assert result == []


def test_get_custom_font_files_returns_font_files(tmp_path, monkeypatch):
    import modules.helpers as helpers
    from modules.bundle_artifacts import get_custom_font_files

    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    (font_dir / "myfont.ttf").write_bytes(b"TTF")
    (font_dir / "otherfont.otf").write_bytes(b"OTF")
    (font_dir / "notafont.txt").write_text("ignore")

    monkeypatch.setattr(helpers, "get_legacy_custom_fonts_dir", lambda: font_dir)
    monkeypatch.setattr(helpers, "get_custom_fonts_dir", lambda name: font_dir / "nonexistent")
    monkeypatch.setattr(helpers, "migrate_legacy_custom_fonts_to_config", lambda name: None)

    result = get_custom_font_files(config_name="myconfig")
    names = [f.name for f in result]
    assert "myfont.ttf" in names
    assert "otherfont.otf" in names
    assert "notafont.txt" not in names


def test_get_custom_font_files_deduplicates_across_dirs(tmp_path, monkeypatch):
    import modules.helpers as helpers
    from modules.bundle_artifacts import get_custom_font_files

    dir_a = tmp_path / "config_fonts"
    dir_a.mkdir()
    (dir_a / "myfont.ttf").write_bytes(b"AAA")

    dir_b = tmp_path / "legacy_fonts"
    dir_b.mkdir()
    (dir_b / "myfont.ttf").write_bytes(b"BBB")  # same name, different dir

    monkeypatch.setattr(helpers, "get_custom_fonts_dir", lambda name: dir_a)
    monkeypatch.setattr(helpers, "get_legacy_custom_fonts_dir", lambda: dir_b)
    monkeypatch.setattr(helpers, "migrate_legacy_custom_fonts_to_config", lambda name: None)

    result = get_custom_font_files(config_name="myconfig")
    names = [f.name for f in result]
    assert names.count("myfont.ttf") == 1


# ---------------------------------------------------------------------------
# iter_bundle_artifacts -- smoke tests via empty / no-library cases
# ---------------------------------------------------------------------------

def test_iter_bundle_artifacts_returns_empty_for_non_dict():
    from modules.bundle_artifacts import iter_bundle_artifacts
    assert iter_bundle_artifacts([]) == []
    assert iter_bundle_artifacts(None) == []
    assert iter_bundle_artifacts("string") == []


def test_iter_bundle_artifacts_returns_empty_for_no_libraries():
    from modules.bundle_artifacts import iter_bundle_artifacts
    assert iter_bundle_artifacts({}) == []
    assert iter_bundle_artifacts({"plex": {"url": "http://x"}}) == []


# ---------------------------------------------------------------------------
# iter_overlay_source_bundle_artifacts -- smoke tests
# ---------------------------------------------------------------------------

def test_iter_overlay_source_bundle_artifacts_returns_empty_for_non_dict():
    from modules.bundle_artifacts import iter_overlay_source_bundle_artifacts
    result, changed = iter_overlay_source_bundle_artifacts(None, "myconfig")
    assert result == []
    assert changed is False


def test_iter_overlay_source_bundle_artifacts_returns_empty_when_no_overlay_files():
    from modules.bundle_artifacts import iter_overlay_source_bundle_artifacts
    data = {"libraries": {"Movies": {"collection_files": []}}}
    result, changed = iter_overlay_source_bundle_artifacts(data, "myconfig")
    assert result == []
    assert changed is False


# ---------------------------------------------------------------------------
# bundle_write_artifact -- directory artifact flattened into zip
# ---------------------------------------------------------------------------

def test_bundle_write_artifact_writes_single_file(tmp_path):
    from modules.bundle_artifacts import bundle_write_artifact
    src = tmp_path / "collections.yml"
    src.write_text("collections: []\n")
    artifact = {"source": src, "archive": "myconfig/collection_files/collections.yml"}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        bundle_write_artifact(zf, artifact)
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        assert "myconfig/collection_files/collections.yml" in zf.namelist()


def test_bundle_write_artifact_writes_directory_recursively(tmp_path):
    from modules.bundle_artifacts import bundle_write_artifact
    src_dir = tmp_path / "mydir"
    src_dir.mkdir()
    (src_dir / "a.yml").write_text("a: 1\n")
    (src_dir / "b.yml").write_text("b: 2\n")
    artifact = {"source": src_dir, "archive": "myconfig/collection_files/mydir"}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        bundle_write_artifact(zf, artifact)
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        names = zf.namelist()
    assert any("a.yml" in n for n in names)
    assert any("b.yml" in n for n in names)


def test_bundle_write_artifact_skips_missing_source(tmp_path):
    from modules.bundle_artifacts import bundle_write_artifact
    artifact = {"source": tmp_path / "does_not_exist.yml", "archive": "archive/path.yml"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        bundle_write_artifact(zf, artifact)  # should not raise
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        assert zf.namelist() == []


def test_bundle_write_artifact_redacts_yaml_content(tmp_path):
    from modules.bundle_artifacts import bundle_write_artifact
    import modules.helpers as helpers
    src = tmp_path / "config.yml"
    src.write_text("tmdb:\n  apikey: REAL_SECRET\n")

    def fake_redact(text):
        return text.replace("REAL_SECRET", "REDACTED")

    artifact = {"source": src, "archive": "config.yml"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        with patch.object(helpers, "redact_sensitive_data", side_effect=fake_redact):
            bundle_write_artifact(zf, artifact, redacted=True)
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        content = zf.read("config.yml").decode()
    assert "REAL_SECRET" not in content
    assert "REDACTED" in content
