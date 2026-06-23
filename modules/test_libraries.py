import os
import sys
import uuid

from flask import current_app as app

from modules import helpers


def normalize_test_libraries_path(raw_path, base_dir):
    value = str(raw_path or "").strip().strip('"').strip("'")
    if not value:
        return ""
    value = os.path.expandvars(value)
    value = os.path.expanduser(value)
    if not os.path.isabs(value):
        value = os.path.abspath(os.path.join(base_dir, value))
    return os.path.abspath(value)


def resolve_test_libraries_paths(quickstart_root):
    base_config_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else quickstart_root
    default_final = os.path.join(base_config_dir, "config", "plex_test_libraries")
    default_tmp = os.path.join(base_config_dir, "config", "tmp")
    raw_final = app.config.get("QS_TEST_LIBS_PATH") or os.getenv("QS_TEST_LIBS_PATH") or default_final
    raw_tmp = app.config.get("QS_TEST_LIBS_TMP") or os.getenv("QS_TEST_LIBS_TMP") or default_tmp
    final_path = normalize_test_libraries_path(raw_final, base_config_dir) or os.path.abspath(default_final)
    tmp_path = normalize_test_libraries_path(raw_tmp, base_config_dir) or os.path.abspath(default_tmp)
    return base_config_dir, final_path, tmp_path, default_final, default_tmp


def test_libraries_present(path):
    if not path or not os.path.isdir(path):
        return False
    expected_dirs = [
        os.path.join(path, "test_tv_lib"),
        os.path.join(path, "test_movie_lib"),
    ]
    marker = os.path.join(path, ".test_libraries_version")
    return all(os.path.isdir(p) for p in expected_dirs) or os.path.exists(marker)


def paths_overlap(path_a, path_b):
    if not path_a or not path_b:
        return False
    try:
        common = os.path.commonpath([os.path.abspath(path_a), os.path.abspath(path_b)])
    except ValueError:
        return False
    return common == os.path.abspath(path_a) or common == os.path.abspath(path_b)


def ensure_rw_dir(path):
    if not path:
        return False, "Path is empty."
    if os.path.exists(path) and not os.path.isdir(path):
        return False, "Path exists but is not a directory."
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as e:
        helpers.ts_log(f"Unable to create folder '{path}': {e}", level="ERROR")
        return False, "Unable to create folder."
    test_file = os.path.join(path, f".qs_write_test_{uuid.uuid4().hex}")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        helpers.ts_log(f"Unable to write to folder '{path}': {e}", level="ERROR")
        return False, "Unable to write to folder."
    return True, ""


def safe_to_replace_test_libraries(path):
    if not path:
        return False
    if not os.path.exists(path):
        return True
    if test_libraries_present(path):
        return True
    if os.path.isdir(path) and not os.listdir(path):
        return True
    return False
