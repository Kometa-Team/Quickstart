import importlib.util
from pathlib import Path


def _load_run_tests_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("qs_run_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_has_usable_ratings_kometa_root_requires_expected_files(tmp_path):
    run_tests = _load_run_tests_module()
    kometa_root = tmp_path / "kometa"
    (kometa_root / "modules").mkdir(parents=True, exist_ok=True)

    assert run_tests.has_usable_ratings_kometa_root(kometa_root) is False

    (kometa_root / "kometa.py").write_text("print('stub')\n", encoding="utf-8")
    assert run_tests.has_usable_ratings_kometa_root(kometa_root) is False

    (kometa_root / "modules" / "overlay.py").write_text("class Overlay: pass\n", encoding="utf-8")
    assert run_tests.has_usable_ratings_kometa_root(kometa_root) is True


def test_maybe_disable_missing_ratings_kometa_turns_off_render_and_warns(capsys, tmp_path):
    run_tests = _load_run_tests_module()
    env = {
        "RATINGS_MATRIX_WITH_KOMETA": "1",
        "RATINGS_MATRIX_KOMETA_ROOT": str(tmp_path / "missing-kometa"),
    }

    run_tests.maybe_disable_missing_ratings_kometa(env)

    assert env["RATINGS_MATRIX_WITH_KOMETA"] == "0"
    captured = capsys.readouterr()
    assert "disabling Kometa render" in captured.out
    assert str(tmp_path / "missing-kometa") in captured.out


def test_maybe_disable_missing_ratings_kometa_keeps_valid_override(tmp_path):
    run_tests = _load_run_tests_module()
    kometa_root = tmp_path / "kometa"
    (kometa_root / "modules").mkdir(parents=True, exist_ok=True)
    (kometa_root / "kometa.py").write_text("print('stub')\n", encoding="utf-8")
    (kometa_root / "modules" / "overlay.py").write_text("class Overlay: pass\n", encoding="utf-8")
    env = {
        "RATINGS_MATRIX_WITH_KOMETA": "true",
        "RATINGS_MATRIX_KOMETA_ROOT": str(kometa_root),
    }

    run_tests.maybe_disable_missing_ratings_kometa(env)

    assert env["RATINGS_MATRIX_WITH_KOMETA"] == "true"
