"""Host tests for the controlled B4.1 GitHub Actions workflow."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[3]

WORKFLOW_PATH = (
    REPO_ROOT / ".github" / "workflows" / "ci.yml"
)

WORKFLOW_CHECK_PATH = (
    REPO_ROOT / "tools" / "ci" / "check_workflow.py"
)


def load_module(
    module_name: str,
    module_path: Path,
) -> ModuleType:
    """Load a repository Python script as a test module."""

    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load module specification: {module_path}"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


CHECK_WORKFLOW = load_module(
    "sqd_b41_check_workflow",
    WORKFLOW_CHECK_PATH,
)


def write_mutated_workflow(
    directory: Path,
    mutation: str,
) -> Path:
    """Write a deterministic workflow mutation."""

    workflow_path = directory / "ci.yml"

    workflow_path.write_text(
        mutation,
        encoding="utf-8",
        newline="\n",
    )

    return workflow_path


class WorkflowFileContractTests(unittest.TestCase):
    """Verify workflow and validator file contracts."""

    def test_workflow_files_use_utf8_lf_and_final_newline(
        self,
    ) -> None:
        for path in (
            WORKFLOW_PATH,
            WORKFLOW_CHECK_PATH,
            Path(__file__).resolve(),
        ):
            with self.subTest(path=path.relative_to(REPO_ROOT)):
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


class WorkflowContractTests(unittest.TestCase):
    """Verify positive and negative workflow behavior."""

    def test_repository_workflow_passes_contract(
        self,
    ) -> None:
        workflow = CHECK_WORKFLOW.validate_workflow(
            WORKFLOW_PATH
        )

        self.assertEqual(
            workflow["name"],
            CHECK_WORKFLOW.EXPECTED_WORKFLOW_NAME,
        )

    def test_rejects_write_permission(
        self,
    ) -> None:
        raw_workflow = WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )

        mutated_workflow = raw_workflow.replace(
            "  contents: read\n",
            "  contents: write\n",
            1,
        )

        self.assertNotEqual(
            mutated_workflow,
            raw_workflow,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            mutation_path = write_mutated_workflow(
                Path(temporary_directory),
                mutated_workflow,
            )

            with self.assertRaises(
                CHECK_WORKFLOW.WorkflowContractError
            ):
                CHECK_WORKFLOW.validate_workflow(
                    mutation_path
                )

    def test_rejects_incomplete_profile_matrix(
        self,
    ) -> None:
        raw_workflow = WORKFLOW_PATH.read_text(
            encoding="utf-8"
        )

        mutated_workflow = raw_workflow.replace(
            "          - production\n",
            "",
            1,
        )

        self.assertNotEqual(
            mutated_workflow,
            raw_workflow,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            mutation_path = write_mutated_workflow(
                Path(temporary_directory),
                mutated_workflow,
            )

            with self.assertRaises(
                CHECK_WORKFLOW.WorkflowContractError
            ):
                CHECK_WORKFLOW.validate_workflow(
                    mutation_path
                )


if __name__ == "__main__":
    unittest.main()
