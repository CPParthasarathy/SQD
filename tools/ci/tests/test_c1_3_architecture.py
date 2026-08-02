"""Host tests for the C1.3 architecture contract verifier."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

VERIFIER_RELATIVE_PATH = Path(
    "tools/scripts/C1.3_Verify_Architecture_Contract.ps1"
)

CONTRACT_RELATIVE_PATH = Path(
    "tools/ci/c1_architecture_contract.json"
)

SOURCE_CONTRACT_RELATIVE_PATH = Path(
    "tools/ci/c1_2_component_contract.json"
)

C11_DOCUMENT_RELATIVE_PATH = Path(
    "docs/phase-c/C1.1_System_Architecture.md"
)

C12_DOCUMENT_RELATIVE_PATH = Path(
    "docs/phase-c/C1.2_Component_Interface_and_Runtime_Contracts.md"
)

REVIEW_DOCUMENT_RELATIVE_PATH = Path(
    "docs/phase-c/C1.3_Architecture_Review_and_Gate.md"
)

BASELINE_COPY_PATHS = [
    C11_DOCUMENT_RELATIVE_PATH,
    C12_DOCUMENT_RELATIVE_PATH,
    SOURCE_CONTRACT_RELATIVE_PATH,
    REVIEW_DOCUMENT_RELATIVE_PATH,
    CONTRACT_RELATIVE_PATH,
    VERIFIER_RELATIVE_PATH,
]

CONTROLLED_TEXT_FILES = [
    REPOSITORY_ROOT / REVIEW_DOCUMENT_RELATIVE_PATH,
    REPOSITORY_ROOT / CONTRACT_RELATIVE_PATH,
    REPOSITORY_ROOT / VERIFIER_RELATIVE_PATH,
    Path(__file__).resolve(),
]


def find_powershell() -> str:
    """Return a PowerShell executable suitable for host tests."""

    for candidate in (
        "pwsh",
        "pwsh.exe",
        "powershell.exe",
        "powershell",
    ):
        executable = shutil.which(candidate)

        if executable is not None:
            return executable

    raise RuntimeError(
        "PowerShell is required for C1.3 verifier host tests."
    )


POWERSHELL = find_powershell()


def run_command(
    arguments: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run a controlled subprocess and capture combined output."""

    return subprocess.run(
        arguments,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def require_command_success(
    result: subprocess.CompletedProcess[str],
    description: str,
) -> None:
    """Raise a diagnostic error when a setup command fails."""

    if result.returncode == 0:
        return

    raise RuntimeError(
        f"{description} failed with exit code "
        f"{result.returncode}:\n{result.stdout}"
    )


def write_json(path: Path, value: object) -> None:
    """Write deterministic UTF-8 LF JSON."""

    text = json.dumps(
        value,
        indent=4,
        ensure_ascii=False,
    )

    path.write_text(
        text + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_json(path: Path) -> object:
    """Load a UTF-8 JSON document."""

    return json.loads(path.read_text(encoding="utf-8"))


def create_component_paths(repository_root: Path) -> None:
    """Create all non-planned component paths required by the verifier."""

    contract = load_json(
        repository_root / CONTRACT_RELATIVE_PATH
    )

    if not isinstance(contract, dict):
        raise RuntimeError("C1.3 contract must be a JSON object.")

    components = contract.get("components")

    if not isinstance(components, list):
        raise RuntimeError(
            "C1.3 contract components must be a list."
        )

    for component in components:
        if not isinstance(component, dict):
            raise RuntimeError(
                "C1.3 component records must be objects."
            )

        if component.get("implementation_status") == "planned":
            continue

        component_path = component.get("path")

        if not isinstance(component_path, str):
            raise RuntimeError(
                "C1.3 component path must be a string."
            )

        (
            repository_root / Path(component_path)
        ).mkdir(
            parents=True,
            exist_ok=True,
        )


def initialize_git_repository(repository_root: Path) -> None:
    """Create a deterministic isolated Git baseline."""

    commands = [
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "C1.3 Host Tests"],
        [
            "git",
            "config",
            "user.email",
            "c1.3-host-tests@example.invalid",
        ],
        ["git", "config", "core.autocrlf", "false"],
        ["git", "config", "core.eol", "lf"],
        ["git", "add", "."],
        [
            "git",
            "commit",
            "--quiet",
            "-m",
            "test: create isolated C1.3 baseline",
        ],
    ]

    for command in commands:
        result = run_command(
            command,
            cwd=repository_root,
        )

        require_command_success(
            result,
            " ".join(command),
        )


@contextmanager
def isolated_repository() -> Iterator[Path]:
    """Yield a disposable repository containing the C1.3 baseline."""

    with tempfile.TemporaryDirectory() as directory:
        repository_root = Path(directory) / "repository"
        repository_root.mkdir(parents=True)

        for relative_path in BASELINE_COPY_PATHS:
            source_path = REPOSITORY_ROOT / relative_path
            target_path = repository_root / relative_path

            target_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            shutil.copy2(
                source_path,
                target_path,
            )

        create_component_paths(repository_root)
        initialize_git_repository(repository_root)

        yield repository_root


def run_verifier(
    repository_root: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute the verifier against an isolated repository."""

    environment = os.environ.copy()
    environment["SQD_C13_REPO_ROOT"] = str(repository_root)

    return subprocess.run(
        [
            POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(
                repository_root / VERIFIER_RELATIVE_PATH
            ),
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def mutate_contract(
    repository_root: Path,
    mutation,
) -> None:
    """Apply a test mutation to the isolated C1.3 contract."""

    contract_path = (
        repository_root / CONTRACT_RELATIVE_PATH
    )

    contract = load_json(contract_path)

    if not isinstance(contract, dict):
        raise RuntimeError("C1.3 contract must be an object.")

    mutation(contract)
    write_json(contract_path, contract)


def get_component(
    contract: dict[str, object],
    component_id: str,
) -> dict[str, object]:
    """Return one component record by identifier."""

    components = contract.get("components")

    if not isinstance(components, list):
        raise RuntimeError("components must be a list.")

    matches = [
        component
        for component in components
        if isinstance(component, dict)
        and component.get("id") == component_id
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one component '{component_id}'."
        )

    return matches[0]


def evidence_files(repository_root: Path) -> list[Path]:
    """Return generated C1.3 evidence files."""

    evidence_directory = (
        repository_root
        / "verification"
        / "c1_3_architecture"
    )

    if not evidence_directory.is_dir():
        return []

    return sorted(
        evidence_directory.glob(
            "C1.3_verification_result_*.json"
        )
    )


class C13TextFileTests(unittest.TestCase):
    """Validate C1.3 controlled text-file encoding."""

    def test_c1_3_files_use_utf8_lf_and_final_newline(
        self,
    ) -> None:
        for path in CONTROLLED_TEXT_FILES:
            with self.subTest(path=path):
                data = path.read_bytes()

                self.assertFalse(
                    data.startswith(b"\xef\xbb\xbf"),
                    f"{path} contains a UTF-8 BOM.",
                )

                self.assertNotIn(
                    b"\r",
                    data,
                    f"{path} is not LF-only.",
                )

                self.assertTrue(
                    data.endswith(b"\n"),
                    f"{path} lacks a final newline.",
                )

                data.decode("utf-8")


class C13ArchitectureVerifierTests(unittest.TestCase):
    """Validate positive and negative C1.3 verifier behavior."""

    def assert_verifier_rejects(
        self,
        repository_root: Path,
        expected_marker: str,
    ) -> None:
        result = run_verifier(repository_root)

        self.assertNotEqual(
            0,
            result.returncode,
            result.stdout,
        )

        self.assertIn(
            expected_marker,
            result.stdout,
        )

        generated_evidence = evidence_files(
            repository_root
        )

        self.assertEqual(
            1,
            len(generated_evidence),
            generated_evidence,
        )

        evidence = load_json(generated_evidence[0])

        self.assertIsInstance(evidence, dict)
        self.assertEqual(
            "FAIL",
            evidence["OverallResult"],
        )

    def test_repository_contract_passes(self) -> None:
        with isolated_repository() as repository_root:
            result = run_verifier(repository_root)

            self.assertEqual(
                0,
                result.returncode,
                result.stdout,
            )

            self.assertIn(
                "C1.3 architecture contract: PASS",
                result.stdout,
            )

            generated_evidence = evidence_files(
                repository_root
            )

            self.assertEqual(
                1,
                len(generated_evidence),
                generated_evidence,
            )

            evidence = load_json(generated_evidence[0])

            self.assertIsInstance(evidence, dict)
            self.assertEqual(
                "PASS",
                evidence["OverallResult"],
            )

            checks = evidence["Checks"]

            self.assertEqual(11, len(checks))
            self.assertTrue(
                all(
                    check["Status"] == "PASS"
                    for check in checks
                )
            )

    def test_dependency_cycle_is_rejected(self) -> None:
        with isolated_repository() as repository_root:
            def add_cycle(
                contract: dict[str, object],
            ) -> None:
                board = get_component(
                    contract,
                    "board",
                )

                dependencies = board.get(
                    "permitted_dependencies"
                )

                if not isinstance(dependencies, list):
                    raise RuntimeError(
                        "board dependencies must be a list."
                    )

                dependencies.append("app")

            mutate_contract(
                repository_root,
                add_cycle,
            )

            self.assert_verifier_rejects(
                repository_root,
                (
                    "FAIL: complete permitted-dependency "
                    "graph is acyclic"
                ),
            )

    def test_upward_dependency_is_rejected(self) -> None:
        with isolated_repository() as repository_root:
            def add_upward_dependency(
                contract: dict[str, object],
            ) -> None:
                build_metadata = get_component(
                    contract,
                    "build_metadata",
                )

                dependencies = build_metadata.get(
                    "permitted_dependencies"
                )

                if not isinstance(dependencies, list):
                    raise RuntimeError(
                        "build_metadata dependencies "
                        "must be a list."
                    )

                dependencies.append("board")

            mutate_contract(
                repository_root,
                add_upward_dependency,
            )

            self.assert_verifier_rejects(
                repository_root,
                (
                    "FAIL: all dependencies point to "
                    "a larger layer rank"
                ),
            )

    def test_overlapping_resource_ownership_is_rejected(
        self,
    ) -> None:
        with isolated_repository() as repository_root:
            def add_overlapping_claim(
                contract: dict[str, object],
            ) -> None:
                storage = get_component(
                    contract,
                    "storage",
                )

                owns = storage.get("owns")

                if not isinstance(owns, list):
                    raise RuntimeError(
                        "storage owns must be a list."
                    )

                owns.append(
                    "product_orchestration_state"
                )

            mutate_contract(
                repository_root,
                add_overlapping_claim,
            )

            self.assert_verifier_rejects(
                repository_root,
                (
                    "FAIL: every mutable resource has "
                    "exactly one aligned owner"
                ),
            )

    def test_source_contract_blob_drift_is_rejected(
        self,
    ) -> None:
        with isolated_repository() as repository_root:
            source_document = (
                repository_root
                / C11_DOCUMENT_RELATIVE_PATH
            )

            original_text = source_document.read_text(
                encoding="utf-8"
            )

            source_document.write_text(
                original_text
                + "\nTest-only accepted-source drift.\n",
                encoding="utf-8",
                newline="\n",
            )

            add_result = run_command(
                [
                    "git",
                    "add",
                    str(C11_DOCUMENT_RELATIVE_PATH),
                ],
                cwd=repository_root,
            )

            require_command_success(
                add_result,
                "git add source drift",
            )

            commit_result = run_command(
                [
                    "git",
                    "commit",
                    "--quiet",
                    "-m",
                    "test: introduce accepted-source drift",
                ],
                cwd=repository_root,
            )

            require_command_success(
                commit_result,
                "git commit source drift",
            )

            self.assert_verifier_rejects(
                repository_root,
                (
                    "FAIL: accepted source paths "
                    "and blobs resolve"
                ),
            )


if __name__ == "__main__":
    unittest.main()
