import importlib
import os
import shutil
import sys

import pytest

_LOADED = {}


def _seed_schema_files(config_dir):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    schema_root = os.path.join(repo_root, "config", ".schema")
    target_schema_root = os.path.join(str(config_dir), ".schema")
    os.makedirs(target_schema_root, exist_ok=True)
    for name in (
        "README.md",
        "collection-schema.json",
        "config-schema.json",
        "config.yml.template",
        "kitchen_sink_config.yml",
        "metadata-schema.json",
        "overlay-schema.json",
        "playlist-schema.json",
        "prototype_comprehensive.yml",
        "prototype_config.yml",
        "file_hashes.txt",
    ):
        source = os.path.join(schema_root, name)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(target_schema_root, name))


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
