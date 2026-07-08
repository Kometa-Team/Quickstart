"""Startup preflight checks that run BEFORE Quickstart's real imports.

These probe for C-extension stdlib modules that a broken Python build
might be missing. When someone installs Python via pyenv/asdf/`make
install` on a host without the required system dev headers, the
resulting Python has the *pure-Python* stdlib package but its
underlying C extension (`_sqlite3`, `_ssl`, ...) is absent. The
traceback that surfaces from an app doing `import sqlite3` is
confusing because it points into stdlib source, not at the real
problem (missing system libraries at build time).

We catch this class of failure early and print a friendly message
that names the missing extension, the OS package that provides it,
and how to fix it. This module deliberately has zero third-party
imports and touches only stdlib primitives — it must be safe to
import from the very top of quickstart.py before any dependency
has been loaded.

Design notes:
  - Each check is a tuple describing (import target, friendly name,
    hint packages). New checks are one-liners to add.
  - `run_preflight_checks()` returns a list of failure descriptors so
    the runner can decide what to do (print + exit vs. return).
  - `format_failure_message()` is a pure function so it can be
    exercised in tests without touching stderr.
"""

from __future__ import annotations

import importlib
import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PreflightCheck:
    """A single C-extension stdlib module we want to probe for."""

    # Module name to attempt importing (e.g. "sqlite3").
    module: str
    # Human-readable name used in the failure message.
    friendly_name: str
    # Package names by OS family. Used to tell the user what to
    # install before rebuilding Python.
    debian_pkg: str
    fedora_pkg: str
    macos_hint: str


@dataclass(frozen=True)
class PreflightFailure:
    """Result of a failed check plus the underlying exception."""

    check: PreflightCheck
    error: BaseException


# The set of stdlib modules Quickstart transitively imports that are
# C extensions and therefore skippable from a broken Python build.
# `sqlite3` is the one that bit users first (via modules/database.py).
# `_ssl` is the next-most-likely trap — anything that touches HTTPS
# (requests, urllib) will explode if it's missing.
CHECKS: tuple[PreflightCheck, ...] = (
    PreflightCheck(
        module="sqlite3",
        friendly_name="SQLite (sqlite3)",
        debian_pkg="libsqlite3-dev",
        fedora_pkg="sqlite-devel",
        macos_hint="brew install sqlite3  (then rebuild Python)",
    ),
    PreflightCheck(
        module="ssl",
        friendly_name="OpenSSL (ssl)",
        debian_pkg="libssl-dev",
        fedora_pkg="openssl-devel",
        macos_hint="brew install openssl  (then rebuild Python)",
    ),
)


def _try_import(module_name: str) -> BaseException | None:
    """Attempt to import `module_name`. Returns None on success or
    the raised exception on failure. Any exception is caught (not
    just ImportError) because a broken C extension might raise
    SystemError, OSError, etc."""
    try:
        importlib.import_module(module_name)
    except BaseException as exc:  # noqa: BLE001 - deliberate broad catch
        return exc
    return None


def run_preflight_checks(
    checks: tuple[PreflightCheck, ...] = CHECKS,
) -> list[PreflightFailure]:
    """Run every check and return the list of failures. Passes an
    empty list means everything's fine."""
    failures: list[PreflightFailure] = []
    for check in checks:
        err = _try_import(check.module)
        if err is not None:
            failures.append(PreflightFailure(check=check, error=err))
    return failures


def _detect_os_family() -> str:
    """Return one of 'debian', 'fedora', 'macos', or 'other'.
    Best-effort — used only to pick which install hint leads."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system != "Linux":
        return "other"
    # /etc/os-release is the modern way to identify Linux distros.
    try:
        with open("/etc/os-release", encoding="utf-8") as fh:
            content = fh.read().lower()
    except OSError:
        return "other"
    if "id=debian" in content or "id_like=debian" in content or "ubuntu" in content:
        return "debian"
    if "id=fedora" in content or "rhel" in content or "centos" in content or "id_like=fedora" in content:
        return "fedora"
    return "other"


def format_failure_message(
    failures: list[PreflightFailure],
    os_family: str | None = None,
) -> str:
    """Produce the user-facing message describing what's missing and
    how to fix it. Pure function — no I/O — so tests can assert on
    the exact text.

    `os_family` is auto-detected from the platform if not supplied;
    tests pass it explicitly to exercise each branch.
    """
    if not failures:
        return ""

    if os_family is None:
        os_family = _detect_os_family()

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("Quickstart cannot start: your Python is missing required C extensions")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Python version : {platform.python_version()}")
    lines.append(f"Python binary  : {sys.executable}")
    lines.append("")

    for failure in failures:
        check = failure.check
        lines.append(f"MISSING: {check.friendly_name}")
        lines.append(f"  import {check.module!r} failed with:")
        lines.append(f"    {type(failure.error).__name__}: {failure.error}")
        lines.append("")

    lines.append("Why this happens")
    lines.append("-" * 72)
    lines.append(
        "This almost always means Python was built from source (e.g. via"
        " pyenv, asdf, or manual `./configure && make`) on a host that"
        " didn't have the required system development headers installed."
        " Python's build silently skips the corresponding C extension"
        " when the headers are missing, leaving a Python that mostly"
        " works but breaks the moment anything touches the affected"
        " module."
    )
    lines.append("")
    lines.append("How to fix it")
    lines.append("-" * 72)
    lines.append(
        "Install the OS development headers listed below, then reinstall"
        " Python (`pyenv uninstall X.Y.Z && pyenv install X.Y.Z`, or the"
        " equivalent for your version manager). Recreate your venv"
        " afterwards."
    )
    lines.append("")

    # Show the hint for the detected OS first, then the others.
    hint_order = ["debian", "fedora", "macos", "other"]
    if os_family in hint_order:
        hint_order.remove(os_family)
        hint_order.insert(0, os_family)

    debian_pkgs = " ".join(sorted({f.check.debian_pkg for f in failures}))
    fedora_pkgs = " ".join(sorted({f.check.fedora_pkg for f in failures}))
    macos_hints = "\n    ".join(sorted({f.check.macos_hint for f in failures}))

    hints_by_family = {
        "debian": f"Debian / Ubuntu:\n    sudo apt install {debian_pkgs}",
        "fedora": f"Fedora / RHEL / CentOS:\n    sudo dnf install {fedora_pkgs}",
        "macos": f"macOS (Homebrew):\n    {macos_hints}",
        "other": (
            "Other Linux / BSD: install the equivalent development"
            " packages for your distribution (search for packages"
            " providing headers for: " + ", ".join(sorted({f.check.friendly_name for f in failures})) + ")."
        ),
    }
    for family in hint_order:
        lines.append(hints_by_family[family])
        lines.append("")

    lines.append("For more detail see: https://github.com/Kometa-Team/Quickstart" "#missing-stdlib-c-extensions-sqlite3-_ssl-etc")
    lines.append("=" * 72)
    return "\n".join(lines)


def enforce_preflight(exit_code: int = 1) -> None:
    """Run all checks; if any fail, print the friendly message to
    stderr and `sys.exit(exit_code)`. Called from quickstart.py's
    top-level import block, so it must be self-contained."""
    failures = run_preflight_checks()
    if not failures:
        return
    sys.stderr.write(format_failure_message(failures))
    sys.stderr.write("\n")
    sys.stderr.flush()
    sys.exit(exit_code)
