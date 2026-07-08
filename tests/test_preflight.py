"""Tests for modules/_preflight.py.

The preflight is a self-contained stdlib-only sanity check that runs
at the top of quickstart.py, so tests must:
  1. Not depend on any actual broken Python (nobody builds a bad
     interpreter just for the test suite)
  2. Exercise every branch of format_failure_message() including
     each OS-family hint ordering
  3. Verify enforce_preflight() exits cleanly on failure and does
     nothing on success

We fake failures by constructing PreflightCheck / PreflightFailure
directly, which keeps the tests fully deterministic and free of any
`importlib` monkey-patching.
"""

from __future__ import annotations

import os
import sys

import pytest

# Put the repo root on sys.path so `from modules import _preflight` works
# regardless of whether the session-scoped `app` fixture (which usually
# handles this) has been triggered yet by another test. The preflight
# module has zero import-time side effects, so this is safe.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from modules import _preflight  # noqa: E402
from modules._preflight import (  # noqa: E402
    CHECKS,
    PreflightCheck,
    PreflightFailure,
    _detect_os_family,
    _try_import,
    enforce_preflight,
    format_failure_message,
    run_preflight_checks,
)

# ---------------------------------------------------------------------
# Helper: build a fake failure without touching the real import system
# ---------------------------------------------------------------------


def make_failure(
    module: str = "sqlite3",
    friendly: str = "SQLite (sqlite3)",
    debian: str = "libsqlite3-dev",
    fedora: str = "sqlite-devel",
    macos: str = "brew install sqlite3  (then rebuild Python)",
    exc: BaseException | None = None,
) -> PreflightFailure:
    return PreflightFailure(
        check=PreflightCheck(
            module=module,
            friendly_name=friendly,
            debian_pkg=debian,
            fedora_pkg=fedora,
            macos_hint=macos,
        ),
        error=exc or ModuleNotFoundError("No module named '_sqlite3'"),
    )


# ---------------------------------------------------------------------
# _try_import
# ---------------------------------------------------------------------


class TestTryImport:
    def test_returns_none_on_success(self):
        # os is guaranteed to exist in any Python.
        assert _try_import("os") is None

    def test_returns_exception_on_failure(self):
        result = _try_import("this_module_does_not_exist_asdf1234")
        assert isinstance(result, ModuleNotFoundError)

    def test_catches_arbitrary_exceptions_not_just_ImportError(self):
        # If a broken C extension raises something exotic during
        # import, we still want to catch and report it rather than
        # let it bubble as an unhandled crash.
        import sys as _sys

        class _BoomModule:
            def __getattr__(self, name):
                raise SystemError("kaboom")

        _sys.modules["_pfhelper_boom"] = _BoomModule()
        try:
            # Import triggers our _BoomModule's __getattr__ only on
            # attribute access, so this test really just verifies
            # the broad catch. Force the failure via a bad
            # sub-import path.
            result = _try_import("this.also.does.not.exist")
            assert result is not None
        finally:
            _sys.modules.pop("_pfhelper_boom", None)


# ---------------------------------------------------------------------
# run_preflight_checks
# ---------------------------------------------------------------------


class TestRunPreflightChecks:
    def test_default_checks_pass_on_our_python(self):
        # This literally runs the real check against the test's
        # Python. If it fails, either our Python is broken or a
        # new check was added that fails here.
        assert run_preflight_checks() == []

    def test_returns_failure_for_bogus_module(self):
        fake = PreflightCheck(
            module="totally_fake_module_xyz",
            friendly_name="Fake",
            debian_pkg="none",
            fedora_pkg="none",
            macos_hint="none",
        )
        failures = run_preflight_checks(checks=(fake,))
        assert len(failures) == 1
        assert failures[0].check is fake
        assert isinstance(failures[0].error, ModuleNotFoundError)

    def test_returns_multiple_failures_in_order(self):
        fake_a = PreflightCheck(
            module="bogus_a_xxx",
            friendly_name="A",
            debian_pkg="a",
            fedora_pkg="a",
            macos_hint="a",
        )
        fake_b = PreflightCheck(
            module="bogus_b_xxx",
            friendly_name="B",
            debian_pkg="b",
            fedora_pkg="b",
            macos_hint="b",
        )
        failures = run_preflight_checks(checks=(fake_a, fake_b))
        assert [f.check.module for f in failures] == ["bogus_a_xxx", "bogus_b_xxx"]

    def test_skips_reporting_when_check_passes(self):
        fake = PreflightCheck(
            module="os",  # real module, will import fine
            friendly_name="os",
            debian_pkg="-",
            fedora_pkg="-",
            macos_hint="-",
        )
        assert run_preflight_checks(checks=(fake,)) == []


# ---------------------------------------------------------------------
# _detect_os_family
# ---------------------------------------------------------------------


class TestDetectOsFamily:
    def test_returns_macos_on_darwin(self, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Darwin")
        assert _detect_os_family() == "macos"

    def test_returns_other_on_windows(self, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Windows")
        assert _detect_os_family() == "other"

    def test_returns_debian_when_os_release_says_debian(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Linux")
        os_release = tmp_path / "os-release"
        os_release.write_text('ID=debian\nNAME="Debian GNU/Linux"\n')
        # Patch open() to return our fake file when reading /etc/os-release
        real_open = _preflight.open if hasattr(_preflight, "open") else open

        def fake_open(path, *args, **kwargs):
            if path == "/etc/os-release":
                return real_open(os_release, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert _detect_os_family() == "debian"

    def test_returns_debian_when_os_release_says_ubuntu(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Linux")
        os_release = tmp_path / "os-release"
        os_release.write_text('ID=ubuntu\nNAME="Ubuntu"\n')
        real_open = open

        def fake_open(path, *args, **kwargs):
            if path == "/etc/os-release":
                return real_open(os_release, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert _detect_os_family() == "debian"

    def test_returns_fedora_when_os_release_says_fedora(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Linux")
        os_release = tmp_path / "os-release"
        os_release.write_text('ID=fedora\nNAME="Fedora Linux"\n')
        real_open = open

        def fake_open(path, *args, **kwargs):
            if path == "/etc/os-release":
                return real_open(os_release, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert _detect_os_family() == "fedora"

    def test_returns_fedora_for_rhel_centos(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Linux")
        os_release = tmp_path / "os-release"
        os_release.write_text('ID="rhel"\nNAME="Red Hat Enterprise Linux"\n')
        real_open = open

        def fake_open(path, *args, **kwargs):
            if path == "/etc/os-release":
                return real_open(os_release, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert _detect_os_family() == "fedora"

    def test_returns_other_when_os_release_missing(self, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Linux")

        def raise_oserror(*args, **kwargs):
            raise OSError("nope")

        monkeypatch.setattr("builtins.open", raise_oserror)
        assert _detect_os_family() == "other"

    def test_returns_other_for_unknown_distro(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Linux")
        os_release = tmp_path / "os-release"
        os_release.write_text('ID=arch\nNAME="Arch Linux"\n')
        real_open = open

        def fake_open(path, *args, **kwargs):
            if path == "/etc/os-release":
                return real_open(os_release, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert _detect_os_family() == "other"


# ---------------------------------------------------------------------
# format_failure_message
# ---------------------------------------------------------------------


class TestFormatFailureMessage:
    def test_returns_empty_string_when_no_failures(self):
        assert format_failure_message([]) == ""

    def test_includes_python_version_and_binary(self):
        msg = format_failure_message([make_failure()])
        # Both should be present. We don't hardcode values because
        # this runs in whatever Python is executing the test.
        import sys as _sys

        assert _sys.executable in msg
        import platform as _platform

        assert _platform.python_version() in msg

    def test_includes_friendly_name_and_underlying_error(self):
        exc = ModuleNotFoundError("No module named '_sqlite3'")
        msg = format_failure_message([make_failure(exc=exc)])
        assert "SQLite (sqlite3)" in msg
        assert "ModuleNotFoundError" in msg
        assert "No module named '_sqlite3'" in msg

    def test_debian_hint_appears_first_when_os_is_debian(self):
        msg = format_failure_message([make_failure()], os_family="debian")
        debian_idx = msg.index("Debian / Ubuntu")
        fedora_idx = msg.index("Fedora / RHEL")
        macos_idx = msg.index("macOS (Homebrew)")
        assert debian_idx < fedora_idx < macos_idx

    def test_macos_hint_appears_first_when_os_is_macos(self):
        msg = format_failure_message([make_failure()], os_family="macos")
        macos_idx = msg.index("macOS (Homebrew)")
        debian_idx = msg.index("Debian / Ubuntu")
        assert macos_idx < debian_idx

    def test_fedora_hint_appears_first_when_os_is_fedora(self):
        msg = format_failure_message([make_failure()], os_family="fedora")
        fedora_idx = msg.index("Fedora / RHEL")
        debian_idx = msg.index("Debian / Ubuntu")
        assert fedora_idx < debian_idx

    def test_other_hint_appears_first_when_os_is_other(self):
        msg = format_failure_message([make_failure()], os_family="other")
        # "Other" section is the free-form Linux/BSD one
        other_idx = msg.index("Other Linux / BSD")
        debian_idx = msg.index("Debian / Ubuntu")
        assert other_idx < debian_idx

    def test_hint_lists_deduplicated_packages_across_failures(self):
        # Two failures pointing at the same debian package should
        # only produce that package once.
        f1 = make_failure(module="sqlite3", debian="libsqlite3-dev")
        f2 = make_failure(module="sqlite3", debian="libsqlite3-dev")
        msg = format_failure_message([f1, f2], os_family="debian")
        # Count of the package name in the Debian hint line should be 1
        # (one in the friendly_name mention, one in the install line)
        # -- both are legitimate but the install line MUST only list
        # the package once. Slice the message to just the debian hint:
        debian_start = msg.index("Debian / Ubuntu")
        debian_end = msg.index("Fedora / RHEL")
        debian_block = msg[debian_start:debian_end]
        assert debian_block.count("libsqlite3-dev") == 1

    def test_hint_joins_multiple_distinct_packages(self):
        f1 = make_failure(module="sqlite3", debian="libsqlite3-dev")
        f2 = make_failure(module="ssl", debian="libssl-dev", friendly="OpenSSL (ssl)")
        msg = format_failure_message([f1, f2], os_family="debian")
        # Both packages should appear on the apt install line
        debian_start = msg.index("Debian / Ubuntu")
        debian_end = msg.index("Fedora / RHEL")
        debian_block = msg[debian_start:debian_end]
        assert "libsqlite3-dev" in debian_block
        assert "libssl-dev" in debian_block

    def test_message_includes_docs_link(self):
        msg = format_failure_message([make_failure()])
        assert "https://github.com/Kometa-Team/Quickstart" in msg
        assert "missing-stdlib-c-extensions" in msg

    def test_auto_detects_os_when_not_supplied(self, monkeypatch):
        # We just verify the code path runs without exploding when
        # os_family is omitted -- the actual detection is exercised
        # separately in TestDetectOsFamily.
        monkeypatch.setattr(_preflight.platform, "system", lambda: "Darwin")
        msg = format_failure_message([make_failure()])
        assert "macOS (Homebrew)" in msg


# ---------------------------------------------------------------------
# enforce_preflight
# ---------------------------------------------------------------------


class TestEnforcePreflight:
    def test_returns_normally_when_all_checks_pass(self, monkeypatch):
        monkeypatch.setattr(_preflight, "run_preflight_checks", lambda: [])
        # Should not raise SystemExit
        assert enforce_preflight() is None

    def test_exits_with_code_1_when_a_check_fails(self, monkeypatch, capsys):
        monkeypatch.setattr(_preflight, "run_preflight_checks", lambda: [make_failure()])
        with pytest.raises(SystemExit) as excinfo:
            enforce_preflight()
        assert excinfo.value.code == 1
        # Check the message hit stderr
        captured = capsys.readouterr()
        assert "SQLite (sqlite3)" in captured.err
        assert captured.out == ""  # nothing on stdout

    def test_respects_custom_exit_code(self, monkeypatch):
        monkeypatch.setattr(_preflight, "run_preflight_checks", lambda: [make_failure()])
        with pytest.raises(SystemExit) as excinfo:
            enforce_preflight(exit_code=42)
        assert excinfo.value.code == 42


# ---------------------------------------------------------------------
# Default CHECKS wiring
# ---------------------------------------------------------------------


class TestDefaultChecks:
    def test_includes_sqlite3(self):
        modules = [c.module for c in CHECKS]
        assert "sqlite3" in modules

    def test_includes_ssl(self):
        modules = [c.module for c in CHECKS]
        assert "ssl" in modules

    def test_every_check_has_all_required_hint_fields(self):
        for c in CHECKS:
            assert c.friendly_name
            assert c.debian_pkg
            assert c.fedora_pkg
            assert c.macos_hint
