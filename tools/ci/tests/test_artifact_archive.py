"""Host-side tests for the B4.2 artifact archive contract."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_PATH = REPO_ROOT / "tools" / "ci" / "artifact_archive.py"
VERIFY_PATH = REPO_ROOT / "tools" / "ci" / "verify_b4_2.py"
PROFILE_WRAPPER_PATH = (
    REPO_ROOT / "tools" / "ci" / "run_profile_build.ps1"
)
CONTRACT_PATH = (
    REPO_ROOT / "tools" / "ci" / "artifact_archive_contract.json"
)
RECORD_PATH = (
    REPO_ROOT
    / "docs"
    / "phase-b"
    / "B4.2_Artifact_Archive_and_Traceability.md"
)


def load_module(module_name: str, module_path: Path) -> ModuleType:
    """Load a repository Python file without requiring a package."""

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ARCHIVE = load_module("sqd_b42_archive_tests", ARCHIVE_PATH)
VERIFY = load_module("sqd_b42_verify_tests", VERIFY_PATH)

GITHUB_ENVIRONMENT_VARIABLES = (
    "GITHUB_ACTIONS",
    "GITHUB_WORKFLOW",
    "GITHUB_JOB",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_EVENT_NAME",
    "GITHUB_REF",
    "GITHUB_HEAD_REF",
    "GITHUB_BASE_REF",
    "GITHUB_SHA",
    "GITHUB_REPOSITORY",
)


def github_environment(**overrides: str):
    """Provide deterministic GitHub metadata for an archive fixture."""

    values = {
        name: ""
        for name in GITHUB_ENVIRONMENT_VARIABLES
    }
    values.update(overrides)
    return mock.patch.dict(os.environ, values)


class B42TextFileTests(unittest.TestCase):
    """Verify deterministic encoding for B4.2-controlled text files."""

    def test_b42_text_files_use_utf8_lf_and_final_newline(self) -> None:
        paths = (
            ARCHIVE_PATH,
            CONTRACT_PATH,
            VERIFY_PATH,
            PROFILE_WRAPPER_PATH,
            RECORD_PATH,
            Path(__file__).resolve(),
        )
        for path in paths:
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", data)
                self.assertTrue(data.endswith(b"\n"))
                data.decode("utf-8")

    def test_profile_wrapper_captures_native_stderr(self) -> None:
        wrapper_text = PROFILE_WRAPPER_PATH.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            wrapper_text.count(
                "$PreviousErrorActionPreference = "
                "$ErrorActionPreference"
            ),
            2,
        )
        self.assertGreaterEqual(
            wrapper_text.count(
                '$ErrorActionPreference = "Continue"'
            ),
            2,
        )
        self.assertGreaterEqual(
            wrapper_text.count(
                "$ErrorActionPreference = "
                "$PreviousErrorActionPreference"
            ),
            2,
        )
        self.assertIn(
            "The native exit code remains",
            wrapper_text,
        )




class B42WorktreeCleanupTests(unittest.TestCase):
    def test_profile_wrapper_returns_to_repository_before_cleanup(
        self,
    ) -> None:
        from pathlib import Path

        wrapper_path = (
            Path(__file__).resolve().parents[1]
            / "run_profile_build.ps1"
        )

        wrapper_text = wrapper_path.read_text(
            encoding="utf-8"
        )

        cleanup_marker = (
            'Write-Host '
            '"=== Remove isolated compatibility worktree ==="'
        )

        cleanup_index = wrapper_text.index(
            cleanup_marker
        )

        finally_index = wrapper_text.rfind(
            "finally {",
            0,
            cleanup_index,
        )

        self.assertGreaterEqual(
            finally_index,
            0,
        )

        location_statement = (
            "Set-Location -LiteralPath $ResolvedRepoRoot"
        )

        location_index = wrapper_text.find(
            location_statement,
            finally_index,
            cleanup_index,
        )

        self.assertGreaterEqual(
            location_index,
            0,
        )

        remove_index = wrapper_text.find(
            '"worktree"',
            cleanup_index,
        )

        self.assertGreaterEqual(
            remove_index,
            0,
        )

        self.assertLess(
            location_index,
            remove_index,
        )


class B42VerificationTests(unittest.TestCase):
    """Verify positive and negative archive-matrix behavior."""

    def create_profile_archive(
        self,
        root: Path,
        profile: str,
        source_commit: str,
    ) -> None:
        profile_root = root / profile
        profile_root.mkdir(parents=True)
        ARCHIVE.create_fixture(profile_root)
        debug_evidence = next(
            (profile_root / "evidence").glob(
                "B3.2_debug_build_result_*.json"
            )
        )
        debug_evidence.rename(
            debug_evidence.with_name(
                debug_evidence.name.replace("_debug_", f"_{profile}_")
            )
        )
        values = argparse.Namespace(
            archive_root=profile_root,
            contract=CONTRACT_PATH,
            profile=profile,
            source_repository="CPParthasarathy/SQD",
            source_commit=source_commit,
            hardware_compatibility="heltec-wifi-lora-32-v3",
            idf_version="v6.0.2",
            idf_commit="2" * 40,
        )
        ARCHIVE.finalize(values)

    def test_repository_contract_passes(self) -> None:
        VERIFY.validate_repository(REPO_ROOT)

    def test_complete_profile_matrix_passes(self) -> None:
        source_commit = "1" * 40

        # This fixture represents a local archive. It must not inherit
        # GitHub Actions metadata from the process running the test.
        with github_environment():
            with tempfile.TemporaryDirectory() as temporary_directory:
                archive_root = Path(temporary_directory)
                for profile in VERIFY.PROFILES:
                    self.create_profile_archive(
                        archive_root,
                        profile,
                        source_commit,
                    )
                VERIFY.verify_archive_matrix(
                    REPO_ROOT,
                    archive_root,
                    VERIFY.PROFILES,
                    source_commit,
                )

    def test_missing_profile_archive_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.verify_archive_matrix(
                    REPO_ROOT,
                    Path(temporary_directory),
                    ("production",),
                    "1" * 40,
                )

    def test_incomplete_github_traceability_is_rejected(self) -> None:
        source_commit = "1" * 40
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory)

            # Set only the Actions marker. All other GitHub fields stay
            # empty so the fixture is deterministically incomplete.
            with github_environment(GITHUB_ACTIONS="true"):
                self.create_profile_archive(
                    archive_root,
                    "debug",
                    source_commit,
                )

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.verify_archive_matrix(
                    REPO_ROOT,
                    archive_root,
                    ("debug",),
                    source_commit,
                )


if __name__ == "__main__":
    unittest.main()
