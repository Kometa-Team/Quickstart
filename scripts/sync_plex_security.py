"""Vendor the authoritative offline advisory core from a local Logscan checkout."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logscan", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = args.logscan / "logscan_web" / "plex_security.py"
    content = source.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
    target = Path(__file__).resolve().parents[1] / "modules" / "_vendor" / "plex_security.py"
    if args.check:
        if target.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8") != content:
            raise SystemExit("Vendored Plex advisory core differs from Logscan")
        return
    revision = subprocess.check_output(["git", "-C", str(args.logscan), "rev-parse", "HEAD"], text=True).strip()
    committed = subprocess.check_output(["git", "-C", str(args.logscan), "show", f"{revision}:logscan_web/plex_security.py"])
    if committed.decode("utf-8").replace("\r\n", "\n").encode("utf-8") != content:
        raise SystemExit("Commit the authoritative Logscan source before vendoring it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    manifest = {"repository": "Kometa-Team/Logscan", "revision": revision, "path": "logscan_web/plex_security.py", "sha256": hashlib.sha256(content).hexdigest()}
    target.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
