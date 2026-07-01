#!/usr/bin/env python3
"""Cross-platform test runner for Quickstart."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_PATH = Path(__file__).with_name("run-tests.config.json")

STRING_SETTINGS = {
    "ratings_profile_order": "RATINGS_MATRIX_PROFILE_ORDER",
    "ratings_with_kometa": "RATINGS_MATRIX_WITH_KOMETA",
    "ratings_fail_on_diff": "RATINGS_MATRIX_FAIL_ON_DIFF",
    "ratings_diff_ignore_alpha": "RATINGS_MATRIX_DIFF_IGNORE_ALPHA",
    "ratings_include_nudges": "RATINGS_MATRIX_INCLUDE_NUDGES",
    "ratings_nudge_profiles": "RATINGS_MATRIX_NUDGE_PROFILES",
    "ratings_nudge_apply_to": "RATINGS_MATRIX_NUDGE_APPLY_TO",
    "ratings_diff_use_slot_thresholds": "RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS",
    "ratings_execution_mode": "RATINGS_MATRIX_EXECUTION_MODE",
    "ratings_random_seed": "RATINGS_MATRIX_RANDOM_SEED",
    "ratings_case_ids": "RATINGS_MATRIX_CASE_IDS",
    "ratings_case_ids_file": "RATINGS_MATRIX_CASE_IDS_FILE",
}

NUMERIC_SETTINGS = {
    "ratings_diff_threshold_percent": "RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT",
    "ratings_diff_threshold_one_slot_percent": "RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT",
    "ratings_diff_threshold_two_slot_percent": "RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT",
    "ratings_diff_threshold_three_slot_percent": "RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT",
    "ratings_chunk_size": "RATINGS_MATRIX_CHUNK_SIZE",
    "ratings_show_layer_ready_timeout_ms": "RATINGS_SHOW_LAYER_READY_TIMEOUT_MS",
    "ratings_show_library_load_timeout_ms": "RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS",
    "ratings_library_load_retries": "RATINGS_LIBRARY_LOAD_RETRIES",
    "ratings_random_count": "RATINGS_MATRIX_RANDOM_COUNT",
    "ratings_case_offset": "RATINGS_MATRIX_CASE_OFFSET",
    "ratings_case_limit": "RATINGS_MATRIX_CASE_LIMIT",
}

DIRECT_ENV_SETTINGS = {
    "ratings_kometa_root": "RATINGS_MATRIX_KOMETA_ROOT",
    "ratings_movie_library": "RATINGS_MATRIX_MOVIE_LIBRARY",
    "ratings_show_library": "RATINGS_MATRIX_SHOW_LIBRARY",
    "ratings_artifact_dir": "RATINGS_MATRIX_ARTIFACT_DIR",
}

EMPTY_SENTINELS = {
    "ratings_case_ids",
    "ratings_case_ids_file",
}


def detect_venv_python() -> Path | None:
    windows_python = REPO_ROOT / "venv" / "Scripts" / "python.exe"
    unix_python = REPO_ROOT / "venv" / "bin" / "python"
    if windows_python.exists():
        return windows_python
    if unix_python.exists():
        return unix_python
    return None


def detect_python() -> str:
    venv_python = detect_venv_python()
    if venv_python:
        return str(venv_python)
    return sys.executable or "python"


def detect_precommit_command(python_cmd: str) -> list[str]:
    windows_precommit = REPO_ROOT / "venv" / "Scripts" / "pre-commit.exe"
    unix_precommit = REPO_ROOT / "venv" / "bin" / "pre-commit"
    if windows_precommit.exists():
        return [str(windows_precommit)]
    if unix_precommit.exists():
        return [str(unix_precommit)]
    return [python_cmd, "-m", "pre_commit"]


def detect_npm_command() -> list[str] | None:
    npm_cmd = shutil.which("npm.cmd")
    if npm_cmd:
        return [npm_cmd]
    npm_cmd = shutil.which("npm")
    if npm_cmd:
        return [npm_cmd]
    return None


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> int:
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env)
    return completed.returncode


def load_local_config() -> dict[str, Any]:
    if not LOCAL_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        print(f"Warning: Failed to parse {LOCAL_CONFIG_PATH}. Ignoring local config.", file=sys.stderr)
        return {}


def resolve_setting(
    cli_value: Any,
    config: dict[str, Any],
    config_key: str,
    env_key: str,
) -> Any:
    if cli_value is not None:
        return cli_value
    if config_key in config:
        return config[config_key]
    env_value = os.environ.get(env_key)
    if env_value not in (None, ""):
        return env_value
    return None


def stringify_setting(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def build_runner_env(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()

    for config_key, env_key in STRING_SETTINGS.items():
        resolved_value = resolve_setting(getattr(args, config_key), config, config_key, env_key)
        if resolved_value is None:
            if config_key in EMPTY_SENTINELS:
                env.pop(env_key, None)
            continue
        value_str = stringify_setting(resolved_value).strip()
        if value_str:
            env[env_key] = value_str
        elif config_key in EMPTY_SENTINELS:
            env.pop(env_key, None)

    for config_key, env_key in NUMERIC_SETTINGS.items():
        resolved_value = resolve_setting(getattr(args, config_key), config, config_key, env_key)
        if resolved_value is not None:
            env[env_key] = stringify_setting(resolved_value)

    for config_key, env_key in DIRECT_ENV_SETTINGS.items():
        resolved_value = resolve_setting(getattr(args, config_key), config, config_key, env_key)
        if resolved_value:
            env[env_key] = stringify_setting(resolved_value)

    return env


def resolve_ratings_kometa_root(env: dict[str, str]) -> Path:
    override = str(env.get("RATINGS_MATRIX_KOMETA_ROOT", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT / "config" / "kometa"


def has_usable_ratings_kometa_root(path: Path) -> bool:
    return (path / "kometa.py").exists() and (path / "modules" / "overlay.py").exists()


def maybe_disable_missing_ratings_kometa(env: dict[str, str]) -> None:
    requested = str(env.get("RATINGS_MATRIX_WITH_KOMETA", "") or "").strip().lower()
    if requested in {"", "0", "false", "no"}:
        return

    kometa_root = resolve_ratings_kometa_root(env)
    if has_usable_ratings_kometa_root(kometa_root):
        return

    print(
        "RatingsArtifacts: disabling Kometa render because no usable Kometa checkout "
        f"was found at {kometa_root}. Set RATINGS_MATRIX_KOMETA_ROOT or -RatingsKometaRoot "
        "to a valid checkout to re-enable it."
    )
    env["RATINGS_MATRIX_WITH_KOMETA"] = "0"


def run_precommit(python_cmd: str, env: dict[str, str]) -> int:
    command = detect_precommit_command(python_cmd) + ["run", "--all-files", "--show-diff-on-failure", "--color=always"]
    return run_command(command, env=env)


def run_pytest(python_cmd: str, pytest_args: list[str], env: dict[str, str]) -> int:
    return run_command([python_cmd, "-m", "pytest", "-p", "pytest_progress_plugin", *pytest_args], env=env)


def run_setup(python_cmd: str, *, skip_playwright: bool) -> int:
    venv_python = detect_venv_python()
    if venv_python is None:
        venv_dir = REPO_ROOT / "venv"
        print(f"Creating virtual environment: {venv_dir}")
        exit_code = run_command([python_cmd, "-m", "venv", str(venv_dir)])
        if exit_code != 0:
            return exit_code
        venv_python = detect_venv_python()

    if venv_python is None:
        print("Failed to resolve the virtualenv Python after creation.", file=sys.stderr)
        return 1

    venv_python_str = str(venv_python)

    print("Upgrading pip...")
    exit_code = run_command([venv_python_str, "-m", "pip", "install", "--upgrade", "pip"])
    if exit_code != 0:
        return exit_code

    print("Installing runtime and developer requirements...")
    exit_code = run_command(
        [
            venv_python_str,
            "-m",
            "pip",
            "install",
            "-r",
            str(REPO_ROOT / "requirements.txt"),
            "-r",
            str(REPO_ROOT / "requirements-dev.txt"),
        ]
    )
    if exit_code != 0:
        return exit_code

    if (REPO_ROOT / "package.json").exists():
        npm_command = detect_npm_command()
        if npm_command is None:
            print(
                "Node tooling is configured for this repo, but npm was not found on PATH. " "Install Node.js/npm, then rerun setup.",
                file=sys.stderr,
            )
            return 1
        print("Installing Node dependencies...")
        exit_code = run_command([*npm_command, "install"])
        if exit_code != 0:
            return exit_code

    if not skip_playwright:
        print("Installing Playwright browsers...")
        exit_code = run_command([venv_python_str, "-m", "playwright", "install"])
        if exit_code != 0:
            return exit_code

    print("Developer environment is ready.")
    return 0


def print_ratings_artifact_config(env: dict[str, str]) -> None:
    kometa_root = resolve_ratings_kometa_root(env)
    print("RatingsArtifacts effective config:")
    print(f"  profile_order={env.get('RATINGS_MATRIX_PROFILE_ORDER', '')}")
    print("  execution_mode=" f"{env.get('RATINGS_MATRIX_EXECUTION_MODE', '')} chunk_size={env.get('RATINGS_MATRIX_CHUNK_SIZE', '')}")
    print(f"  random_count={env.get('RATINGS_MATRIX_RANDOM_COUNT', '')} random_seed={env.get('RATINGS_MATRIX_RANDOM_SEED', '')}")
    print(f"  case_offset={env.get('RATINGS_MATRIX_CASE_OFFSET', '')} case_limit={env.get('RATINGS_MATRIX_CASE_LIMIT', '')}")
    print(f"  case_ids={env.get('RATINGS_MATRIX_CASE_IDS', '')} case_ids_file={env.get('RATINGS_MATRIX_CASE_IDS_FILE', '')}")
    print(f"  kometa_root={kometa_root}")
    print(
        "  with_kometa="
        f"{env.get('RATINGS_MATRIX_WITH_KOMETA', '')} fail_on_diff={env.get('RATINGS_MATRIX_FAIL_ON_DIFF', '')} "
        f"diff_ignore_alpha={env.get('RATINGS_MATRIX_DIFF_IGNORE_ALPHA', '')}"
    )
    print(
        "  include_nudges="
        f"{env.get('RATINGS_MATRIX_INCLUDE_NUDGES', '')} "
        f"nudge_profiles={env.get('RATINGS_MATRIX_NUDGE_PROFILES', '')} "
        f"nudge_apply_to={env.get('RATINGS_MATRIX_NUDGE_APPLY_TO', '')}"
    )
    print(
        "  diff_use_slot_thresholds=" f"{env.get('RATINGS_MATRIX_DIFF_USE_SLOT_THRESHOLDS', '')} " f"diff_threshold_percent={env.get('RATINGS_MATRIX_DIFF_THRESHOLD_PERCENT', '')}"
    )
    print(
        "  slot_thresholds(one/two/three)="
        f"{env.get('RATINGS_MATRIX_DIFF_THRESHOLD_ONE_SLOT_PERCENT', '')}/"
        f"{env.get('RATINGS_MATRIX_DIFF_THRESHOLD_TWO_SLOT_PERCENT', '')}/"
        f"{env.get('RATINGS_MATRIX_DIFF_THRESHOLD_THREE_SLOT_PERCENT', '')}"
    )
    print(
        "  show_layer_ready_timeout_ms="
        f"{env.get('RATINGS_SHOW_LAYER_READY_TIMEOUT_MS', '')} "
        f"show_library_load_timeout_ms={env.get('RATINGS_SHOW_LIBRARY_LOAD_TIMEOUT_MS', '')} "
        f"library_load_retries={env.get('RATINGS_LIBRARY_LOAD_RETRIES', '')}"
    )
    print(
        "  movie_library="
        f"{env.get('RATINGS_MATRIX_MOVIE_LIBRARY', '')} "
        f"show_library={env.get('RATINGS_MATRIX_SHOW_LIBRARY', '')} "
        f"artifact_dir={env.get('RATINGS_MATRIX_ARTIFACT_DIR', '')}"
    )


def add_bool_switch(
    parser: argparse.ArgumentParser,
    pascal_name: str,
    *,
    dest: str | None = None,
    help_text: str | None = None,
    aliases: list[str] | None = None,
) -> None:
    kebab = "--" + to_kebab_case(pascal_name)
    parser.add_argument(
        f"-{pascal_name}",
        kebab,
        *(aliases or []),
        dest=dest or pascal_name_to_snake(pascal_name),
        action="store_true",
        help=help_text,
    )


def add_string_arg(parser: argparse.ArgumentParser, pascal_name: str) -> None:
    kebab = "--" + to_kebab_case(pascal_name)
    parser.add_argument(f"-{pascal_name}", kebab, dest=pascal_name_to_snake(pascal_name))


def add_int_arg(parser: argparse.ArgumentParser, pascal_name: str, *, default: int | None = None) -> None:
    kebab = "--" + to_kebab_case(pascal_name)
    parser.add_argument(f"-{pascal_name}", kebab, dest=pascal_name_to_snake(pascal_name), type=int, default=default)


def add_float_arg(parser: argparse.ArgumentParser, pascal_name: str, *, default: float | None = None) -> None:
    kebab = "--" + to_kebab_case(pascal_name)
    parser.add_argument(f"-{pascal_name}", kebab, dest=pascal_name_to_snake(pascal_name), type=float, default=default)


def pascal_name_to_snake(name: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(name):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def to_kebab_case(name: str) -> str:
    return pascal_name_to_snake(name).replace("_", "-")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cross-platform test runner for Quickstart.")

    add_bool_switch(parser, "E2E", dest="e2e", aliases=["--e2e"])
    add_bool_switch(parser, "Unit")
    add_bool_switch(parser, "Lint")
    add_bool_switch(parser, "RepoChecks", dest="repochecks", aliases=["--repochecks"])
    add_bool_switch(parser, "RatingsMatrix", dest="ratings_matrix")
    add_bool_switch(parser, "RatingsArtifacts", dest="ratings_artifacts")
    add_bool_switch(parser, "NoCapture")
    add_bool_switch(parser, "Setup")
    add_bool_switch(parser, "All")
    parser.add_argument("--skip-playwright", action="store_true", help="Skip Playwright browser installation during setup.")

    add_string_arg(parser, "RatingsProfileOrder")
    add_string_arg(parser, "RatingsWithKometa")
    add_string_arg(parser, "RatingsFailOnDiff")
    add_string_arg(parser, "RatingsDiffIgnoreAlpha")
    add_string_arg(parser, "RatingsIncludeNudges")
    add_string_arg(parser, "RatingsNudgeProfiles")
    add_string_arg(parser, "RatingsNudgeApplyTo")
    add_string_arg(parser, "RatingsDiffUseSlotThresholds")
    add_string_arg(parser, "RatingsRandomSeed")
    add_string_arg(parser, "RatingsKometaRoot")
    add_string_arg(parser, "RatingsMovieLibrary")
    add_string_arg(parser, "RatingsShowLibrary")
    add_string_arg(parser, "RatingsArtifactDir")
    add_string_arg(parser, "RatingsCaseIds")
    add_string_arg(parser, "RatingsCaseIdsFile")
    add_string_arg(parser, "RatingsExecutionMode")

    add_float_arg(parser, "RatingsDiffThresholdPercent")
    add_float_arg(parser, "RatingsDiffThresholdOneSlotPercent")
    add_float_arg(parser, "RatingsDiffThresholdTwoSlotPercent")
    add_float_arg(parser, "RatingsDiffThresholdThreeSlotPercent")

    add_int_arg(parser, "RatingsCaseOffset")
    add_int_arg(parser, "RatingsCaseLimit")
    add_int_arg(parser, "RatingsChunkSize")
    add_int_arg(parser, "RatingsShowLayerReadyTimeoutMs")
    add_int_arg(parser, "RatingsShowLibraryLoadTimeoutMs")
    add_int_arg(parser, "RatingsLibraryLoadRetries")
    add_int_arg(parser, "RatingsRandomCount")

    return parser


def validate_mode_selection(args: argparse.Namespace) -> int:
    selected_modes = [
        args.e2e,
        args.unit,
        args.lint,
        args.repochecks,
        args.ratings_matrix,
        args.ratings_artifacts,
    ]
    if sum(1 for selected in selected_modes if selected) > 1:
        print(
            "Choose only one: -E2E, -Unit, -Lint, -RepoChecks, -RatingsMatrix, or -RatingsArtifacts (or use -All).",
            file=sys.stderr,
        )
        return 2
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    python_cmd = detect_python()

    if args.setup:
        exit_code = run_setup(python_cmd, skip_playwright=args.skip_playwright)
        if exit_code != 0:
            return exit_code
        python_cmd = detect_python()
        if not any([args.e2e, args.unit, args.lint, args.repochecks, args.ratings_matrix, args.ratings_artifacts, args.all]):
            return 0

    exit_code = validate_mode_selection(args)
    if exit_code != 0:
        return exit_code

    config = load_local_config()
    env = build_runner_env(args, config)
    maybe_disable_missing_ratings_kometa(env)

    if args.lint:
        return run_precommit(python_cmd, env)

    if args.repochecks:
        print("RepoChecks: running pre-commit first, then full pytest flow.")
        precommit_exit = run_precommit(python_cmd, env)
        if precommit_exit != 0:
            return precommit_exit
        args.all = True

    if args.e2e:
        pytest_args = ["-m", "e2e", "-vv", "-o", "console_output_style=count"]
        if args.no_capture:
            pytest_args.append("-s")
        return run_pytest(python_cmd, pytest_args, env)

    if args.ratings_matrix:
        pytest_args = ["-m", "ratings_matrix", "-vv", "-o", "console_output_style=count"]
        if args.no_capture:
            pytest_args.append("-s")
        return run_pytest(python_cmd, pytest_args, env)

    if args.ratings_artifacts:
        print_ratings_artifact_config(env)
        return run_pytest(python_cmd, ["-m", "ratings_artifacts", "-vv", "-o", "console_output_style=count", "-s"], env)

    if args.all:
        all_random_count = args.ratings_random_count if args.ratings_random_count is not None else 9
        env["RATINGS_MATRIX_RANDOM_COUNT"] = str(all_random_count)
        print(f"All mode: RATINGS_MATRIX_RANDOM_COUNT={env['RATINGS_MATRIX_RANDOM_COUNT']} " "(override with -RatingsRandomCount).")
        print("All mode: running non-ratings_artifacts tests first, then ratings_artifacts last.")

        phase_one_args = ["-o", "addopts=", "-m", "not ratings_artifacts", "-vv", "-o", "console_output_style=count"]
        phase_two_args = ["-o", "addopts=", "-m", "ratings_artifacts", "-vv", "-o", "console_output_style=count"]
        if args.no_capture:
            phase_one_args.append("-s")
            phase_two_args.append("-s")

        phase_one_exit = run_pytest(python_cmd, phase_one_args, env)
        phase_two_exit = run_pytest(python_cmd, phase_two_args, env)
        return phase_two_exit if phase_two_exit != 0 else phase_one_exit

    if args.unit:
        pytest_args = ["-m", "not e2e and not ratings_matrix", "-vv", "-o", "console_output_style=count"]
        if args.no_capture:
            pytest_args.append("-s")
        return run_pytest(python_cmd, pytest_args, env)

    pytest_args = ["-m", "not e2e and not ratings_matrix", "-vv", "-o", "console_output_style=count"]
    if args.no_capture:
        pytest_args.append("-s")
    return run_pytest(python_cmd, pytest_args, env)


if __name__ == "__main__":
    raise SystemExit(main())
