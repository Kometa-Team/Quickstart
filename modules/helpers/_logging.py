"""Log rotation, initialization, and timestamped logging extracted from _legacy.py.

Contains the core write-to-file logging plumbing used by the entire Quickstart
codebase via ``helpers.ts_log()``. The output includes stderr-safe console
output and a redacted on-disk log to avoid leaking secrets.
"""

from __future__ import annotations

import datetime
import os
import re

from flask import has_request_context, session

LOG_DIR = os.path.join("config", "logs")
LOG_FILE = os.path.join(LOG_DIR, "quickstart.log")
MAX_LOG_BACKUPS = 10


def rotate_logs():
    if not os.path.exists(LOG_FILE):
        return

    # Delete the oldest backup if it would exceed MAX_LOG_BACKUPS
    oldest = os.path.join(LOG_DIR, f"quickstart-{MAX_LOG_BACKUPS:03}.log")
    if os.path.exists(oldest):
        os.remove(oldest)

    # Rotate existing backups
    for i in range(MAX_LOG_BACKUPS - 1, 0, -1):
        src = os.path.join(LOG_DIR, f"quickstart-{i:03}.log")
        dst = os.path.join(LOG_DIR, f"quickstart-{i+1:03}.log")
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)

    # Rotate the current log to quickstart-001.log
    dst = os.path.join(LOG_DIR, "quickstart-001.log")
    if os.path.exists(dst):
        os.remove(dst)
    os.rename(LOG_FILE, dst)


def initialize_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    rotate_logs()
    with open(LOG_FILE, "w", encoding="utf-8"):
        pass
    ts_log(f"New log started at {datetime.datetime.now()}", level="INFO")


def redact_string(text):
    redacted = text
    sensitive_keys = [
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "auth",
        "secret",
        "client_id",
        "client_secret",
        "plex_token",
        "password",
        "pin",
        "username",
    ]

    for key in sensitive_keys:
        key_escaped = re.escape(key)

        patterns = [
            # JSON-style quoted
            (rf'("{key_escaped}"\s*:\s*")[^"]*(")', r"\1(redacted)\2"),
            (rf"('{key_escaped}'\s*:\s*')[^']*(')", r"\1(redacted)\2"),
            # Dict-style key = value
            (rf"({key_escaped}\s*=\s*)[^\s,}}]+", r"\1(redacted)"),
            # YAML/Python-style key: value
            (rf"({key_escaped}\s*:\s*)[^\s,}}]+", r"\1(redacted)"),
            # JSON bare/null values
            (rf"({key_escaped}['\"]?\s*:\s*)(None|null)", r"\1(redacted)"),
        ]

        for pattern, repl in patterns:
            redacted = re.sub(pattern, repl, redacted, flags=re.IGNORECASE)

    return redacted


def ts_log(*args, level="INFO"):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    level_str = f"[{level}]"
    padding = " " * (10 - len(level_str))  # Pad to align

    # Grab session ID if in request context
    user_tag = ""
    if has_request_context() and "qs_session_id" in session:
        user_tag = f"[{session['qs_session_id']}] "

    message = " ".join(str(arg) for arg in args)

    # Console (NOT redacted)
    line_console = f"[{now}] {level_str}{padding}| {user_tag}{message}"
    print(line_console)

    # File (redacted)
    redacted_msg = redact_string(message)
    line_file = f"[{now}] {level_str}{padding}| {user_tag}{redacted_msg}"

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line_file + "\n")
    except Exception:
        pass
