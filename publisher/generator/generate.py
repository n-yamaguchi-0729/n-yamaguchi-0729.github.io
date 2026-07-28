#!/usr/bin/env python3
"""Generate the personal homepage and complete Lean library documentation."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import build_site


ROOT = Path(__file__).resolve().parent
PUBLISHER = ROOT.parent
DATABASE = PUBLISHER / "data"
SITE_REPOSITORY = PUBLISHER.parent
PROJECTS_ROOT = SITE_REPOSITORY.parent
HOME_DATABASE = DATABASE / "homepage.json"
HOME_STYLESHEET = DATABASE / "homepage.css"
LIBRARIES_DATABASE = DATABASE / "libraries.json"
PORTAL_ASSETS = DATABASE / "assets"
PUBLIC_SITE_CI_TEMPLATE = ROOT / "templates" / "public-site-ci.yml"
PUBLIC_SITE_PAGES_TEMPLATE = ROOT / "templates" / "public-site-pages.yml"
PUBLIC_PATHS_SOURCE = ROOT / "public_paths.py"
GENERATED_SITE_CHECKER = ROOT / "tools" / "check_generated_site.py"
PUBLIC_REPOSITORY_CHECKER = ROOT / "tools" / "check_public_repository.py"
PUBLIC = SITE_REPOSITORY
SITE_URL = "https://n-yamaguchi-0729.github.io"
PORTAL = "YamaLean4Lib_pages"
LANGUAGES = ("ja", "en")
HOME_OUTPUT = {"ja": "homepage-jp.html", "en": "homepage-en.html"}
OTHER_LANGUAGE = {"ja": "en", "en": "ja"}
ALWAYS_PRESERVED_OUTPUT_TOP_LEVEL = frozenset({
    ".git",
    "LICENSE",
    "publisher",
})
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
LEAN_MODULE = re.compile(r"^[A-Za-z0-9_']+(?:\.[A-Za-z0-9_']+)*$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPOSITORY = re.compile(
    r"^https://github\.com/n-yamaguchi-0729/[A-Za-z0-9_.-]+$"
)
PUBLIC_SITE_REPOSITORY_IDENTITY = (
    "github.com/n-yamaguchi-0729/n-yamaguchi-0729.github.io"
)


class DatabaseError(ValueError):
    """A site database does not match its public schema."""


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DatabaseError(f"duplicate key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except json.JSONDecodeError as error:
        raise DatabaseError(f"{path.name}: invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error


def load_home_database() -> dict[str, Any]:
    data = read_json(HOME_DATABASE)
    if data.get("schema_version") != 1 or set(data.get("pages", {})) != set(LANGUAGES):
        raise DatabaseError("homepage.json must contain schema_version 1 and ja/en pages")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise DatabaseError("homepage.json sections must be a non-empty list")
    seen: set[str] = set()
    for section in sections:
        section_id = section.get("id") if isinstance(section, dict) else None
        if not isinstance(section_id, str) or not IDENTIFIER.fullmatch(section_id) or section_id in seen:
            raise DatabaseError(f"invalid or duplicate homepage section id: {section_id!r}")
        seen.add(section_id)
        for field in ("nav", "title", "body_html"):
            if set(section.get(field, {})) != set(LANGUAGES):
                raise DatabaseError(f"homepage section {section_id}: invalid {field}")
    return data


def load_libraries_database() -> dict[str, Any]:
    data = read_json(LIBRARIES_DATABASE)
    libraries = data.get("libraries")
    if data.get("schema_version") != 2 or not isinstance(libraries, list) or not libraries:
        raise DatabaseError("libraries.json must contain schema_version 2 and libraries")
    site = data.get("site")
    site_fields = {
        "title",
        "description",
        "lean_version",
        "mathlib_version",
        "license",
    }
    if (
        not isinstance(site, dict)
        or set(site) != site_fields
        or any(not isinstance(site[field], str) or not site[field].strip() for field in site_fields)
    ):
        raise DatabaseError("libraries.json site metadata is incomplete")
    required_fields = {
        "id",
        "display_name",
        "repository",
        "data",
        "import",
        "module_roots",
        "summary",
        "contents",
    }
    seen_ids: set[str] = set()
    seen_id_keys: set[str] = set()
    seen_display_names: set[str] = set()
    seen_roots: set[str] = set()
    seen_root_keys: set[str] = set()
    seen_data_directories: set[str] = set()
    for item in libraries:
        if not isinstance(item, dict) or set(item) != required_fields:
            raise DatabaseError("libraries.json contains an invalid library record")
        library_id = item["id"]
        if (
            not isinstance(library_id, str)
            or not IDENTIFIER.fullmatch(library_id)
            or library_id in seen_ids
            or library_id.casefold() in seen_id_keys
            or library_id.casefold() == "src"
        ):
            raise DatabaseError(f"invalid or duplicate public library id: {library_id!r}")
        seen_ids.add(library_id)
        seen_id_keys.add(library_id.casefold())
        if (
            not isinstance(item["repository"], str)
            or not GITHUB_REPOSITORY.fullmatch(item["repository"])
        ):
            raise DatabaseError(f"{item.get('id', '?')}: invalid public-library schema or repository")
        data_directory = item["data"]
        if (
            not isinstance(data_directory, str)
            or PurePosixPath(data_directory).parts != ("libraries", library_id)
            or data_directory.casefold() in seen_data_directories
        ):
            raise DatabaseError(
                f"{library_id}: data must be the unique path "
                f"'libraries/{library_id}'"
            )
        seen_data_directories.add(data_directory.casefold())
        if (
            not isinstance(item["display_name"], str)
            or not item["display_name"].strip()
            or item["display_name"].casefold() in seen_display_names
            or not isinstance(item["import"], str)
            or not LEAN_MODULE.fullmatch(item["import"])
        ):
            raise DatabaseError(f"{library_id}: invalid display name or import root")
        seen_display_names.add(item["display_name"].casefold())
        import_root = item["import"].split(".", 1)[0]
        if library_id != import_root:
            raise DatabaseError(
                f"{library_id}: public directory id must equal the import namespace "
                f"{import_root!r}"
            )
        roots = item["module_roots"]
        if (
            not isinstance(roots, list)
            or not roots
            or any(
                not isinstance(root, str)
                or "." in root
                or not LEAN_MODULE.fullmatch(root)
                for root in roots
            )
            or len(set(roots)) != len(roots)
            or len({root.casefold() for root in roots}) != len(roots)
        ):
            raise DatabaseError(f"{library_id}: module_roots must be unique top-level Lean names")
        if import_root not in roots:
            raise DatabaseError(
                f"{library_id}: import root {import_root!r} is not in module_roots"
            )
        overlap = seen_roots.intersection(roots)
        folded_overlap = seen_root_keys.intersection(root.casefold() for root in roots)
        if overlap or folded_overlap:
            raise DatabaseError(
                f"{library_id}: module roots already owned by another library: "
                + ", ".join(sorted(overlap or folded_overlap))
            )
        seen_roots.update(roots)
        seen_root_keys.update(root.casefold() for root in roots)
        if (
            not isinstance(item["summary"], str)
            or not item["summary"].strip()
            or not isinstance(item["contents"], list)
            or not item["contents"]
            or any(
                not isinstance(content, str) or not content.strip()
                for content in item["contents"]
            )
        ):
            raise DatabaseError(
                f"{item['id']}: summary and contents must contain public text"
            )
    return data


def library_data_directory(library: dict[str, Any]) -> Path:
    """Return a validated publishing-data directory for one library."""
    relative = PurePosixPath(library["data"])
    path = DATABASE.joinpath(*relative.parts)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(DATABASE.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise DatabaseError(
            f"{library['id']}: publishing data directory is missing or unsafe: {path}"
        ) from error
    if path.is_symlink() or not resolved.is_dir():
        raise DatabaseError(
            f"{library['id']}: publishing data directory is missing or unsafe: {path}"
        )
    return resolved


def library_for_module(module: str, libraries: list[dict[str, Any]]) -> str:
    root = module.split(".", 1)[0]
    owners = [item["id"] for item in libraries if root in item["module_roots"]]
    if len(owners) != 1:
        raise DatabaseError(
            f"Lean module {module!r} must belong to exactly one public library; "
            f"found {owners or 'none'}"
        )
    return owners[0]


def module_owners(
    modules: list[str],
    libraries: list[dict[str, Any]],
) -> dict[str, str]:
    return {module: library_for_module(module, libraries) for module in modules}


def library_module_counts(
    modules: list[str],
    libraries: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {item["id"]: 0 for item in libraries}
    for owner in module_owners(modules, libraries).values():
        counts[owner] += 1
    empty = [library_id for library_id, count in counts.items() if count == 0]
    if empty:
        raise DatabaseError(
            "each configured library must own at least one module: "
            + ", ".join(empty)
        )
    return counts


def load_modules_database(
    libraries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    libraries = libraries or load_libraries_database()["libraries"]
    fields = {"schema", "package", "module_count", "modules"}
    combined: list[str] = []
    by_library: dict[str, dict[str, Any]] = {}
    for library in libraries:
        path = library_data_directory(library) / "modules.json"
        data = read_json(path)
        if (
            set(data) != fields
            or data.get("schema") != 3
            or data.get("package") != library["id"]
        ):
            raise DatabaseError(
                f"{path}: must be a schema 3 {library['id']} module manifest"
            )
        modules = data.get("modules")
        if (
            not isinstance(modules, list)
            or not modules
            or any(not isinstance(module, str) for module in modules)
            or len(set(modules)) != len(modules)
            or len({module.casefold() for module in modules}) != len(modules)
            or modules != sorted(modules)
            or any(not LEAN_MODULE.fullmatch(module) for module in modules)
            or data.get("module_count") != len(modules)
            or any(library_for_module(module, libraries) != library["id"] for module in modules)
            or library["import"] not in modules
        ):
            raise DatabaseError(
                f"{path}: must contain the unique, sorted modules owned by "
                f"{library['id']}"
            )
        by_library[library["id"]] = data
        combined.extend(modules)
    if (
        len(set(combined)) != len(combined)
        or len({module.casefold() for module in combined}) != len(combined)
    ):
        raise DatabaseError("library module manifests overlap")
    combined.sort()
    library_module_counts(combined, libraries)
    return {
        "schema": 3,
        "module_count": len(combined),
        "modules": combined,
        "by_library": by_library,
    }


def load_export_databases(
    libraries: list[dict[str, Any]],
    modules: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate the optional workspace exporter contract for each library."""
    results: dict[str, dict[str, Any]] = {}
    export_fields = {
        "id",
        "display_name",
        "module_roots",
        "source_roots",
        "import_target",
        "description",
    }
    for library in libraries:
        path = library_data_directory(library) / "export.json"
        data = read_json(path)
        if set(data) != {
            "schema",
            "package",
            "version",
            "summary",
            "website",
            "source_dir",
            "libraries",
        } or data.get("schema") != 2:
            raise DatabaseError(f"{path}: invalid exporter schema")
        if (
            data.get("package") != library["id"]
            or data.get("source_dir") != "Lean4"
            or data.get("website") != f"{SITE_URL}/{PORTAL}/"
            or not isinstance(data.get("version"), str)
            or not data["version"].strip()
            or not isinstance(data.get("summary"), str)
            or not data["summary"].strip()
        ):
            raise DatabaseError(f"{path}: invalid package metadata")
        export_libraries = data.get("libraries")
        if (
            not isinstance(export_libraries, list)
            or len(export_libraries) != 1
            or not isinstance(export_libraries[0], dict)
            or export_libraries[0].get("id") != library["id"]
        ):
            raise DatabaseError(
                f"{path}: must contain exactly the {library['id']} export record"
            )
        item = export_libraries[0]
        if set(item) != export_fields:
            raise DatabaseError(f"{path}: invalid library record")
        if (
            item["display_name"] != library["display_name"]
            or item["module_roots"] != library["module_roots"]
            or item["import_target"] != library["import"]
            or not isinstance(item["description"], str)
            or not item["description"].strip()
        ):
            raise DatabaseError(f"{path}: metadata differs from libraries.json")
        library_modules = modules["by_library"][library["id"]]["modules"]
        module_set = set(library_modules)
        expected_source_roots: list[dict[str, Any]] = []
        for root in item["module_roots"]:
            if root in module_set:
                expected_source_roots.append(
                    {"path": f"Lean4/{root}.lean", "include_root": False}
                )
            if any(module.startswith(root + ".") for module in library_modules):
                expected_source_roots.append(
                    {"path": f"Lean4/{root}", "include_root": True}
                )
        if item["source_roots"] != expected_source_roots:
            raise DatabaseError(
                f"{path}: source_roots are not derived from modules.json"
            )
        results[library["id"]] = data
    return results


def load_release_databases(
    libraries: list[dict[str, Any]],
    modules: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Load the pinned release represented by each library's documentation."""
    fields = {
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
    results: dict[str, dict[str, Any]] = {}
    for library in libraries:
        path = library_data_directory(library) / "release.json"
        data = read_json(path)
        source_commit = data.get("source_commit")
        generated_at = data.get("generated_at")
        expected_count = modules["by_library"][library["id"]]["module_count"]
        if (
            set(data) != fields
            or data.get("schema_version") != 3
            or data.get("repository") != library["repository"]
            or not isinstance(source_commit, str)
            or not GIT_COMMIT.fullmatch(source_commit)
            or not isinstance(data.get("version"), str)
            or not data["version"].strip()
            or not isinstance(data.get("lean_toolchain"), str)
            or not data["lean_toolchain"].strip()
            or not isinstance(data.get("mathlib_ref"), str)
            or not data["mathlib_ref"].strip()
            or data.get("source_dir") != "Lean4"
            or data.get("module_count") != expected_count
            or not isinstance(generated_at, str)
            or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                generated_at,
            )
        ):
            raise DatabaseError(f"{path}: invalid pinned library release")
        results[library["id"]] = data
    return results


def module_records(
    data: dict[str, Any],
    libraries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for module in data["modules"]:
        records.append({
            "name": module,
            "component": library_for_module(module, libraries),
            "source": f"Lean4/{module.replace('.', '/')}.lean",
        })
    return records


def public_page_paths(
    data: dict[str, Any],
    libraries: list[dict[str, Any]],
) -> tuple[set[Path], set[Path]]:
    """Return canonical page inventories after a case-insensitive collision check."""
    module_paths: set[str] = set()
    source_paths: set[str] = set()
    casefolded: dict[str, tuple[str, str, str]] = {}
    for record in module_records(data, libraries):
        source_relative = (
            PurePosixPath(record["source"])
            .relative_to("Lean4")
            .as_posix()
        )
        routes = (
            (
                "module",
                build_site.module_html_path(
                    record["name"],
                    record["component"],
                ),
                module_paths,
            ),
            (
                "source",
                build_site.source_html_path(
                    source_relative,
                    record["component"],
                ),
                source_paths,
            ),
        )
        for kind, route, inventory in routes:
            folded = route.casefold()
            previous = casefolded.get(folded)
            if previous is not None:
                previous_kind, previous_module, previous_route = previous
                raise DatabaseError(
                    "case-insensitive public URL collision: "
                    f"{previous_kind} {previous_module!r} -> {previous_route!r}; "
                    f"{kind} {record['name']!r} -> {route!r}"
                )
            casefolded[folded] = (kind, record["name"], route)
            inventory.add(route)
    return (
        {Path(route) for route in module_paths},
        {Path(route) for route in source_paths},
    )


def _git_output(repository: Path, *args: str, purpose: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise DatabaseError(f"cannot inspect {purpose}: {detail.strip()}") from error
    return result.stdout.strip()


def git_output(repository: Path, *args: str) -> str:
    """Return Git output for the Lean source repository."""
    return _git_output(repository, *args, purpose="Lean source repository")


def normalize_github_remote(remote: str) -> str:
    """Normalize an HTTPS or SSH GitHub remote to a host/owner/repository identity."""
    value = remote.strip().rstrip("/")
    prefixes = (
        "https://github.com/",
        "ssh://git@github.com/",
        "git@github.com:",
    )
    path = next(
        (
            value[len(prefix):]
            for prefix in prefixes
            if value.casefold().startswith(prefix)
        ),
        None,
    )
    if path is None:
        raise DatabaseError(f"unsupported GitHub origin URL: {remote!r}")
    if path.casefold().endswith(".git"):
        path = path[:-4]
    components = path.split("/")
    if (
        len(components) != 2
        or not all(components)
        or any(component in {".", ".."} for component in components)
    ):
        raise DatabaseError(f"unsupported GitHub origin URL: {remote!r}")
    return "github.com/" + "/".join(component.casefold() for component in components)


def validate_public_output_repository(output: Path) -> Path:
    """Require the exact public Pages repository root before reading or mutating it."""
    candidate = output.expanduser()
    if candidate.is_symlink():
        raise DatabaseError(f"refusing symlinked generated output target: {candidate}")
    candidate = candidate.resolve()
    if candidate == ROOT or candidate == Path(candidate.anchor):
        raise DatabaseError(f"refusing unsafe generated output target: {candidate}")
    if not candidate.is_dir():
        raise DatabaseError(
            f"public output repository was not found: {candidate}"
        )

    top_level_text = _git_output(
        candidate,
        "rev-parse",
        "--show-toplevel",
        purpose="public output repository",
    )
    top_level = Path(top_level_text).resolve()
    if top_level != candidate:
        raise DatabaseError(
            "generated output must be the public repository top-level: "
            f"{candidate} (Git top-level is {top_level})"
        )

    origin = _git_output(
        candidate,
        "remote",
        "get-url",
        "origin",
        purpose="public output repository",
    )
    if normalize_github_remote(origin) != PUBLIC_SITE_REPOSITORY_IDENTITY:
        raise DatabaseError(
            "refusing generated output repository with unexpected origin: "
            f"{origin!r}"
        )
    return candidate


def validate_lean_repository(
    repository: Path,
    modules: dict[str, Any],
    release: dict[str, Any],
    library: dict[str, Any],
) -> Path:
    repository = repository.resolve()
    if repository.is_symlink() or not repository.is_dir() or not (repository / ".git").exists():
        raise DatabaseError(
            f"{library['id']}: Lean source repository was not found: {repository}"
        )
    top_level = Path(git_output(repository, "rev-parse", "--show-toplevel")).resolve()
    if top_level != repository:
        raise DatabaseError(
            f"{library['id']}: source path is not the Git repository root: "
            f"{repository}"
        )
    origin = git_output(repository, "remote", "get-url", "origin")
    if normalize_github_remote(origin) != normalize_github_remote(
        library["repository"]
    ):
        raise DatabaseError(
            f"{library['id']}: unexpected source repository origin: {origin!r}"
        )
    head = git_output(repository, "rev-parse", "HEAD")
    if head != release["source_commit"]:
        raise DatabaseError(
            f"{library['id']}: source repository is at {head}, expected "
            f"{release['source_commit']}"
        )
    dirty = git_output(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        "Lean4",
        "lean-toolchain",
        "lakefile.toml",
    )
    if dirty:
        raise DatabaseError(
            f"{library['id']}: Lean source inputs contain uncommitted changes:\n"
            + dirty
        )
    if (
        repository.joinpath("lean-toolchain").read_text(encoding="utf-8").strip()
        != release["lean_toolchain"]
    ):
        raise DatabaseError(
            f"{library['id']}: source toolchain differs from release.json"
        )
    lakefile = (repository / "lakefile.toml").read_text(encoding="utf-8")
    if f'rev = "{release["mathlib_ref"]}"' not in lakefile:
        raise DatabaseError(
            f"{library['id']}: source mathlib revision differs from release.json"
        )

    lean_root = repository / release["source_dir"]
    if lean_root.is_symlink() or not lean_root.is_dir():
        raise DatabaseError(f"Lean source directory is missing or unsafe: {lean_root}")
    expected = {
        f"Lean4/{module.replace('.', '/')}.lean"
        for module in modules["modules"]
    }
    actual: set[str] = set()
    for path in lean_root.rglob("*.lean"):
        if path.is_symlink() or not path.is_file():
            raise DatabaseError(f"unsafe Lean source path: {path}")
        actual.add(path.relative_to(repository).as_posix())
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra or len(actual) != release["module_count"]:
        details = [
            *(f"missing {path}" for path in missing[:10]),
            *(f"unexpected {path}" for path in extra[:10]),
        ]
        raise DatabaseError(
            "Lean source inventory does not match the module manifest"
            + (": " + ", ".join(details) if details else "")
        )
    if release["module_count"] != modules["module_count"]:
        raise DatabaseError(
            f"{library['id']}: release.json and modules.json counts differ"
        )
    return lean_root


def materialize_source_tree(
    destination: Path,
    libraries: list[dict[str, Any]],
    repositories: dict[str, Path],
    modules: dict[str, Any],
    releases: dict[str, dict[str, Any]],
) -> Path:
    """Copy pinned library sources into one temporary documentation input tree."""
    destination = destination.resolve()
    if destination.exists() or destination == Path(destination.anchor):
        raise DatabaseError(
            f"refusing unsafe aggregate source destination: {destination}"
        )
    destination.mkdir(parents=True)
    copied: set[str] = set()
    for library in libraries:
        library_id = library["id"]
        manifest = modules["by_library"][library_id]
        lean_root = validate_lean_repository(
            repositories[library_id],
            manifest,
            releases[library_id],
            library,
        )
        for module in manifest["modules"]:
            relative = PurePosixPath(*module.split(".")).with_suffix(".lean")
            relative_text = relative.as_posix()
            if relative_text in copied:
                raise DatabaseError(
                    f"duplicate aggregate Lean source path: {relative_text}"
                )
            copied.add(relative_text)
            source = lean_root.joinpath(*relative.parts)
            target = destination.joinpath(*relative.parts)
            if source.is_symlink() or not source.is_file():
                raise DatabaseError(
                    f"{library_id}: missing or unsafe source file: {source}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if len(copied) != modules["module_count"]:
        raise DatabaseError("aggregate Lean source count differs from publishing data")
    return destination


def analytics(measurement_id: str | None) -> str:
    if not measurement_id:
        return ""
    value = html.escape(measurement_id, quote=True)
    return f'''    <script async src="https://www.googletagmanager.com/gtag/js?id={value}"></script>
    <script>window.dataLayer = window.dataLayer || []; function gtag() {{ dataLayer.push(arguments); }} gtag("js", new Date()); gtag("config", "{value}");</script>
'''


def home_page(data: dict[str, Any], language: str, stylesheet: str) -> str:
    page = data["pages"][language]
    other = OTHER_LANGUAGE[language]
    switch = HOME_OUTPUT[other]
    navigation: list[str] = []
    sections: list[str] = []
    for section in data["sections"]:
        section_id = html.escape(section["id"], quote=True)
        navigation.append(f'          <li><a href="#{section_id}">{html.escape(section["nav"][language])}</a></li>')
        mobile_switch = ""
        if section["id"] == "intro":
            mobile_switch = ('      <div id="additionalContent"><p><b>' + html.escape(page["mobile_switch_label"]) + f'</b> <a href="{switch}">URL</a></p></div>\n')
        sections.append(f'    <section id="{section_id}">\n      <h1>{html.escape(section["title"][language])}</h1>\n{mobile_switch}{section["body_html"][language].strip()}\n    </section>')
    verification = ""
    if page.get("site_verification"):
        verification = f'    <meta name="google-site-verification" content="{html.escape(page["site_verification"], quote=True)}">\n'
    author = f'      <p class="header_author">{page["header_author_html"]}</p>\n' if page.get("header_author_html") else ""
    sections_html = "\n\n".join(sections)
    navigation_html = "\n".join(navigation)
    return f'''<!DOCTYPE html>
<html lang="{language}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{html.escape(page["description"], quote=True)}">
{verification}    <link rel="canonical" href="{SITE_URL}/{HOME_OUTPUT[language]}"><link rel="alternate" hreflang="{other}" href="{SITE_URL}/{switch}">
    <title>{html.escape(page["title"])}</title>
{analytics(page.get("analytics_id"))}    <style>{stylesheet.rstrip()}</style>
</head><body><div id="homepage-root"><div class="header"><p class="header_words">{page["header_quote_html"]}</p>
{author}  </div><main class="container">{sections_html}</main><aside class="sidebar"><nav aria-label="Homepage sections"><ul>
{navigation_html}
          <li><a href="{switch}">{html.escape(page["switch_label"])}</a></li>
      </ul></nav></aside></div></body></html>
'''


def root_index() -> str:
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="Naganori Yamaguchi: mathematics and Lean 4 libraries."><link rel="canonical" href="https://n-yamaguchi-0729.github.io/"><title>Naganori Yamaguchi</title><style>html{font-family:system-ui,sans-serif;color:#172033;background:#f4f7fa}body{width:min(720px,calc(100% - 2rem));margin:10vh auto}main{padding:clamp(1.5rem,5vw,3rem);border:1px solid #dce2ea;border-radius:16px;background:#fff}h1{margin-top:0;font-size:clamp(2rem,7vw,3.8rem);letter-spacing:-.04em}ul{padding-left:1.2rem}li{margin:.7rem 0}a{color:#315c8c}</style></head><body><main><h1>Naganori Yamaguchi</h1><p>Mathematics and formalized mathematics in Lean 4.</p><nav aria-label="Main pages"><ul><li><a href="homepage-en.html">English homepage</a></li><li><a href="homepage-jp.html">Japanese homepage</a></li><li><a href="YamaLean4Lib_pages/">Lean 4 libraries</a></li></ul></nav></main></body></html>
'''


def repository_readme() -> str:
    return """# n-yamaguchi-0729.github.io

Public website for Naganori Yamaguchi:

- [Homepage](https://n-yamaguchi-0729.github.io/)
- [Yamaguchi Lean 4 Library](https://n-yamaguchi-0729.github.io/YamaLean4Lib_pages/)
- [ProCGroups source repository](https://github.com/n-yamaguchi-0729/ProCGroups)

Each Lean library has its own source repository. The shared documentation site
and its reproducible publisher are maintained here under `publisher/`.
"""


def repository_support_generated() -> dict[Path, str]:
    """Return the generated Git/GitHub files that support public deployment."""
    return {
        Path(".gitattributes"): "* text=auto eol=lf\n",
        Path(".github/validation/check_generated_site.py"):
            GENERATED_SITE_CHECKER.read_text(encoding="utf-8"),
        Path(".github/validation/check_public_repository.py"):
            PUBLIC_REPOSITORY_CHECKER.read_text(encoding="utf-8"),
        Path(".github/validation/public_paths.py"):
            PUBLIC_PATHS_SOURCE.read_text(encoding="utf-8"),
        Path(".github/workflows/ci.yml"):
            PUBLIC_SITE_CI_TEMPLATE.read_text(encoding="utf-8"),
        Path(".github/workflows/pages.yml"):
            PUBLIC_SITE_PAGES_TEMPLATE.read_text(encoding="utf-8"),
    }


def static_generated() -> dict[Path, str]:
    home = load_home_database()
    output: dict[Path, str] = {
        **repository_support_generated(),
        Path("index.html"): root_index(),
        Path("README.md"): repository_readme(),
    }
    stylesheet = HOME_STYLESHEET.read_text(encoding="utf-8")
    output.update({Path(HOME_OUTPUT[language]): home_page(home, language, stylesheet) for language in LANGUAGES})
    output[Path(".nojekyll")] = ""
    output[Path("googlee8a500422e0afa27.html")] = "google-site-verification: googlee8a500422e0afa27.html\n"
    output[Path("robots.txt")] = f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n"
    return output


def write_text_files(output: Path, files: dict[Path, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")


def window_json(path: Path, assignment: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    prefix = f"window.{assignment}="
    if not text.startswith(prefix) or not text.endswith(";"):
        raise DatabaseError(f"{path.name}: invalid generated JavaScript assignment")
    value = json.loads(text[len(prefix):-1])
    if not isinstance(value, list):
        raise DatabaseError(f"{path.name}: generated value must be an array")
    return value


def add_library_search_entries(
    portal_root: Path,
    libraries: list[dict[str, Any]],
) -> None:
    path = portal_root / "assets" / "search-index.js"
    entries = window_json(path, "LEAN_DOCS_INDEX")
    library_entries = [{
        "n": item["display_name"],
        "s": item["display_name"],
        "m": item["display_name"],
        "k": "Library",
        "t": " ".join([item["summary"], item["import"], *item["contents"]]),
        "u": f"index.html#library-{item['id']}",
    } for item in libraries]
    path.write_text(
        "window.LEAN_DOCS_INDEX="
        + json.dumps([*library_entries, *entries], ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
        newline="\n",
    )


def validate_generated_portal(
    portal_root: Path,
    modules: dict[str, Any],
    libraries: list[dict[str, Any]],
) -> tuple[int, int]:
    expected_modules = set(modules["modules"])
    index = window_json(portal_root / "assets" / "search-index.js", "LEAN_DOCS_INDEX")
    indexed_modules = {
        item.get("n") for item in index
        if item.get("k") == "Lean file" and isinstance(item.get("n"), str)
    }
    if indexed_modules != expected_modules:
        raise DatabaseError("generated search index differs from modules.json")

    tree = window_json(portal_root / "assets" / "tree-data.js", "LEAN_DOCS_TREE")
    tree_modules: set[str] = set()

    def collect(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            children = node.get("c")
            if isinstance(children, list):
                collect(children)
            elif isinstance(node.get("m"), str):
                tree_modules.add(node["m"])

    collect(tree)
    if tree_modules != expected_modules:
        raise DatabaseError("generated file tree differs from modules.json")

    expected_module_pages, expected_source_pages = public_page_paths(
        modules,
        libraries,
    )
    actual_module_pages = {
        path.relative_to(portal_root)
        for path in (portal_root / "library").rglob("*.html")
        if "src" not in path.relative_to(portal_root / "library").parts
    }
    actual_source_pages = {
        path.relative_to(portal_root)
        for library in libraries
        for path in (portal_root / "library" / library["id"] / "src").rglob("*.html")
    }
    actual_components = {
        path.name
        for path in (portal_root / "library").iterdir()
        if path.is_dir()
    }
    expected_components = {item["id"] for item in libraries}
    if actual_components != expected_components:
        raise DatabaseError(
            "generated library directories differ from libraries.json"
        )
    if actual_module_pages != expected_module_pages:
        raise DatabaseError("generated module-page inventory differs from modules.json")
    if actual_source_pages != expected_source_pages:
        raise DatabaseError("generated source-page inventory differs from the unified layout")
    declaration_entries = sum(1 for item in index if item.get("k") not in {"Library", "Lean file"})
    if declaration_entries == 0:
        raise DatabaseError("generated search index contains no Lean declarations")
    html_count = sum(1 for path in portal_root.rglob("*.html") if path.is_file())
    expected_html_count = 2 * len(expected_modules) + 2
    if html_count != expected_html_count:
        raise DatabaseError(
            f"generated portal has {html_count} HTML files, "
            f"expected {expected_html_count}"
        )
    return html_count, declaration_entries


def build_public_tree(
    output: Path,
    repositories: dict[str, Path],
    *,
    verbose: bool,
) -> tuple[int, int]:
    """Build the shared documentation site from pinned independent projects."""
    libraries = load_libraries_database()
    library_records = libraries["libraries"]
    modules = load_modules_database(library_records)
    exports = load_export_databases(library_records, modules)
    releases = load_release_databases(library_records, modules)
    site = libraries["site"]
    expected_ids = {library["id"] for library in library_records}
    if set(repositories) != expected_ids:
        raise DatabaseError(
            "source repository ids differ from libraries.json: "
            f"expected={sorted(expected_ids)}, found={sorted(repositories)}"
        )
    for library in library_records:
        library_id = library["id"]
        release = releases[library_id]
        if release["mathlib_ref"] != site["mathlib_version"]:
            raise DatabaseError(
                f"{library_id}: release mathlib differs from libraries.json"
            )
        if release["version"] != exports[library_id]["version"]:
            raise DatabaseError(
                f"{library_id}: release version differs from export.json"
            )
        if not release["lean_toolchain"].endswith(":" + site["lean_version"]):
            raise DatabaseError(
                f"{library_id}: release toolchain differs from libraries.json"
            )

    aggregate_root = materialize_source_tree(
        output.parent / "lean-sources",
        library_records,
        repositories,
        modules,
        releases,
    )
    owners = module_owners(modules["modules"], library_records)
    module_counts = library_module_counts(modules["modules"], library_records)
    library_metadata = [
        {
            "id": library["id"],
            "display_name": library["display_name"],
            "import": library["import"],
            "module_roots": library["module_roots"],
            "module_count": module_counts[library["id"]],
            "repository": library["repository"],
            "source_commit": releases[library["id"]]["source_commit"],
            "version": releases[library["id"]]["version"],
            "summary": library["summary"],
            "contents": library["contents"],
        }
        for library in library_records
    ]
    sole_release = (
        releases[library_records[0]["id"]]
        if len(library_records) == 1
        else None
    )
    portal_root = output / PORTAL
    build_site.generate_site(
        lean_root=aggregate_root,
        source_root=aggregate_root,
        module_components=owners,
        component_display_names={
            library["id"]: library["display_name"]
            for library in library_records
        },
        library_metadata=library_metadata,
        include_maintenance_files=False,
        out=portal_root,
        title=site["title"],
        github_repo=(
            library_records[0]["repository"]
            if sole_release is not None
            else ""
        ),
        commit=sole_release["source_commit"] if sole_release is not None else "",
        version="",
        source_ref=(
            sole_release["source_commit"]
            if sole_release is not None
            else ""
        ),
        assets_root=PORTAL_ASSETS,
        generated_at=max(
            release["generated_at"] for release in releases.values()
        ),
        lean_distribution_package="YamaLean4Lib",
        lean_distribution_toolchain=next(iter(releases.values()))[
            "lean_toolchain"
        ],
        mathlib_ref=site["mathlib_version"],
        documentation_url=f"{SITE_URL}/{PORTAL}/",
        download_mode=build_site.DOWNLOAD_MODE_NONE,
        reporter=build_site.BuildReporter(enabled=verbose),
    )
    write_text_files(output, static_generated())
    license_source = SITE_REPOSITORY / "LICENSE"
    if license_source.is_symlink() or not license_source.is_file():
        raise DatabaseError(f"website license is missing or unsafe: {license_source}")
    shutil.copy2(license_source, output / "LICENSE")
    add_library_search_entries(portal_root, library_records)
    html_count, declaration_count = validate_generated_portal(
        portal_root,
        modules,
        library_records,
    )
    subprocess.run(
        [sys.executable, str(GENERATED_SITE_CHECKER), str(portal_root)],
        cwd=ROOT,
        check=True,
    )
    (output / "sitemap.xml").write_text(
        build_site.render_public_sitemap(output, SITE_URL),
        encoding="utf-8",
        newline="\n",
    )
    subprocess.run(
        [
            sys.executable,
            str(PUBLIC_REPOSITORY_CHECKER),
            "--filesystem",
            str(output),
        ],
        cwd=ROOT,
        check=True,
    )
    return html_count, declaration_count


def inventory(
    root: Path,
    *,
    excluded_top_level: frozenset[str] = frozenset(),
) -> set[Path]:
    if root.is_symlink():
        raise DatabaseError(f"generated tree must not be a symlink: {root}")
    if not root.exists():
        return set()
    if not root.is_dir():
        raise DatabaseError(f"generated output is not a directory: {root}")
    paths: set[Path] = set()
    for child in root.iterdir():
        if child.name in excluded_top_level:
            continue
        candidates = [child] if child.is_file() or child.is_symlink() else child.rglob("*")
        for path in candidates:
            if path.is_symlink():
                raise DatabaseError(f"generated tree must not contain symlinks: {path}")
            if path.is_file():
                paths.add(path.relative_to(root))
    return paths


def compare_trees(
    expected_root: Path,
    actual_root: Path,
    preserved_top_level: frozenset[str],
) -> list[str]:
    expected = inventory(
        expected_root,
        excluded_top_level=preserved_top_level,
    )
    actual = inventory(
        actual_root,
        excluded_top_level=preserved_top_level,
    )
    problems = [
        *(f"missing {path.as_posix()}" for path in sorted(expected - actual)),
        *(f"unexpected {path.as_posix()}" for path in sorted(actual - expected)),
    ]
    for relative in sorted(expected & actual):
        if (expected_root / relative).read_bytes() != (actual_root / relative).read_bytes():
            problems.append(f"stale {relative.as_posix()}")
    return problems


def synchronize_tree(
    source: Path,
    destination: Path,
    preserved_top_level: frozenset[str],
) -> tuple[int, int]:
    source = source.resolve()
    destination = destination.resolve()
    if destination == ROOT or destination == Path(destination.anchor):
        raise DatabaseError(f"refusing unsafe generated output target: {destination}")
    source_files = inventory(
        source,
        excluded_top_level=preserved_top_level,
    )
    destination_files = inventory(
        destination,
        excluded_top_level=preserved_top_level,
    )
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for relative in sorted(source_files):
        src = source / relative
        dest = destination / relative
        if dest.exists() and dest.read_bytes() == src.read_bytes():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied += 1
    deleted = 0
    for relative in sorted(destination_files - source_files, key=lambda path: len(path.parts), reverse=True):
        (destination / relative).unlink()
        deleted += 1
    for child in destination.iterdir():
        if child.name in preserved_top_level or not child.is_dir():
            continue
        for path in sorted(
            (path for path in child.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                path.rmdir()
            except OSError:
                pass
        try:
            child.rmdir()
        except OSError:
            pass
    return copied, deleted


def synchronize_repository_support(output: Path) -> tuple[int, int]:
    """Update generated CI/deployment support without rebuilding public HTML."""
    output = validate_public_output_repository(output)
    generated = repository_support_generated()
    copied = 0
    for relative, content in sorted(generated.items()):
        destination = output / relative
        encoded = content.encode("utf-8")
        if destination.is_file() and destination.read_bytes() == encoded:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")
        copied += 1

    expected_github = {
        relative.relative_to(".github")
        for relative in generated
        if relative.parts[0] == ".github"
    }
    github_root = output / ".github"
    actual_github = inventory(github_root)
    deleted = 0
    for relative in sorted(
        actual_github - expected_github,
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        (github_root / relative).unlink()
        deleted += 1
    if github_root.is_dir():
        for directory in sorted(
            (path for path in github_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
    return copied, deleted


def library_repositories(
    libraries: list[dict[str, Any]],
    overrides: list[str],
) -> dict[str, Path]:
    """Resolve one independent source repository for every public library."""
    known = {library["id"] for library in libraries}
    repositories = {
        library_id: PROJECTS_ROOT / library_id
        for library_id in known
    }
    seen: set[str] = set()
    for override in overrides:
        library_id, separator, raw_path = override.partition("=")
        if (
            not separator
            or library_id not in known
            or library_id in seen
            or not raw_path.strip()
        ):
            raise DatabaseError(
                "--library-repository must be a unique configured ID=PATH "
                f"mapping: {override!r}"
            )
        seen.add(library_id)
        repositories[library_id] = Path(raw_path).expanduser()
    return repositories


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PUBLIC)
    parser.add_argument(
        "--library-repository",
        action="append",
        default=[],
        metavar="ID=PATH",
        help=(
            "override an independent library source repository; may be repeated "
            "(defaults to a sibling directory named after each library id)"
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument(
        "--repository-support-only",
        action="store_true",
        help="update only generated .gitattributes and .github support files",
    )
    args = parser.parse_args()
    output = validate_public_output_repository(args.output)
    if args.repository_support_only:
        copied, deleted = synchronize_repository_support(output)
        print(
            f"generated repository support in {output} "
            f"({copied} updated, {deleted} removed)"
        )
        return 0
    libraries = load_libraries_database()["libraries"]
    preserved = ALWAYS_PRESERVED_OUTPUT_TOP_LEVEL
    repositories = library_repositories(
        libraries,
        args.library_repository,
    )
    with tempfile.TemporaryDirectory(prefix="yamalean4lib-public-") as directory:
        expected = Path(directory) / "public"
        html_count, module_count = build_public_tree(
            expected,
            repositories,
            verbose=not args.check,
        )
        if args.check:
            problems = compare_trees(expected, output, preserved)
            if problems:
                shown = ", ".join(problems[:100])
                remainder = len(problems) - min(len(problems), 100)
                if remainder:
                    shown += f", ... and {remainder} more"
                print("generated-file check failed: " + shown, file=sys.stderr)
                return 1
            print(
                f"generated site is current: "
                f"{len(inventory(output, excluded_top_level=preserved))} managed files, "
                f"{html_count} Lean HTML pages, {module_count} declarations"
            )
            return 0
        output = validate_public_output_repository(output)
        copied, deleted = synchronize_tree(expected, output, preserved)
    print(
        f"generated "
        f"{len(inventory(output, excluded_top_level=preserved))} "
        f"managed public files in {output} "
        f"({copied} updated, {deleted} removed; "
        f"{html_count} Lean HTML pages, {module_count} declarations)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
