#!/usr/bin/env python3
"""Audit and, when explicitly requested, add missing Lean documentation comments.

The documentation site uses :mod:`build_site` to decide which Lean declarations
are public and which doc comment is attached to each declaration.  This tool
uses the same parser instead of maintaining a second, subtly different parser.

The default mode is a read-only dry run.  ``--write`` is required to modify
Lean sources, and ``--check`` is intended for CI: it exits unsuccessfully when
documentation gaps, inventory errors, or obvious documentation defects remain.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

GENERATOR_ROOT = Path(__file__).resolve().parents[1]
if str(GENERATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(GENERATOR_ROOT))

import build_site  # noqa: E402  (path setup above is intentional)


SCHEMA_VERSION = 1
FORBIDDEN_ABBREVIATION_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:PCG|LCFT|CES)(?![A-Za-z0-9_])"
)
PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:TODO|FIXME|TBD|XXX)\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\blorem\s+ipsum\b", re.IGNORECASE),
    re.compile(r"\bno\s+prose\s+statement\b", re.IGNORECASE),
    re.compile(r"\bdocumentation\s+(?:goes|to\s+be)\s+here\b", re.IGNORECASE),
    re.compile(r"\bfill\s+(?:this|me)\s+in\b", re.IGNORECASE),
    re.compile(r"\?{3,}"),
)
MOJIBAKE_MARKERS = (
    "\ufffd",
    "â€",
    "â€“",
    "â€”",
    "â€™",
    "Ã",
    "Â",
    "ðŸ",
    "窶",
    "竄",
)
CONTROLLED_DECL_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*(?:States\s+(?:the\s+)?(?:theorem|lemma|axiom)|"
        r"Defines\s+(?:the\s+)?(?:definition|structure|class|inductive\s+type|"
        r"opaque\s+constant)?|"
        r"Introduces\s+(?:the\s+)?abbreviation|"
        r"Declares\s+(?:the\s+)?constant|"
        r"Provides\s+(?:the\s+)?instance)\s+`([^`]+)`",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:The|This)\s+"
        r"(?:theorem|lemma|definition|abbreviation|instance|structure|class|"
        r"inductive\s+type|axiom|constant|macro)\s+`([^`]+)`",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*Documentation\s+for\s+(?:the\s+)?(?:declaration\s+)?`([^`]+)`",
        re.IGNORECASE,
    ),
)
CONTROLLED_MODULE_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*(?:This\s+)?module\s+`([^`]+)`\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*Documentation\s+for\s+(?:the\s+)?module\s+`([^`]+)`",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*Provides\s+the\s+public\s+declarations\s+in\s+the\s+"
        r"`([^`]+)`\s+Lean\s+module\b",
        re.IGNORECASE,
    ),
)
SYNTHETIC_DECL_RE = re.compile(r"^(?:inst|example|macro)_\d+$")


@dataclass(frozen=True, slots=True)
class SourceSpec:
    path: Path
    module_root: Path
    module: str


@dataclass(frozen=True, slots=True)
class AuditIssue:
    category: str
    path: str
    module: str
    line: int
    scope: str
    declaration: str
    message: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class MissingDoc:
    scope: str
    path: str
    module: str
    line: int
    declaration: str
    kind: str
    suggested_doc: str


@dataclass(frozen=True, slots=True)
class Insertion:
    line_index: int
    priority: int
    text: str


@dataclass(slots=True)
class FilePlan:
    path: Path
    module_root: Path
    module: str
    original_bytes: bytes
    updated_bytes: bytes
    missing: list[MissingDoc]

    @property
    def changed(self) -> bool:
        return self.original_bytes != self.updated_bytes


@dataclass(slots=True)
class AuditResult:
    source_root: Path
    files: list[SourceSpec]
    public_declaration_count: int
    missing: list[MissingDoc]
    issues: list[AuditIssue]
    plans: list[FilePlan]

    @property
    def changed_plans(self) -> list[FilePlan]:
        return [plan for plan in self.plans if plan.changed]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.issues


def _clean_identifier_for_doc(identifier: str) -> str:
    """Make an identifier safe inside a one-line Lean doc comment."""
    return " ".join(identifier.replace("-/", "- /").replace("`", "'").split())


def _declaration_has_stable_name(declaration: build_site.Declaration) -> bool:
    if declaration.kind == "example":
        return False
    return not SYNTHETIC_DECL_RE.fullmatch(declaration.name)


def suggested_module_doc(module: str) -> str:
    display = _clean_identifier_for_doc(module)
    return f"Provides the public declarations in the `{display}` Lean module."


def suggested_declaration_doc(declaration: build_site.Declaration) -> str:
    """Return a deliberately modest, factually safe declaration description."""
    stable_name = _declaration_has_stable_name(declaration)
    name = _clean_identifier_for_doc(declaration.name)
    named = f"`{name}`" if stable_name else ""
    kind = declaration.kind
    if kind == "theorem":
        return f"States the theorem {named}."
    if kind == "lemma":
        return f"States the lemma {named}."
    if kind == "def":
        return f"Defines {named}."
    if kind == "abbrev":
        return f"Introduces the abbreviation {named}."
    if kind == "instance":
        return f"Provides the instance {named}." if stable_name else "Provides this instance."
    if kind == "structure":
        return f"Defines the structure {named}."
    if kind == "class":
        return f"Defines the class {named}."
    if kind == "inductive":
        return f"Defines the inductive type {named}."
    if kind == "axiom":
        return f"States the axiom {named}."
    if kind == "opaque":
        return f"Defines the opaque constant {named}."
    if kind == "constant":
        return f"Declares the constant {named}."
    if kind == "macro":
        return f"Defines the macro syntax {named}." if stable_name else "Defines this macro syntax."
    if kind == "example":
        return "Records this Lean example."
    return f"Documents the declaration {named}." if stable_name else "Documents this declaration."


def _newline_for(source: str) -> str:
    without_crlf = source.replace("\r\n", "")
    if "\r\n" in source and "\n" not in without_crlf and "\r" not in without_crlf:
        return "\r\n"
    if "\n" in source:
        return "\n"
    if "\r" in source:
        return "\r"
    return os.linesep


def _module_doc_insert_index(lines: list[str], scan_lines: list[str]) -> int:
    import_lines = [
        index for index, line in enumerate(scan_lines) if build_site.IMPORT_RE.match(line)
    ]
    if import_lines:
        return import_lines[-1] + 1
    for index, line in enumerate(scan_lines):
        if line.strip():
            return index
    return len(lines)


def _declaration_doc_insert_index(lines: list[str], declaration_index: int) -> int:
    """Insert before attributes, but after any scoped ``... in`` wrapper."""
    cursor = declaration_index - 1
    if cursor >= 0 and not lines[cursor].strip():
        return declaration_index
    attribute_start = (
        build_site.attribute_block_start(lines, cursor) if cursor >= 0 else None
    )
    return attribute_start if attribute_start is not None else declaration_index


def _insert_text(
    source: str,
    insertions: Iterable[Insertion],
) -> str:
    physical_lines = source.splitlines(keepends=True)
    newline = _newline_for(source)
    grouped: dict[int, list[Insertion]] = defaultdict(list)
    for insertion in insertions:
        grouped[insertion.line_index].append(insertion)
    output: list[str] = []
    for index in range(len(physical_lines) + 1):
        for insertion in sorted(
            grouped.get(index, ()),
            key=lambda item: (item.priority, item.text),
        ):
            if output and not output[-1].endswith(("\n", "\r")):
                output.append(newline)
            output.append(insertion.text + newline)
        if index < len(physical_lines):
            output.append(physical_lines[index])
    return "".join(output)


def _normalise_doc_name(name: str) -> str:
    return name.strip().removeprefix("_root_.").replace(" ", "")


def _doc_name_matches(candidate: str, declaration: build_site.Declaration) -> bool:
    candidate = _normalise_doc_name(candidate)
    expected = {
        _normalise_doc_name(declaration.name),
        _normalise_doc_name(declaration.full_name),
    }
    return candidate in expected


def _snippet(doc: str, length: int = 180) -> str:
    compact = " ".join(doc.split())
    return compact if len(compact) <= length else compact[: length - 1] + "…"


def _has_placeholder_text(doc: str) -> bool:
    for pattern in PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(doc):
            if match.group(0).casefold() == "placeholder":
                preceding_clause = doc[max(0, match.start() - 60) : match.start()]
                if re.search(
                    r"\b(?:not|no|without)\b[^.!?\n]{0,40}$",
                    preceding_clause,
                    re.IGNORECASE,
                ):
                    continue
            return True
    return False


def _looks_like_lean_identifier(name: str) -> bool:
    """Exclude mathematical expressions that are legitimately named in prose."""
    name = _normalise_doc_name(name)
    return bool(re.fullmatch(r"[^\W\d][\w'.]*(?:\.[^\W\d][\w']*)*", name))


def quality_issues_for_doc(
    doc: str,
    *,
    path: str,
    module: str,
    line: int,
    scope: str,
    declaration: build_site.Declaration | None = None,
) -> list[AuditIssue]:
    """Find high-confidence defects without making mathematical judgements."""
    issues: list[AuditIssue] = []
    declaration_name = declaration.full_name if declaration else ""

    if _has_placeholder_text(doc):
        issues.append(
            AuditIssue(
                "placeholder",
                path,
                module,
                line,
                scope,
                declaration_name,
                "The doc comment contains obvious placeholder text.",
                _snippet(doc),
            )
        )
    marker = next((value for value in MOJIBAKE_MARKERS if value in doc), "")
    if marker:
        issues.append(
            AuditIssue(
                "mojibake",
                path,
                module,
                line,
                scope,
                declaration_name,
                f"The doc comment contains the mojibake marker {marker!r}.",
                _snippet(doc),
            )
        )
    abbreviation = FORBIDDEN_ABBREVIATION_RE.search(doc)
    if abbreviation:
        issues.append(
            AuditIssue(
                "forbidden_abbreviation",
                path,
                module,
                line,
                scope,
                declaration_name,
                (
                    f"Use the full library name instead of "
                    f"{abbreviation.group(0)!r} in public prose."
                ),
                _snippet(doc),
            )
        )

    if declaration is None:
        for pattern in CONTROLLED_MODULE_NAME_PATTERNS:
            match = pattern.search(doc)
            if (
                match
                and _looks_like_lean_identifier(match.group(1))
                and _normalise_doc_name(match.group(1)) != _normalise_doc_name(module)
            ):
                issues.append(
                    AuditIssue(
                        "mismatched_doc_name",
                        path,
                        module,
                        line,
                        scope,
                        "",
                        (
                            f"The attached module doc names {match.group(1)!r}, "
                            f"but the module is {module!r}."
                        ),
                        _snippet(doc),
                    )
                )
                break
    elif _declaration_has_stable_name(declaration):
        for pattern in CONTROLLED_DECL_NAME_PATTERNS:
            match = pattern.search(doc)
            if (
                match
                and _looks_like_lean_identifier(match.group(1))
                and not _doc_name_matches(match.group(1), declaration)
            ):
                issues.append(
                    AuditIssue(
                        "mismatched_doc_name",
                        path,
                        module,
                        line,
                        scope,
                        declaration.full_name,
                        (
                            f"The attached doc names {match.group(1)!r}, but it is "
                            f"attached to {declaration.full_name!r}."
                        ),
                        _snippet(doc),
                    )
                )
                break
    return issues


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON from {path}: {error}") from error


def _module_names_from_data(data: Any, *, label: str) -> set[str]:
    if isinstance(data, list):
        values = data
    elif isinstance(data, dict) and isinstance(data.get("modules"), list):
        values = data["modules"]
    else:
        raise ValueError(f"{label} must be a JSON list or an object with a modules list")
    names: set[str] = set()
    for value in values:
        if isinstance(value, str):
            name = value.strip()
        elif isinstance(value, dict):
            name = str(value.get("module") or value.get("name") or "").strip()
        else:
            name = ""
        if not name:
            raise ValueError(f"{label} contains an invalid module entry: {value!r}")
        names.add(name)
    return names


def load_module_allowlist(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json" or text.lstrip().startswith(("[", "{")):
        return _module_names_from_data(json.loads(text), label=str(path))
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_manifest_source(
    raw_path: str,
    *,
    source_root: Path,
    manifest_path: Path,
) -> Path:
    supplied = Path(raw_path)
    candidates: list[Path] = []
    if supplied.is_absolute():
        candidates.append(supplied)
    else:
        candidates.extend((manifest_path.parent / supplied, source_root / supplied))
        parts = supplied.parts
        if source_root.name in parts:
            root_index = parts.index(source_root.name)
            candidates.append(source_root.joinpath(*parts[root_index + 1 :]))
    resolved_candidates = [candidate.resolve() for candidate in candidates]
    for candidate in resolved_candidates:
        if candidate.exists() and _inside(candidate, source_root):
            return candidate
    safe_candidates = [candidate for candidate in resolved_candidates if _inside(candidate, source_root)]
    return safe_candidates[0] if safe_candidates else resolved_candidates[0]


def _manifest_records(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    for key in ("module_records", "files"):
        records = data.get(key)
        if isinstance(records, list) and records and all(
            isinstance(record, dict) for record in records
        ):
            if any(record.get("source") or record.get("path") for record in records):
                return records
    modules = data.get("modules")
    if isinstance(modules, list) and modules and all(
        isinstance(record, dict) for record in modules
    ):
        if any(record.get("source") or record.get("path") for record in modules):
            return modules
    return []


def _component_roots(
    source_root: Path,
    manifest_data: Any,
    manifest_path: Path | None,
) -> list[Path]:
    if not isinstance(manifest_data, dict) or not isinstance(
        manifest_data.get("layout"), dict
    ):
        return [source_root]
    assert manifest_path is not None
    roots: list[Path] = []
    for raw_path in manifest_data["layout"].values():
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("manifest layout entries must be non-empty paths")
        root = _resolve_manifest_source(
            raw_path,
            source_root=source_root,
            manifest_path=manifest_path,
        )
        if not root.is_dir() or root.is_symlink() or not _inside(root, source_root):
            raise ValueError(f"unsafe or missing component root in manifest: {root}")
        roots.append(root)
    if len(set(roots)) != len(roots):
        raise ValueError("manifest layout contains duplicate component roots")
    return sorted(roots)


def discover_sources(
    source_root: Path,
    *,
    manifest_path: Path | None = None,
    allowlist_path: Path | None = None,
    selected_modules: Iterable[str] = (),
) -> tuple[list[SourceSpec], list[AuditIssue]]:
    """Resolve public source files from a flat root and optional allowlists."""
    source_root = source_root.resolve()
    if not source_root.is_dir() or source_root.is_symlink():
        raise ValueError(f"source root must be a real directory: {source_root}")

    manifest_data: Any = None
    manifest_modules: set[str] | None = None
    if manifest_path is not None:
        manifest_path = manifest_path.resolve()
        manifest_data = _read_json(manifest_path)
        if isinstance(manifest_data, dict) and isinstance(
            manifest_data.get("modules"), list
        ):
            manifest_modules = _module_names_from_data(
                manifest_data, label=str(manifest_path)
            )

    filters: list[set[str]] = []
    if manifest_modules is not None:
        filters.append(manifest_modules)
    if allowlist_path is not None:
        filters.append(load_module_allowlist(allowlist_path.resolve()))
    explicit = {name.strip() for name in selected_modules if name.strip()}
    if explicit:
        filters.append(explicit)
    allowed = set.intersection(*filters) if filters else None

    issues: list[AuditIssue] = []
    specs: list[SourceSpec] = []
    records = _manifest_records(manifest_data)
    if records:
        assert manifest_path is not None
        for record in records:
            module = str(record.get("module") or record.get("name") or "").strip()
            raw_source = str(record.get("source") or record.get("path") or "").strip()
            if not module or not raw_source or (allowed is not None and module not in allowed):
                continue
            path = _resolve_manifest_source(
                raw_source,
                source_root=source_root,
                manifest_path=manifest_path,
            )
            if path.is_file() and path.suffix == ".lean" and not path.is_symlink():
                specs.append(SourceSpec(path, path.parent, module))
            else:
                issues.append(
                    AuditIssue(
                        "missing_module_file",
                        raw_source,
                        module,
                        0,
                        "inventory",
                        "",
                        f"The allowlisted source for {module!r} is missing or unsafe.",
                    )
                )
    else:
        roots = _component_roots(source_root, manifest_data, manifest_path)
        seen_paths: set[Path] = set()
        for module_root in roots:
            for path in sorted(module_root.rglob("*.lean")):
                relative = path.relative_to(module_root)
                if (
                    relative.name in build_site.SKIP_LEAN_FILES
                    or any(
                        part.startswith(".") or part in build_site.SKIP_LEAN_DIRS
                        for part in relative.parts
                    )
                ):
                    continue
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                module = build_site.module_name_from_path(path, module_root)
                if allowed is None or module in allowed:
                    if path.is_file() and not path.is_symlink():
                        specs.append(SourceSpec(path, module_root, module))
                    else:
                        issues.append(
                            AuditIssue(
                                "unsafe_source",
                                path.relative_to(source_root).as_posix(),
                                module,
                                0,
                                "inventory",
                                "",
                                "A selected Lean source is not a regular, non-symlink file.",
                            )
                        )

    by_module: dict[str, list[SourceSpec]] = defaultdict(list)
    for spec in specs:
        by_module[spec.module].append(spec)
    for module, matches in sorted(by_module.items()):
        if len(matches) > 1:
            issues.append(
                AuditIssue(
                    "duplicate_module",
                    ", ".join(str(match.path) for match in matches),
                    module,
                    0,
                    "inventory",
                    "",
                    f"The module {module!r} resolves to {len(matches)} source files.",
                )
            )

    found = set(by_module)
    if allowed is not None:
        for module in sorted(allowed - found):
            issues.append(
                AuditIssue(
                    "missing_module_file",
                    "",
                    module,
                    0,
                    "inventory",
                    "",
                    f"The allowlisted module {module!r} has no source file.",
                )
            )
    return sorted(specs, key=lambda spec: (spec.module, str(spec.path))), issues


def _parse_spec(spec: SourceSpec, source_root: Path) -> build_site.Module:
    parsed = build_site.parse_lean_file(
        spec.path,
        spec.module_root,
        source_root=source_root,
    )
    if parsed.name != spec.module:
        # Exact-source manifest records may intentionally supply the module name.
        parsed.name = spec.module
        for declaration in parsed.decls:
            declaration.module = spec.module
    return parsed


def audit_sources(
    source_root: Path,
    specs: Sequence[SourceSpec],
    inventory_issues: Iterable[AuditIssue] = (),
) -> AuditResult:
    source_root = source_root.resolve()
    missing: list[MissingDoc] = []
    issues = list(inventory_issues)
    plans: list[FilePlan] = []
    public_declaration_count = 0

    for spec in specs:
        relative_path = spec.path.relative_to(source_root).as_posix()
        try:
            original_bytes = spec.path.read_bytes()
            source = original_bytes.decode("utf-8")
            module = _parse_spec(spec, source_root)
        except (OSError, UnicodeError, ValueError) as error:
            issues.append(
                AuditIssue(
                    "source_parse_error",
                    relative_path,
                    spec.module,
                    0,
                    "inventory",
                    "",
                    str(error),
                )
            )
            continue

        lines = source.splitlines()
        scan_lines = build_site.stripped_code_lines_for_parsing(lines)
        insertions: list[Insertion] = []
        file_missing: list[MissingDoc] = []
        if not module.module_doc.strip():
            suggested = suggested_module_doc(module.name)
            record = MissingDoc(
                "module",
                relative_path,
                module.name,
                1,
                "",
                "module",
                suggested,
            )
            missing.append(record)
            file_missing.append(record)
            insertions.append(
                Insertion(
                    _module_doc_insert_index(lines, scan_lines),
                    0,
                    f"/-! {suggested} -/",
                )
            )
        else:
            issues.extend(
                quality_issues_for_doc(
                    module.module_doc,
                    path=relative_path,
                    module=module.name,
                    line=1,
                    scope="module",
                )
            )

        public_declaration_count += len(module.decls)
        for declaration in module.decls:
            declaration_index = declaration.line - 1
            # This explicit guard documents and enforces the public-only policy,
            # even if build_site's declaration regexp grows new modifiers.
            declaration_line = scan_lines[declaration_index]
            match = build_site.DECL_RE.match(declaration_line)
            prefix = declaration_line[: match.start("kind")] if match else ""
            if re.search(r"\b(?:private|local)\b", prefix):
                continue
            if not declaration.doc.strip():
                suggested = suggested_declaration_doc(declaration)
                record = MissingDoc(
                    "declaration",
                    relative_path,
                    module.name,
                    declaration.line,
                    declaration.full_name,
                    declaration.kind,
                    suggested,
                )
                missing.append(record)
                file_missing.append(record)
                insertions.append(
                    Insertion(
                        _declaration_doc_insert_index(lines, declaration_index),
                        1,
                        f"/-- {suggested} -/",
                    )
                )
            else:
                if build_site.attached_doc_span(lines, declaration_index) is None:
                    issues.append(
                        AuditIssue(
                            "detached_doc",
                            relative_path,
                            module.name,
                            declaration.line,
                            "declaration",
                            declaration.full_name,
                            "The parser returned a doc with no attached /-- ... -/ span.",
                            _snippet(declaration.doc),
                        )
                    )
                issues.extend(
                    quality_issues_for_doc(
                        declaration.doc,
                        path=relative_path,
                        module=module.name,
                        line=declaration.line,
                        scope="declaration",
                        declaration=declaration,
                    )
                )

        updated_source = _insert_text(source, insertions)
        plans.append(
            FilePlan(
                spec.path,
                spec.module_root,
                module.name,
                original_bytes,
                updated_source.encode("utf-8"),
                file_missing,
            )
        )

    return AuditResult(
        source_root,
        list(specs),
        public_declaration_count,
        sorted(
            missing,
            key=lambda item: (item.path, item.line, item.scope, item.declaration),
        ),
        sorted(
            issues,
            key=lambda item: (
                item.category,
                item.path,
                item.line,
                item.declaration,
            ),
        ),
        plans,
    )


def write_plans(plans: Iterable[FilePlan]) -> list[str]:
    """Atomically apply planned insertions, refusing stale source contents."""
    changed: list[str] = []
    for plan in sorted(plans, key=lambda item: str(item.path)):
        if not plan.changed:
            continue
        current = plan.path.read_bytes()
        if current != plan.original_bytes:
            raise RuntimeError(f"source changed during audit; refusing to write {plan.path}")
        stat_result = plan.path.stat()
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{plan.path.name}.doc-audit-",
            dir=plan.path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(plan.updated_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_path, stat_result.st_mode)
            os.replace(temporary_path, plan.path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        changed.append(str(plan.path))
    return changed


def result_payload(
    result: AuditResult,
    *,
    mode: str,
    changed_files: Iterable[str] = (),
    planned_missing: Iterable[MissingDoc] | None = None,
) -> dict[str, Any]:
    planned = list(planned_missing if planned_missing is not None else result.missing)
    categories = Counter(issue.category for issue in result.issues)
    missing_modules = sum(item.scope == "module" for item in result.missing)
    missing_declarations = sum(item.scope == "declaration" for item in result.missing)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "source_root": str(result.source_root),
        "ok": result.ok,
        "summary": {
            "files": len(result.files),
            "public_declarations": result.public_declaration_count,
            "missing_module_docs": missing_modules,
            "missing_declaration_docs": missing_declarations,
            "quality_or_inventory_issues": len(result.issues),
            "would_change_files": len(result.changed_plans),
            "planned_insertions": len(planned),
        },
        "issue_categories": dict(sorted(categories.items())),
        "missing": [asdict(item) for item in result.missing],
        "issues": [asdict(item) for item in result.issues],
        "changed_files": sorted(changed_files),
    }


def text_report(payload: dict[str, Any], *, max_examples: int = 20) -> str:
    summary = payload["summary"]
    lines = [
        "Lean documentation audit",
        f"Mode: {payload['mode']}",
        f"Source root: {payload['source_root']}",
        f"Files: {summary['files']}",
        f"Public declarations: {summary['public_declarations']}",
        f"Missing module docs: {summary['missing_module_docs']}",
        f"Missing declaration docs: {summary['missing_declaration_docs']}",
        f"Quality/inventory issues: {summary['quality_or_inventory_issues']}",
        f"Files that would change: {summary['would_change_files']}",
    ]
    if payload["issue_categories"]:
        lines.append("Issue categories:")
        lines.extend(
            f"  {category}: {count}"
            for category, count in payload["issue_categories"].items()
        )
    examples = [*payload["issues"], *payload["missing"]][:max_examples]
    if examples:
        lines.append("Examples:")
        for item in examples:
            label = item.get("category") or f"missing_{item['scope']}_doc"
            location = item.get("path", "")
            if item.get("line"):
                location += f":{item['line']}"
            detail = (
                item.get("message")
                or item.get("declaration")
                or item.get("module")
            )
            lines.append(f"  [{label}] {location}: {detail}")
        total = len(payload["issues"]) + len(payload["missing"])
        if total > len(examples):
            lines.append(f"  ... {total - len(examples)} more; use JSON for the full report")
    lines.append("Status: clean" if payload["ok"] else "Status: documentation work remains")
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Flat root containing the selected Lean source tree.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Optional JSON manifest. A modules list acts as an allowlist; an "
            "optional layout object identifies module roots below source-root."
        ),
    )
    parser.add_argument(
        "--module-allowlist",
        type=Path,
        help="Optional JSON modules list or newline-delimited module allowlist.",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help="Select one module exactly; repeat to select several modules.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="Explicitly insert missing docs. Without this flag the tool is read-only.",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Read-only CI mode; exit 1 when any gap or issue remains.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Console report format (default: text).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Also write the complete JSON report to this path.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=20,
        help="Maximum issue examples in the text report.",
    )
    return parser


def run(arguments: argparse.Namespace) -> tuple[dict[str, Any], int]:
    source_root = arguments.source_root.resolve()
    specs, inventory_issues = discover_sources(
        source_root,
        manifest_path=arguments.manifest,
        allowlist_path=arguments.module_allowlist,
        selected_modules=arguments.module,
    )
    initial = audit_sources(source_root, specs, inventory_issues)
    mode = "write" if arguments.write else "check" if arguments.check else "dry-run"
    changed_files: list[str] = []
    result = initial
    if arguments.write:
        changed_files = write_plans(initial.plans)
        # Reparse the actual files. This proves that every inserted comment is
        # attached according to build_site and makes --write idempotence visible.
        specs, inventory_issues = discover_sources(
            source_root,
            manifest_path=arguments.manifest,
            allowlist_path=arguments.module_allowlist,
            selected_modules=arguments.module,
        )
        result = audit_sources(source_root, specs, inventory_issues)
    payload = result_payload(
        result,
        mode=mode,
        changed_files=changed_files,
        planned_missing=initial.missing,
    )
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    exit_code = 1 if (arguments.check or arguments.write) and not result.ok else 0
    return payload, exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    try:
        payload, exit_code = run(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    if arguments.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text_report(payload, max_examples=max(0, arguments.max_examples)))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
