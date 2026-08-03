from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

ADR_PATH = (
    REPO_ROOT
    / "docs"
    / "phase-c"
    / "architecture-decisions"
    / "ADR-0003_Shared_Status_Foundation_Contract.md"
)

AMENDMENT_PATH = (
    REPO_ROOT
    / "tools"
    / "ci"
    / "c2_2_architecture_amendment.json"
)

CORE_CMAKE_PATH = (
    REPO_ROOT
    / "components"
    / "core"
    / "CMakeLists.txt"
)

STATUS_HEADER_PATH = (
    REPO_ROOT
    / "components"
    / "core"
    / "include"
    / "sqd_status.h"
)

VERIFIER_PATH = (
    REPO_ROOT
    / "tools"
    / "scripts"
    / "C2.2_Verify_Architecture_Prerequisite.ps1"
)

EXPECTED_STATUS_CODES = [
    "SQD_STATUS_OK",
    "SQD_STATUS_INVALID_ARGUMENT",
    "SQD_STATUS_INVALID_STATE",
    "SQD_STATUS_ALREADY_INITIALIZED",
    "SQD_STATUS_NOT_FOUND",
    "SQD_STATUS_BUSY",
    "SQD_STATUS_TIMEOUT",
    "SQD_STATUS_IO",
    "SQD_STATUS_INTEGRITY",
    "SQD_STATUS_AUTHORIZATION",
    "SQD_STATUS_NO_MEMORY",
    "SQD_STATUS_NOT_SUPPORTED",
    "SQD_STATUS_CANCELLED",
    "SQD_STATUS_INTERNAL",
]


def git_blob(relative_path: str) -> str:
    result = subprocess.run(
        ["git", "hash-object", "--", relative_path],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class C22ArchitecturePrerequisiteTests(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        required_paths = [
            ADR_PATH,
            AMENDMENT_PATH,
            CORE_CMAKE_PATH,
            STATUS_HEADER_PATH,
            VERIFIER_PATH,
        ]

        for path in required_paths:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"Missing file: {path}")

    def test_core_component_is_header_only(self) -> None:
        cmake = CORE_CMAKE_PATH.read_text(encoding="utf-8")

        self.assertIn("idf_component_register(", cmake)
        self.assertIn('    INCLUDE_DIRS "include"', cmake)
        self.assertNotIn("SRCS", cmake)
        self.assertNotIn("REQUIRES", cmake)
        self.assertNotIn("PRIV_REQUIRES", cmake)

    def test_status_header_contains_exact_contract(self) -> None:
        header = STATUS_HEADER_PATH.read_text(encoding="utf-8")

        for index, code in enumerate(EXPECTED_STATUS_CODES):
            with self.subTest(code=code):
                self.assertIn(f"{code} = {index}", header)

        self.assertIn("} sqd_status_t;", header)

        forbidden_tokens = [
            "esp_err_t",
            "driver/",
            "freertos/",
            "gpio_num_t",
            "sqd_board",
            "sqd_platform",
        ]

        for token in forbidden_tokens:
            with self.subTest(token=token):
                self.assertNotIn(token, header)

    def test_amendment_preserves_accepted_sources(self) -> None:
        amendment = json.loads(AMENDMENT_PATH.read_text(encoding="utf-8"))

        for source in amendment["accepted_sources"].values():
            with self.subTest(path=source["path"]):
                self.assertEqual(source["blob"], git_blob(source["path"]))

    def test_amendment_records_core_ownership(self) -> None:
        amendment = json.loads(AMENDMENT_PATH.read_text(encoding="utf-8"))
        component = amendment["component_addition"]

        self.assertEqual(component["id"], "core")
        self.assertEqual(component["path"], "components/core")
        self.assertEqual(component["implementation_status"], "header-only")
        self.assertFalse(component["owns_mutable_state"])
        self.assertEqual(component["permitted_dependencies"], [])

        self.assertEqual(
            amendment["status_contract"]["status_codes"],
            EXPECTED_STATUS_CODES,
        )

    def test_amendment_records_board_core_dependency(self) -> None:
        amendment = json.loads(AMENDMENT_PATH.read_text(encoding="utf-8"))
        dependencies = amendment["dependency_additions"]

        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0]["caller"], "board")
        self.assertEqual(dependencies[0]["target"], "core")
        self.assertEqual(dependencies[0]["direction"], "downward")
        self.assertFalse(dependencies[0]["same_level_exception"])

    def test_adr_records_additive_decision(self) -> None:
        adr = ADR_PATH.read_text(encoding="utf-8")

        required_tokens = [
            "ADR-0003",
            "components/core",
            "sqd_status_t",
            "board -> core",
            "accepted C1.1, C1.2 and C1.3",
            "must remain header-only",
        ]

        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, adr)

    def test_powershell_verifier_passes(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")

        if powershell is None:
            self.skipTest("PowerShell executable is unavailable.")

        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(VERIFIER_PATH),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

        output = "`n".join(
            part for part in [result.stdout, result.stderr] if part
        )

        self.assertEqual(result.returncode, 0, output)
        self.assertIn("C2.2 architecture prerequisite PASSED.", output)


if __name__ == "__main__":
    unittest.main()
