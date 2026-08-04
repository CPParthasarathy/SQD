"""Host-side tests for the C2.2 board-support contract."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_PATH = REPO_ROOT / "tools" / "ci" / "verify_c2_2.py"
CONTRACT_PATH = (
    REPO_ROOT / "tools" / "ci" / "c2_2_board_contract.json"
)
DOCUMENT_PATH = (
    REPO_ROOT
    / "docs"
    / "phase-c"
    / "C2.2_Board_Support_Implementation.md"
)


def load_module(module_name: str, module_path: Path) -> ModuleType:
    """Load a repository Python module from its path."""

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


VERIFY = load_module("sqd_c22_verify", VERIFY_PATH)


def write_text(path: Path, content: str) -> None:
    """Write deterministic UTF-8/LF fixture content."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        content,
        encoding="utf-8",
        newline="\n",
    )


def copy_relative(root: Path, relative_path: Path) -> Path:
    """Copy one repository file into an isolated fixture."""

    source = REPO_ROOT / relative_path
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def copy_configuration_fixture(
    root: Path,
    contract: dict,
) -> None:
    """Copy all files consumed by configuration verification."""

    relative_paths = {
        VERIFY.KCONFIG_RELATIVE_PATH,
        VERIFY.CMAKE_RELATIVE_PATH,
        VERIFY.SDKCONFIG_RELATIVE_PATH,
        VERIFY.B32_COMMON_RELATIVE_PATH,
        VERIFY.B32_BUILD_RELATIVE_PATH,
        VERIFY.PROFILE_BUILD_RELATIVE_PATH,
        VERIFY.B43_RELATIVE_PATH,
        VERIFY.WORKFLOW_RELATIVE_PATH,
        VERIFY.B33_BASELINE_RELATIVE_PATH,
    }
    relative_paths.update(
        Path(value)
        for value in contract["active_compatibility_paths"]
    )

    for relative_path in relative_paths:
        copy_relative(root, relative_path)


class C22TextContractTests(unittest.TestCase):
    """Verify controlled C2.2 text-file encoding."""

    def test_c22_text_files_use_utf8_lf_and_final_newline(
        self,
    ) -> None:
        for path in (
            VERIFY_PATH,
            CONTRACT_PATH,
            DOCUMENT_PATH,
            Path(__file__).resolve(),
        ):
            with self.subTest(path=path.relative_to(REPO_ROOT)):
                data = path.read_bytes()
                self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r", data)
                self.assertTrue(data.endswith(b"\n"))
                data.decode("utf-8")


class C22PositiveVerificationTests(unittest.TestCase):
    """Verify the accepted repository and CLI paths."""

    def test_repository_contract_passes(self) -> None:
        contract = VERIFY.validate_repository(
            REPO_ROOT,
            CONTRACT_PATH,
        )
        self.assertEqual(contract["work_package"], "C2.2")
        self.assertEqual(
            len(contract["private_mapping"]["mappings"]),
            17,
        )
        self.assertEqual(
            len(contract["verification_requirements"]),
            25,
        )

    def test_verifier_cli_passes(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VERIFY_PATH),
                "--repo-root",
                str(REPO_ROOT),
            ],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = "\n".join(
            value
            for value in (result.stdout, result.stderr)
            if value
        )
        self.assertEqual(result.returncode, 0, output)
        self.assertIn(
            "PASS: C2.2 board support contract validated.",
            output,
        )


class C22MutationNegativeTests(unittest.TestCase):
    """Verify that controlled contract mutations are rejected."""

    def test_rejects_mutated_compatibility_id(self) -> None:
        contract = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )
        contract["board_identity"]["compatibility_id"] = (
            "heltec-wifi-lora-32-v3"
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            write_text(
                path,
                json.dumps(contract, indent=4) + "\n",
            )
            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_contract(path)

    def test_rejects_public_gpio_type_leak(self) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header_path = copy_relative(
                root,
                VERIFY.PUBLIC_HEADER_RELATIVE_PATH,
            )
            header = header_path.read_text(encoding="utf-8")
            write_text(
                header_path,
                header + "\ngpio_num_t leaked_gpio;\n",
            )

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_public_interface(root, contract)

    def test_rejects_mutated_gpio_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_relative(
                root,
                VERIFY.PRIVATE_HEADER_RELATIVE_PATH,
            )
            mapping_path = copy_relative(
                root,
                VERIFY.MAPPING_SOURCE_RELATIVE_PATH,
            )
            mapping = mapping_path.read_text(encoding="utf-8")
            mutated = mapping.replace(
                "GPIO_NUM_18",
                "GPIO_NUM_17",
                1,
            )
            self.assertNotEqual(mutated, mapping)
            write_text(mapping_path, mutated)

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_private_mapping(root)

    def test_rejects_level_after_output_direction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = copy_relative(
                root,
                VERIFY.BOARD_SOURCE_RELATIVE_PATH,
            )
            source = source_path.read_text(encoding="utf-8")
            mutated = source.replace(
                "gpio_set_level(pin->gpio, level)",
                "gpio_level_not_latched(pin->gpio, level)",
                1,
            )
            self.assertNotEqual(mutated, source)
            write_text(source_path, mutated)

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_safe_state(root)

    def test_rejects_unguarded_requirement_discovery_check(
        self,
    ) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_configuration_fixture(root, contract)
            cmake_path = root / VERIFY.CMAKE_RELATIVE_PATH
            cmake = cmake_path.read_text(encoding="utf-8")
            mutated = cmake.replace(
                "if(NOT CMAKE_SCRIPT_MODE_FILE)",
                "if(TRUE)",
                1,
            )
            self.assertNotEqual(mutated, cmake)
            write_text(cmake_path, mutated)

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_configuration(root, contract)
    def test_rejects_kconfig_default_y(self) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_configuration_fixture(root, contract)
            kconfig_path = root / VERIFY.KCONFIG_RELATIVE_PATH
            kconfig = kconfig_path.read_text(encoding="utf-8")
            mutated = kconfig.replace("default n", "default y", 1)
            self.assertNotEqual(mutated, kconfig)
            write_text(kconfig_path, mutated)

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_configuration(root, contract)

    def test_rejects_split_initialization_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            document_path = copy_relative(
                root,
                VERIFY.DOCUMENT_RELATIVE_PATH,
            )
            document = document_path.read_text(encoding="utf-8")
            original = (
                "Vext and battery measurement remain disabled "
                "after initialization."
            )
            replacement = (
                "Vext remains disabled after initialization."
            )
            mutated = document.replace(original, replacement, 1)
            self.assertNotEqual(mutated, document)
            write_text(document_path, mutated)

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_document(root)

    def test_rejects_mutated_implementation_file(self) -> None:
        contract = VERIFY.validate_contract(CONTRACT_PATH)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for record in contract["implementation_files"]:
                copy_relative(root, Path(record["path"]))

            readme_path = (
                root / "components" / "board" / "README.md"
            )
            readme = readme_path.read_text(encoding="utf-8")
            write_text(readme_path, readme + "\nmutation\n")

            with self.assertRaises(VERIFY.VerificationError):
                VERIFY.validate_implementation_hashes(
                    root,
                    contract,
                )


if __name__ == "__main__":
    unittest.main()
