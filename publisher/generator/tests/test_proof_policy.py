from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import build_site

class ProofTranslationPolicyTests(unittest.TestCase):
    def test_declaration_renders_only_the_lean_proof(self) -> None:
        declaration = build_site.Declaration(
            kind="theorem",
            name="demo",
            full_name="Example.demo",
            line=1,
            code="theorem demo : True := by\n  trivial",
            doc="",
            module="Example",
            rel_path="Example.lean",
            id="decl-example-demo",
            natural={"statement": "Truth holds.", "proof": "must never appear"},
        )
        rendered = build_site.render_decl(declaration, "", {}, "")
        self.assertIn("Show Lean proof", rendered)
        self.assertIn("lean-proof-code", rendered)
        self.assertNotIn("<details class=\"proof-details\" open", rendered)
        self.assertIn(
            'data-proof-declaration="decl-example-demo"',
            rendered,
        )
        self.assertNotIn("must never appear", rendered)
        self.assertNotIn("proof-pair", rendered)
        self.assertNotIn("proof-text", rendered)
        self.assertNotIn("source-link", rendered)

        rendered_with_remote_source = build_site.render_decl(
            declaration,
            "",
            {},
            "https://github.com/example/repo/blob/" + "a" * 40 + "/Lean4",
        )
        self.assertNotIn("github.com", rendered_with_remote_source)
        self.assertNotIn("source-link", rendered_with_remote_source)

    def test_equation_style_theorem_separates_equation_proof(self) -> None:
        declaration = build_site.Declaration(
            kind="theorem",
            name="demo",
            full_name="Example.demo",
            line=1,
            code="theorem demo : ∀ n : Nat, True\n  | 0 => by trivial\n  | _ + 1 => by trivial",
            doc="",
            module="Example",
            rel_path="Example.lean",
            id="decl-example-demo",
        )
        rendered = build_site.render_decl(declaration, "", {}, "")
        self.assertNotIn("No Lean proof was detected.", rendered)
        self.assertIn("proof-details", rendered)
        self.assertIn("lean-proof-code", rendered)
        self.assertIn("| 0 =&gt; <span class=\"kw\">by</span> trivial", rendered)

    def test_top_level_let_bindings_remain_in_theorem_statement(self) -> None:
        code = (
            "theorem demo :\n"
            "  let x := 1\n"
            "  letI : Inhabited Nat := ⟨x⟩\n"
            "  x = 1 := by\n"
            "  rfl"
        )

        statement, proof = build_site.split_lean_statement_proof(code)

        self.assertIn("let x := 1", statement)
        self.assertIn("letI : Inhabited Nat := ⟨x⟩", statement)
        self.assertTrue(statement.endswith("x = 1"))
        self.assertEqual(proof, "by\n  rfl")

    def test_top_level_match_branches_remain_in_theorem_statement(self) -> None:
        code = (
            "theorem demo (b : Bool) :\n"
            "  match b with\n"
            "  | true => True\n"
            "  | false => False := by\n"
            "  cases b <;> simp"
        )

        statement, proof = build_site.split_lean_statement_proof(code)

        self.assertIn("| true => True", statement)
        self.assertTrue(statement.endswith("| false => False"))
        self.assertEqual(proof, "by\n  cases b <;> simp")

    def test_github_source_links_require_sha_and_include_lean4(self) -> None:
        sha = "a" * 40
        self.assertEqual(
            build_site.github_source_base("https://github.com/example/repo", sha),
            f"https://github.com/example/repo/blob/{sha}/Lean4/",
        )
        with self.assertRaises(ValueError):
            build_site.github_source_base("https://github.com/example/repo", "main")

    def test_site_manifest_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            generated = {"index.html", "assets/site.css"}
            build_site.write_site_manifest(root, generated, "2026-07-22T00:00:00Z")
            first = (root / build_site.SITE_MANIFEST_NAME).read_bytes()
            build_site.write_site_manifest(root, generated, "2026-07-22T00:00:00Z")
            second = (root / build_site.SITE_MANIFEST_NAME).read_bytes()
            self.assertEqual(first, second)
            manifest = json.loads(first)
            self.assertNotIn("stats", manifest)

    def test_publish_timestamp_is_a_fixed_epoch(self) -> None:
        self.assertEqual(
            build_site.timestamp_epoch("2026-07-22T00:00:00Z"),
            build_site.timestamp_epoch("2026-07-22T09:00:00+09:00"),
        )

    def test_copy_file_compares_content_even_when_size_and_mtime_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.lean"
            destination = root / "destination.lean"
            source.write_text("new\n", encoding="utf-8")
            destination.write_text("old\n", encoding="utf-8")
            fixed_time = 1_700_000_000
            os.utime(source, (fixed_time, fixed_time))
            os.utime(destination, (fixed_time, fixed_time))

            build_site.copy_file_if_changed(source, destination)

            self.assertEqual(destination.read_text(encoding="utf-8"), "new\n")

    def test_fixed_publish_timestamp_ignores_source_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lean_root = Path(directory)
            source = lean_root / "ProCGroups.lean"
            source.write_text("def example : Nat := 1\n", encoding="utf-8")
            fixed = build_site.timestamp_epoch("2026-07-22T00:00:00Z")
            os.utime(source, (1_600_000_000, 1_600_000_000))
            first, _ = build_site.prepare_modules(
                lean_root, fixed_updated_at=fixed
            )
            os.utime(source, (1_800_000_000, 1_800_000_000))
            second, _ = build_site.prepare_modules(
                lean_root, fixed_updated_at=fixed
            )
            self.assertEqual(first[0].updated_at, fixed)
            self.assertEqual(second[0].updated_at, fixed)

    def test_sync_preserves_repository_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            mirror = root / "mirror"
            source.mkdir()
            mirror.mkdir()
            (source / "generated.txt").write_text("new", encoding="utf-8")
            (mirror / "stale.txt").write_text("old", encoding="utf-8")
            (mirror / "LICENSE").write_text("chosen by author", encoding="utf-8")
            workflow = mirror / ".github" / "workflows" / "ci.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("name: CI\n", encoding="utf-8")

            build_site.sync_directory_contents(
                source,
                mirror,
                preserve_top_level_names=set(build_site.REPOSITORY_METADATA_NAMES),
            )

            self.assertTrue((mirror / "generated.txt").is_file())
            self.assertFalse((mirror / "stale.txt").exists())
            self.assertTrue((mirror / "LICENSE").is_file())
            self.assertTrue(workflow.is_file())

    def test_zip_rejects_symlink_before_reading_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.txt"
            real.write_text("content", encoding="utf-8")
            try:
                (root / "linked.txt").symlink_to(real)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlinks are unavailable on this filesystem: {error}")

            with self.assertRaisesRegex(ValueError, "symlink"):
                build_site.zip_directory_bytes(root)

    def test_zip_rejects_casefold_collision_before_reading_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Name.txt").write_text("upper", encoding="utf-8")
            (root / "name.txt").write_text("lower", encoding="utf-8")
            if len(list(root.iterdir())) != 2:
                self.skipTest("filesystem does not permit case-distinct paths")

            with self.assertRaisesRegex(ValueError, "case-insensitive path collision"):
                build_site.zip_directory_bytes(root)

    def test_directory_sync_rejects_source_symlink_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            mirror = root / "mirror"
            source.mkdir()
            mirror.mkdir()
            real = source / "real.txt"
            real.write_text("content", encoding="utf-8")
            try:
                (source / "linked.txt").symlink_to(real)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlinks are unavailable on this filesystem: {error}")

            with self.assertRaisesRegex(ValueError, "symlink"):
                build_site.sync_directory_contents(source, mirror)

    def test_directory_sync_rejects_target_casefold_collision_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            mirror = root / "mirror"
            source.mkdir()
            mirror.mkdir()
            (source / "safe.txt").write_text("new", encoding="utf-8")
            (mirror / "Name.txt").write_text("upper", encoding="utf-8")
            (mirror / "name.txt").write_text("lower", encoding="utf-8")
            if len(list(mirror.iterdir())) != 2:
                self.skipTest("filesystem does not permit case-distinct paths")

            with self.assertRaisesRegex(ValueError, "case-insensitive path collision"):
                build_site.sync_directory_contents(source, mirror)
            self.assertFalse((mirror / "safe.txt").exists())

    def test_distribution_separates_safe_axiom_and_paper_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lean_root = root / "lean"
            project = root / "project"
            (lean_root / "FenchelNielsenZomorrodian").mkdir(parents=True)
            (lean_root / "ProCGroups.lean").write_text("/-! safe -/\n", encoding="utf-8")
            (lean_root / "FenchelNielsenZomorrodian.lean").write_text(
                "/-! safe FNZ root -/\n", encoding="utf-8"
            )
            (lean_root / "FenchelNielsenZomorrodian" / "WithAxioms.lean").write_text(
                "axiom finiteSubgroup_le_conj_ellipticStabilizer : True\n"
                "axiom finiteSubgroup_le_conj_inertia : True\n",
                encoding="utf-8",
            )
            (lean_root / "Yama2026_Sections_1_And_2_1.lean").write_text(
                "/-! paper -/\n", encoding="utf-8"
            )

            build_site.write_lean_distribution_project(
                lean_root,
                project,
                package_name="YamaguchiLean4Library",
                toolchain="leanprover/lean4:v4.27.0",
                mathlib_ref="v4.27.0",
                title="Test",
                version="0.1.0-dev",
                commit="a" * 40,
                github_repo="https://github.com/example/repo",
                source_ref="a" * 40,
                generated_at="2026-07-22T00:00:00Z",
            )

            stable = (project / "YamaguchiLean4Library.lean").read_text(encoding="utf-8")
            experimental = (
                project / "YamaguchiLean4LibraryExperimental.lean"
            ).read_text(encoding="utf-8")
            papers = (project / "YamaguchiLean4LibraryPapers.lean").read_text(encoding="utf-8")
            manifest = json.loads((project / build_site.AXIOM_MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertIn("import ProCGroups", stable)
            self.assertIn("import FenchelNielsenZomorrodian", stable)
            self.assertNotIn("WithAxioms", stable)
            self.assertNotIn("Yama2026_Sections_1_And_2_1", stable)
            self.assertEqual(
                experimental.strip(), "import FenchelNielsenZomorrodian.WithAxioms"
            )
            self.assertEqual(papers.strip(), "import Yama2026_Sections_1_And_2_1")
            self.assertEqual(len(manifest["projectLocalAxioms"]), 2)
            self.assertEqual(
                (project / ".gitattributes").read_text(encoding="utf-8"),
                "* text=auto eol=lf\n*.bat text eol=crlf\n",
            )
            readme = (project / "README.md").read_text(encoding="utf-8")
            self.assertIn("includes the axiom-free, conditional", readme)
            self.assertIn("FenchelNielsenZomorrodian.WithAxioms", readme)

    def test_axiom_checker_rejects_transitive_opt_in_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lean_root = root / "Lean4"
            (lean_root / "FenchelNielsenZomorrodian").mkdir(parents=True)
            (root / "Stable.lean").write_text("import Safe\n", encoding="utf-8")
            (lean_root / "Safe.lean").write_text(
                "import FenchelNielsenZomorrodian.WithAxioms\n", encoding="utf-8"
            )
            axiom_source = (
                "axiom finiteSubgroup_le_conj_ellipticStabilizer : True\n"
            )
            axiom_path = lean_root / "FenchelNielsenZomorrodian" / "WithAxioms.lean"
            axiom_path.write_text(axiom_source, encoding="utf-8")
            manifest = {
                "stableRoot": "Stable",
                "stableModules": ["Safe"],
                "optInModules": ["FenchelNielsenZomorrodian.WithAxioms"],
                "projectLocalAxioms": [
                    {
                        "module": "FenchelNielsenZomorrodian.WithAxioms",
                        "name": "finiteSubgroup_le_conj_ellipticStabilizer",
                        "path": "FenchelNielsenZomorrodian/WithAxioms.lean",
                        "line": 1,
                        "boundary": "opt-in",
                    }
                ],
            }
            (root / "axiom-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            checker = Path(build_site.__file__).parent / "tools" / "check_axiom_manifest.py"
            result = subprocess.run(
                [sys.executable, str(checker), str(root)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("stable import closure reaches opt-in module", result.stderr)


if __name__ == "__main__":
    unittest.main()
