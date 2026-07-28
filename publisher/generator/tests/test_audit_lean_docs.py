from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

GENERATOR_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = GENERATOR_ROOT / "tools"
for path in (GENERATOR_ROOT, TOOLS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import audit_lean_docs


class AuditLeanDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str, *, newline: str = "\n") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.replace("\n", newline).encode("utf-8"))
        return path

    def audit(self, **kwargs):
        specs, inventory = audit_lean_docs.discover_sources(self.root, **kwargs)
        return audit_lean_docs.audit_sources(self.root, specs, inventory)

    def test_missing_docs_use_build_site_public_declaration_semantics(self) -> None:
        self.write(
            "Demo.lean",
            """import Mathlib

private theorem hidden : True := by trivial
local instance : Inhabited Nat := ⟨0⟩

theorem visible : True := by
  trivial
""",
        )

        result = self.audit()

        self.assertEqual(len(result.files), 1)
        self.assertEqual(result.public_declaration_count, 1)
        self.assertEqual(
            [(item.scope, item.declaration) for item in result.missing],
            [
                ("module", ""),
                ("declaration", "visible"),
            ],
        )
        self.assertNotIn("PCG", result.missing[0].suggested_doc)
        self.assertEqual(
            result.missing[1].suggested_doc,
            "States the theorem `visible`.",
        )

    def test_write_preserves_crlf_and_attaches_docs_before_attributes(self) -> None:
        path = self.write(
            "Wrapped.lean",
            """import Mathlib

omit x in
@[simp,
  norm_num]
theorem wrapped : True := by
  trivial
""",
            newline="\r\n",
        )
        before = path.read_bytes()
        result = self.audit()

        changed = audit_lean_docs.write_plans(result.plans)
        after_first = path.read_bytes()
        second = self.audit()
        changed_again = audit_lean_docs.write_plans(second.plans)

        self.assertEqual(changed, [str(path)])
        self.assertEqual(changed_again, [])
        self.assertNotEqual(before, after_first)
        self.assertNotIn(b"\n", after_first.replace(b"\r\n", b""))
        text = after_first.decode("utf-8")
        self.assertIn(
            "omit x in\r\n"
            "/-- States the theorem `wrapped`. -/\r\n"
            "@[simp,\r\n"
            "  norm_num]\r\n"
            "theorem wrapped",
            text,
        )
        self.assertTrue(second.ok)
        self.assertEqual(second.missing, [])

    def test_blank_line_prevents_reusing_the_previous_declarations_attributes(self) -> None:
        path = self.write(
            "Adjacent.lean",
            """import Mathlib
/-! Adjacent declarations. -/

/-- States the theorem `first`. -/
@[simp] theorem first : True := by trivial

@[simp] theorem second : True := by trivial
""",
        )

        first = self.audit()
        audit_lean_docs.write_plans(first.plans)
        text = path.read_text(encoding="utf-8")
        second = self.audit()

        self.assertIn(
            "@[simp] theorem first : True := by trivial\n\n"
            "/-- States the theorem `second`. -/\n"
            "@[simp] theorem second",
            text,
        )
        self.assertTrue(second.ok)

    def test_manifest_layout_and_allowlist_are_future_proof(self) -> None:
        self.write(
            "LocalClassFieldTheory/Alpha.lean",
            "/-! Alpha module. -/\n/-- Defines `x`. -/\ndef x := 1\n",
        )
        self.write(
            "ProCGroups/Beta.lean",
            "/-! Beta module. -/\n/-- Defines `y`. -/\ndef y := 2\n",
        )
        manifest = self.root.parent / f"{self.root.name}-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "modules": ["Alpha", "Beta", "Missing"],
                    "layout": {
                        "local_class_field_theory": str(
                            self.root / "LocalClassFieldTheory"
                        ),
                        "pro_c_groups": str(self.root / "ProCGroups"),
                    },
                }
            ),
            encoding="utf-8",
        )
        allowlist = self.root.parent / f"{self.root.name}-allowlist.txt"
        allowlist.write_text("Alpha\nMissing\n", encoding="utf-8")
        self.addCleanup(manifest.unlink)
        self.addCleanup(allowlist.unlink)

        specs, issues = audit_lean_docs.discover_sources(
            self.root,
            manifest_path=manifest,
            allowlist_path=allowlist,
        )

        self.assertEqual([spec.module for spec in specs], ["Alpha"])
        self.assertEqual(
            [(issue.category, issue.module) for issue in issues],
            [("missing_module_file", "Missing")],
        )

    def test_quality_checks_find_only_high_confidence_categories(self) -> None:
        self.write(
            "Wrong.lean",
            """import Mathlib
/-! Documentation for module `Other`.

TODO: explain the LCFT material. â€™
-/

/-- The theorem `copied_name` is useful. -/
theorem actual_name : True := by trivial
""",
        )

        result = self.audit()
        categories = [issue.category for issue in result.issues]

        self.assertEqual(
            sorted(categories),
            sorted(
                [
                    "forbidden_abbreviation",
                    "mismatched_doc_name",
                    "mismatched_doc_name",
                    "mojibake",
                    "placeholder",
                ]
            ),
        )
        self.assertEqual(result.missing, [])

    def test_mathematical_names_and_negated_placeholder_are_not_mismatches(self) -> None:
        self.write(
            "Precise.lean",
            """import Mathlib
/-! Precise module docs. -/

/-- The class `u - 1` is equivariant; this is not a compatibility placeholder. -/
theorem equivariant : True := by trivial

/-- The class `[1+a]` is trivial exactly in the stated case. -/
theorem trivialClass : True := by trivial
""",
        )

        result = self.audit()

        self.assertEqual(result.missing, [])
        self.assertEqual(result.issues, [])

    def test_check_fails_but_default_dry_run_succeeds(self) -> None:
        self.write("Gap.lean", "def uncovered := 1\n")

        base = dict(
            source_root=self.root,
            manifest=None,
            module_allowlist=None,
            module=[],
            report=None,
            format="json",
            max_examples=20,
        )
        dry_payload, dry_exit = audit_lean_docs.run(
            Namespace(**base, write=False, check=False)
        )
        check_payload, check_exit = audit_lean_docs.run(
            Namespace(**base, write=False, check=True)
        )

        self.assertEqual(dry_exit, 0)
        self.assertEqual(check_exit, 1)
        self.assertFalse(dry_payload["ok"])
        self.assertEqual(dry_payload["summary"], check_payload["summary"])

    def test_explicit_write_reaudits_and_is_idempotent(self) -> None:
        path = self.write("Write.lean", "def publicValue := 1\n")
        arguments = Namespace(
            source_root=self.root,
            manifest=None,
            module_allowlist=None,
            module=[],
            report=None,
            format="json",
            max_examples=20,
            write=True,
            check=False,
        )

        first, first_exit = audit_lean_docs.run(arguments)
        first_bytes = path.read_bytes()
        second, second_exit = audit_lean_docs.run(arguments)

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertTrue(first["ok"])
        self.assertEqual(first["summary"]["planned_insertions"], 2)
        self.assertEqual(len(first["changed_files"]), 1)
        self.assertEqual(second["summary"]["planned_insertions"], 0)
        self.assertEqual(second["changed_files"], [])
        self.assertEqual(path.read_bytes(), first_bytes)


if __name__ == "__main__":
    unittest.main()
