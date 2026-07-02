"""Process ID and runtime state utilities extracted from the original helpers.py monolith."""

import os
import stat

import psutil

from modules.helpers._constants import CONFIG_DIR


def get_app_root():
    # Go up one directory to reach the Quickstart root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def handle_remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def get_kometa_pid_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return os.path.join(CONFIG_DIR, "kometa.pid")


def get_kometa_pid():
    pid_file = get_kometa_pid_file()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None


def is_kometa_running():
    pid = get_kometa_pid()
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and "kometa.py" in " ".join(proc.cmdline())
    except psutil.NoSuchProcess:
        try:
            os.remove(get_kometa_pid_file())
        except Exception:
            pass
        return False


def get_imagemaid_pid_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return os.path.join(CONFIG_DIR, "imagemaid.pid")


def get_imagemaid_launch_log_file():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return os.path.join(CONFIG_DIR, "imagemaid-launch.log")


def get_imagemaid_pid():
    pid_file = get_imagemaid_pid_file()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return None
    return None


def is_imagemaid_running():
    pid = get_imagemaid_pid()
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and "imagemaid.py" in " ".join(proc.cmdline())
    except psutil.NoSuchProcess:
        try:
            os.remove(get_imagemaid_pid_file())
        except Exception:
            pass
        return False
