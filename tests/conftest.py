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


@pytest.fixture(scope="session")
def workspace_status_module(qs_module):
    """Direct handle to ``modules.workspace_status``.

    Tests must patch *this* module (not ``qs_module``) for symbols whose
    runtime call site lives inside ``modules/workspace_status.py`` --
    e.g. ``_build_kometa_install_context``, ``_build_final_gate``,
    ``_get_imagemaid_settings_section``. ``qs_module`` re-exports these
    names but the functions inside ``workspace_status`` resolve them in
    their own module namespace.
    """
    import modules.workspace_status as ws

    return ws


@pytest.fixture(scope="session")
def library_routes_module(qs_module):
    """Direct handle to ``blueprints.library_routes``.

    Same rationale as ``workspace_status_module`` -- when a test needs to
    monkeypatch a helper (e.g. ``_build_library_lists``,
    ``_migrate_legacy_playlist_libraries_to_library_toggles``,
    ``_build_preview_image_data``) that is called from *inside* a route in
    ``blueprints/library_routes.py``, patching ``qs_module`` will only
    update the re-export; the actual call resolves through the blueprint
    module's own namespace.
    """
    import blueprints.library_routes as lr

    return lr


@pytest.fixture(scope="session")
def import_config_routes_module(qs_module):
    """Direct handle to ``blueprints.import_config_routes``.

    Same rationale as ``workspace_status_module`` and
    ``library_routes_module`` -- patches on ``qs_module._foo`` only update
    the re-export.  Use this fixture to monkeypatch helpers that route
    callers inside the import-config blueprint resolve through their own
    module namespace (e.g. ``_coerce_validation_response_payload``,
    ``_map_playlist_libraries``, ``count_annotated_lines``).
    """
    import blueprints.import_config_routes as ic

    return ic


@pytest.fixture(scope="session")
def imagemaid_routes_module(qs_module):
    """Direct handle to ``blueprints.imagemaid_routes``.

    Same rationale as the other ``*_routes_module`` fixtures -- patches on
    ``qs_module._foo`` only update the re-export.  Use this fixture to
    monkeypatch helpers that route callers inside the imagemaid-runtime
    blueprint resolve through their own module namespace.
    """
    import blueprints.imagemaid_routes as ir

    return ir


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
