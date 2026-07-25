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

REPO_ROOT = Path(__file__).resolve().parents[3]
ARCHIVE_PATH = REPO_ROOT / "tools" / "ci" / "artifact_archive.py"
VERIFY_PATH = REPO_ROOT / "tools" / "ci" / "verify_b4_2.py"
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


class B42TextFileTests(unittest.TestCase):
    """Verify deterministic encoding for B4.2-controlled text files."""

    def test_b42_text_files_use_utf8_lf_and_final_newline(self) -> None:
        paths = (
            ARCHIVE_PATH,
            CONTRACT_PATH,
            VERIFY_PATH,
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
            old_actions = os.environ.get("GITHUB_ACTIONS")
            os.environ["GITHUB_ACTIONS"] = "true"
            try:
                self.create_profile_archive(
                    archive_root,
                    "debug",
                    source_commit,
                )
            finally:
                if old_actions is None:
                    os.environ.pop("GITHUB_ACTIONS", None)
                else:
                    os.environ["GITHUB_ACTIONS"] = old_actions
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.verify_archive_matrix(
                    REPO_ROOT,
                    archive_root,
                    ("debug",),
                    source_commit,
                )


if __name__ == "__main__":
    unittest.main()
