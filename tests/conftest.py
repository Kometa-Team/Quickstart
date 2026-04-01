import importlib
import os
import sys

import pytest


_LOADED = {}


def _load_app():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    import modules.helpers as helpers

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
    _LOADED["module"] = quickstart
    return quickstart.app


@pytest.fixture(scope="session")
def app():
    return _load_app()


@pytest.fixture(scope="session")
def qs_module(app):
    import sys

    return sys.modules.get("quickstart") or _LOADED.get("module")

@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def isolated_config_dir(tmp_path, monkeypatch, app):
    import modules.helpers as helpers

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    kometa_root = tmp_path / "kometa"
    kometa_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(helpers, "CONFIG_DIR", str(config_dir))
    app.config["KOMETA_ROOT"] = str(kometa_root)

    return config_dir
