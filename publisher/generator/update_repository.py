#!/usr/bin/env python3
"""Run the canonical public-library exporter with the publishing database."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
PUBLISHER = ROOT.parent
PROJECTS_ROOT = PUBLISHER.parent.parent
DATABASE = PUBLISHER / "data" / "libraries" / "ProCGroups"
PUBLIC_REPOSITORY = PROJECTS_ROOT / "ProCGroups"
DEFAULT_SOURCE_ROOT = (
    Path(r"\\wsl.localhost\Ubuntu\home\nyama\work")
    if os.name == "nt"
    else Path("/home/nyama/work")
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument(
        "--config",
        type=Path,
        default=DATABASE / "export.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DATABASE / "modules.json",
    )
    parser.add_argument("--target", type=Path, default=PUBLIC_REPOSITORY)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if args.write:
        print(
            "refusing --write: the shared exporter still owns README.md and "
            "would overwrite the standalone ProCGroups README. Use the "
            "ProCGroups-owned export workflow after it supports preserving "
            "the project README.",
            file=sys.stderr,
        )
        return 2

    source_root = args.source_root.resolve()
    exporter = source_root / "scripts" / "export_public_libraries.py"
    if exporter.is_symlink() or not exporter.is_file():
        print(
            f"public-library exporter was not found: {exporter}",
            file=sys.stderr,
        )
        return 2

    command = [
        sys.executable,
        str(exporter),
        "--source-root",
        str(source_root),
        "--config",
        str(args.config.resolve()),
        "--manifest",
        str(args.manifest.resolve()),
        "--target",
        str(args.target.resolve()),
    ]
    if args.check:
        command.append("--check")
    elif args.write:
        command.append("--write")
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"cannot run public-library exporter: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
