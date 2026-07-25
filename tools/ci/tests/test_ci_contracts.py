"""Host-side tests for the B4.1 CI tooling contracts."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]

CHECK_FORMAT_PATH = (
    REPO_ROOT / "tools" / "ci" / "check_format.py"
)

CHECK_CLANG_TIDY_PATH = (
    REPO_ROOT / "tools" / "ci" / "check_clang_tidy.py"
)

CI_TEXT_FILES = (
    REPO_ROOT / ".clang-format",
    REPO_ROOT / ".clang-tidy",
    REPO_ROOT / ".editorconfig",
    REPO_ROOT / "tools" / "ci" / "requirements-ci.txt",
    CHECK_FORMAT_PATH,
    CHECK_CLANG_TIDY_PATH,
    REPO_ROOT / "tools" / "ci" / "run_host_tests.py",
    REPO_ROOT / "tools" / "ci" / "tests" / "__init__.py",
    REPO_ROOT
    / "tools"
    / "ci"
    / "tests"
    / "test_ci_contracts.py",
)


def load_module(
    module_name: str,
    module_path: Path,
) -> ModuleType:
    """Load a repository Python file without requiring a package."""

    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to create an import specification for {module_path}"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


CHECK_FORMAT = load_module(
    "sqd_b41_check_format",
    CHECK_FORMAT_PATH,
)

CHECK_CLANG_TIDY = load_module(
    "sqd_b41_check_clang_tidy",
    CHECK_CLANG_TIDY_PATH,
)


def run_git(
    repo_root: Path,
    arguments: Sequence[str],
) -> str:
    """Run Git in a temporary test repository."""

    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip()

        raise AssertionError(
            f"Git command failed: git {' '.join(arguments)}: "
            f"{diagnostic}"
        )

    return result.stdout


def initialize_git_repository(repo_root: Path) -> None:
    """Create a minimal isolated Git repository."""

    repo_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_git(
        repo_root,
        ("init", "--quiet"),
    )

    run_git(
        repo_root,
        (
            "config",
            "user.name",
            "SQD CI Test",
        ),
    )

    run_git(
        repo_root,
        (
            "config",
            "user.email",
            "ci-test@example.invalid",
        ),
    )


def write_text(
    path: Path,
    content: str,
) -> None:
    """Write deterministic UTF-8/LF test data."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )


class CiTextContractTests(unittest.TestCase):
    """Verify deterministic encoding and line-ending contracts."""

    def test_ci_text_files_use_utf8_lf_and_final_newline(
        self,
    ) -> None:
        for path in CI_TEXT_FILES:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                self.assertTrue(
                    path.is_file(),
                    f"Required CI file is missing: {path}",
                )

                data = path.read_bytes()

                self.assertFalse(
                    data.startswith(b"\xef\xbb\xbf"),
                    f"Unexpected UTF-8 BOM: {path}",
                )

                self.assertNotIn(
                    b"\r",
                    data,
                    f"Non-LF line ending detected: {path}",
                )

                self.assertTrue(
                    data.endswith(b"\n"),
                    f"Missing final newline: {path}",
                )


class FormatSourceDiscoveryTests(unittest.TestCase):
    """Verify formatting-gate source enumeration."""

    def test_discovers_tracked_and_nonignored_untracked_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory).resolve()

            initialize_git_repository(repo_root)

            write_text(
                repo_root / ".gitignore",
                "verification/ignored.c\n",
            )

            write_text(
                repo_root / "components" / "source.c",
                "int component_value(void) { return 1; }\n",
            )

            write_text(
                repo_root
                / "components"
                / "include"
                / "source.h",
                "int component_value(void);\n",
            )

            write_text(
                repo_root / "main" / "main.c",
                "int main(void) { return 0; }\n",
            )

            write_text(
                repo_root
                / "verification"
                / "pending.cpp",
                "int pending_value = 1;\n",
            )

            write_text(
                repo_root
                / "verification"
                / "ignored.c",
                "int ignored_value = 1;\n",
            )

            write_text(
                repo_root / "docs" / "example.c",
                "int documentation_value = 1;\n",
            )

            run_git(
                repo_root,
                (
                    "add",
                    ".gitignore",
                    "components",
                    "main",
                ),
            )

            discovered = CHECK_FORMAT.discover_source_files(
                repo_root
            )

            discovered_paths = [
                path.as_posix()
                for path in discovered
            ]

            self.assertEqual(
                discovered_paths,
                [
                    "components/include/source.h",
                    "components/source.c",
                    "main/main.c",
                    "verification/pending.cpp",
                ],
            )

    def test_rejects_repository_without_owned_sources(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory).resolve()

            initialize_git_repository(repo_root)

            with self.assertRaises(
                CHECK_FORMAT.FormatCheckError
            ):
                CHECK_FORMAT.discover_source_files(repo_root)


class ClangTidyCompilationDatabaseTests(unittest.TestCase):
    """Verify Clang-Tidy compilation-database filtering."""

    def test_filters_to_repository_owned_translation_units(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory).resolve()
            repo_root = temporary_root / "repo"
            database_directory = repo_root / "build"

            database_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

            component_source = (
                repo_root / "components" / "component.c"
            )

            main_source = (
                repo_root / "main" / "main.cpp"
            )

            verification_source = (
                repo_root
                / "verification"
                / "case"
                / "verify.c"
            )

            header_file = (
                repo_root
                / "components"
                / "include"
                / "component.h"
            )

            documentation_source = (
                repo_root / "docs" / "example.c"
            )

            external_source = (
                temporary_root / "external.c"
            )

            for source_path in (
                component_source,
                main_source,
                verification_source,
                header_file,
                documentation_source,
                external_source,
            ):
                write_text(
                    source_path,
                    "int value = 0;\n",
                )

            database_entries = [
                {
                    "directory": str(repo_root),
                    "file": "components/component.c",
                    "command": "cc -c components/component.c",
                },
                {
                    "directory": str(repo_root),
                    "file": str(main_source),
                    "command": f"c++ -c {main_source}",
                },
                {
                    "directory": str(repo_root),
                    "file": "verification/case/verify.c",
                    "command": (
                        "cc -c verification/case/verify.c"
                    ),
                },
                {
                    "directory": str(repo_root),
                    "file": "components/include/component.h",
                    "command": (
                        "cc -c components/include/component.h"
                    ),
                },
                {
                    "directory": str(repo_root),
                    "file": "docs/example.c",
                    "command": "cc -c docs/example.c",
                },
                {
                    "directory": str(temporary_root),
                    "file": str(external_source),
                    "command": f"cc -c {external_source}",
                },
            ]

            database_file = (
                database_directory / "compile_commands.json"
            )

            write_text(
                database_file,
                json.dumps(
                    database_entries,
                    indent=2,
                )
                + "\n",
            )

            translation_units = (
                CHECK_CLANG_TIDY.load_compilation_entries(
                    database_file,
                    database_directory.resolve(),
                    repo_root.resolve(),
                )
            )

            relative_sources = sorted(
                source_path.relative_to(
                    repo_root
                ).as_posix()
                for source_path in translation_units
            )

            self.assertEqual(
                relative_sources,
                [
                    "components/component.c",
                    "main/main.cpp",
                    "verification/case/verify.c",
                ],
            )

            for resolved_database_directory in (
                translation_units.values()
            ):
                self.assertEqual(
                    resolved_database_directory,
                    database_directory.resolve(),
                )

    def test_resolves_database_directory_and_file_arguments(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_directory = (
                Path(temporary_directory).resolve()
            )

            database_file = (
                database_directory / "compile_commands.json"
            )

            write_text(
                database_file,
                "[]\n",
            )

            from_directory = (
                CHECK_CLANG_TIDY.resolve_compilation_database(
                    database_directory
                )
            )

            from_file = (
                CHECK_CLANG_TIDY.resolve_compilation_database(
                    database_file
                )
            )

            expected = (
                database_file.resolve(),
                database_directory.resolve(),
            )

            self.assertEqual(
                from_directory,
                expected,
            )

            self.assertEqual(
                from_file,
                expected,
            )

    def test_rejects_incorrect_database_filename(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            incorrect_file = (
                Path(temporary_directory).resolve()
                / "commands.json"
            )

            write_text(
                incorrect_file,
                "[]\n",
            )

            with self.assertRaises(
                CHECK_CLANG_TIDY.StaticAnalysisError
            ):
                CHECK_CLANG_TIDY.resolve_compilation_database(
                    incorrect_file
                )

    def test_rejects_database_without_owned_translation_units(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = (
                Path(temporary_directory).resolve()
                / "repo"
            )

            database_directory = repo_root / "build"
            documentation_source = (
                repo_root / "docs" / "example.c"
            )

            write_text(
                documentation_source,
                "int documentation_value = 0;\n",
            )

            database_file = (
                database_directory / "compile_commands.json"
            )

            write_text(
                database_file,
                json.dumps(
                    [
                        {
                            "directory": str(repo_root),
                            "file": "docs/example.c",
                            "command": "cc -c docs/example.c",
                        }
                    ],
                    indent=2,
                )
                + "\n",
            )

            with self.assertRaises(
                CHECK_CLANG_TIDY.StaticAnalysisError
            ):
                CHECK_CLANG_TIDY.collect_translation_units(
                    [database_directory],
                    repo_root.resolve(),
                )


if __name__ == "__main__":
    unittest.main()
