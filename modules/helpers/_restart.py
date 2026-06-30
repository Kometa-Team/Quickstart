"""Restart notice and environment variable utilities extracted from _legacy.py."""

import datetime
import json
import os

from modules.helpers._legacy import CONFIG_DIR, RESTART_NOTICE_FILE


def update_env_variable(key, value):
    env_path = os.path.join(CONFIG_DIR, ".env")

    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as file:
            env_lines = file.readlines()

    with open(env_path, "w") as file:
        key_found = False
        for line in env_lines:
            if line.startswith(f"{key}="):
                file.write(f"{key}={value}\n")
                key_found = True
            else:
                file.write(line)
        if not key_found:
            file.write(f"{key}={value}\n")


def set_restart_notice(reason, message=None):
    if not isinstance(reason, str) or not reason.strip():
        return False
    payload = {
        "reason": reason.strip(),
        "message": message.strip() if isinstance(message, str) and message.strip() else None,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
    }
    from modules.helpers._legacy import ts_log

    try:
        with open(RESTART_NOTICE_FILE, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return True
    except Exception as exc:
        ts_log(f"Failed to write restart notice: {exc}", level="WARNING")
        return False


def consume_restart_notice():
    if not os.path.exists(RESTART_NOTICE_FILE):
        return None
    from modules.helpers._legacy import ts_log

    try:
        with open(RESTART_NOTICE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        ts_log(f"Failed to read restart notice: {exc}", level="WARNING")
        payload = None
    try:
        os.remove(RESTART_NOTICE_FILE)
    except Exception as exc:
        ts_log(f"Failed to remove restart notice: {exc}", level="WARNING")
    return payload
