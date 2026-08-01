"""Host tests for the C1.2 component-interface contract."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = REPOSITORY_ROOT / "tools" / "ci" / "verify_c1_2.py"

CONTROLLED_FILES = [
    REPOSITORY_ROOT
    / "docs"
    / "phase-c"
    / "C1.2_Component_Interface_and_Runtime_Contracts.md",
    REPOSITORY_ROOT / "tools" / "ci" / "c1_2_component_contract.json",
    VERIFIER_PATH,
]


def load_verifier() -> ModuleType:
    """Load the C1.2 verifier as a Python module."""
    specification = importlib.util.spec_from_file_location(
        "verify_c1_2",
        VERIFIER_PATH,
    )

    if specification is None or specification.loader is None:
        raise RuntimeError("Could not load the C1.2 verifier module.")

    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class C12TextFileTests(unittest.TestCase):
    """Validate controlled C1.2 text-file encoding."""

    def test_c1_2_files_use_utf8_lf_and_final_newline(self) -> None:
        for path in CONTROLLED_FILES:
            with self.subTest(path=path):
                data = path.read_bytes()

                self.assertFalse(
                    data.startswith(b"\xef\xbb\xbf"),
                    f"{path} contains a UTF-8 BOM.",
                )
                self.assertNotIn(b"\r", data, f"{path} is not LF-only.")
                self.assertTrue(
                    data.endswith(b"\n"),
                    f"{path} lacks a final newline.",
                )
                data.decode("utf-8")


class C12VerificationTests(unittest.TestCase):
    """Validate the repository C1.2 contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def test_repository_contract_passes(self) -> None:
        contract = self.verifier.load_contract(
            self.verifier.CONTRACT_PATH
        )

        result = self.verifier.verify_contract(contract)

        self.assertEqual((14, 12), result)

    def test_resource_owner_must_claim_resource(self) -> None:
        contract = self.verifier.load_contract(
            self.verifier.CONTRACT_PATH
        )
        invalid_contract = copy.deepcopy(contract)
        invalid_contract["mutable_resources"][0]["owner"] = "storage"

        with self.assertRaisesRegex(
            self.verifier.ContractError,
            "must claim resource",
        ):
            self.verifier.verify_contract(invalid_contract)


    def test_unknown_component_dependency_is_rejected(self) -> None:
        contract = self.verifier.load_contract(
            self.verifier.CONTRACT_PATH
        )
        invalid_contract = copy.deepcopy(contract)
        invalid_contract["components"][0]["permitted_dependencies"].append(
            "unknown_component"
        )

        with self.assertRaisesRegex(
            self.verifier.ContractError,
            "references unknown dependency",
        ):
            self.verifier.verify_contract(invalid_contract)

if __name__ == "__main__":
    unittest.main()
