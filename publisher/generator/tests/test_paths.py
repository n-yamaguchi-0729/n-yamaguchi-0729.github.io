from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

import build_site
import generate


class PortablePathTests(unittest.TestCase):
    def make_layout(self, directory: str) -> tuple[Path, Path, Path]:
        workspace = Path(directory) / "Github"
        repo = workspace / "YamaLean4Lib_Generator"
        lean_repo = workspace / "YamaLean4Lib"
        public_repo = workspace / "n-yamaguchi-0729.github.io"
        for path in (repo, lean_repo, public_repo):
            path.mkdir(parents=True)
        for path in (lean_repo, public_repo):
            (path / ".git").mkdir()
        return repo, lean_repo, public_repo

    def test_default_local_paths_are_relative(self) -> None:
        self.assertFalse(build_site.DEFAULT_LEAN_REPOSITORY_MIRROR.is_absolute())
        self.assertFalse(build_site.DEFAULT_PAGES_OUTPUT_ROOT.is_absolute())
        self.assertEqual(
            build_site.DEFAULT_PAGES_OUTPUT_ROOT.name,
            "YamaLean4Lib_pages",
        )
        self.assertTrue(
            build_site.DEFAULT_DOCUMENTATION_URL.endswith(
                "/YamaLean4Lib_pages/"
            )
        )

    def test_relative_config_path_is_anchored_to_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, lean_repo, _ = self.make_layout(directory)
            self.assertEqual(
                build_site.resolve_config_path(repo, "../YamaLean4Lib"),
                lean_repo.resolve(),
            )

    def test_valid_sibling_layout_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, lean_repo, public_repo = self.make_layout(directory)
            build_site.validate_publish_layout(
                repo_root=repo,
                pages_root=lean_repo / "docs",
                published_pages_root=public_repo / "YamaLean4Lib_pages",
                lean_repository_mirror=lean_repo,
                public_site_root=public_repo,
            )

    def test_pages_output_outside_lean_repo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, lean_repo, public_repo = self.make_layout(directory)
            with self.assertRaises(ValueError):
                build_site.validate_publish_layout(
                    repo_root=repo,
                    pages_root=repo.parent / "wrong-output",
                    published_pages_root=public_repo / "YamaLean4Lib_pages",
                    lean_repository_mirror=lean_repo,
                    public_site_root=public_repo,
                )

    def test_non_git_sync_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, lean_repo, public_repo = self.make_layout(directory)
            (lean_repo / ".git").rmdir()
            with self.assertRaises(ValueError):
                build_site.validate_publish_layout(
                    repo_root=repo,
                    pages_root=lean_repo / "docs",
                    published_pages_root=public_repo / "YamaLean4Lib_pages",
                    lean_repository_mirror=lean_repo,
                    public_site_root=public_repo,
                )


class PublicOutputRepositorySafetyTests(unittest.TestCase):
    EXPECTED_ORIGIN = (
        "https://github.com/n-yamaguchi-0729/"
        "n-yamaguchi-0729.github.io.git"
    )

    @staticmethod
    def run_git(repository: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def make_repository(
        self,
        root: Path,
        *,
        origin: str = EXPECTED_ORIGIN,
    ) -> Path:
        repository = root / "public"
        repository.mkdir()
        self.run_git(repository, "init")
        self.run_git(repository, "remote", "add", "origin", origin)
        return repository

    def test_exact_pages_repository_with_https_origin_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(Path(directory))

            self.assertEqual(
                generate.validate_public_output_repository(repository),
                repository.resolve(),
            )

    def test_non_git_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-a-repository"
            output.mkdir()

            with self.assertRaises(generate.DatabaseError):
                generate.validate_public_output_repository(output)

    def test_repository_support_does_not_write_to_non_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "not-a-repository"
            output.mkdir()

            with self.assertRaises(generate.DatabaseError):
                generate.synchronize_repository_support(output)

            self.assertEqual(list(output.iterdir()), [])

    def test_repository_with_wrong_origin_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(
                Path(directory),
                origin="https://github.com/example/not-the-pages-repository.git",
            )

            with self.assertRaisesRegex(
                generate.DatabaseError,
                "unexpected origin",
            ):
                generate.validate_public_output_repository(repository)

    def test_nested_directory_inside_pages_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = self.make_repository(Path(directory))
            nested = repository / "nested"
            nested.mkdir()

            with self.assertRaisesRegex(
                generate.DatabaseError,
                "must be the public repository top-level",
            ):
                generate.validate_public_output_repository(nested)

    def test_linked_worktree_with_git_file_and_ssh_origin_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = self.make_repository(
                root,
                origin=(
                    "git@github.com:n-yamaguchi-0729/"
                    "n-yamaguchi-0729.github.io.git"
                ),
            )
            self.run_git(repository, "config", "user.name", "Generator Tests")
            self.run_git(
                repository,
                "config",
                "user.email",
                "generator-tests@example.invalid",
            )
            (repository / "tracked.txt").write_text("test\n", encoding="utf-8")
            self.run_git(repository, "add", "tracked.txt")
            self.run_git(repository, "commit", "-m", "Initialize test repository")
            worktree = root / "worktree"
            self.run_git(
                repository,
                "worktree",
                "add",
                "-b",
                "pages-worktree-test",
                str(worktree),
            )

            self.assertTrue((worktree / ".git").is_file())
            self.assertEqual(
                generate.validate_public_output_repository(worktree),
                worktree.resolve(),
            )


if __name__ == "__main__":
    unittest.main()
