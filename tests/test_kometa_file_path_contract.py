"""Optional integration with the installed Kometa loader, without Plex/network.

Execute the actual upstream functions with requests/logging adapters. The app's
modules package would otherwise shadow Kometa's package. CI installs defaults
only, so this contract is skipped when the upstream Python sources are absent.
"""

import ast
import glob
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

KOMETA_MODULES = Path(__file__).resolve().parents[1] / "config/kometa/modules"
pytestmark = pytest.mark.skipif(not (KOMETA_MODULES / "meta.py").is_file(), reason="Requires an installed Kometa source tree")


def _upstream_function(filename, function_name, namespace, class_name=None):
    source = KOMETA_MODULES / filename
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name).body if class_name else tree.body
    function = next(node for node in nodes if isinstance(node, ast.FunctionDef) and node.name == function_name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace[function_name]


@pytest.mark.parametrize("kind", ["collection_files", "metadata_files", "overlay_files", "playlist_files"])
@pytest.mark.parametrize("entry_type", ["file", "folder"])
@pytest.mark.parametrize("custom_config_directory", [False, True])
def test_actual_kometa_loads_generated_managed_file_and_external_template(tmp_path, monkeypatch, kind, entry_type, custom_config_directory):
    from modules.managed_file_paths import managed_runtime_path

    logger = SimpleNamespace(info=lambda *_: None, debug=lambda *_: None, error=lambda *_: None)
    load_files = _upstream_function("util.py", "load_files", {"os": os, "logger": logger, "Failed": RuntimeError, "get_list": lambda value, **_: value, "glob_filter": glob.glob})
    load_file = _upstream_function(
        "meta.py", "load_file", {"os": os, "logger": logger, "Failed": RuntimeError, "util": SimpleNamespace(remove_trakt=lambda data: (data, False))}, class_name="DataFile"
    )
    working = tmp_path / "kometa"
    working.mkdir()
    config_directory = tmp_path / "separate config mount" if custom_config_directory else working / "config"
    relative = f"custom_main/{kind}/shared/custom.yml"
    actual = config_directory / relative
    actual.parent.mkdir(parents=True)
    template = config_directory / f"custom_main/{kind}/templates/shared.yml"
    template.parent.mkdir()
    # JSON is valid YAML and keeps the file-reading adapter dependency-free.
    template.write_text(json.dumps({"templates": {"Shared": {"summary": "Example"}}}), encoding="utf-8")
    actual.write_text(json.dumps({"example": True}), encoding="utf-8")

    def file_yaml(path, **_kwargs):
        return SimpleNamespace(data=json.loads(Path(path).read_text(encoding="utf-8")))

    loader = SimpleNamespace(config=SimpleNamespace(Requests=SimpleNamespace(file_yaml=file_yaml)), library=None)
    monkeypatch.chdir(working)
    token = "config/" + relative
    emitted = managed_runtime_path(token, config_directory=config_directory, working_directory=working)
    if entry_type == "folder":
        emitted = str(Path(emitted).parent)
    files, _scheduled = load_files([{entry_type: emitted}], kind)
    assert len(files) == 1
    assert load_file(loader, files[0][0], files[0][1]) == {"example": True}
    template_token = "config/" + template.relative_to(config_directory).as_posix()
    emitted_template = managed_runtime_path(template_token, config_directory=config_directory, working_directory=working)
    templates, _scheduled = load_files([{"file": emitted_template}], "external_templates", single=True)
    assert load_file(loader, templates[0][0], templates[0][1]) == {"templates": {"Shared": {"summary": "Example"}}}
    # The reported token fails even though the YAML exists under the config root.
    with pytest.raises(RuntimeError, match="File does not exist"):
        load_file(loader, "File", relative)
