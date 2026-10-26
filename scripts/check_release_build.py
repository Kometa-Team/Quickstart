"""Check the build manifest entries required by the lint workflow."""

import json
from pathlib import Path

ENTRIES = ("000-base", "001-start", "010-plex", "025-libraries", "900-kometa", "905-analytics", "eventHandler", "overlayHandler")


def main():
    manifest = json.loads(Path("static/dist/.vite/manifest.json").read_text(encoding="utf-8"))
    missing = [entry for entry in ENTRIES if f"static/local-js/{entry}.js" not in manifest]
    if missing:
        raise SystemExit(f"Missing build entries: {missing}")


if __name__ == "__main__":
    main()
