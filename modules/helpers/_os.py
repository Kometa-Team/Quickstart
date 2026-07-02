"""OS detection utility extracted from the original helpers.py monolith."""

import os
import platform
import sys


def get_running_os():
    # Preserve build for backward compatibility, even if unused
    build = os.getenv("BUILD_OS", "local").lower()  # noqa: F841

    # 1. Docker check via env
    if os.getenv("QUICKSTART_DOCKER", "False").lower() in ["true", "1"]:
        return "Docker", ""

    # 2. Frozen build (e.g., PyInstaller)
    if getattr(sys, "frozen", False):
        system = platform.system()
        if system == "Windows":
            return "Frozen-Windows", ".exe"
        elif system == "Darwin":
            return "Frozen-macOS", ""
        elif system == "Linux":
            return "Frozen-Linux", ""
        else:
            return "Frozen-Unknown", ""

    # 3. Local run
    system = platform.system()
    if system == "Windows":
        return "Local-Windows", ".exe"
    elif system == "Darwin":
        return "Local-macOS", ""
    elif system == "Linux":
        return "Local-Linux", ""
    else:
        return "Local-Unknown", ""
