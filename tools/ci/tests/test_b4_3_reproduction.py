"""Host-side tests for the B4.3 reproduction and gate contract."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_PATH = REPO_ROOT / "tools" / "ci" / "verify_b4_3.py"
CONTRACT_PATH = (
    REPO_ROOT
    / "tools"
    / "ci"
    / "b4_3_reproduction_contract.json"
)
RECORD_PATH = (
    REPO_ROOT
    / "docs"
    / "phase-b"
    / "B4.3_Clean_Checkout_To_Flash_and_Cluster_B_Gate.md"
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
            f"Unable to load module: {module_path}"
        )
    module = importlib.util.module_from_spec(
        spec
    )
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = load_module(
    "sqd_b43_verify_tests",
    VERIFY_PATH,
)


def sha256(path: Path) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


class B43TextFileTests(unittest.TestCase):
    """Verify controlled text-file encoding."""

    def test_b43_text_files_use_utf8_lf_and_final_newline(
        self,
    ) -> None:
        for path in (
            VERIFY_PATH,
            CONTRACT_PATH,
            RECORD_PATH,
            Path(__file__).resolve(),
        ):
            data = path.read_bytes()
            self.assertNotIn(b"\r\n", data)
            self.assertTrue(data.endswith(b"\n"))
            data.decode("utf-8")


class B43RepositoryContractTests(unittest.TestCase):
    """Verify positive and negative repository contracts."""

    def test_repository_contract_passes(self) -> None:
        contract, lifecycle = VERIFY.validate_repository(
            REPO_ROOT
        )
        self.assertEqual(contract["work_package"], "B4.3")
        self.assertIn(
            lifecycle["status"],
            {"In Progress", "Accepted"},
        )

    def test_rejects_incorrect_parent_baseline(self) -> None:
        contract = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )
        contract["parent_baseline"] = "0" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(
                json.dumps(contract, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(
                VERIFY.VerificationError
            ):
                VERIFY.validate_contract(path)


class B43ManifestTests(unittest.TestCase):
    """Verify evidence and repeatability behavior."""

    def create_manifest(
        self,
        root: Path,
        *,
        pass_id: str,
        clone_root: str,
        build_directory: str,
        metadata_commit: str | None = None,
    ) -> Path:
        contract = VERIFY.validate_contract(CONTRACT_PATH)
        evidence_root = root / "evidence"
        evidence_root.mkdir(parents=True)

        files: list[dict[str, object]] = []
        for index, role in enumerate(
            contract["required_evidence_roles"],
            start=1,
        ):
            relative_path = f"{index:02d}_{role}.txt"
            path = evidence_root / relative_path
            path.write_text(
                f"{role}\n",
                encoding="utf-8",
                newline="\n",
            )
            files.append(
                {
                    "role": role,
                    "path": relative_path,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

        checksum_lines = [
            f"{record['sha256']}  {record['path']}"
            for record in files
        ]
        (evidence_root / "SHA256SUMS.txt").write_text(
            "\n".join(checksum_lines) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        source_commit = "a" * 40
        metadata = {
            "product_version": "0.1.0-dev.0",
            "git_commit": (
                metadata_commit
                if metadata_commit is not None
                else source_commit
            ),
            "git_commit_short": "a" * 12,
            "git_dirty": "false",
            "source_timestamp_utc": "2026-07-26T07:00:00Z",
            "build_timestamp_utc": "2026-07-26T07:00:00Z",
            "build_profile": "validation",
            "target": "esp32s3",
            "idf_version": "v6.0.2",
            "compiler_version": "test compiler",
            "hardware_compatibility": (
                "heltec-wifi-lora-32-v3"
            ),
            "secure_version": "0",
            "elf_sha256": "b" * 64,
        }
        marker_map = {
            marker: True
            for marker in contract["required_serial_markers"]
        }
        manifest = {
            "schema_version": 1,
            "work_package": "B4.3",
            "operation": (
                "clean-checkout-to-flash-reproduction"
            ),
            "status": "PASS",
            "pass_id": pass_id,
            "source": {
                "repository": contract["repository"],
                "parent_baseline": contract["parent_baseline"],
                "commit": source_commit,
                "branch": f"b4.3-reproduction-{pass_id}",
            },
            "cleanroom": {
                "root": str(root / "cleanroom"),
                "clone_root": clone_root,
                "clone_created": True,
                "existing_directory_reused": False,
                "existing_build_reused": False,
                "tracked_tree_clean_before": True,
                "tracked_tree_clean_after": True,
            },
            "toolchain": dict(contract["toolchain"]),
            "build": {
                "profile": "validation",
                "status": "PASS",
                "directory": build_directory,
                "application_sha256": "c" * 64,
            },
            "device": {
                "status": "PASS",
                "port": "COM3",
                "hardware_compatibility": (
                    "heltec-wifi-lora-32-v3"
                ),
                "erase_status": "PASS",
                "flash_status": "PASS",
            },
            "monitor": {
                "status": "PASS",
                "fatal_markers": 0,
                "heartbeat_records": 3,
                "required_markers": marker_map,
                "metadata": metadata,
            },
            "evidence": {
                "root": "evidence",
                "checksums": "SHA256SUMS.txt",
                "files": files,
            },
        }
        manifest_path = root / f"{pass_id}.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return manifest_path

    def test_two_independent_manifests_pass(self) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.create_manifest(
                root / "first",
                pass_id="pass-1",
                clone_root=r"D:\cleanroom\pass1\clone",
                build_directory=(
                    r"D:\cleanroom\pass1\worktree\build"
                ),
            )
            second = self.create_manifest(
                root / "second",
                pass_id="pass-2",
                clone_root=r"D:\cleanroom\pass2\clone",
                build_directory=(
                    r"D:\cleanroom\pass2\worktree\build"
                ),
            )
            manifests = [
                VERIFY.validate_manifest(first, contract),
                VERIFY.validate_manifest(second, contract),
            ]
            VERIFY.validate_repeatability(
                manifests,
                contract,
            )

    def test_rejects_reused_clone_root(self) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = self.create_manifest(
                root / "first",
                pass_id="pass-1",
                clone_root=r"D:\cleanroom\shared\clone",
                build_directory=(
                    r"D:\cleanroom\pass1\worktree\build"
                ),
            )
            second = self.create_manifest(
                root / "second",
                pass_id="pass-2",
                clone_root=r"D:\cleanroom\shared\clone",
                build_directory=(
                    r"D:\cleanroom\pass2\worktree\build"
                ),
            )
            manifests = [
                VERIFY.validate_manifest(first, contract),
                VERIFY.validate_manifest(second, contract),
            ]
            with self.assertRaises(
                VERIFY.VerificationError
            ):
                VERIFY.validate_repeatability(
                    manifests,
                    contract,
                )

    def test_rejects_firmware_commit_mismatch(self) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = self.create_manifest(
                Path(directory),
                pass_id="pass-1",
                clone_root=r"D:\cleanroom\pass1\clone",
                build_directory=(
                    r"D:\cleanroom\pass1\worktree\build"
                ),
                metadata_commit="d" * 40,
            )
            with self.assertRaises(
                VERIFY.VerificationError
            ):
                VERIFY.validate_manifest(
                    manifest_path,
                    contract,
                )


if __name__ == "__main__":
    unittest.main()
