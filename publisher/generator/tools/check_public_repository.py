#!/usr/bin/env python3
"""Validate the generated GitHub Pages repository outside the Lean portal."""

from __future__ import annotations

import argparse
from html import unescape
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


CANONICAL_ORIGIN = "https://n-yamaguchi-0729.github.io"
PORTAL_NAME = "YamaLean4Lib_pages"
EXPECTED_REPOSITORY_ROOTS = frozenset({
    ".gitattributes",
    ".github",
    ".nojekyll",
    "README.md",
    PORTAL_NAME,
    "googlee8a500422e0afa27.html",
    "homepage-en.html",
    "homepage-jp.html",
    "index.html",
    "robots.txt",
    "sitemap.xml",
})
OPTIONAL_REPOSITORY_ROOTS = frozenset({
    "LICENSE",
})
EXPECTED_GITHUB_FILES = frozenset({
    ".github/validation/check_generated_site.py",
    ".github/validation/check_public_repository.py",
    ".github/validation/public_paths.py",
    ".github/workflows/ci.yml",
    ".github/workflows/pages.yml",
})
EXPECTED_PORTAL_ROOTS = frozenset({
    "assets",
    "build-info.json",
    "find",
    "index.html",
    "library",
})
EXPECTED_PORTAL_ASSETS = frozenset({
    "search-index.js",
    "site.css",
    "site.js",
    "tree-data.js",
})
ROOT_HTML_FILES = (
    "homepage-en.html",
    "homepage-jp.html",
    "index.html",
    f"{PORTAL_NAME}/index.html",
)
HREF = re.compile(r'\bhref="([^"]+)"')
LIBRARY_CARD = re.compile(
    r'<section\b[^>]*\bdata-sort-item\b[^>]*>.*?</section>',
    re.DOTALL,
)
HOME_LIBRARY_LINK = '<a href="./YamaLean4Lib_pages/">URL</a>'
FORBIDDEN_NOTICE_PHRASES = (
    "subject-matter expert",
    "accuracy and completeness are not guaranteed",
    "at your own risk",
    "cannot answer questions",
    "個別の質問",
    "自己責任",
    "正確性や完全性は保証されません",
)


def filesystem_inventory(root: Path) -> tuple[list[str], set[str]]:
    """Inventory regular files without following links or entering .git."""
    errors: list[str] = []
    files: set[str] = set()
    casefolded: dict[str, str] = {}
    pending: list[tuple[Path, PurePosixPath]] = [(root, PurePosixPath())]
    while pending:
        directory, relative_directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            errors.append(f"{directory}: cannot inspect repository: {error}")
            continue
        for entry in entries:
            if (
                not relative_directory.parts
                and entry.name in {".git", "publisher"}
            ):
                continue
            relative_path = relative_directory / entry.name
            relative = relative_path.as_posix()
            previous = casefolded.setdefault(relative.casefold(), relative)
            if previous != relative:
                errors.append(
                    f"case-insensitive path collision: {previous!r} and {relative!r}"
                )
            try:
                if entry.is_symlink():
                    errors.append(f"{relative}: symlinks are forbidden")
                elif entry.is_dir(follow_symlinks=False):
                    pending.append((Path(entry.path), relative_path))
                elif entry.is_file(follow_symlinks=False):
                    files.add(relative)
                else:
                    errors.append(f"{relative}: unsupported repository entry")
            except OSError as error:
                errors.append(f"{relative}: cannot inspect entry: {error}")
    return errors, files


def tracked_inventory(root: Path) -> tuple[list[str], set[str]]:
    """Read the exact Git-tracked inventory used by public CI."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        decoded = completed.stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeError) as error:
        return [f"cannot read the Git-tracked inventory: {error}"], set()
    files = {
        relative
        for relative in decoded.split("\0")
        if relative and not relative.startswith("publisher/")
    }
    errors: list[str] = []
    casefolded: dict[str, str] = {}
    for relative in sorted(files):
        previous = casefolded.setdefault(relative.casefold(), relative)
        if previous != relative:
            errors.append(
                f"case-insensitive tracked-path collision: {previous!r} and {relative!r}"
            )
        path = root / PurePosixPath(relative)
        if path.is_symlink():
            errors.append(f"{relative}: tracked symlinks are forbidden")
        elif not path.is_file():
            errors.append(f"{relative}: tracked file is absent from the checkout")
    return errors, files


def load_build_info(
    documentation: Path,
    documentation_name: str,
    errors: list[str],
) -> dict[str, object]:
    try:
        value = json.loads(
            (documentation / "build-info.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(
            f"{documentation_name}/build-info.json: invalid metadata: {error}"
        )
        return {}
    if not isinstance(value, dict):
        errors.append(
            f"{documentation_name}/build-info.json: root must be an object"
        )
        return {}
    return value


def local_target(relative: str, href: str) -> str | None:
    parsed = urlsplit(unescape(href.strip()))
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    path = unquote(parsed.path)
    if path.startswith("/"):
        target = posixpath.normpath(path.lstrip("/"))
    else:
        target = posixpath.normpath(
            posixpath.join(posixpath.dirname(relative), path)
        )
    if target in {"", "."}:
        return "index.html"
    if path.endswith("/"):
        return posixpath.join(target, "index.html")
    return target


def check_sitemap(
    root: Path,
    files: set[str],
    errors: list[str],
) -> None:
    public_pages = {
        relative
        for relative in files
        if relative.endswith(".html")
        and not PurePosixPath(relative).name.casefold().startswith("google")
    }
    expected = set()
    for relative in public_pages:
        public_path = relative
        if public_path == "index.html":
            public_path = ""
        elif public_path.endswith("/index.html"):
            public_path = public_path[: -len("index.html")]
        expected.add(f"{CANONICAL_ORIGIN}/{public_path}")
    try:
        sitemap_root = ET.parse(root / "sitemap.xml").getroot()
        actual_list = [
            element.text.strip()
            for element in sitemap_root.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
                "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
            if element.text
        ]
    except (OSError, ET.ParseError) as error:
        errors.append(f"sitemap.xml: invalid XML: {error}")
        return
    actual = set(actual_list)
    if len(actual_list) != len(actual):
        errors.append("sitemap.xml: duplicate URLs")
    if actual != expected:
        errors.append(
            "sitemap.xml: URL coverage differs from public pages; "
            f"missing={sorted(expected - actual)[:10]}, "
            f"extra={sorted(actual - expected)[:10]}"
        )


def check_public_presentation(root: Path, errors: list[str]) -> None:
    """Check the exact homepage/catalog contract requested for this release."""
    inspected: list[tuple[str, str]] = []
    for relative in ("homepage-en.html", "homepage-jp.html"):
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"{relative}: cannot read UTF-8 content: {error}")
            continue
        inspected.append((relative, text))
        if text.count("Yamaguchi Lean 4 Library:") != 1:
            errors.append(
                f"{relative}: expected exactly one "
                "'Yamaguchi Lean 4 Library:' label"
            )
        if text.count(HOME_LIBRARY_LINK) != 1:
            errors.append(
                f"{relative}: shared documentation URL is missing or duplicated"
            )
        if "https://github.com/n-yamaguchi-0729/YamaLean4Lib" in text:
            errors.append(f"{relative}: private YamaLean4Lib link remains")

    portal_relative = f"{PORTAL_NAME}/index.html"
    try:
        portal = (root / portal_relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"{portal_relative}: cannot read UTF-8 content: {error}")
        portal = ""
    inspected.append((portal_relative, portal))
    cards = LIBRARY_CARD.findall(portal)
    if len(cards) != 1:
        errors.append(
            f"{portal_relative}: expected exactly one library card, "
            f"found {len(cards)}"
        )
    else:
        card = cards[0]
        for marker in (
            'id="library-ProCGroups"',
            ">Pro-C Groups</a>",
            'href="https://github.com/n-yamaguchi-0729/ProCGroups"',
            "A Lean library for profinite groups and pro-C groups.",
        ):
            if marker not in card:
                errors.append(
                    f"{portal_relative}: ProCGroups card is missing {marker!r}"
                )
        if "Open documentation" in card:
            errors.append(
                f"{portal_relative}: ProCGroups card contains Open documentation"
            )
    if portal.count(
        'href="https://github.com/n-yamaguchi-0729/ProCGroups"'
    ) != 1:
        errors.append(
            f"{portal_relative}: ProCGroups GitHub link must occur exactly once"
        )
    github_links: list[tuple[str, str]] = []
    if (root / PORTAL_NAME).is_dir():
        for path in sorted((root / PORTAL_NAME).rglob("*.html")):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                errors.append(f"{path}: cannot inspect GitHub links: {error}")
                continue
            relative = path.relative_to(root).as_posix()
            github_links.extend(
                (relative, href)
                for href in HREF.findall(text)
                if urlsplit(unescape(href.strip())).netloc.casefold()
                == "github.com"
            )
    expected_github_links = [
        (
            portal_relative,
            "https://github.com/n-yamaguchi-0729/ProCGroups",
        )
    ]
    if github_links != expected_github_links:
        errors.append(
            "GitHub links must consist only of the ProCGroups repository in "
            f"its library card; found={github_links}"
        )
    for marker in (
        '<title>Yamaguchi Lean 4 Library</title>',
        '<a class="brand" href="./index.html">Yamaguchi Lean 4 Library</a>',
        '<h1 class="page-title">Yamaguchi Lean 4 Library</h1>',
    ):
        if marker not in portal:
            errors.append(
                f"{portal_relative}: shared site marker is missing: {marker!r}"
            )
    for marker in (
        "LocalClassFieldTheory",
        "Local Class Field Theory",
        "CrowellExactSequence",
    ):
        if marker in portal:
            errors.append(
                f"{portal_relative}: removed library marker remains: {marker!r}"
            )

    for relative, text in inspected:
        folded = text.casefold()
        for phrase in FORBIDDEN_NOTICE_PHRASES:
            if phrase.casefold() in folded:
                errors.append(
                    f"{relative}: obsolete long-form notice remains: {phrase!r}"
                )


def check_repository(root: Path, *, filesystem: bool) -> list[str]:
    root = root.resolve()
    errors, files = (
        filesystem_inventory(root)
        if filesystem
        else tracked_inventory(root)
    )
    actual_roots = {
        PurePosixPath(relative).parts[0]
        for relative in files
    }
    if (
        not EXPECTED_REPOSITORY_ROOTS.issubset(actual_roots)
        or frozenset(actual_roots - EXPECTED_REPOSITORY_ROOTS)
        not in {frozenset(), OPTIONAL_REPOSITORY_ROOTS}
    ):
        errors.append(
            "top-level entries differ from the public allowlist; "
            f"required={sorted(EXPECTED_REPOSITORY_ROOTS)}, "
            f"optional={sorted(OPTIONAL_REPOSITORY_ROOTS)}, "
            f"found={sorted(actual_roots)}"
        )

    github_files = {
        relative for relative in files if relative.startswith(".github/")
    }
    if github_files != EXPECTED_GITHUB_FILES:
        errors.append(
            ".github/: files differ from the generated CI allowlist; "
            f"expected={sorted(EXPECTED_GITHUB_FILES)}, "
            f"found={sorted(github_files)}"
        )

    for relative in sorted(files):
        parts = tuple(part.casefold() for part in PurePosixPath(relative).parts)
        if (
            PurePosixPath(relative).suffix.casefold() == ".zip"
            or "download" in parts
            or "backup" in parts
        ):
            errors.append(f"{relative}: archive/download/backup content is forbidden")

    portal = root / PORTAL_NAME
    portal_roots = (
        {entry.name for entry in portal.iterdir()}
        if portal.is_dir()
        else set()
    )
    if portal_roots != EXPECTED_PORTAL_ROOTS:
        errors.append(
            f"{PORTAL_NAME}/: entries differ from the runtime allowlist; "
            f"expected={sorted(EXPECTED_PORTAL_ROOTS)}, "
            f"found={sorted(portal_roots)}"
        )
    portal_assets = (
        {entry.name for entry in (portal / "assets").iterdir()}
        if (portal / "assets").is_dir()
        else set()
    )
    if portal_assets != EXPECTED_PORTAL_ASSETS:
        errors.append(
            f"{PORTAL_NAME}/assets: entries differ from the catalog allowlist; "
            f"expected={sorted(EXPECTED_PORTAL_ASSETS)}, "
            f"found={sorted(portal_assets)}"
        )

    library_names: set[str] = set()
    build_info = load_build_info(portal, PORTAL_NAME, errors)
    raw_libraries = build_info.get("libraries")
    if isinstance(raw_libraries, list):
        library_names.update(
            str(item.get("display_name"))
            for item in raw_libraries
            if isinstance(item, dict)
            and isinstance(item.get("display_name"), str)
        )

    try:
        root_index = (root / "index.html").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"index.html: cannot read UTF-8 content: {error}")
        root_index = ""
    if "Lean 4 libraries" not in root_index:
        errors.append("index.html: generic 'Lean 4 libraries' link is missing")
    for display_name in sorted(library_names):
        if display_name in root_index:
            errors.append(
                "index.html: current library name is hard-coded: "
                f"{display_name!r}"
            )

    try:
        readme = (root / "README.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        errors.append(f"README.md: cannot read UTF-8 content: {error}")
        readme = ""
    for internal_marker in (
        "YamaLean4Lib_Database",
        "YamaLean4Lib_Generator",
        "generate.py",
        "LICENSE",
    ):
        if internal_marker in readme:
            errors.append(
                f"README.md: internal implementation detail is public: {internal_marker!r}"
            )

    for relative in ROOT_HTML_FILES:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"{relative}: cannot read UTF-8 content: {error}")
            continue
        for href in HREF.findall(text):
            target = local_target(relative, href)
            if target is not None and target not in files:
                errors.append(
                    f"{relative}: broken local link {href!r} -> {target!r}"
                )

    check_public_presentation(root, errors)
    check_sitemap(root, files, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--filesystem",
        action="store_true",
        help="inspect an untracked temporary generation instead of Git files",
    )
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    errors = list(dict.fromkeys(
        check_repository(args.root, filesystem=args.filesystem)
    ))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"{args.root.resolve()}: public repository structure verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
