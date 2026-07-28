#!/usr/bin/env python3
"""Validate both the generated ProCGroups tree and its deployed subset."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile

import site_policy


def check_site(root: Path) -> list[str]:
    """Return validation errors for the generated and public forms of ``root``."""
    absolute_root = root.absolute()
    errors = list(site_policy.check_root(absolute_root))
    if errors:
        return errors

    with tempfile.TemporaryDirectory(prefix="procgroups-public-site-") as temp:
        public_root = Path(temp) / "site"
        shutil.copytree(absolute_root, public_root)
        (public_root / site_policy.SITE_MANIFEST_NAME).unlink()
        errors.extend(site_policy.check_public_artifacts(public_root))
    return list(dict.fromkeys(errors))


def main() -> int:
    """Run validation for every site root supplied on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    errors = [error for root in args.roots for error in check_site(root)]
    if errors:
        for error in errors[:200]:
            print(f"ERROR: {error}")
        if len(errors) > 200:
            print(f"ERROR: ... and {len(errors) - 200} more")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
