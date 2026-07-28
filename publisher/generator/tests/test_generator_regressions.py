from __future__ import annotations

import html
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import build_site
import generate


REPOSITORY_ROOT = Path(build_site.__file__).resolve().parent


def load_tool(name: str):
    path = REPOSITORY_ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_site_manifest(root: Path, manifest_name: str = ".site-manifest.json") -> None:
    files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    files.add(manifest_name)
    (root / manifest_name).write_text(
        json.dumps(
            {"version": 1, "generated_at": "2026-07-22T00:00:00Z", "file_count": len(files), "files": sorted(files)}
        ),
        encoding="utf-8",
    )


def make_symlink_or_skip(
    test: unittest.TestCase, link: Path, target: Path, *, directory: bool = False
) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (NotImplementedError, OSError) as error:
        test.skipTest(f"symlinks are unavailable on this filesystem: {error}")


class LeanParserRegressionTests(unittest.TestCase):
    def test_nested_comments_strings_and_sections_do_not_create_or_lose_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "import Actual\n"
                "namespace Demo\n"
                "section\n"
                "def before : Nat := 1\n"
                "end\n"
                "def text : String := \"line one\n"
                "theorem phantomInString : False\n"
                "import PhantomInString\"\n"
                "/- outer comment\n"
                "  /- theorem phantomNested : False -/\n"
                "  theorem phantomOuter : False\n"
                "-/\n"
                "theorem after : True := by trivial\n"
                "end Demo\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)

            self.assertEqual(module.imports, ["Actual"])
            self.assertEqual(
                [declaration.full_name for declaration in module.decls],
                ["Demo.before", "Demo.text", "Demo.after"],
            )

    def test_mutual_end_does_not_pop_the_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "namespace Demo\n"
                "mutual\n"
                "def left : Nat := 0\n"
                "def right : Nat := left\n"
                "end\n"
                "def after : Nat := right\n"
                "end Demo\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)

            self.assertEqual(
                [declaration.full_name for declaration in module.decls],
                ["Demo.left", "Demo.right", "Demo.after"],
            )

    def test_private_declarations_are_not_published_as_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "namespace Demo\n"
                "private theorem internal : True := by trivial\n"
                "/-- Public theorem. -/\n"
                "theorem visible : True := by trivial\n"
                "end Demo\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)

            self.assertEqual(
                [declaration.full_name for declaration in module.decls],
                ["Demo.visible"],
            )

    def test_multiline_names_priority_instances_and_macros_keep_real_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "namespace Demo\n"
                "theorem\n"
                "    multilineName : True := by trivial\n"
                "noncomputable instance (priority := 100) MonoidHom.namedInstance : "
                "Inhabited Nat := inferInstance\n"
                'macro "demo_tactic!" : tactic => `(tactic| trivial)\n'
                "end Demo\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)

            self.assertEqual(
                [declaration.full_name for declaration in module.decls],
                [
                    "Demo.multilineName",
                    "Demo.MonoidHom.namedInstance",
                    "Demo.demo_tactic!",
                ],
            )

    def test_noncomputable_section_and_top_level_commands_preserve_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "namespace Demo\n"
                "noncomputable section\n"
                "/-- First declaration. -/\n"
                "def first : Nat := 1\n"
                "@[simp]\n"
                "theorem second : True := by trivial\n"
                "@[reducible] noncomputable local instance : Inhabited Nat := inferInstance\n"
                "private noncomputable local instance : Inhabited Nat := inferInstance\n"
                "/-! A section heading, not declaration documentation. -/\n"
                "theorem third : True := by trivial\n"
                "end\n"
                "def after : Nat := 2\n"
                "end Demo\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)
            by_name = {declaration.full_name: declaration for declaration in module.decls}

            self.assertEqual(
                list(by_name),
                ["Demo.first", "Demo.second", "Demo.third", "Demo.after"],
            )
            self.assertEqual(by_name["Demo.first"].code, "def first : Nat := 1")
            self.assertEqual(
                by_name["Demo.second"].code,
                "@[simp]\ntheorem second : True := by trivial",
            )
            self.assertNotIn("local instance", by_name["Demo.second"].code)
            self.assertEqual(by_name["Demo.third"].doc, "")

    def test_scoped_wrappers_and_attributes_are_kept_in_declaration_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "namespace Demo\n"
                "omit [Inhabited Nat] in\n"
                "/-- Wrapped theorem. -/\n"
                "@[simp]\n"
                "theorem wrapped : True := by trivial\n"
                "end Demo\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)
            declaration = module.decls[0]

            self.assertEqual(declaration.line, 5)
            self.assertEqual(declaration.doc, "Wrapped theorem.")
            self.assertEqual(
                declaration.code,
                "omit [Inhabited Nat] in\n"
                "@[simp]\n"
                "theorem wrapped : True := by trivial",
            )

    def test_multiline_scoped_wrapper_is_kept_in_declaration_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "namespace Demo\n"
                "omit [Inhabited Nat]\n"
                "    [DecidableEq Nat] in\n"
                "/-- Wrapped theorem. -/\n"
                "theorem wrapped : True := by trivial\n"
                "end Demo\n",
                encoding="utf-8",
            )

            declaration = build_site.parse_lean_file(source, root).decls[0]

            self.assertEqual(
                declaration.code,
                "omit [Inhabited Nat]\n"
                "    [DecidableEq Nat] in\n"
                "theorem wrapped : True := by trivial",
            )

    def test_mid_file_section_heading_is_not_a_module_or_declaration_doc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Demo.lean"
            source.write_text(
                "/-- First declaration. -/\n"
                "def first : Nat := 1\n"
                "/-! ### Later section -/\n"
                "theorem second : True := by trivial\n",
                encoding="utf-8",
            )

            module = build_site.parse_lean_file(source, root)

            self.assertEqual(module.module_doc, "")
            self.assertEqual(module.decls[1].doc, "")

    def test_anonymous_examples_are_namespaced_by_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "First.lean"
            second = root / "Second.lean"
            for path in (first, second):
                path.write_text(
                    "namespace Demo\n\nexample : True := by trivial\nend Demo\n",
                    encoding="utf-8",
                )

            modules = [
                build_site.parse_lean_file(first, root),
                build_site.parse_lean_file(second, root),
            ]
            lookup = build_site.declaration_lookup(modules)

            self.assertEqual(
                set(lookup),
                {"First.example_3", "Second.example_3"},
            )

    def test_prepare_modules_uses_lean_doc_comments_as_natural_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ProCGroups.lean").write_text(
                "/-!\n"
                "# Demo\n\n"
                "This module exposes the demonstration API.\n\n"
                "Its declarations are documented in Lean source.\n"
                "-/\n"
                "namespace Demo\n"
                "/-- Every natural number equals itself. -/\n"
                "theorem self_eq (n : Nat) : n = n := by rfl\n"
                "end Demo\n",
                encoding="utf-8",
            )

            modules, _ = build_site.prepare_modules(root, fixed_updated_at=1)

            self.assertEqual(
                modules[0].natural,
                {
                    "summary": "This module exposes the demonstration API.",
                    "statement": (
                        "This module exposes the demonstration API.\n\n"
                        "Its declarations are documented in Lean source."
                    ),
                },
            )
            self.assertEqual(
                modules[0].decls[0].natural,
                {"statement": "Every natural number equals itself."},
            )


class ComponentSourceRegressionTests(unittest.TestCase):
    def test_explicit_mapping_selects_any_flat_manifest_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory) / "Lean4"
            path = source_root / "AbstractClassFieldTheory" / "Demo.lean"
            path.parent.mkdir(parents=True)
            path.write_text(
                "/-! Demonstration module. -/\n"
                "/-- Demonstration definition. -/\n"
                "def value : Nat := 1\n",
                encoding="utf-8",
            )

            modules, _ = build_site.prepare_modules(
                source_root,
                module_components={
                    "AbstractClassFieldTheory.Demo": "LocalClassFieldTheory"
                },
                fixed_updated_at=1,
            )

            self.assertEqual(
                [
                    (module.name, module.component, module.source_component_prefix)
                    for module in modules
                ],
                [
                    (
                        "AbstractClassFieldTheory.Demo",
                        "LocalClassFieldTheory",
                        None,
                    )
                ],
            )

    def test_flat_sources_strip_one_matching_public_library_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "Lean4"
            module_path = source_root / "ProCGroups" / "Demo.lean"
            module_path.parent.mkdir(parents=True)
            module_path.write_text(
                "/-! Demonstration module. -/\n"
                "namespace ProCGroups\n"
                "/-- Demonstration theorem. -/\n"
                "theorem demo : True := by trivial\n"
                "end ProCGroups\n",
                encoding="utf-8",
            )
            assets = root / "assets"
            assets.mkdir()
            (assets / "site.css").write_text("", encoding="utf-8")
            (assets / "site.js").write_text("", encoding="utf-8")
            output = root / "site"
            commit = "a" * 40
            metadata = [{
                "id": "ProCGroups",
                "display_name": "Pro-C Groups",
                "import": "ProCGroups",
                "module_roots": ["ProCGroups"],
                "module_count": 1,
            }]

            build_site.generate_site(
                source_root,
                output,
                "Demo",
                github_repo="https://github.com/example/library",
                commit=commit,
                source_ref=commit,
                assets_root=assets,
                generated_at="2026-07-25T00:00:00Z",
                module_components={"ProCGroups.Demo": "ProCGroups"},
                component_display_names={"ProCGroups": "Pro-C Groups"},
                library_metadata=metadata,
                download_mode=build_site.DOWNLOAD_MODE_NONE,
                include_maintenance_files=False,
            )

            self.assertTrue(
                (
                    output
                    / "library"
                    / "ProCGroups"
                    / "src"
                    / "Demo.html"
                ).is_file()
            )
            self.assertTrue(
                (
                    output
                    / "library"
                    / "ProCGroups"
                    / "Demo.html"
                ).is_file()
            )
            self.assertFalse(
                (
                    output
                    / "library"
                    / "ProCGroups"
                    / "ProCGroups"
                    / "Demo.html"
                ).exists()
            )
            self.assertFalse((output / "README.md").exists())
            self.assertFalse((output / ".site-manifest.json").exists())
            info = json.loads((output / "build-info.json").read_text(encoding="utf-8"))
            self.assertEqual(info["libraries"], metadata)

    def test_component_relative_module_names_keep_component_source_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory) / "Lean4"
            group_library = source_root / "GroupTheoryLibrary"
            class_field_library = source_root / "ClassFieldTheoryLibrary"
            (group_library / "ProCGroups").mkdir(parents=True)
            (class_field_library / "LocalClassFieldTheory").mkdir(parents=True)
            (group_library / "ProCGroups" / "Demo.lean").write_text(
                "namespace ProCGroups\n"
                "def demo : Nat := 1\n"
                "end ProCGroups\n",
                encoding="utf-8",
            )
            (class_field_library / "LocalClassFieldTheory" / "Demo.lean").write_text(
                "namespace LocalClassFieldTheory\n"
                "def demo : Nat := 1\n"
                "end LocalClassFieldTheory\n",
                encoding="utf-8",
            )

            modules, _ = build_site.prepare_modules(
                None,
                source_root=source_root,
                component_dirs=(group_library, class_field_library),
                fixed_updated_at=1,
            )

            self.assertEqual(
                [
                    (module.name, module.rel_path, module.component)
                    for module in modules
                ],
                [
                    (
                        "LocalClassFieldTheory.Demo",
                        "ClassFieldTheoryLibrary/LocalClassFieldTheory/Demo.lean",
                        "ClassFieldTheoryLibrary",
                    ),
                    (
                        "ProCGroups.Demo",
                        "GroupTheoryLibrary/ProCGroups/Demo.lean",
                        "GroupTheoryLibrary",
                    ),
                ],
            )

    def test_duplicate_module_names_across_components_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory) / "Lean4"
            first = source_root / "FirstLibrary"
            second = source_root / "SecondLibrary"
            first.mkdir(parents=True)
            second.mkdir()
            (first / "Demo.lean").write_text("def first : Nat := 1\n", encoding="utf-8")
            (second / "Demo.lean").write_text("def second : Nat := 2\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicate Lean module name 'Demo'"):
                build_site.prepare_modules(
                    None,
                    source_root=source_root,
                    component_dirs=(first, second),
                    fixed_updated_at=1,
                )

    def test_no_download_mode_generates_only_documentation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "Lean4"
            component = source_root / "GroupTheoryLibrary"
            module_path = component / "ProCGroups" / "Demo.lean"
            module_path.parent.mkdir(parents=True)
            module_path.write_text(
                "/-! Demonstration module. -/\n"
                "namespace ProCGroups\n"
                "/-- Demonstration theorem. -/\n"
                "theorem demo : True := by trivial\n"
                "end ProCGroups\n",
                encoding="utf-8",
            )
            assets = root / "assets"
            assets.mkdir()
            (assets / "site.css").write_text("", encoding="utf-8")
            (assets / "site.js").write_text("", encoding="utf-8")
            output = root / "site"
            commit = "a" * 40

            build_site.generate_site(
                None,
                output,
                "Demo",
                github_repo="https://github.com/example/library",
                commit=commit,
                source_ref=commit,
                assets_root=assets,
                generated_at="2026-07-25T00:00:00Z",
                component_dirs=(component,),
                source_root=source_root,
                download_mode=build_site.DOWNLOAD_MODE_NONE,
            )

            self.assertFalse((output / "download").exists())
            module = (
                output
                / "library"
                / "GroupTheoryLibrary"
                / "module-roots"
                / "ProCGroups"
                / "Demo.html"
            ).read_text(encoding="utf-8")
            self.assertNotIn("/blob/", module)
            self.assertNotIn('class="source-link"', module)
            self.assertNotIn("Open this file on GitHub", module)
            self.assertIn('id="toggle_all_proofs"', module)
            self.assertIn('aria-pressed="false"', module)
            self.assertTrue(
                (
                    output
                    / "library"
                    / "GroupTheoryLibrary"
                    / "src"
                    / "module-roots"
                    / "ProCGroups"
                    / "Demo.html"
                ).is_file()
            )

    def test_component_layout_cannot_use_the_flat_distribution_zip_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_root = Path(directory) / "Lean4"
            component = source_root / "ProCGroups"
            component.mkdir(parents=True)

            with self.assertRaisesRegex(
                ValueError, "component directories require github-archive"
            ):
                build_site.generate_site(
                    None,
                    Path(directory) / "site",
                    "Demo",
                    component_dirs=(component,),
                    source_root=source_root,
                    download_mode=build_site.DOWNLOAD_MODE_DISTRIBUTION,
                )


class PublicPathRegressionTests(unittest.TestCase):
    def test_formal_library_ids_are_not_duplicated_in_public_urls(self) -> None:
        cases = (
            (
                "ProCGroups",
                "ProCGroups",
                "library/ProCGroups/root-module.html",
                "library/ProCGroups/src/root-module.html",
            ),
            (
                "LocalClassFieldTheory.All",
                "LocalClassFieldTheory",
                "library/LocalClassFieldTheory/All.html",
                "library/LocalClassFieldTheory/src/All.html",
            ),
            (
                "CrowellExactSequence",
                "CrowellExactSequence",
                "library/CrowellExactSequence/root-module.html",
                "library/CrowellExactSequence/src/root-module.html",
            ),
            (
                "ExampleLibrary",
                "ExampleLibrary",
                "library/ExampleLibrary/root-module.html",
                "library/ExampleLibrary/src/root-module.html",
            ),
        )
        for module, component, module_url, source_url in cases:
            with self.subTest(module=module):
                self.assertEqual(
                    build_site.module_html_path(module, component),
                    module_url,
                )
                self.assertEqual(
                    build_site.source_html_path(
                        module.replace(".", "/") + ".lean",
                        component,
                    ),
                    source_url,
                )

    def test_only_one_matching_prefix_is_removed(self) -> None:
        self.assertEqual(
            build_site.module_html_path(
                "LocalClassFieldTheory.LocalClassFieldTheory.All",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/LocalClassFieldTheory/All.html",
        )
        self.assertEqual(
            build_site.source_html_path(
                "LocalClassFieldTheory/LocalClassFieldTheory/All.lean",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/src/LocalClassFieldTheory/All.html",
        )

    def test_nonmatching_owned_module_keeps_its_namespace_path(self) -> None:
        self.assertEqual(
            build_site.module_html_path(
                "AbstractClassFieldTheory.Reciprocity",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/module-roots/AbstractClassFieldTheory/Reciprocity.html",
        )
        self.assertEqual(
            build_site.source_html_path(
                "AbstractClassFieldTheory/Reciprocity.lean",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/src/module-roots/AbstractClassFieldTheory/Reciprocity.html",
        )

    def test_owned_top_level_root_does_not_collide_with_stripped_facade(self) -> None:
        self.assertEqual(
            build_site.module_html_path(
                "LocalClassFieldTheory.LubinTate",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/LubinTate.html",
        )
        self.assertEqual(
            build_site.module_html_path(
                "LubinTate",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/module-roots/LubinTate.html",
        )
        self.assertEqual(
            build_site.source_html_path(
                "LocalClassFieldTheory/LubinTate.lean",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/src/LubinTate.html",
        )
        self.assertEqual(
            build_site.source_html_path(
                "LubinTate.lean",
                "LocalClassFieldTheory",
            ),
            "library/LocalClassFieldTheory/src/module-roots/LubinTate.html",
        )

    def test_generated_three_libraries_and_future_library_share_canonical_routes(self) -> None:
        checker = load_tool("check_generated_site")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lean_root = root / "Lean4"
            sources = {
                "ProCGroups": lean_root / "ProCGroups.lean",
                "LocalClassFieldTheory.All": (
                    lean_root / "LocalClassFieldTheory" / "All.lean"
                ),
                "CrowellExactSequence": lean_root / "CrowellExactSequence.lean",
                "ExampleLibrary": lean_root / "ExampleLibrary.lean",
            }
            for index, (module, path) in enumerate(sources.items(), start=1):
                path.parent.mkdir(parents=True, exist_ok=True)
                namespace = module.split(".", 1)[0]
                path.write_text(
                    f"/-! Documentation for {module}. -/\n"
                    f"namespace {namespace}\n"
                    f"/-- Public value for {module}. -/\n"
                    f"def value{index} : Nat := {index}\n"
                    f"end {namespace}\n",
                    encoding="utf-8",
                )

            library_records = [
                {
                    "id": "ProCGroups",
                    "display_name": "Pro-C Groups",
                    "repository": "https://github.com/example/library",
                    "import": "ProCGroups",
                    "module_roots": ["ProCGroups"],
                    "summary": "Pro-C group theory.",
                    "contents": ["Pro-C groups"],
                },
                {
                    "id": "LocalClassFieldTheory",
                    "display_name": "Local Class Field Theory",
                    "repository": "https://github.com/example/library",
                    "import": "LocalClassFieldTheory.All",
                    "module_roots": ["LocalClassFieldTheory"],
                    "summary": "Local class field theory.",
                    "contents": ["Local fields"],
                },
                {
                    "id": "CrowellExactSequence",
                    "display_name": "Crowell Exact Sequences",
                    "repository": "https://github.com/example/library",
                    "import": "CrowellExactSequence",
                    "module_roots": ["CrowellExactSequence"],
                    "summary": "Crowell exact sequences.",
                    "contents": ["Exact sequences"],
                },
                {
                    "id": "ExampleLibrary",
                    "display_name": "Example Library",
                    "repository": "https://github.com/example/library",
                    "import": "ExampleLibrary",
                    "module_roots": ["ExampleLibrary"],
                    "summary": "A future library.",
                    "contents": ["Example content"],
                },
            ]
            owners = {
                record["import"]: record["id"] for record in library_records
            }
            metadata = [
                {
                    "id": record["id"],
                    "display_name": record["display_name"],
                    "import": record["import"],
                    "module_roots": record["module_roots"],
                    "module_count": 1,
                }
                for record in library_records
            ]
            assets = root / "assets-source"
            assets.mkdir()
            (assets / "site.css").write_text("", encoding="utf-8")
            (assets / "site.js").write_text("", encoding="utf-8")
            output = root / "site"
            sha = "a" * 40

            build_site.generate_site(
                lean_root,
                output,
                "Lean 4 libraries",
                github_repo="https://github.com/example/library",
                commit=sha,
                source_ref=sha,
                assets_root=assets,
                generated_at="2026-07-26T00:00:00Z",
                module_components=owners,
                component_display_names={
                    record["id"]: record["display_name"]
                    for record in library_records
                },
                library_metadata=metadata,
                download_mode=build_site.DOWNLOAD_MODE_NONE,
                include_maintenance_files=False,
            )
            generate.add_library_search_entries(output, library_records)
            (output / "index.html").write_text(
                "<h1>Lean 4 libraries</h1>"
                + "".join(
                    f'<section id="library-{record["id"]}">'
                    f'<h2>{record["display_name"]}</h2></section>'
                    for record in library_records
                ),
                encoding="utf-8",
            )

            module_data = {
                "module_count": len(sources),
                "modules": list(sources),
            }
            html_count, declaration_count = generate.validate_generated_portal(
                output,
                module_data,
                library_records,
            )
            self.assertEqual((html_count, declaration_count), (10, 4))
            self.assertEqual(checker.check_root(output), [])
            self.assertEqual(checker.check_public_artifacts(output), [])

            expected_pages = {
                build_site.module_html_path(module, owners[module])
                for module in sources
            }
            expected_sources = {
                build_site.source_html_path(
                    module.replace(".", "/") + ".lean",
                    owners[module],
                )
                for module in sources
            }
            for relative in expected_pages | expected_sources:
                self.assertTrue((output / Path(relative)).is_file(), relative)
            self.assertFalse(
                (
                    output
                    / "library"
                    / "LocalClassFieldTheory"
                    / "LocalClassFieldTheory"
                    / "All.html"
                ).exists()
            )
            sitemap = build_site.render_public_sitemap(
                output,
                "https://example.com/docs",
            )
            for relative in expected_pages | expected_sources:
                self.assertIn(
                    "https://example.com/docs/" + relative,
                    sitemap,
                )


class DocumentationSourceRegressionTests(unittest.TestCase):
    def test_build_info_identifies_lean_doc_comments(self) -> None:
        with mock.patch.object(Path, "cwd", return_value=REPOSITORY_ROOT.parent):
            info = build_site.build_info_dict(
                title="Demo",
                version="",
                commit="a" * 40,
                github_repo="https://github.com/example/demo",
                lean_root=REPOSITORY_ROOT / "data" / "lean4",
                lean_toolchain="leanprover/lean4:v4.27.0",
            )

            self.assertEqual(info["documentationSource"], "Lean doc comments")
            self.assertEqual(info["leanRoot"], "data/lean4")
            self.assertEqual(info["leanToolchain"], "leanprover/lean4:v4.27.0")

    def test_mathematical_bracket_parenthesis_is_not_a_markdown_link(self) -> None:
        rendered = build_site.simple_markdown(
            "The pairing [x](y) is mathematical notation."
        )

        self.assertIn("[x](y)", rendered)
        self.assertNotIn('href="y"', rendered)

    def test_short_names_and_natural_words_are_never_auto_linked(self) -> None:
        declaration = build_site.Declaration(
            kind="def",
            name="v",
            full_name="Other.Namespace.v",
            line=1,
            code="def v : Nat := 1",
            doc="",
            module="Other",
            rel_path="Other.lean",
            id="decl-Other.Namespace.v",
        )
        lookup = build_site.declaration_lookup(
            [
                build_site.Module(
                    name="Other",
                    rel_path="Other.lean",
                    source=declaration.code,
                    imports=[],
                    module_doc="",
                    decls=[declaration],
                )
            ]
        )
        links = build_site.link_map_for(lookup, "")

        rendered_code = build_site.highlight_lean(
            "def demo (v : Nat) := Other.Namespace.v",
            links,
        )
        rendered_prose = build_site.simple_markdown(
            "A comparison uses a cyclic formation and the variable v."
        )

        self.assertIn("demo (v : Nat)", rendered_code)
        self.assertEqual(rendered_code.count('class="decl-ref"'), 1)
        self.assertIn(
            '<a class="decl-ref" href="library/Other.html#decl-Other.Namespace.v">'
            "Other.Namespace.v</a>",
            rendered_code,
        )
        self.assertNotIn("decl-ref", rendered_prose)
        self.assertNotIn("href=", rendered_prose)

    def test_string_highlighting_does_not_parse_comment_markers_or_names(self) -> None:
        rendered = build_site.highlight_lean(
            'def text := "hello -- Other.Namespace.v"',
            {"Other.Namespace.v": "target.html"},
        )

        self.assertIn(
            '<span class="str">&quot;hello -- Other.Namespace.v&quot;</span>',
            rendered,
        )
        self.assertNotIn('class="comment"', rendered)
        self.assertNotIn('class="decl-ref"', rendered)

    def test_missing_prose_uses_a_single_code_column_without_placeholder(self) -> None:
        declaration = build_site.Declaration(
            kind="def",
            name="demo",
            full_name="Demo.demo",
            line=1,
            code="def demo : Nat := 1",
            doc="",
            module="Demo",
            rel_path="Demo.lean",
            id="decl-Demo.demo",
        )

        rendered = build_site.render_decl(declaration, "", {}, "")

        self.assertIn("statement-only", rendered)
        self.assertNotIn("No prose statement has been entered", rendered)
        self.assertNotIn("natural-text", rendered)

    def test_module_math_loads_mathjax_but_source_code_does_not(self) -> None:
        module = build_site.Module(
            name="Demo",
            rel_path="Demo.lean",
            source="/-! The group \\(G\\). -/\n",
            imports=[],
            module_doc="The group \\(G\\).",
            decls=[],
            component="ExampleLibrary",
        )
        module.natural = build_site.module_doc_natural_entry(module.module_doc)

        module_page = build_site.render_module_page(
            module,
            [module],
            {},
            "Demo",
            documentation_url="https://example.com/docs/",
        )
        source_page = build_site.render_source_page(
            module,
            {},
            "Demo",
            module_names={"Demo"},
            module_components={"Demo": "ExampleLibrary"},
            documentation_url="https://example.com/docs/",
        )

        self.assertIn("mathjax@3.2.2", module_page)
        self.assertIn("tex2jax_process", module_page)
        self.assertNotIn("mathjax@3.2.2", source_page)
        self.assertIn(
            '<link rel="canonical" href="https://example.com/docs/library/ExampleLibrary/module-roots/Demo.html">',
            module_page,
        )
        self.assertIn(
            '<link rel="canonical" href="https://example.com/docs/library/ExampleLibrary/src/module-roots/Demo.html">',
            source_page,
        )
        self.assertIn('<meta name="description"', module_page)
        self.assertIn('<meta name="description"', source_page)

    def test_search_page_loads_mathjax_for_dynamically_inserted_statements(self) -> None:
        page = build_site.render_find_page("Demo")
        javascript = (
            REPOSITORY_ROOT.parent
            / "data"
            / "assets"
            / "site.js"
        ).read_text(encoding="utf-8")

        self.assertIn("mathjax@3.2.2", page)
        self.assertIn("search-results tex2jax_process", page)
        self.assertIn("MathJax.typesetPromise([mount])", javascript)

    def test_import_labels_counts_and_tree_roots_are_human_readable(self) -> None:
        module = build_site.Module(
            name="Demo",
            rel_path="ProCGroups/Demo.lean",
            source="import One\nimport Two\n",
            imports=["One", "Two"],
            module_doc="",
            decls=[],
            component="ProCGroups",
        )

        imports = build_site.render_module_imports(
            module,
            {"Demo"},
            "",
        )
        tree = build_site.build_tree_data(
            [module],
            component_display_names={"ProCGroups": "Pro-C Groups"},
        )

        self.assertIn("<summary>imports</summary>", imports)
        self.assertEqual(tree[0]["n"], "Pro-C Groups")
        self.assertEqual(build_site.count_label(1, "file"), "1 file")
        self.assertEqual(build_site.count_label(2, "file"), "2 files")
        self.assertEqual(
            build_site.kind_summary(
                [
                    build_site.Declaration(
                        kind="theorem",
                        name=f"t{index}",
                        full_name=f"Demo.t{index}",
                        line=index,
                        code=f"theorem t{index} : True := by trivial",
                        doc="",
                        module="Demo",
                        rel_path="Demo.lean",
                        id=f"decl-Demo.t{index}",
                    )
                    for index in (1, 2)
                ]
            ),
            "2 Theorems",
        )

    def test_homepage_and_module_page_copy_the_full_aggregate_doc_comment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ProCGroups").mkdir()
            (root / "ProCGroups.lean").write_text(
                "import ProCGroups.Child\n"
                "/-!\n"
                "# Demo\n\n"
                "First sentence describes the library. "
                "Second sentence records its scope. "
                "Third sentence names its public surface. "
                "Fourth sentence must remain visible on the homepage and module page.\n"
                "-/\n",
                encoding="utf-8",
            )
            (root / "ProCGroups" / "Child.lean").write_text(
                "/-! # Child -/\n"
                "namespace ProCGroups\n"
                "/-- A visible declaration. -/\n"
                "theorem child : True := by trivial\n"
                "end ProCGroups\n",
                encoding="utf-8",
            )

            modules, by_token = build_site.prepare_modules(
                root, fixed_updated_at=1
            )
            wrapper = next(module for module in modules if module.name == "ProCGroups")
            homepage = build_site.render_index(modules, "Demo")
            module_page = build_site.render_module_page(
                wrapper, modules, by_token, "Demo"
            )

            final_sentence = (
                "Fourth sentence must remain visible on the homepage and module page."
            )
            self.assertIn(final_sentence, homepage)
            self.assertIn(final_sentence, module_page)
            self.assertIn("<summary>import</summary>", module_page)
            self.assertIn("<summary>Imported by</summary>", module_page)

    def test_library_card_preserves_multiple_paragraphs(self) -> None:
        single = "<p>One paragraph.</p>"
        multiple = "<p>First paragraph.</p>\n<p>Second paragraph.</p>"

        self.assertEqual(
            build_site.strip_paragraph_wrapper(single),
            "One paragraph.",
        )
        self.assertEqual(
            build_site.strip_paragraph_wrapper(multiple),
            multiple,
        )

    def test_import_only_leaf_page_lists_imports_instead_of_empty_children(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ProCGroups").mkdir()
            (root / "ProCGroups" / "All.lean").write_text(
                "import ProCGroups.FiniteReciprocity\n"
                "/-! # Complete API\n\nReader-facing import surface. -/\n",
                encoding="utf-8",
            )
            (root / "ProCGroups" / "FiniteReciprocity.lean").write_text(
                "namespace ProCGroups\n"
                "/-- Finite reciprocity. -/\n"
                "theorem finiteReciprocity : True := by trivial\n"
                "end ProCGroups\n",
                encoding="utf-8",
            )

            modules, by_token = build_site.prepare_modules(
                root, fixed_updated_at=1
            )
            aggregate = next(
                module for module in modules if module.name == "ProCGroups.All"
            )
            page = build_site.render_module_page(
                aggregate, modules, by_token, "Demo"
            )

            self.assertIn(
                "1 import | import-only module | 0 declarations", page
            )
            self.assertIn('<details class="imports" open>', page)
            self.assertIn(
                "ProCGroups/FiniteReciprocity.html", page
            )
            self.assertIn(
                "This import-only module declares no new names.", page
            )
            self.assertNotIn("0 sections | 0 files", page)
            self.assertNotIn("No files.", page)
            self.assertNotIn("toggle_all_proofs", page)

    def test_source_page_keeps_multiline_doc_comment_out_of_code_highlighting(self) -> None:
        module = build_site.Module(
            name="LocalClassFieldTheory.All",
            rel_path="LocalClassFieldTheory/All.lean",
            source=(
                "import LocalClassFieldTheory.FiniteReciprocity\n"
                "\n"
                "/-!\n"
                "This class-formation theorem is an import surface.\n"
                "-/\n"
            ),
            imports=["LocalClassFieldTheory.FiniteReciprocity"],
            module_doc="This class-formation theorem is an import surface.",
            decls=[],
            component="LocalClassFieldTheory",
        )
        formation = build_site.Declaration(
            kind="class",
            name="Formation",
            full_name="ProCGroups.FiniteGroupClass.Formation",
            line=1,
            code="class Formation",
            doc="",
            module="ProCGroups.FiniteGroups.Classes",
            rel_path="ProCGroups/FiniteGroups/Classes.lean",
            id="decl-ProCGroups.FiniteGroupClass.Formation",
            component="ProCGroups",
        )

        page = build_site.render_source_page(
            module,
            {
                formation.full_name: formation,
                formation.name: formation,
            },
            "Demo",
            module_names={"LocalClassFieldTheory.All"},
            module_components={
                "LocalClassFieldTheory.All": "LocalClassFieldTheory"
            },
        )
        comment_line = re.search(
            r'<div class="src-line" id="L4">.*?</div>', page
        )

        self.assertIsNotNone(comment_line)
        rendered = comment_line.group(0)
        self.assertIn(
            '<span class="comment">'
            "This class-formation theorem is an import surface."
            "</span>",
            rendered,
        )
        self.assertNotIn('class="kw"', rendered)
        self.assertNotIn('class="decl-ref"', rendered)

        module_page = build_site.render_module_page(
            module,
            [module],
            {
                formation.full_name: formation,
                formation.name: formation,
            },
            "Demo",
            module_names={"LocalClassFieldTheory.All"},
        )
        self.assertIn(
            "This class-formation theorem is an import surface.",
            module_page,
        )
        self.assertNotIn('class="decl-ref"', module_page)
    def test_publish_build_uses_only_lean_documentation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_root = root / "data"
            lean_root = data_root / "lean4"
            assets_root = data_root / "assets"
            pages_root = root / "pages"
            repository_mirror = root / "lean-repository"
            lean_root.mkdir(parents=True)
            assets_root.mkdir()
            repository_mirror.mkdir()
            (lean_root / "ProCGroups.lean").write_text(
                "/-! Pro-C groups. -/\n", encoding="utf-8"
            )
            config = {
                "pages_output_root": str(pages_root),
                "lean_repository_mirror": str(repository_mirror),
                "commit": "a" * 40,
            }

            with (
                mock.patch.object(build_site, "read_site_config", return_value=config),
                mock.patch.object(build_site, "validate_publish_layout"),
                mock.patch.object(
                    build_site,
                    "git_commit_timestamp",
                    return_value="2026-07-22T00:00:00Z",
                ),
                mock.patch.object(build_site, "cleanup_distribution_workdirs"),
                mock.patch.object(
                    build_site,
                    "generate_site",
                    return_value=build_site.WriteStats(),
                ) as generate_site,
                mock.patch.object(
                    build_site, "run_python_tool", return_value=True
                ) as run_python_tool,
            ):
                build_site.build_publish_pages(data_root, show_git_diff=False)

            self.assertEqual(generate_site.call_count, 1)
            checked_tools = [call.args[1] for call in run_python_tool.call_args_list]
            self.assertEqual(checked_tools, ["tools/check_generated_site.py"])


class PublicWorkflowRegressionTests(unittest.TestCase):
    def test_public_ci_is_generated_from_canonical_validation_sources(self) -> None:
        files = generate.static_generated()

        self.assertEqual(
            generate.ALWAYS_PRESERVED_OUTPUT_TOP_LEVEL,
            frozenset({".git", "LICENSE", "publisher"}),
        )
        self.assertEqual(
            files[Path(".github/workflows/ci.yml")],
            generate.PUBLIC_SITE_CI_TEMPLATE.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            files[Path(".github/workflows/pages.yml")],
            generate.PUBLIC_SITE_PAGES_TEMPLATE.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            files[Path(".github/validation/public_paths.py")],
            generate.PUBLIC_PATHS_SOURCE.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            files[Path(".github/validation/check_generated_site.py")],
            generate.GENERATED_SITE_CHECKER.read_text(encoding="utf-8"),
        )
        self.assertEqual(
            files[Path(".github/validation/check_public_repository.py")],
            generate.PUBLIC_REPOSITORY_CHECKER.read_text(encoding="utf-8"),
        )
        workflow = files[Path(".github/workflows/ci.yml")]
        self.assertIn(
            "python3 .github/validation/check_generated_site.py",
            workflow,
        )
        self.assertIn(
            "python3 .github/validation/check_public_repository.py .",
            workflow,
        )
        self.assertNotIn("PurePosixPath(*module.split", workflow)

    def test_synchronization_replaces_stale_workflow_and_removes_unknown_ci_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            write_text = {
                path: content
                for path, content in generate.static_generated().items()
                if path.parts[0] in {".gitattributes", ".github"}
            }
            generate.write_text_files(source, write_text)
            stale = destination / ".github" / "workflows" / "ci.yml"
            stale.parent.mkdir(parents=True)
            stale.write_text("name: stale\n", encoding="utf-8")
            unknown = destination / ".github" / "workflows" / "unknown.yml"
            unknown.write_text("name: unknown\n", encoding="utf-8")
            (destination / ".git").mkdir()
            (destination / "LICENSE").write_text(
                "preserved license\n",
                encoding="utf-8",
            )
            publisher = destination / "publisher"
            publisher.mkdir()
            publisher_file = publisher / "source.txt"
            publisher_file.write_text(
                "preserved publisher source\n",
                encoding="utf-8",
            )
            obsolete_pages = destination / "ProCGroups_pages"
            obsolete_pages.mkdir()
            obsolete_page = obsolete_pages / "index.html"
            obsolete_page.write_text("obsolete split site\n", encoding="utf-8")
            preserved = generate.ALWAYS_PRESERVED_OUTPUT_TOP_LEVEL

            generate.synchronize_tree(source, destination, preserved)

            self.assertEqual(
                stale.read_text(encoding="utf-8"),
                generate.PUBLIC_SITE_CI_TEMPLATE.read_text(encoding="utf-8"),
            )
            self.assertFalse(unknown.exists())
            self.assertTrue((destination / ".git").is_dir())
            self.assertEqual(
                (destination / "LICENSE").read_text(encoding="utf-8"),
                "preserved license\n",
            )
            self.assertEqual(
                publisher_file.read_text(encoding="utf-8"),
                "preserved publisher source\n",
            )
            self.assertFalse(obsolete_page.exists())


class HomepageNamingRegressionTests(unittest.TestCase):
    def test_homepages_show_full_library_names_without_abbreviations(self) -> None:
        libraries = generate.load_libraries_database()
        modules = generate.load_modules_database(libraries["libraries"])
        counts = generate.library_module_counts(
            modules["modules"],
            libraries["libraries"],
        )
        root_page = generate.root_index()
        metadata = [
            {
                **library,
                "module_count": counts[library["id"]],
            }
            for library in libraries["libraries"]
        ]
        portal_page = build_site.render_index(
            [
                build_site.Module(
                    name="ProCGroups",
                    rel_path="ProCGroups.lean",
                    source="import ProCGroups.Demo\n",
                    imports=["ProCGroups.Demo"],
                    module_doc="Pro-C group entry point.",
                    decls=[],
                    component="ProCGroups",
                ),
                build_site.Module(
                    name="ProCGroups.Demo",
                    rel_path="ProCGroups/Demo.lean",
                    source="def demo := 1\n",
                    imports=[],
                    module_doc="Demonstration module.",
                    decls=[],
                    component="ProCGroups",
                ),
            ],
            libraries["site"]["title"],
            library_metadata=metadata,
        )

        for page in (root_page, portal_page):
            visible_text = html.unescape(re.sub(r"<[^>]+>", " ", page))
            visible_text = re.sub(r"\s+", " ", visible_text)
            for abbreviation in ("PCG", "LCFT", "CES", "CGA"):
                self.assertIsNone(
                    re.search(rf"\b{abbreviation}\b", visible_text),
                    f"{abbreviation} must not be visible on a homepage",
                )

        root_text = html.unescape(re.sub(r"<[^>]+>", " ", root_page))
        self.assertIn("Lean 4 libraries", root_text)
        self.assertNotIn("Pro-C Groups", root_text)
        self.assertIn("Pro-C Groups", portal_page)
        for removed_name in (
            "Local Class Field Theory",
            "Crowell Exact Sequences",
        ):
            self.assertNotIn(removed_name, root_text)
            self.assertNotIn(removed_name, portal_page)

    def test_public_repository_readme_contains_only_stable_public_links(self) -> None:
        readme = generate.repository_readme()

        self.assertIn("Yamaguchi Lean 4 Library", readme)
        self.assertNotIn("1,088", readme)
        self.assertNotIn("three", readme.lower())
        self.assertNotIn("YamaLean4Lib_Database", readme)
        self.assertNotIn("YamaLean4Lib_Generator", readme)


class DatabaseContractRegressionTests(unittest.TestCase):
    def test_export_and_website_databases_agree(self) -> None:
        libraries = generate.load_libraries_database()
        modules = generate.load_modules_database(libraries["libraries"])

        exports = generate.load_export_databases(
            libraries["libraries"],
            modules,
        )

        self.assertEqual(
            list(exports),
            [item["id"] for item in libraries["libraries"]],
        )
        module_pages, source_pages = generate.public_page_paths(
            modules,
            libraries["libraries"],
        )
        self.assertEqual(len(module_pages), modules["module_count"])
        self.assertEqual(len(source_pages), modules["module_count"])
        self.assertIn(
            Path("library/ProCGroups/root-module.html"),
            module_pages,
        )
        self.assertIn(
            Path("library/ProCGroups/CrowellExactSequence.html"),
            module_pages,
        )
        self.assertTrue(
            all(
                path.parts[:2] == ("library", "ProCGroups")
                for path in module_pages | source_pages
            )
        )

    def test_a_new_library_is_added_by_data_without_generator_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            libraries_data = generate.read_json(generate.LIBRARIES_DATABASE)
            pcg_data = generate.library_data_directory(
                libraries_data["libraries"][0]
            )
            pcg_modules = generate.read_json(pcg_data / "modules.json")
            pcg_export = generate.read_json(pcg_data / "export.json")
            library = {
                "id": "ExampleLibrary",
                "display_name": "Example Library",
                "repository":
                    "https://github.com/n-yamaguchi-0729/ExampleLibrary",
                "data": "libraries/ExampleLibrary",
                "import": "ExampleLibrary",
                "module_roots": ["ExampleLibrary"],
                "summary": "An example future library.",
                "contents": ["Example formalization"],
            }
            libraries_data["libraries"].append(library)
            libraries_path = root / "libraries.json"
            values = {
                libraries_path: libraries_data,
                root / "libraries" / "ProCGroups" / "modules.json":
                    pcg_modules,
                root / "libraries" / "ProCGroups" / "export.json":
                    pcg_export,
                root / "libraries" / "ExampleLibrary" / "modules.json": {
                    "schema": 3,
                    "package": "ExampleLibrary",
                    "module_count": 1,
                    "modules": ["ExampleLibrary"],
                },
                root / "libraries" / "ExampleLibrary" / "export.json": {
                    "schema": 2,
                    "package": "ExampleLibrary",
                    "version": "1.0.0",
                    "summary": "An example future library.",
                    "website":
                        "https://n-yamaguchi-0729.github.io/"
                        "YamaLean4Lib_pages/",
                    "source_dir": "Lean4",
                    "libraries": [{
                        "id": "ExampleLibrary",
                        "display_name": "Example Library",
                        "module_roots": ["ExampleLibrary"],
                        "source_roots": [{
                            "path": "Lean4/ExampleLibrary.lean",
                            "include_root": False,
                        }],
                        "import_target": "ExampleLibrary",
                        "description": "An example future library.",
                    }],
                },
            }
            for path, value in values.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(value, ensure_ascii=False),
                    encoding="utf-8",
                )

            with (
                mock.patch.object(generate, "DATABASE", root),
                mock.patch.object(
                    generate,
                    "LIBRARIES_DATABASE",
                    libraries_path,
                ),
            ):
                libraries = generate.load_libraries_database()
                modules = generate.load_modules_database(libraries["libraries"])
                exports = generate.load_export_databases(
                    libraries["libraries"],
                    modules,
                )
                counts = generate.library_module_counts(
                    modules["modules"],
                    libraries["libraries"],
                )

            self.assertEqual(counts["ExampleLibrary"], 1)
            self.assertEqual(
                set(exports),
                {"ProCGroups", "ExampleLibrary"},
            )
            repositories = generate.library_repositories(
                libraries["libraries"],
                [f"ExampleLibrary={root / 'example-checkout'}"],
            )
            self.assertEqual(
                repositories["ExampleLibrary"],
                root / "example-checkout",
            )

    def test_case_insensitive_public_route_collisions_are_rejected(self) -> None:
        libraries = [{
            "id": "LocalClassFieldTheory",
            "module_roots": ["LocalClassFieldTheory"],
        }]
        modules = {
            "module_count": 2,
            "modules": [
                "LocalClassFieldTheory.All",
                "LocalClassFieldTheory.all",
            ],
        }

        with self.assertRaisesRegex(
            generate.DatabaseError,
            "case-insensitive public URL collision",
        ):
            generate.public_page_paths(modules, libraries)


class OutputSafetyRegressionTests(unittest.TestCase):
    def test_generated_output_path_can_never_resolve_to_root_or_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            for unsafe in ("", ".", "..", "../outside", "/absolute", "C:\\outside"):
                with self.subTest(path=unsafe):
                    with self.assertRaises(ValueError):
                        build_site.safe_output_path(root, unsafe)

            self.assertEqual(
                build_site.safe_output_path(root, "library/Demo.html"),
                (root / "library" / "Demo.html").resolve(),
            )


class AxiomScannerRegressionTests(unittest.TestCase):
    def test_nested_comments_and_strings_are_not_axioms(self) -> None:
        checker = load_tool("check_axiom_manifest")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Demo.lean").write_text(
                "/- axiom outerFake : False /- axiom nestedFake : False -/ -/\n"
                "def text : String := \"first line\naxiom stringFake : False\"\n"
                "private axiom actual : True\n",
                encoding="utf-8",
            )

            rows = checker.scan_axioms(root)

            self.assertEqual([row["name"] for row in rows], ["actual"])
            self.assertEqual(rows[0]["line"], 4)

    def test_axiom_line_starts_at_the_declaration_not_preceding_doc_comments(self) -> None:
        checker = load_tool("check_axiom_manifest")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Demo.lean").write_text(
                "namespace Demo\n"
                "\n"
                "/- FRONTIER note. -/\n"
                "/-- Public declaration documentation. -/\n"
                "axiom actual : True\n",
                encoding="utf-8",
            )

            rows = checker.scan_axioms(root)

            self.assertEqual([row["name"] for row in rows], ["actual"])
            self.assertEqual(rows[0]["line"], 5)


class GeneratedSiteCheckerRegressionTests(unittest.TestCase):
    def make_valid_site(self, root: Path) -> tuple[object, str, str]:
        checker = load_tool("check_generated_site")
        sha = "a" * 40
        repository = "https://github.com/example/library"
        libraries = [
            {
                "id": "ProCGroups",
                "display_name": "Pro-C Groups",
                "import": "ProCGroups",
                "module_roots": ["ProCGroups"],
                "module_count": 1,
            },
            {
                "id": "LocalClassFieldTheory",
                "display_name": "Local Class Field Theory",
                "import": "LocalClassFieldTheory",
                "module_roots": ["LocalClassFieldTheory"],
                "module_count": 1,
            },
            {
                "id": "CrowellExactSequence",
                "display_name": "Crowell Exact Sequences",
                "import": "CrowellExactSequence",
                "module_roots": ["CrowellExactSequence"],
                "module_count": 1,
            },
            {
                "id": "ExampleLibrary",
                "display_name": "Example Library",
                "import": "ExampleLibrary",
                "module_roots": ["ExampleLibrary"],
                "module_count": 1,
            },
        ]
        search_entries = []
        tree = []
        for library in libraries:
            library_id = library["id"]
            module_name = library["import"]
            module_path = module_name.replace(".", "/")
            module_url = build_site.module_html_path(module_name, library_id)
            module_page = root / Path(module_url)
            module_page.parent.mkdir(parents=True, exist_ok=True)
            module_page.write_text(
                f"<h1>{module_name}</h1>",
                encoding="utf-8",
            )
            source_page = root / Path(
                build_site.source_html_path(
                    module_path + ".lean",
                    library_id,
                )
            )
            source_page.parent.mkdir(parents=True, exist_ok=True)
            source_page.write_text(
                '<div class="src-line" id="L1">source</div>',
                encoding="utf-8",
            )
            search_entries.append(
                {
                    "n": module_name,
                    "k": "Lean file",
                    "u": module_url,
                }
            )
            tree.append(
                {
                    "n": library["display_name"],
                    "c": [
                        {
                            "n": f"{module_name}.lean",
                            "m": module_name,
                            "u": module_url,
                        }
                    ],
                }
            )
        library_anchors = {
            "ProCGroups": "pro-c-groups",
            "LocalClassFieldTheory": "local-class-field-theory",
            "CrowellExactSequence": "crowell-exact-sequences",
            "ExampleLibrary": "example-library",
        }
        for library in libraries:
            search_entries.append(
                {
                    "n": library["display_name"],
                    "k": "Library",
                    "u": f"index.html#{library_anchors[library['id']]}",
                }
            )
        (root / "index.html").write_text(
            '<h1>Lean 4 libraries</h1><section id="pro-c-groups"></section>'
            '<section id="local-class-field-theory"></section>'
            '<section id="crowell-exact-sequences"></section>'
            '<section id="example-library"></section>',
            encoding="utf-8",
        )
        assets = root / "assets"
        assets.mkdir()
        (assets / "search-index.js").write_text(
            "window.LEAN_DOCS_INDEX="
            + json.dumps(search_entries, separators=(",", ":"))
            + ";\n",
            encoding="utf-8",
        )
        (assets / "tree-data.js").write_text(
            "window.LEAN_DOCS_TREE="
            + json.dumps(tree, separators=(",", ":"))
            + ";\n",
            encoding="utf-8",
        )
        (root / "build-info.json").write_text(
            json.dumps(
                {
                    "commit": sha,
                    "sourceRef": sha,
                    "sourceRepository": repository,
                    "libraries": libraries,
                }
            ),
            encoding="utf-8",
        )
        write_site_manifest(root, checker.SITE_MANIFEST_NAME)
        return checker, sha, repository

    def test_library_inventory_is_data_driven(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)

            self.assertEqual(checker.check_root(root), [])

    def test_public_deployment_does_not_require_private_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            (root / checker.SITE_MANIFEST_NAME).unlink()

            self.assertEqual(checker.check_root(root), [])
            self.assertEqual(checker.check_public_artifacts(root), [])

    def test_public_allowlist_rejects_archives_backups_and_internal_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            (root / checker.SITE_MANIFEST_NAME).unlink()

            for relative in (
                "download/source.zip",
                "backup/index.html",
                "README.md",
                "LICENSE",
                "tools/check_generated_site.py",
            ):
                with self.subTest(relative=relative):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("not public", encoding="utf-8")
                    errors = checker.check_public_artifacts(root)
                    self.assertTrue(
                        any(relative in error for error in errors),
                        errors,
                    )
                    path.unlink()

    def test_sha_pinned_source_links_are_not_exposed_on_module_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, sha, repository = self.make_valid_site(root)
            module_page = root / "library" / "ProCGroups" / "root-module.html"
            module_page.write_text(
                module_page.read_text(encoding="utf-8")
                + f'<a href="{repository}/blob/{sha}/Lean4/ProCGroups.lean#L12">line</a>',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(
                any(
                    "generated GitHub blob/source references are forbidden"
                    in error
                    for error in errors
                )
            )

    def test_multi_digit_counts_do_not_trigger_singular_grammar_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            module_page = (
                root / "library" / "ProCGroups" / "root-module.html"
            )
            module_page.write_text(
                module_page.read_text(encoding="utf-8")
                + "<p>11 declarations | 21 sections | 31 files | "
                "41 top-level groups</p>",
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            self.assertEqual(checker.check_root(root), [])

    def test_incorrect_singular_grammar_is_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            module_page = (
                root / "library" / "ProCGroups" / "root-module.html"
            )
            module_page.write_text(
                module_page.read_text(encoding="utf-8")
                + "<p>1 declarations</p>",
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(
                any("incorrect singular grammar" in error for error in errors)
            )

    def test_manifest_listed_missing_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            manifest_path = root / checker.SITE_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"].append("missing.txt")
            manifest["file_count"] += 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = checker.check_root(root)

            self.assertTrue(any("listed files missing" in error for error in errors))

    def test_manifest_unlisted_extra_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            (root / "extra.txt").write_text("not in manifest", encoding="utf-8")

            errors = checker.check_root(root)

            self.assertTrue(any("unlisted files" in error for error in errors))

    def test_manifest_file_count_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            manifest_path = root / checker.SITE_MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["file_count"] += 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            errors = checker.check_root(root)

            self.assertTrue(any("does not equal files length" in error for error in errors))

    def test_build_metadata_module_count_must_match_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            build_info_path = root / "build-info.json"
            build_info = json.loads(build_info_path.read_text(encoding="utf-8"))
            build_info["libraries"][0]["module_count"] = 2
            build_info_path.write_text(json.dumps(build_info), encoding="utf-8")
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(
                any("declares module_count=2, tree contains 1" in error for error in errors)
            )

    def test_legacy_abbreviations_are_rejected_in_public_paths_and_headings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            (root / "index.html").write_text(
                '<h1>LCFT reference</h1><section id="pro-c-groups"></section>'
                '<section id="local-class-field-theory"></section>',
                encoding="utf-8",
            )
            legacy = root / "library" / "PCG" / "Legacy.html"
            legacy.parent.mkdir()
            legacy.write_text("<p>legacy</p>", encoding="utf-8")
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(any("public path uses a legacy" in error for error in errors))
            self.assertTrue(any("page heading uses a legacy" in error for error in errors))

    def test_symlink_in_generated_tree_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            make_symlink_or_skip(self, root / "linked.html", root / "index.html")

            errors = checker.check_root(root)

            self.assertTrue(any("must not contain symlinks" in error for error in errors))

    def test_casefold_collision_in_generated_tree_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            collision_root = root / "collision"
            collision_root.mkdir()
            (collision_root / "Name.txt").write_text("upper", encoding="utf-8")
            (collision_root / "name.txt").write_text("lower", encoding="utf-8")
            if len(list(collision_root.iterdir())) != 2:
                self.skipTest("filesystem does not permit case-distinct paths")

            errors = checker.check_root(root)

            self.assertTrue(any("case-insensitive path collision" in error for error in errors))

    def test_declaration_and_module_source_links_are_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            module_page = root / "library" / "ProCGroups" / "root-module.html"
            module_page.write_text(
                '<h1>No source link</h1><a class="source-link" '
                'href="src/root-module.html#L1">Source</a>',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(
                any(
                    "library/ProCGroups/root-module.html: "
                    "declaration/module source links are forbidden"
                    in error
                    for error in errors
                )
            )

    def test_proof_controls_are_collapsed_accessible_and_hash_aware(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            declaration = build_site.Declaration(
                kind="theorem",
                name="demo",
                full_name="ProCGroups.demo",
                line=1,
                code="theorem demo : True := by trivial",
                doc="A demonstration theorem.",
                module="ProCGroups",
                rel_path="ProCGroups.lean",
                id="decl-ProCGroups.demo",
                component="ProCGroups",
            )
            module = build_site.Module(
                name="ProCGroups",
                rel_path="ProCGroups.lean",
                source="theorem demo : True := by trivial\n",
                imports=[],
                module_doc="Pro-C groups.",
                decls=[declaration],
                component="ProCGroups",
            )
            module_page = root / "library" / "ProCGroups" / "root-module.html"
            module_page.write_text(
                build_site.render_module_page(
                    module,
                    [module],
                    {
                        declaration.name: declaration,
                        declaration.full_name: declaration,
                    },
                    "Demo",
                ),
                encoding="utf-8",
            )
            assets = root / "assets"
            for name in ("site.css", "site.js"):
                (assets / name).write_text(
                    (generate.PORTAL_ASSETS / name).read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            self.assertEqual(checker.check_root(root), [])

            script = assets / "site.js"
            script.write_text(
                script.read_text(encoding="utf-8").replace(
                    "window.addEventListener('hashchange', openHashProof);",
                    "",
                ),
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)
            errors = checker.check_root(root)
            self.assertTrue(
                any("hashchange" in error for error in errors),
                errors,
            )

    def test_generated_text_assets_are_checked_for_proof_markers_and_blob_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            assets = root / "assets"
            assets.mkdir(exist_ok=True)
            (assets / "policy.js").write_text(
                'const marker = "proof-text"; const url = "https://github.com/example/library/blob/main/Lean4/Demo.lean";',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(any("forbidden generated-proof marker" in error for error in errors))
            self.assertTrue(
                any(
                    "generated GitHub blob/source references are forbidden"
                    in error
                    for error in errors
                )
            )

    def test_broken_local_html_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            page = root / "library" / "ProCGroups" / "root-module.html"
            page.write_text(
                page.read_text(encoding="utf-8")
                + '<a href="../missing/index.html">missing</a>',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(any("broken local link" in error for error in errors))

    def test_broken_fragment_and_short_declaration_link_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            page = root / "library" / "ProCGroups" / "root-module.html"
            page.write_text(
                page.read_text(encoding="utf-8")
                + '<a href="#missing">missing fragment</a>'
                + '<a class="decl-ref" href="#L1">v</a>',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(any("broken local fragment" in error for error in errors))
            self.assertTrue(
                any("unsafe short-name declaration link" in error for error in errors)
            )

    def test_search_index_rejects_anonymous_and_missing_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            search = root / checker.SEARCH_INDEX_PATH
            search.write_text(
                'window.LEAN_DOCS_INDEX=[{"n":"Demo.anonymous_1",'
                '"k":"Definition","u":"missing.html"}];\n',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(
                any("synthetic anonymous declaration leaked" in error for error in errors)
            )
            self.assertTrue(any("missing search target" in error for error in errors))

    def test_source_line_ids_must_be_contiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checker, _, _ = self.make_valid_site(root)
            source = (
                root / "library" / "ProCGroups" / "src" / "root-module.html"
            )
            source.write_text(
                '<div class="src-line" id="L2">source</div>',
                encoding="utf-8",
            )
            write_site_manifest(root, checker.SITE_MANIFEST_NAME)

            errors = checker.check_root(root)

            self.assertTrue(
                any("source line ids are not the contiguous" in error for error in errors)
            )


if __name__ == "__main__":
    unittest.main()
