"""Regression guard for the project's ESLint config.

These tests prove that the rules in `eslint.config.js` actually catch the
regressions they were added to catch. If someone weakens or removes a
rule, the corresponding test fails -- not at runtime, but at lint time.

We invoke ESLint via npx on synthetic JS snippets written to a temp
directory. We assert the violations show up (or don't) by checking
ESLint's JSON output.

The synthetic-snippet approach decouples the tests from the real
codebase -- they don't depend on the production JS staying clean, only
on the config behaving as documented.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ESLINT_CONFIG = REPO_ROOT / "eslint.config.js"


def _resolve_eslint_executable() -> str | None:
    """Return the repo-local ESLint executable path when available.

    On Windows the installed shim is typically `eslint.cmd`; on Unix-like
    platforms it is usually `eslint`. Fall back to PATH so the tests still
    work in environments that install the toolchain globally.
    """
    local_bin_dir = REPO_ROOT / "node_modules" / ".bin"
    if os.name == "nt":
        local_candidates = [local_bin_dir / "eslint.cmd", local_bin_dir / "eslint"]
        path_candidates = ("eslint.cmd", "eslint")
    else:
        local_candidates = [local_bin_dir / "eslint", local_bin_dir / "eslint.cmd"]
        path_candidates = ("eslint", "eslint.cmd")
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    for candidate in path_candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _eslint_available() -> bool:
    """ESLint is only available where a runnable executable can be resolved.

    Skip these tests in environments that don't have the JS toolchain
    installed (e.g. some CI matrix entries that only run Python tests).
    """
    return _resolve_eslint_executable() is not None


pytestmark = pytest.mark.skipif(
    not _eslint_available(),
    reason="node_modules/.bin/eslint not installed (run `npm install` first)",
)


def _run_eslint(snippet: str, filename: str = "snippet.js") -> list[dict]:
    """Write a snippet to a temp file under static/local-js/ and lint it.

    We have to place the file under static/local-js/ because the ESLint
    config's `files: ['static/local-js/**/*.js']` glob only matches there.
    Returns the parsed JSON results (list of one file-result dict).
    """
    target_dir = REPO_ROOT / "static" / "local-js"
    # Use a name that the moduleFiles allow-list does NOT contain so the
    # snippet is treated as a classic (sourceType: 'script') file by
    # default. That's what matters for the inline-handler / shim tests.
    target = target_dir / f"__eslint_test_{filename}"
    target.write_text(snippet, encoding="utf-8")
    eslint_executable = _resolve_eslint_executable()
    if not eslint_executable:
        raise AssertionError("ESLint executable could not be resolved for tests.")
    try:
        result = subprocess.run(
            [
                eslint_executable,
                "--format=json",
                "--config",
                str(ESLINT_CONFIG),
                str(target),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "CI": "true"},
        )
        # eslint exits 1 when violations exist; both 0 and 1 are valid
        # outcomes for these tests. Anything else is a real failure.
        if result.returncode not in (0, 1):
            raise AssertionError(f"eslint exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}")
        return json.loads(result.stdout)
    finally:
        target.unlink(missing_ok=True)


def _messages(results: list[dict]) -> list[dict]:
    """Flatten ESLint's per-file message lists into a single list."""
    return [msg for file_result in results for msg in file_result.get("messages", [])]


def _rule_ids(messages: list[dict]) -> set[str]:
    return {msg.get("ruleId") for msg in messages if msg.get("ruleId")}


# ---------- inline-handler regression guards ----------


@pytest.mark.parametrize(
    "snippet",
    [
        # Regular string literal containing inline handler.
        "const html = '<a onclick=\"jumpTo(\\'foo\\')\">x</a>'\nconsole.log(html)\n",
        # Template literal containing inline handler.
        'const html = `<button oninput="foo()">x</button>`\nconsole.log(html)\n',
        # Inline handler with whitespace before =.
        "const html = '<div onclick =\"x()\">y</div>'\nconsole.log(html)\n",
        # Different event name.
        'const html = `<form onsubmit="return false">x</form>`\nconsole.log(html)\n',
        # onkey* family.
        "const html = '<input onkeyup=\"f()\">' \nconsole.log(html)\n",
        # mouse* family.
        "const html = `<div onmouseover='x()'>y</div>`\nconsole.log(html)\n",
    ],
)
def test_inline_handler_in_string_is_flagged(snippet: str) -> None:
    results = _run_eslint(snippet)
    msgs = _messages(results)
    assert "no-restricted-syntax" in _rule_ids(msgs), f"expected no-restricted-syntax violation for inline handler, got messages: {msgs}"


@pytest.mark.parametrize(
    "snippet",
    [
        # Real anchor href, not an event handler -- must NOT be flagged.
        "const html = '<a href=\"foo\">click</a>'\nconsole.log(html)\n",
        # data-attribute that contains the substring "onclick" but isn't
        # an event attribute -- must NOT be flagged.
        "const html = '<div data-onclick-handler=\"x\">y</div>'\nconsole.log(html)\n",
        # Adding event listener via JS property is fine (MemberExpression,
        # not a Literal containing "onclick=").
        "const el = document.createElement('div')\nel.onclick = () => console.log('hi')\n",
        # FileReader.onload property assignment -- common idiom, fine.
        "const reader = new FileReader()\nreader.onload = () => {}\n",
    ],
)
def test_legitimate_patterns_not_flagged(snippet: str) -> None:
    results = _run_eslint(snippet)
    msgs = _messages(results)
    inline_handler_msgs = [m for m in msgs if m.get("ruleId") == "no-restricted-syntax"]
    assert not inline_handler_msgs, f"expected NO no-restricted-syntax violations for legitimate pattern, got: {inline_handler_msgs}"


# ---------- retired-shim regression guards ----------


def test_window_loading_assignment_is_flagged() -> None:
    """PR #1382 retired window.loading. The rule must reject re-introducing it."""
    snippet = "function loading () { return 1 }\n" "window.loading = loading\n"
    results = _run_eslint(snippet)
    msgs = _messages(results)
    no_restricted = [m for m in msgs if m.get("ruleId") == "no-restricted-syntax"]
    assert no_restricted, f"expected window.loading = ... to be flagged, got: {msgs}"
    # The message body should mention 'loading' so the developer knows what they did.
    assert any("loading" in (m.get("message") or "") for m in no_restricted)


def test_window_jumpto_assignment_is_NOT_flagged_yet() -> None:
    """window.jumpTo is intentionally still allowed -- PR #1383 restored
    the shim because static/local-js/025-libraries.js (a classic script)
    still depends on it. When that file becomes a module, this test
    should flip to assert the assignment IS flagged.
    """
    snippet = "function jumpTo (page, label) { return 1 }\n" "window.jumpTo = jumpTo\n"
    results = _run_eslint(snippet)
    msgs = _messages(results)
    no_restricted = [m for m in msgs if m.get("ruleId") == "no-restricted-syntax"]
    assert not no_restricted, (
        "window.jumpTo = ... should still be allowed (025-libraries.js depends on it). "
        f"If you've converted 025-libraries.js to a module, flip this test and add a ban "
        f"selector to eslint.config.js. Got violations: {no_restricted}"
    )


# ---------- modernization guards ----------


def test_var_is_flagged() -> None:
    """no-var: enforces let/const over var. Codebase is currently clean."""
    snippet = "var x = 1\nconsole.log(x)\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "no-var" in rule_ids, f"expected no-var violation; got rules: {rule_ids}"


def test_let_that_should_be_const_is_flagged() -> None:
    """prefer-const: locals that are never reassigned must be const."""
    snippet = "let x = 1\nconsole.log(x)\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "prefer-const" in rule_ids, f"expected prefer-const violation; got rules: {rule_ids}"


def test_loose_equality_is_flagged() -> None:
    """eqeqeq: == must be ===."""
    snippet = "const x = 1\nif (x == '1') console.log('match')\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "eqeqeq" in rule_ids, f"expected eqeqeq violation; got rules: {rule_ids}"


def test_eq_null_is_NOT_flagged() -> None:
    """eqeqeq 'null' exception: `x == null` and `x != null` are idiomatic."""
    snippet = "function foo (x) {\n" "  if (x == null) return 'nullish'\n" "  if (x != null) return 'present'\n" "  return 'other'\n" "}\n" "console.log(foo(1))\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "eqeqeq" not in rule_ids, f"x == null / x != null must be allowed (idiomatic null-or-undefined check); got: {rule_ids}"


# ---------- pre-existing rules (don't regress these) ----------


def test_no_shadow_is_active() -> None:
    """The no-shadow rule already caught two bugs in PR #1382. Keep it on."""
    snippet = "const loading = 'outer'\n" "function f () {\n" "  const loading = 'inner'\n" "  return loading\n" "}\n" "console.log(loading, f())\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "no-shadow" in rule_ids, f"expected no-shadow violation; got rules: {rule_ids}"


def test_no_undef_is_active() -> None:
    """no-undef catches typos / missing imports. Keep it on."""
    snippet = "thisIsDefinitelyNotAGlobal('x')\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "no-undef" in rule_ids, f"expected no-undef violation; got rules: {rule_ids}"


def test_no_implied_eval_is_active() -> None:
    """no-implied-eval catches setTimeout(string, ...) etc."""
    snippet = "setTimeout('alert(1)', 100)\n"
    results = _run_eslint(snippet)
    rule_ids = _rule_ids(_messages(results))
    assert "no-implied-eval" in rule_ids, f"expected no-implied-eval; got rules: {rule_ids}"
