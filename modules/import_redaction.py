"""Helpers for recognizing redacted import credential placeholders."""

from __future__ import annotations

from typing import Any

REDACTED_CREDENTIAL_VALUES = {
    "(redacted)",
    "<redacted>",
    "redacted",
    "(saved plex token)",
    "(saved plex url)",
}


def is_redacted_credential_value(value: Any) -> bool:
    return str(value or "").strip().lower() in REDACTED_CREDENTIAL_VALUES


def clean_import_credential_value(value: Any) -> str:
    text = str(value or "").strip()
    if is_redacted_credential_value(text):
        return ""
    return text
