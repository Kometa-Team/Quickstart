"""Quickstart settings utilities extracted from the original helpers.py monolith."""

import os

from flask import current_app as app


def booler(thing):
    from modules.helpers._logging import ts_log

    if isinstance(thing, str):
        thing = thing.lower().strip()
        if thing in ("true", "yes", "1"):
            return True
        elif thing in ("false", "no", "0"):
            return False
        else:
            if app.config["QS_DEBUG"]:
                ts_log(
                    f"Warning: Invalid boolean string encountered: {thing}. Defaulting to False.",
                    level="DEBUG",
                )
            return False
    return bool(thing)


def get_quickstart_settings_summary():
    from modules import helpers as _h_settings

    def get_value(key, default=""):
        value = app.config.get(key)
        if value is None or value == "":
            value = os.getenv(key, default)
        return value

    def format_bool(value):
        return "Enabled" if booler(value) else "Disabled"

    def format_keep(value):
        if value is None or str(value).strip() == "":
            return "Keep all (0)"
        try:
            num = int(str(value).strip())
        except (TypeError, ValueError):
            return str(value)
        return "Keep all (0)" if num == 0 else str(num)

    handled = {
        "QS_PORT",
        "QS_DEBUG",
        "QS_THEME",
        "QS_OPTIMIZE_DEFAULTS",
        "QS_CONFIG_HISTORY",
        "QS_KOMETA_LOG_KEEP",
        "QS_IMAGEMAID_LOG_KEEP",
        "QS_TEST_LIBS_TMP",
        "QS_TEST_LIBS_PATH",
    }
    skip = {"QS_FLASK_SESSION_DIR", "QS_CONFIG_CLEANUP_DONE", "QS_SKIP_AUTO_OPEN"}

    summary = [
        ("QS_PORT", "Quickstart Port", lambda v: v or "Unknown"),
        ("QS_DEBUG", "Quickstart Debug", format_bool),
        ("QS_THEME", "Quickstart Theme", lambda v: v or "kometa"),
        ("QS_OPTIMIZE_DEFAULTS", "Quickstart Optimize Template Defaults", format_bool),
        ("QS_CONFIG_HISTORY", "Quickstart Config Archive History", format_keep),
        ("QS_KOMETA_LOG_KEEP", "Quickstart Kometa Log Retention", format_keep),
        ("QS_IMAGEMAID_LOG_KEEP", "Quickstart ImageMaid Log Retention", format_keep),
        ("QS_TEST_LIBS_TMP", "Quickstart Test Libraries Temp Path", lambda v: v or "Default"),
        ("QS_TEST_LIBS_PATH", "Quickstart Test Libraries Install Path", lambda v: v or "Default"),
    ]

    lines = []
    for key, label, formatter in summary:
        value = get_value(key, "")
        lines.append(f"# {label}: {formatter(value)}")

    kometa_mode = _h_settings.get_kometa_install_mode()
    lines.append(f"# Kometa Runtime Mode: {_h_settings.get_kometa_install_mode_label(kometa_mode)}")

    extra_keys = sorted(key for key in app.config.keys() if key.startswith("QS_") and key not in handled and key not in skip)
    for key in extra_keys:
        value = get_value(key, "")
        if value is None or value == "":
            continue
        if isinstance(value, bool) or str(value).strip().lower() in {"true", "false", "yes", "no", "1", "0"}:
            display = format_bool(value)
        else:
            display = str(value)
        label = "Quickstart " + key.replace("QS_", "").replace("_", " ").title()
        lines.append(f"# {label}: {display}")

    return lines
