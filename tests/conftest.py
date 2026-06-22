import importlib
import os
import shutil
import sys

import pytest

_LOADED = {}


def _seed_schema_files(config_dir):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    # `config/.schema` is a gitignored local cache that the app populates at runtime by
    # downloading from GitHub. It won't exist on a fresh checkout (e.g. CI), so fall back
    # to the checked-in fixtures in tests/fixtures/schema to keep tests reproducible offline.
    schema_roots = [
        os.path.join(repo_root, "config", ".schema"),
        os.path.join(os.path.dirname(__file__), "fixtures", "schema"),
    ]
    target_schema_root = os.path.join(str(config_dir), ".schema")
    os.makedirs(target_schema_root, exist_ok=True)
    copied = set()
    for schema_root in schema_roots:
        if not os.path.isdir(schema_root):
            continue
        for current_root, _dirs, files in os.walk(schema_root):
            rel_root = os.path.relpath(current_root, schema_root)
            target_root = target_schema_root if rel_root == "." else os.path.join(target_schema_root, rel_root)
            for name in files:
                rel_name = name if rel_root == "." else os.path.join(rel_root, name)
                if rel_name in copied:
                    continue
                os.makedirs(target_root, exist_ok=True)
                source = os.path.join(current_root, name)
                shutil.copy2(source, os.path.join(target_root, name))
                copied.add(rel_name)


def _load_app(config_dir, kometa_root):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    import modules.helpers as helpers

    _seed_schema_files(config_dir)
    helpers.CONFIG_DIR = str(config_dir)
    helpers.JSON_SCHEMA_DIR = os.path.join(str(config_dir), ".schema")
    helpers.HASH_FILE = os.path.join(str(config_dir), ".schema", "file_hashes.txt")
    helpers.RESTART_NOTICE_FILE = os.path.join(str(config_dir), "restart_needed.flag")
    helpers.check_for_update = lambda: {
        "local_version": "0.0.0",
        "remote_version": "0.0.0",
        "branch": "master",
        "kometa_branch": "nightly",
        "update_available": False,
        "running_on": "Local-Tests",
        "file_ext": "",
    }
    helpers.ensure_json_schema = lambda: None

    if "quickstart" in sys.modules:
        del sys.modules["quickstart"]
    quickstart = importlib.import_module("quickstart")
    quickstart.app.config["KOMETA_ROOT"] = str(kometa_root)
    _LOADED["module"] = quickstart
    return quickstart.app


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    config_dir = tmp_path_factory.mktemp("qs_session_config")
    kometa_root = tmp_path_factory.mktemp("qs_session_kometa_root")
    return _load_app(config_dir, kometa_root)


@pytest.fixture(scope="session")
def qs_module(app):
    return sys.modules.get("quickstart") or _LOADED.get("module")


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def isolated_config_dir(tmp_path, monkeypatch, app):
    import modules.helpers as helpers

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    _seed_schema_files(config_dir)
    kometa_root = tmp_path / "_qs_test_kometa_root"
    kometa_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(helpers, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(helpers, "JSON_SCHEMA_DIR", str(config_dir / ".schema"))
    monkeypatch.setattr(helpers, "HASH_FILE", str(config_dir / ".schema" / "file_hashes.txt"))
    monkeypatch.setattr(helpers, "RESTART_NOTICE_FILE", str(config_dir / "restart_needed.flag"))
    app.config["KOMETA_ROOT"] = str(kometa_root)

    return config_dir


@pytest.fixture()
def _runtime_isolation(tmp_path, monkeypatch, app):
    import modules.helpers as helpers

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    _seed_schema_files(config_dir)
    kometa_root = tmp_path / "_qs_test_kometa_root"
    kometa_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(helpers, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(helpers, "JSON_SCHEMA_DIR", str(config_dir / ".schema"))
    monkeypatch.setattr(helpers, "HASH_FILE", str(config_dir / ".schema" / "file_hashes.txt"))
    monkeypatch.setattr(helpers, "RESTART_NOTICE_FILE", str(config_dir / "restart_needed.flag"))
    app.config["KOMETA_ROOT"] = str(kometa_root)

    return {"config_dir": config_dir, "kometa_root": kometa_root}


@pytest.fixture(autouse=True)
def _auto_runtime_isolation(_runtime_isolation):
    return _runtime_isolation
