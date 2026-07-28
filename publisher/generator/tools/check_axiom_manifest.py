#!/usr/bin/env python3
"""Check the generated project-local axiom manifest and import boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


AXIOM_RE = re.compile(
    r"^\s*(?:@\[[^\]\n]*\]\s*)*"
    r"(?:(?:private|protected|noncomputable|partial|unsafe|scoped)\s+)*"
    r"axiom\s+([^\s(:]+)",
    re.MULTILINE,
)
IMPORT_RE = re.compile(r"^\s*import\s+([^\s]+)", re.MULTILINE)


def lean_code_without_comments(source: str) -> str:
    """Erase nested Lean comments and strings while preserving line numbers."""
    output: list[str] = []
    index = 0
    block_depth = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if block_depth:
            if char == "/" and following == "-":
                block_depth += 1
                output.extend((" ", " "))
                index += 2
                continue
            if char == "-" and following == "/":
                block_depth -= 1
                output.extend((" ", " "))
                index += 2
                continue
            output.append("\n" if char == "\n" else " ")
            index += 1
            continue
        if in_string:
            output.append("\n" if char == "\n" else " ")
            if char == "\\" and not escaped:
                escaped = True
            else:
                if char == '"' and not escaped:
                    in_string = False
                escaped = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(" ")
            index += 1
            continue
        if char == "-" and following == "-":
            while index < len(source) and source[index] != "\n":
                output.append(" ")
                index += 1
            continue
        if char == "/" and following == "-":
            block_depth = 1
            output.extend((" ", " "))
            index += 2
            continue
        output.append(char)
        index += 1
    return "".join(output)


def module_name(path: Path, lean_root: Path) -> str:
    return ".".join(path.relative_to(lean_root).with_suffix("").parts)


def scan_axioms(lean_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(lean_root.rglob("*.lean")):
        source = path.read_text(encoding="utf-8")
        code = lean_code_without_comments(source)
        module = module_name(path, lean_root)
        for match in AXIOM_RE.finditer(code):
            rows.append({
                "module": module,
                "name": match.group(1).strip("`"),
                "path": path.relative_to(lean_root).as_posix(),
                "line": source.count("\n", 0, match.start(1)) + 1,
                "boundary": "opt-in",
            })
    return sorted(rows, key=lambda row: (row["module"], row["name"], row["line"]))


def source_imports(source: str) -> set[str]:
    return {
        match.group(1) for match in IMPORT_RE.finditer(lean_code_without_comments(source))
    }


def local_import_graph(lean_root: Path) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for path in sorted(lean_root.rglob("*.lean")):
        graph[module_name(path, lean_root)] = source_imports(path.read_text(encoding="utf-8"))
    return graph


def reachable_local_modules(
    graph: dict[str, set[str]], seeds: set[str]
) -> tuple[set[str], dict[str, str]]:
    reached: set[str] = set()
    parent: dict[str, str] = {}
    pending = sorted(seeds, reverse=True)
    while pending:
        module = pending.pop()
        if module in reached or module not in graph:
            continue
        reached.add(module)
        for imported in sorted(graph[module], reverse=True):
            if imported in graph and imported not in reached:
                parent.setdefault(imported, module)
                pending.append(imported)
    return reached, parent


def import_chain(parent: dict[str, str], target: str) -> str:
    chain = [target]
    while chain[-1] in parent:
        chain.append(parent[chain[-1]])
    return " -> ".join(reversed(chain))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    lean_root = root / "Lean4"
    manifest_path = (args.manifest or root / "axiom-manifest.json").resolve()
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"ERROR: cannot read {manifest_path}: {error}", file=sys.stderr)
        return 2

    if manifest.get("schemaVersion") != 1:
        errors.append("unsupported or missing manifest schemaVersion")
    source_commit = str(manifest.get("sourceCommit") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        errors.append("sourceCommit is not a lowercase full Git SHA")

    actual = scan_axioms(lean_root)
    expected = manifest.get("projectLocalAxioms")
    if expected != actual:
        errors.append("projectLocalAxioms does not match Lean source")
    opt_in_modules = set(manifest.get("optInModules") or [])
    for row in actual:
        if row["module"] not in opt_in_modules:
            errors.append(
                f'axiom outside opt-in module: {row["module"]}.{row["name"]}'
            )
    stable_root = str(manifest.get("stableRoot") or "")
    stable_path = root / f"{stable_root}.lean"
    if not stable_root or not stable_path.is_file():
        errors.append("stable root is missing")
    else:
        stable_source = stable_path.read_text(encoding="utf-8")
        direct_stable_imports = source_imports(stable_source)
        manifest_stable_modules = set(manifest.get("stableModules") or [])
        if direct_stable_imports != manifest_stable_modules:
            errors.append(
                "stableModules does not match the stable root imports: "
                f"root={sorted(direct_stable_imports)}, manifest={sorted(manifest_stable_modules)}"
            )
        graph = local_import_graph(lean_root)
        manifest_stable_modules = set(manifest.get("stableModules") or [])
        paper_modules = set(manifest.get("paperModules") or [])
        for label, declared in (
            ("stableModules", manifest_stable_modules),
            ("optInModules", opt_in_modules),
            ("paperModules", paper_modules),
        ):
            for module in sorted(declared - graph.keys()):
                errors.append(f"{label} names missing local module: {module}")
        reached, parent = reachable_local_modules(graph, direct_stable_imports)
        for module in sorted(opt_in_modules.intersection(reached)):
            errors.append(
                f"stable import closure reaches opt-in module {module}: "
                f"{import_chain(parent, module)}"
            )
        axiom_modules = {str(row.get("module") or "") for row in actual}
        for module in sorted(axiom_modules.intersection(reached)):
            errors.append(
                f"stable import closure reaches axiom-bearing module {module}: "
                f"{import_chain(parent, module)}"
            )
        for module in sorted(paper_modules.intersection(reached)):
            errors.append(
                f"stable import closure reaches paper module {module}: "
                f"{import_chain(parent, module)}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"Axiom manifest checks passed: {len(actual)} project-local axiom(s), "
        f"all behind {len(opt_in_modules)} opt-in module(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
