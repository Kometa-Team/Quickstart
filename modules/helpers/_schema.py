"""Schema/hash utilities and small constants extracted from _legacy.py."""

import hashlib
import os

from modules.helpers._legacy import ALLOWED_EXTENSIONS, HASH_FILE, JSON_SCHEMA_DIR, JSON_SCHEMA_SYNC_FILES


def allowed_extensions_string():
    return ", ".join(sorted(ALLOWED_EXTENSIONS))


def calculate_hash(content):
    """Compute the SHA256 hash of the given content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _schema_files_present():
    return all(os.path.exists(os.path.join(JSON_SCHEMA_DIR, filename)) for filename, _remote_path in JSON_SCHEMA_SYNC_FILES)


def load_previous_hashes():
    """Load the last known hashes of schema files."""
    if not os.path.exists(HASH_FILE):
        return {}

    hashes = {}
    with open(HASH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            filename, file_hash = line.strip().split(":", 1)
            hashes[filename] = file_hash
    return hashes


def save_hashes(hashes):
    """Save updated hashes to the hash file."""
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        for filename, file_hash in hashes.items():
            f.write(f"{filename}:{file_hash}\n")
