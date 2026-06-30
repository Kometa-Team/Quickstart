"""File utility functions extracted from _legacy.py."""

import re

from pathlib import Path


def contains_non_latin(text):
    return bool(re.search(r"[^\x00-\x7F]", text))


def _read_text_if_exists(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _directory_tree_signature(root: Path) -> list[tuple[str, int, int]]:
    if not root.exists() or not root.is_dir():
        return []

    entries: list[tuple[str, int, int]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append((f"{relative}/", 0, 0))
            continue
        try:
            stats = path.stat()
            entries.append((relative, int(stats.st_size), int(stats.st_mtime_ns)))
        except Exception:
            entries.append((relative, -1, -1))
    return entries
