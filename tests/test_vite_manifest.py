"""Tests for the Vite manifest lookup (modules.helpers._vite_manifest).

Covers the ``asset_url()`` Jinja global that resolves a source-file
name (e.g. ``'000-base'``) to the URL a template should serve
(``/static/dist/000-base-<hash>.js`` when a Vite build exists,
``/static/local-js/000-base.js`` otherwise). Part of roadmap #1334
Step 4 activation.

Two design invariants under test:

1. **Fallback preserves dev ergonomics.** When ``static/dist/.vite/manifest.json``
   doesn't exist, ``asset_url()`` returns the raw source URL. That's
   the state right after a fresh ``git clone`` where nobody has run
   ``npm run build`` yet. It has to keep working, otherwise
   ``python quickstart.py`` breaks for every new contributor.

2. **Cache lifetime is process-local.** The manifest is loaded once
   per process and cached. That matches the production reality
   (containers/binaries have a baked-at-build-time manifest) and
   avoids one filesystem read per request. Tests using
   ``reload_manifest()`` clear the cache between assertions so they
   don't pollute each other.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.helpers import _vite_manifest
from modules.helpers._vite_manifest import (
    _MANIFEST_MISSING,
    _load_manifest,
    asset_url,
    reload_manifest,
    vite_dev_mode,
    vite_dev_origin,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_manifest_cache():
    """Force every test to start with an empty cache so tests are order-independent."""
    reload_manifest()
    yield
    reload_manifest()


@pytest.fixture
def fake_manifest(tmp_path, monkeypatch):
    """Point the module at a tmp_path manifest and return the file path.

    Yields the manifest ``Path`` so the test can write JSON into it
    before calling ``reload_manifest()`` + ``asset_url()``.
    """
    manifest_path = tmp_path / "manifest.json"
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    monkeypatch.setattr(_vite_manifest, "_MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(_vite_manifest, "_DIST_DIR", str(dist_dir))
    reload_manifest()
    return manifest_path


def _touch_dist_file(path):
    built_path = Path(_vite_manifest._DIST_DIR) / path
    built_path.parent.mkdir(parents=True, exist_ok=True)
    built_path.write_text("// built\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_returns_missing_sentinel_when_file_absent(self, fake_manifest):
        assert not fake_manifest.exists()
        result = _load_manifest()
        assert result is _MANIFEST_MISSING
        assert result == {}

    def test_reads_valid_manifest_from_disk(self, fake_manifest):
        payload = {
            "static/local-js/000-base.js": {
                "file": "000-base-abc123.js",
                "src": "static/local-js/000-base.js",
                "isEntry": True,
            }
        }
        fake_manifest.write_text(json.dumps(payload))
        result = _load_manifest()
        assert result == payload

    def test_corrupt_manifest_returns_missing_sentinel(self, fake_manifest):
        """A malformed manifest must degrade to source-serving, not crash the app."""
        fake_manifest.write_text("{not valid json at all")
        result = _load_manifest()
        assert result is _MANIFEST_MISSING

    def test_unreadable_manifest_returns_missing_sentinel(self, fake_manifest, monkeypatch):
        """OSError paths (permissions, IO error) also degrade cleanly."""
        fake_manifest.write_text("{}")

        def _boom(*args, **kwargs):
            raise OSError("permission denied")

        # Patch the open() the module uses.
        monkeypatch.setattr("builtins.open", _boom)
        result = _load_manifest()
        assert result is _MANIFEST_MISSING


# ---------------------------------------------------------------------------
# asset_url — manifest present
# ---------------------------------------------------------------------------


class TestAssetUrlWithManifest:
    def test_returns_hashed_dist_path_for_entry(self, fake_manifest):
        _touch_dist_file("000-base-DKccW2Od.js")
        fake_manifest.write_text(
            json.dumps(
                {
                    "static/local-js/000-base.js": {
                        "file": "000-base-DKccW2Od.js",
                        "isEntry": True,
                    }
                }
            )
        )
        assert asset_url("000-base") == "/static/dist/000-base-DKccW2Od.js"

    def test_prefers_dist_over_source_when_both_exist(self, fake_manifest):
        """Manifest entry always wins; we never inspect the source path."""
        _touch_dist_file("010-plex-xyz789.js")
        fake_manifest.write_text(
            json.dumps(
                {
                    "static/local-js/010-plex.js": {
                        "file": "010-plex-xyz789.js",
                        "isEntry": True,
                    }
                }
            )
        )
        assert asset_url("010-plex") == "/static/dist/010-plex-xyz789.js"

    def test_returns_dist_path_for_chunk_keyed_by_source(self, fake_manifest):
        """Non-entry chunks that are still keyed with a source path resolve too.

        (Vite emits entries for shared chunks under ``static/local-js/modules/``
        keyed by their source path even though they're not declared as
        entries -- a real entry dynamically imports them. The template never
        references these directly, but if it ever did the lookup should
        still work.)
        """
        _touch_dist_file("chunks/imageHandler-abc.js")
        fake_manifest.write_text(
            json.dumps(
                {
                    "static/local-js/imageHandler.js": {
                        "file": "chunks/imageHandler-abc.js",
                        # No isEntry key -- Vite omits it for non-entry chunks
                    }
                }
            )
        )
        assert asset_url("imageHandler") == "/static/dist/chunks/imageHandler-abc.js"

    def test_manifest_entry_missing_file_field_falls_back(self, fake_manifest):
        """A defensive branch: if manifest schema drifts and ``file`` disappears, don't crash."""
        fake_manifest.write_text(
            json.dumps(
                {
                    "static/local-js/000-base.js": {
                        # deliberately no "file" key
                        "isEntry": True,
                    }
                }
            )
        )
        assert asset_url("000-base") == "/static/local-js/000-base.js"

    def test_manifest_entry_missing_built_file_falls_back(self, fake_manifest):
        """A stale manifest without its dist file must not emit a guaranteed 404 URL."""
        fake_manifest.write_text(json.dumps({"static/local-js/000-base.js": {"file": "000-base-stale.js"}}))
        assert asset_url("000-base") == "/static/local-js/000-base.js"


# ---------------------------------------------------------------------------
# asset_url — fallback to source
# ---------------------------------------------------------------------------


class TestAssetUrlFallback:
    def test_returns_source_path_when_manifest_missing(self, fake_manifest):
        assert not fake_manifest.exists()
        assert asset_url("000-base") == "/static/local-js/000-base.js"

    def test_returns_source_path_when_name_not_in_manifest(self, fake_manifest):
        """Classic non-module scripts (100-anidb, 915-imagemaid) aren't Vite entries."""
        fake_manifest.write_text(json.dumps({"static/local-js/000-base.js": {"file": "000-base-abc.js"}}))
        assert asset_url("100-anidb") == "/static/local-js/100-anidb.js"
        assert asset_url("915-imagemaid") == "/static/local-js/915-imagemaid.js"

    def test_returns_source_path_for_nonexistent_source_too(self, fake_manifest):
        """Even for entries that don't exist on disk, we still return the URL --
        the browser 404 is the honest signal that the caller has the wrong name."""
        assert asset_url("does-not-exist") == "/static/local-js/does-not-exist.js"

    def test_returns_source_path_when_manifest_is_corrupt(self, fake_manifest):
        fake_manifest.write_text("{ not valid json")
        assert asset_url("000-base") == "/static/local-js/000-base.js"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestManifestCaching:
    def test_manifest_is_loaded_only_once(self, fake_manifest):
        """First call reads disk; subsequent calls use the cached dict.

        Verifies the caching contract by counting how many times ``open()``
        is invoked for the manifest path across many ``asset_url()``
        calls.
        """
        _touch_dist_file("000-base-abc.js")
        fake_manifest.write_text(json.dumps({"static/local-js/000-base.js": {"file": "000-base-abc.js"}}))

        real_open = open
        call_count = 0

        def counting_open(path, *args, **kwargs):
            nonlocal call_count
            if str(path) == _vite_manifest._MANIFEST_PATH:
                call_count += 1
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=counting_open):
            for _ in range(10):
                asset_url("000-base")

        assert call_count == 1, f"expected 1 read, got {call_count}"

    def test_reload_manifest_forces_fresh_read(self, fake_manifest):
        """After reload_manifest(), the next asset_url() call re-reads disk."""
        _touch_dist_file("000-base-v1.js")
        fake_manifest.write_text(json.dumps({"static/local-js/000-base.js": {"file": "000-base-v1.js"}}))
        assert asset_url("000-base") == "/static/dist/000-base-v1.js"

        # Rewrite the manifest and reload.
        _touch_dist_file("000-base-v2.js")
        fake_manifest.write_text(json.dumps({"static/local-js/000-base.js": {"file": "000-base-v2.js"}}))
        reload_manifest()

        assert asset_url("000-base") == "/static/dist/000-base-v2.js"

    def test_reload_without_manifest_still_falls_back(self, fake_manifest):
        """A manifest that appears and then disappears must fall back cleanly."""
        _touch_dist_file("000-base-v1.js")
        fake_manifest.write_text(json.dumps({"static/local-js/000-base.js": {"file": "000-base-v1.js"}}))
        assert asset_url("000-base") == "/static/dist/000-base-v1.js"

        fake_manifest.unlink()
        reload_manifest()

        assert asset_url("000-base") == "/static/local-js/000-base.js"


# ---------------------------------------------------------------------------
# vite_dev_mode / vite_dev_origin
# ---------------------------------------------------------------------------


class TestViteDevMode:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("QS_VITE_DEV", raising=False)
        assert vite_dev_mode() is False

    def test_enabled_by_1(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "1")
        assert vite_dev_mode() is True

    def test_enabled_by_true(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "true")
        assert vite_dev_mode() is True

    def test_disabled_by_0(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "0")
        assert vite_dev_mode() is False

    def test_disabled_by_false(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "false")
        assert vite_dev_mode() is False


class TestViteDevOrigin:
    def test_returns_empty_when_not_in_dev_mode(self, monkeypatch):
        monkeypatch.delenv("QS_VITE_DEV", raising=False)
        assert vite_dev_origin() == ""

    def test_returns_default_origin_when_enabled(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "1")
        monkeypatch.delenv("QS_VITE_DEV_HOST", raising=False)
        monkeypatch.delenv("QS_VITE_DEV_PORT", raising=False)
        assert vite_dev_origin() == "http://localhost:5173"

    def test_respects_custom_port(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "1")
        monkeypatch.delenv("QS_VITE_DEV_HOST", raising=False)
        monkeypatch.setenv("QS_VITE_DEV_PORT", "3000")
        assert vite_dev_origin() == "http://localhost:3000"

    def test_respects_custom_host(self, monkeypatch):
        monkeypatch.setenv("QS_VITE_DEV", "1")
        monkeypatch.setenv("QS_VITE_DEV_HOST", "10.10.10.11")
        monkeypatch.delenv("QS_VITE_DEV_PORT", raising=False)
        assert vite_dev_origin() == "http://10.10.10.11:5173"


class TestAssetUrlDevMode:
    def test_returns_vite_url_in_dev_mode(self, monkeypatch, fake_manifest):
        monkeypatch.setenv("QS_VITE_DEV", "1")
        monkeypatch.delenv("QS_VITE_DEV_PORT", raising=False)
        assert asset_url("010-plex") == "http://localhost:5173/static/local-js/010-plex.js"

    def test_dev_mode_bypasses_manifest(self, monkeypatch, fake_manifest):
        """When QS_VITE_DEV is set, the manifest is never consulted."""
        monkeypatch.setenv("QS_VITE_DEV", "1")
        _touch_dist_file("010-plex-abc.js")
        fake_manifest.write_text(json.dumps({"static/local-js/010-plex.js": {"file": "010-plex-abc.js", "isEntry": True}}))
        url = asset_url("010-plex")
        assert url.startswith("http://localhost:"), url
        assert "dist" not in url

    def test_dev_mode_off_still_uses_manifest(self, monkeypatch, fake_manifest):
        monkeypatch.setenv("QS_VITE_DEV", "0")
        _touch_dist_file("010-plex-abc.js")
        fake_manifest.write_text(json.dumps({"static/local-js/010-plex.js": {"file": "010-plex-abc.js", "isEntry": True}}))
        reload_manifest()
        assert asset_url("010-plex") == "/static/dist/010-plex-abc.js"


# ---------------------------------------------------------------------------
# Package re-export contract
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_asset_url_is_reexported_from_helpers(self):
        """``from modules.helpers import asset_url`` must work.

        The Flask app wires it into Jinja globals as
        ``helpers.asset_url`` -- if that import path breaks, template
        rendering breaks. This is a light guardrail against someone
        accidentally moving the function without updating __init__.py.
        """
        from modules import helpers

        assert hasattr(helpers, "asset_url")
        assert helpers.asset_url is asset_url

    def test_reload_manifest_is_reexported_from_helpers(self):
        from modules import helpers

        assert hasattr(helpers, "reload_manifest")
        assert helpers.reload_manifest is reload_manifest

    def test_vite_dev_mode_is_reexported_from_helpers(self):
        from modules import helpers

        assert hasattr(helpers, "vite_dev_mode")
        assert helpers.vite_dev_mode is vite_dev_mode

    def test_vite_dev_origin_is_reexported_from_helpers(self):
        from modules import helpers

        assert hasattr(helpers, "vite_dev_origin")
        assert helpers.vite_dev_origin is vite_dev_origin


# ---------------------------------------------------------------------------
# Path targeting sanity
# ---------------------------------------------------------------------------


class TestManifestPathResolution:
    def test_module_targets_correct_manifest_location(self):
        """The module-scope _MANIFEST_PATH must point at the real repo
        location. If someone moves modules/helpers/_vite_manifest.py to a
        different depth, this fires immediately."""
        expected = Path(__file__).parent.parent / "static" / "dist" / ".vite" / "manifest.json"
        assert Path(_vite_manifest._MANIFEST_PATH) == expected
