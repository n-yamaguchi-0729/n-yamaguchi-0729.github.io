#!/usr/bin/env python3
"""Record a clean ProCGroups commit as the documentation source release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent
PUBLISHER = ROOT.parent
PROJECTS_ROOT = PUBLISHER.parent.parent
DEFAULT_DATABASE = PUBLISHER / "data" / "libraries" / "ProCGroups"
DEFAULT_REPOSITORY = PROJECTS_ROOT / "ProCGroups"
PUBLIC_REPOSITORY = "https://github.com/n-yamaguchi-0729/ProCGroups"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
LEAN_MODULE = re.compile(r"^[A-Za-z0-9_']+(?:\.[A-Za-z0-9_']+)*$")
MATHLIB_REV = re.compile(r'^\s*rev\s*=\s*"([^"]+)"\s*$', re.MULTILINE)
PACKAGE_VERSION = re.compile(
    r'^\s*version\s*=\s*"([^"]+)"\s*$',
    re.MULTILINE,
)


class StampError(RuntimeError):
    """The public repository cannot be recorded as a release."""


def git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise StampError(detail.strip()) from error
    return result.stdout.strip()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StampError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise StampError(f"{path} must contain a JSON object")
    return value


def validate_manifest(manifest: dict[str, Any], label: str) -> list[str]:
    if set(manifest) != {"schema", "package", "module_count", "modules"}:
        raise StampError(f"{label} must use the exact schema-3 public manifest")
    modules = manifest.get("modules")
    if (
        manifest.get("schema") != 3
        or manifest.get("package") != "ProCGroups"
        or not isinstance(modules, list)
        or not modules
        or any(
            not isinstance(module, str) or not LEAN_MODULE.fullmatch(module)
            for module in modules
        )
        or modules != sorted(modules)
        or len(modules) != len(set(modules))
        or manifest.get("module_count") != len(modules)
    ):
        raise StampError(f"{label} contains an invalid module inventory")
    return modules


def repository_modules(repository: Path) -> list[str]:
    """Return the exact Lean module inventory without requiring MANIFEST.json."""
    lean_root = repository / "Lean4"
    if lean_root.is_symlink() or not lean_root.is_dir():
        raise StampError(f"Lean source directory was not found: {lean_root}")
    modules: list[str] = []
    for path in lean_root.rglob("*.lean"):
        if path.is_symlink() or not path.is_file():
            raise StampError(f"unsafe Lean source entry: {path}")
        module = ".".join(path.relative_to(lean_root).with_suffix("").parts)
        if not LEAN_MODULE.fullmatch(module):
            raise StampError(f"invalid Lean module path: {path}")
        modules.append(module)
    modules.sort()
    if not modules or len(modules) != len(set(modules)):
        raise StampError("Lean source inventory is empty or contains duplicates")
    return modules


def expected_docs(
    repository: Path,
    modules_database: Path,
    docs_database: Path,
) -> str:
    repository = repository.resolve()
    if not repository.is_dir() or not (repository / ".git").is_dir():
        raise StampError(f"ProCGroups repository was not found: {repository}")
    dirty = git(repository, "status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise StampError("ProCGroups must be clean before stamping:\n" + dirty)

    commit = git(repository, "rev-parse", "HEAD")
    if not FULL_SHA.fullmatch(commit):
        raise StampError(f"invalid ProCGroups commit: {commit!r}")
    committed_at = datetime.fromisoformat(
        git(repository, "show", "-s", "--format=%cI", "HEAD")
    ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    database_manifest = read_object(modules_database)
    database_modules = validate_manifest(database_manifest, "database modules.json")
    source_modules = repository_modules(repository)
    if source_modules != database_modules:
        raise StampError(
            "ProCGroups Lean inventory differs from the publishing database; "
            "refresh modules.json first"
        )

    toolchain = (repository / "lean-toolchain").read_text(encoding="utf-8").strip()
    if not toolchain:
        raise StampError("lean-toolchain is empty")
    lakefile = (repository / "lakefile.toml").read_text(encoding="utf-8")
    revision = MATHLIB_REV.search(lakefile)
    if revision is None:
        raise StampError("cannot find the mathlib revision in lakefile.toml")
    version = PACKAGE_VERSION.search(lakefile)
    if version is None:
        raise StampError("cannot find the package version in lakefile.toml")

    current = read_object(docs_database)
    expected_fields = {
        "schema_version",
        "repository",
        "source_commit",
        "version",
        "generated_at",
        "lean_toolchain",
        "mathlib_ref",
        "source_dir",
        "module_count",
    }
    if set(current) != expected_fields or current.get("schema_version") != 3:
        raise StampError("release.json must use schema version 3")
    current.update(
        {
            "repository": PUBLIC_REPOSITORY,
            "source_commit": commit,
            "version": version.group(1),
            "generated_at": committed_at,
            "lean_toolchain": toolchain,
            "mathlib_ref": revision.group(1),
            "source_dir": "Lean4",
            "module_count": len(source_modules),
        }
    )
    return json.dumps(current, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Publishing database directory.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    modules_database = args.database / "modules.json"
    docs_database = args.database / "release.json"
    try:
        content = expected_docs(
            args.repository,
            modules_database,
            docs_database,
        )
        stale = (
            not docs_database.is_file()
            or docs_database.read_text(encoding="utf-8") != content
        )
        if args.check:
            if stale:
                print(f"stale release database: {docs_database}", file=sys.stderr)
                return 1
            print("release database matches the clean ProCGroups HEAD")
            return 0
        if args.write:
            docs_database.write_text(content, encoding="utf-8", newline="\n")
            print("recorded the clean ProCGroups HEAD in release.json")
            return 0
        print(
            "dry run: release.json "
            + ("would be updated" if stale else "is already current")
            + "; use --write to modify it"
        )
        return 0
    except (OSError, StampError) as error:
        print(f"stamp failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
