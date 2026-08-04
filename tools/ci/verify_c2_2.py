#!/usr/bin/env python3
"""Verify the C2.2 board-support implementation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence


EXPECTED_PARENT_BASELINE = (
    "1945dc8e983374b342dc4c77589a908fb403f984"
)
EXPECTED_C21_BLOB = (
    "d26f3e00efc5b8b251766eba416d634c63f9c5ba"
)
EXPECTED_COMPATIBILITY_ID = (
    "heltec-wifi-lora-32-v3.2-htit-wb32laf"
)
EXPECTED_REVISION_ENUM = (
    "SQD_BOARD_REVISION_HELTEC_WIFI_LORA_32_V3_2"
)
EXPECTED_KCONFIG_SYMBOL = (
    "SQD_BOARD_HELTEC_WIFI_LORA_32_V3_2"
)
EXPECTED_SELECTION = (
    "CONFIG_SQD_BOARD_HELTEC_WIFI_LORA_32_V3_2=y"
)

CONTRACT_RELATIVE_PATH = Path(
    "tools/ci/c2_2_board_contract.json"
)
DOCUMENT_RELATIVE_PATH = Path(
    "docs/phase-c/C2.2_Board_Support_Implementation.md"
)
PUBLIC_HEADER_RELATIVE_PATH = Path(
    "components/board/include/sqd_board.h"
)
PRIVATE_HEADER_RELATIVE_PATH = Path(
    "components/board/private/sqd_board_internal.h"
)
MAPPING_SOURCE_RELATIVE_PATH = Path(
    "components/board/sqd_board_mapping.c"
)
BOARD_SOURCE_RELATIVE_PATH = Path(
    "components/board/sqd_board.c"
)
KCONFIG_RELATIVE_PATH = Path("components/board/Kconfig")
CMAKE_RELATIVE_PATH = Path("components/board/CMakeLists.txt")
SDKCONFIG_RELATIVE_PATH = Path("sdkconfig.defaults")
B32_COMMON_RELATIVE_PATH = Path(
    "tools/scripts/B3.2_Common.ps1"
)
B32_BUILD_RELATIVE_PATH = Path(
    "tools/scripts/B3.2_Build.ps1"
)
PROFILE_BUILD_RELATIVE_PATH = Path(
    "tools/ci/run_profile_build.ps1"
)
B43_RELATIVE_PATH = Path(
    "tools/scripts/B4.3_Reproduce_Clean_Checkout_To_Flash.ps1"
)
WORKFLOW_RELATIVE_PATH = Path(".github/workflows/ci.yml")
B33_BASELINE_RELATIVE_PATH = Path(
    "tools/config/B3.3_configuration_baseline.json"
)

EXPECTED_PUBLIC_FUNCTIONS = (
    "sqd_board_prepare_safe_state",
    "sqd_board_initialize",
    "sqd_board_get_revision",
    "sqd_board_set_vext_enabled",
    "sqd_board_set_battery_measurement_enabled",
    "sqd_board_set_user_led",
)

EXPECTED_MAPPINGS = (
    ("SQD_BOARD_SIGNAL_OLED_SDA", 17, False,
     "released-open-drain-high"),
    ("SQD_BOARD_SIGNAL_OLED_SCL", 18, False,
     "released-open-drain-high"),
    ("SQD_BOARD_SIGNAL_OLED_RESET", 21, True,
     "asserted-low"),
    ("SQD_BOARD_SIGNAL_LORA_NSS", 8, True,
     "deasserted-high"),
    ("SQD_BOARD_SIGNAL_LORA_SCK", 9, False,
     "input-before-spi"),
    ("SQD_BOARD_SIGNAL_LORA_MOSI", 10, False,
     "input-before-spi"),
    ("SQD_BOARD_SIGNAL_LORA_MISO", 11, False, "input"),
    ("SQD_BOARD_SIGNAL_LORA_RESET", 12, True,
     "deasserted-high"),
    ("SQD_BOARD_SIGNAL_LORA_BUSY", 13, False, "input"),
    ("SQD_BOARD_SIGNAL_LORA_DIO1", 14, False, "input"),
    ("SQD_BOARD_SIGNAL_VEXT_CONTROL", 36, True,
     "deasserted-high-vext-disabled"),
    ("SQD_BOARD_SIGNAL_USER_BUTTON", 0, True,
     "input-pullup"),
    ("SQD_BOARD_SIGNAL_BATTERY_ADC", 1, False,
     "input-divider-disabled"),
    ("SQD_BOARD_SIGNAL_BATTERY_ADC_CONTROL", 37, False,
     "deasserted-low-divider-disabled"),
    ("SQD_BOARD_SIGNAL_USER_LED", 35, False,
     "deasserted-low-led-off"),
    ("SQD_BOARD_SIGNAL_UART0_TX", 43, False,
     "uart-defined"),
    ("SQD_BOARD_SIGNAL_UART0_RX", 44, False, "input"),
)

EXPECTED_REQUIREMENTS = (
    "exact-board-compatibility-id",
    "exact-public-revision-enum",
    "neutral-public-interface",
    "exact-seventeen-signal-private-map",
    "exact-c2-1-gpio-values",
    "valid-unique-gpio-map",
    "gpio0-input-only-pullup",
    "vext-and-battery-divider-disabled-after-initialize",
    "user-led-off-after-initialize",
    "lora-nss-and-reset-deasserted",
    "oled-reset-asserted",
    "oled-bus-open-drain-released",
    "safe-level-before-direction",
    "unknown-selection-fails-closed",
    "setters-reject-before-initialize",
    "gpio-failure-restores-safe-state",
    "kconfig-default-n",
    "common-default-explicit-board-selection",
    "generated-sdkconfig-board-validation",
    "b3-3-canonical-defaults-hash",
    "ci-and-b4-3-defaults-propagation",
    "active-compatibility-id-migration",
    "historical-record-preservation",
    "positive-and-mutation-negative-host-tests",
    "esp-idf-board-component-build",
)

EXPECTED_DOCUMENT_REQUIREMENTS = (
    "Contract records the exact V3.2 compatibility ID.",
    "Contract records the exact public board revision enum.",
    "Public API exposes sqd_status_t and no ESP-IDF GPIO types.",
    "Private mapping contains exactly 17 accepted logical signals.",
    "Every accepted signal maps to its exact C2.1 GPIO.",
    "GPIO mappings are valid and unique.",
    "GPIO0 is configured input-only with pull-up.",
    (
        "Vext and battery measurement remain disabled after "
        "initialization."
    ),
    "User LED remains off after initialization.",
    "LoRa NSS and reset are deasserted in safe state.",
    "OLED reset is asserted in safe state.",
    "OLED SDA and SCL are open-drain released high.",
    "Safe output levels are latched before output direction.",
    "Missing or unknown board selection fails closed.",
    "Runtime setters reject calls before initialization.",
    "Runtime GPIO failures restore safe state.",
    "Kconfig retains explicit default n.",
    "sdkconfig.defaults explicitly selects V3.2.",
    "B3.2 validates the generated board selection.",
    "B3.3 records the current sdkconfig.defaults SHA-256.",
    "CI and B4.3 both inherit common defaults through B3.2.",
    (
        "Active hardware compatibility references use the exact "
        "V3.2 ID."
    ),
    "Historical Phase B evidence remains unchanged.",
    "Host tests include positive and mutation-negative coverage.",
    "ESP-IDF build verification compiles the board component.",
)

EXPECTED_IMPLEMENTATION_HASHES = {
    "components/board/CMakeLists.txt": (
        "a1c0fab74d430d3659f129ee6e334d62"
        "2ccdbb33ac55ae10b4fb8873effed529"
    ),
    "components/board/include/sqd_board.h": (
        "23d1d102623cce4b5cbac3e413c6715e"
        "309ad4089657c40a52fac1d15830a2a5"
    ),
    "components/board/Kconfig": (
        "4bb1413276578a7db1b28fd3e8c70b1c"
        "c3a069bc7c9de8fc7ef5d8e2855bdd4a"
    ),
    "components/board/private/sqd_board_internal.h": (
        "0474751c85162ada4276b43e30022fd4"
        "976ec3fa3351376fd367dd1cd4463344"
    ),
    "components/board/README.md": (
        "306305772c32ce4b0db77bcb2bbc315a"
        "d978dfde1a023752ec6d1f390aa2f29c"
    ),
    "components/board/sqd_board.c": (
        "062158e95fcaaf5f08ea3906aff6a759"
        "58ab28f74f2711969b2ae353a834dc8a"
    ),
    "components/board/sqd_board_mapping.c": (
        "322fac15139d7d1546e38234bbbb3e1b"
        "71f93967529c9ed49012f7cfe5c577a2"
    ),
    "sdkconfig.defaults": (
        "2c96d26cb1b73a9e5abda325badb3f0b"
        "4fa4ebd81f62e5e495be4b3944f69be1"
    ),
    "tools/scripts/B3.2_Common.ps1": (
        "bf746f45aff26bab4cfbd43ec195d11b"
        "989a36f1c2c3ff5d0a08c9c3c17bf426"
    ),
    "tools/config/B3.3_configuration_baseline.json": (
        "bc435e725c35ff78d37d46c4e01b064a"
        "e9a94c7f04ad82654a7ab7f5a510dfb2"
    ),
}

MAPPING_RE = re.compile(
    r"\[(SQD_BOARD_SIGNAL_[A-Z0-9_]+)\]\s*=\s*\{"
    r"\s*\.gpio\s*=\s*GPIO_NUM_([0-9]+),"
    r"\s*\.active_low\s*=\s*(true|false),"
    r"\s*\.defined\s*=\s*true,\s*\}",
    re.DOTALL,
)
OLD_ACTIVE_ID_RE = re.compile(
    r"heltec-wifi-lora-32-v3(?!\.2-htit-wb32laf)"
)


class VerificationError(RuntimeError):
    """C2.2 repository or implementation verification failure."""


def require(condition: bool, message: str) -> None:
    """Raise a controlled verification failure."""

    if not condition:
        raise VerificationError(message)


def digest(path: Path) -> str:
    """Return a lowercase SHA-256 digest."""

    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_text(path: Path) -> str:
    """Read a controlled UTF-8/LF text file."""

    if not path.is_file():
        raise VerificationError(f"Missing file: {path}")
    data = path.read_bytes()
    require(not data.startswith(b"\xef\xbb\xbf"),
            f"Unexpected UTF-8 BOM: {path}")
    require(b"\r" not in data,
            f"Non-LF line ending detected: {path}")
    require(data.endswith(b"\n"),
            f"Missing final newline: {path}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise VerificationError(
            f"Invalid UTF-8 file {path}: {error}"
        ) from error


def read_json(path: Path) -> dict:
    """Read a JSON object."""

    text = read_text(path)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise VerificationError(
            f"Invalid JSON file {path}: {error}"
        ) from error
    require(isinstance(value, dict),
            f"JSON root must be an object: {path}")
    return value


def run_git(
    repo_root: Path,
    arguments: Sequence[str],
    *,
    allow_failure: bool = False,
) -> str:
    """Run Git and return stripped standard output."""

    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0 and not allow_failure:
        diagnostic = (result.stderr or result.stdout).strip()
        raise VerificationError(
            f"git {' '.join(arguments)} failed: {diagnostic}"
        )
    return result.stdout.strip()


def git_blob(repo_root: Path, relative_path: str) -> str:
    """Return the Git blob identity of a working-tree file."""

    return run_git(
        repo_root,
        ["hash-object", "--", relative_path],
    )


def validate_contract(contract_path: Path) -> dict:
    """Validate the machine-readable C2.2 contract."""

    contract = read_json(contract_path)
    expected_scalars = {
        "schema_version": 1,
        "work_package": "C2.2",
        "title": "Board Support Implementation Contract",
        "status": "Proposed",
        "platform": "ESP32-S3FN8",
        "toolchain": "ESP-IDF 6.0.2",
        "parent_baseline": EXPECTED_PARENT_BASELINE,
    }
    for name, expected in expected_scalars.items():
        require(
            contract.get(name) == expected,
            f"Incorrect C2.2 contract field {name}: "
            f"{contract.get(name)!r}",
        )

    sources = contract.get("accepted_sources")
    require(isinstance(sources, dict),
            "accepted_sources must be an object.")
    c21 = sources.get("c2_1_board_contract")
    require(isinstance(c21, dict),
            "C2.1 accepted-source record is missing.")
    require(
        c21.get("path") == (
            "docs/phase-c/"
            "C2.1_Board_Pins_Revision_Detection.md"
        ),
        "Incorrect C2.1 accepted-source path.",
    )
    require(c21.get("blob") == EXPECTED_C21_BLOB,
            "Incorrect accepted C2.1 blob.")

    identity = contract.get("board_identity")
    require(isinstance(identity, dict),
            "board_identity must be an object.")
    require(
        identity.get("compatibility_id") ==
        EXPECTED_COMPATIBILITY_ID,
        "Incorrect board compatibility ID.",
    )
    require(
        identity.get("revision_enum") == EXPECTED_REVISION_ENUM,
        "Incorrect public board revision enum.",
    )
    require(
        identity.get("kconfig_symbol") ==
        EXPECTED_KCONFIG_SYMBOL,
        "Incorrect board Kconfig symbol.",
    )
    require(
        identity.get("sdkconfig_selection") ==
        EXPECTED_SELECTION,
        "Incorrect common board selection.",
    )

    public = contract.get("public_interface")
    require(isinstance(public, dict),
            "public_interface must be an object.")
    require(
        tuple(public.get("functions", [])) ==
        EXPECTED_PUBLIC_FUNCTIONS,
        "Public function inventory is invalid.",
    )
    require(public.get("status_type") == "sqd_status_t",
            "Public status type is invalid.")

    private = contract.get("private_mapping")
    require(isinstance(private, dict),
            "private_mapping must be an object.")
    mappings = private.get("mappings")
    require(isinstance(mappings, list),
            "Private mappings must be an array.")
    expected_records = [
        {
            "signal": signal,
            "gpio": gpio,
            "active_low": active_low,
            "safe_state": safe_state,
        }
        for signal, gpio, active_low, safe_state
        in EXPECTED_MAPPINGS
    ]
    require(mappings == expected_records,
            "Private signal mapping contract is invalid.")
    require(private.get("signal_count") == 17,
            "Private signal count is not 17.")

    requirements = contract.get("verification_requirements")
    require(
        tuple(requirements or []) == EXPECTED_REQUIREMENTS,
        "Frozen verification requirement inventory is invalid.",
    )

    active_paths = contract.get("active_compatibility_paths")
    require(isinstance(active_paths, list),
            "active_compatibility_paths must be an array.")
    require(len(active_paths) == 23,
            "Active compatibility path count is not 23.")
    require(len(active_paths) == len(set(active_paths)),
            "Active compatibility paths contain duplicates.")

    implementation = contract.get("implementation_files")
    require(isinstance(implementation, list),
            "implementation_files must be an array.")
    implementation_map = {
        str(record.get("path")):
        str(record.get("sha256", "")).lower()
        for record in implementation
        if isinstance(record, dict)
    }
    require(
        implementation_map == EXPECTED_IMPLEMENTATION_HASHES,
        "Implementation hash inventory is invalid.",
    )

    verification = contract.get("verification")
    require(isinstance(verification, dict),
            "verification must be an object.")
    require(
        verification.get("verifier") ==
        "tools/ci/verify_c2_2.py",
        "Incorrect verifier path.",
    )
    require(
        verification.get("host_test") ==
        "tools/ci/tests/test_c2_2_board.py",
        "Incorrect host-test path.",
    )
    require(
        verification.get("powershell_entrypoint") ==
        "tools/scripts/C2.2_Verify_Board_Support.ps1",
        "Incorrect PowerShell verifier path.",
    )
    return contract


def validate_implementation_hashes(
    repo_root: Path,
    contract: dict,
) -> None:
    """Validate every controlled implementation SHA-256."""

    for record in contract["implementation_files"]:
        relative_path = str(record["path"])
        expected = str(record["sha256"]).lower()
        path = repo_root / relative_path
        require(path.is_file(),
                f"Missing implementation file: {relative_path}")
        actual = digest(path)
        require(
            actual == expected,
            f"Implementation hash mismatch: {relative_path}",
        )


def validate_public_interface(repo_root: Path, contract: dict) -> None:
    """Validate the public board API and neutral boundary."""

    header = read_text(repo_root / PUBLIC_HEADER_RELATIVE_PATH)
    require(
        f"{EXPECTED_REVISION_ENUM} = 1" in header,
        "Public revision enum value is missing.",
    )
    require(
        "SQD_BOARD_REVISION_UNKNOWN = 0" in header,
        "Unknown revision sentinel is missing.",
    )
    require(
        '#include "sqd_status.h"' in header,
        "Public header does not use the shared status contract.",
    )
    for function in EXPECTED_PUBLIC_FUNCTIONS:
        require(
            re.search(
                rf"\bsqd_status_t\s+{re.escape(function)}\s*\(",
                header,
            ) is not None,
            f"Missing public board function: {function}",
        )
    for token in contract["public_interface"]["forbidden_tokens"]:
        require(token not in header,
                f"Forbidden public-header token: {token}")


def validate_private_mapping(repo_root: Path) -> None:
    """Validate the exact private logical-signal GPIO map."""

    internal = read_text(
        repo_root / PRIVATE_HEADER_RELATIVE_PATH
    )
    mapping = read_text(
        repo_root / MAPPING_SOURCE_RELATIVE_PATH
    )
    require(EXPECTED_COMPATIBILITY_ID in internal,
            "Private compatibility ID is incorrect.")
    require("SQD_BOARD_SIGNAL_COUNT" in internal,
            "Private signal-count sentinel is missing.")

    observed = [
        (
            match.group(1),
            int(match.group(2)),
            match.group(3) == "true",
        )
        for match in MAPPING_RE.finditer(mapping)
    ]
    expected = [
        (signal, gpio, active_low)
        for signal, gpio, active_low, _ in EXPECTED_MAPPINGS
    ]
    require(observed == expected,
            "Private mapping source differs from C2.1.")
    require(len(observed) == 17,
            "Private mapping source does not contain 17 signals.")
    require(len({item[0] for item in observed}) == 17,
            "Private mapping contains duplicate signals.")
    require(len({item[1] for item in observed}) == 17,
            "Private mapping contains duplicate GPIO values.")
    require(
        "sqd_board_internal_mapping_is_valid" in mapping,
        "Runtime mapping validation is missing.",
    )
    require(
        "first->gpio == second->gpio" in mapping,
        "Runtime duplicate-GPIO detection is missing.",
    )


def extract_between(text: str, start: str, end: str) -> str:
    """Return a controlled source segment."""

    start_index = text.find(start)
    require(start_index >= 0, f"Missing source marker: {start}")
    end_index = text.find(end, start_index + len(start))
    require(end_index >= 0, f"Missing source marker: {end}")
    return text[start_index:end_index]


def require_output_call(
    safe_block: str,
    signal: str,
    asserted: bool,
    open_drain: bool,
) -> None:
    """Require one exact safe-state output call."""

    asserted_text = str(asserted).lower()
    open_drain_text = str(open_drain).lower()
    pattern = re.compile(
        rf"sqd_board_configure_output\(\s*"
        rf"{re.escape(signal)},\s*"
        rf"{asserted_text},\s*"
        rf"{open_drain_text}\s*\)",
        re.DOTALL,
    )
    require(
        len(pattern.findall(safe_block)) == 1,
        f"Incorrect safe-state output call: {signal}",
    )


def require_input_call(
    safe_block: str,
    signal: str,
    pull_up: str,
    pull_down: str,
) -> None:
    """Require one exact safe-state input call."""

    pattern = re.compile(
        rf"sqd_board_configure_input\(\s*"
        rf"{re.escape(signal)},\s*"
        rf"{re.escape(pull_up)},\s*"
        rf"{re.escape(pull_down)}\s*\)",
        re.DOTALL,
    )
    require(
        len(pattern.findall(safe_block)) == 1,
        f"Incorrect safe-state input call: {signal}",
    )


def function_block(text: str, function_name: str) -> str:
    """Return one public board-function source block."""

    signature = f"sqd_status_t {function_name}("
    start = text.find(signature)
    require(start >= 0, f"Missing function: {function_name}")
    next_match = re.search(
        r"\nsqd_status_t\s+sqd_board_[a-z0-9_]+\s*\(",
        text[start + len(signature):],
    )
    if next_match is None:
        return text[start:]
    end = start + len(signature) + next_match.start()
    return text[start:end]


def validate_safe_state(repo_root: Path) -> None:
    """Validate fail-closed GPIO sequencing and runtime policy."""

    source = read_text(repo_root / BOARD_SOURCE_RELATIVE_PATH)
    output_function = extract_between(
        source,
        "static sqd_status_t sqd_board_configure_output",
        "static sqd_status_t sqd_board_write_output",
    )
    first_level = output_function.find(
        "gpio_set_level(pin->gpio, level)"
    )
    configure = output_function.find(
        "gpio_config(&configuration)"
    )
    second_level = output_function.find(
        "gpio_set_level(pin->gpio, level)",
        first_level + 1,
    )
    require(
        0 <= first_level < configure < second_level,
        "Safe output level is not latched before direction.",
    )

    safe_block = extract_between(
        source,
        "static sqd_status_t sqd_board_apply_safe_state",
        "static sqd_status_t sqd_board_validate_runtime_state",
    )
    for signal, asserted, open_drain in (
        ("SQD_BOARD_SIGNAL_VEXT_CONTROL", False, False),
        ("SQD_BOARD_SIGNAL_BATTERY_ADC_CONTROL", False, False),
        ("SQD_BOARD_SIGNAL_USER_LED", False, False),
        ("SQD_BOARD_SIGNAL_LORA_NSS", False, False),
        ("SQD_BOARD_SIGNAL_LORA_RESET", False, False),
        ("SQD_BOARD_SIGNAL_OLED_RESET", True, False),
        ("SQD_BOARD_SIGNAL_OLED_SDA", True, True),
        ("SQD_BOARD_SIGNAL_OLED_SCL", True, True),
    ):
        require_output_call(
            safe_block, signal, asserted, open_drain
        )

    require_input_call(
        safe_block,
        "SQD_BOARD_SIGNAL_USER_BUTTON",
        "GPIO_PULLUP_ENABLE",
        "GPIO_PULLDOWN_DISABLE",
    )
    for signal in (
        "SQD_BOARD_SIGNAL_BATTERY_ADC",
        "SQD_BOARD_SIGNAL_LORA_SCK",
        "SQD_BOARD_SIGNAL_LORA_MOSI",
        "SQD_BOARD_SIGNAL_LORA_MISO",
        "SQD_BOARD_SIGNAL_LORA_BUSY",
        "SQD_BOARD_SIGNAL_LORA_DIO1",
        "SQD_BOARD_SIGNAL_UART0_RX",
    ):
        require_input_call(
            safe_block,
            signal,
            "GPIO_PULLUP_DISABLE",
            "GPIO_PULLDOWN_DISABLE",
        )
    require(
        "SQD_BOARD_SIGNAL_UART0_TX" not in safe_block,
        "Safe-state code must not claim UART0 TX ownership.",
    )

    runtime_block = extract_between(
        source,
        "static sqd_status_t sqd_board_validate_runtime_state",
        "static sqd_status_t sqd_board_fail_closed",
    )
    require("if (!s_board_initialized)" in runtime_block,
            "Runtime initialization guard is missing.")
    require("SQD_STATUS_INVALID_STATE" in runtime_block,
            "Pre-initialization status is incorrect.")

    fail_block = extract_between(
        source,
        "static sqd_status_t sqd_board_fail_closed",
        "sqd_status_t sqd_board_prepare_safe_state",
    )
    for token in (
        "sqd_board_apply_safe_state()",
        "s_board_initialized = false",
        "s_board_revision = SQD_BOARD_REVISION_UNKNOWN",
    ):
        require(token in fail_block,
                f"Fail-closed rollback token is missing: {token}")

    initialize = function_block(source, "sqd_board_initialize")
    for token in (
        "sqd_board_internal_mapping_is_valid()",
        "sqd_board_apply_safe_state()",
        "SQD_BOARD_REVISION_UNKNOWN",
        "SQD_STATUS_NOT_SUPPORTED",
        EXPECTED_REVISION_ENUM,
        "s_board_initialized = true",
    ):
        require(token in initialize,
                f"Initialization token is missing: {token}")

    for setter in (
        "sqd_board_set_vext_enabled",
        "sqd_board_set_battery_measurement_enabled",
        "sqd_board_set_user_led",
    ):
        block = function_block(source, setter)
        require(
            "sqd_board_validate_runtime_state()" in block,
            f"Setter lacks runtime-state validation: {setter}",
        )
        require(
            "sqd_board_fail_closed(write_status)" in block,
            f"Setter lacks fail-closed rollback: {setter}",
        )


def validate_configuration(repo_root: Path, contract: dict) -> None:
    """Validate explicit selection and build propagation."""

    kconfig = read_text(repo_root / KCONFIG_RELATIVE_PATH)
    require(
        f"config {EXPECTED_KCONFIG_SYMBOL}" in kconfig,
        "Board Kconfig symbol is missing.",
    )
    require(kconfig.count("default n") == 1,
            "Board Kconfig must contain one default n.")
    require("default y" not in kconfig,
            "Board Kconfig must not contain default y.")

    cmake = read_text(repo_root / CMAKE_RELATIVE_PATH)
    guard_start = cmake.find("if(NOT CMAKE_SCRIPT_MODE_FILE)")
    fatal_check = cmake.find(
        "Exactly one SQD board must be selected"
    )
    register_call = cmake.find("idf_component_register(")
    guard_end = -1
    if guard_start >= 0 and register_call >= 0:
        guard_end = cmake.rfind(
            "endif()",
            guard_start,
            register_call,
        )
    require(
        0 <= guard_start < fatal_check < guard_end < register_call,
        (
            "Board selection check is not guarded during "
            "component requirement discovery."
        ),
    )
    for token in (
        "SQD_BOARD_SELECTION_COUNT",
        "Exactly one SQD board must be selected",
        EXPECTED_KCONFIG_SYMBOL,
    ):
        require(token in cmake,
                f"Board CMake token is missing: {token}")
    require(
        re.search(r"\bREQUIRES\s+core\b", cmake) is not None,
        "Board component does not require core.",
    )
    require(
        re.search(
            r"\bPRIV_REQUIRES\s+esp_driver_gpio\b",
            cmake,
        ) is not None,
        "Board component lacks private GPIO dependency.",
    )

    sdkconfig_path = repo_root / SDKCONFIG_RELATIVE_PATH
    sdkconfig = read_text(sdkconfig_path)
    require(sdkconfig.count(EXPECTED_SELECTION) == 1,
            "Common defaults board selection is invalid.")
    require(
        digest(sdkconfig_path) ==
        EXPECTED_IMPLEMENTATION_HASHES["sdkconfig.defaults"],
        "Common defaults SHA-256 is invalid.",
    )

    b32_common = read_text(repo_root / B32_COMMON_RELATIVE_PATH)
    require(b32_common.count(EXPECTED_SELECTION) == 1,
            "B3.2 generated selection check is invalid.")

    baseline = read_json(repo_root / B33_BASELINE_RELATIVE_PATH)
    records = [
        item
        for item in baseline.get("controlled_files", [])
        if isinstance(item, dict)
        and item.get("relative_path") == "sdkconfig.defaults"
    ]
    require(len(records) == 1,
            "B3.3 sdkconfig.defaults record is ambiguous.")
    require(
        str(records[0].get("canonical_sha256", "")).lower() ==
        digest(sdkconfig_path),
        "B3.3 canonical defaults hash is incorrect.",
    )

    workflow = read_text(repo_root / WORKFLOW_RELATIVE_PATH)
    profile = read_text(repo_root / PROFILE_BUILD_RELATIVE_PATH)
    b32_build = read_text(repo_root / B32_BUILD_RELATIVE_PATH)
    b43 = read_text(repo_root / B43_RELATIVE_PATH)
    require("run_profile_build.ps1" in workflow,
            "CI does not invoke the profile wrapper.")
    require("B3.2_Build.ps1" in profile,
            "Profile wrapper does not invoke B3.2 build.")
    require("SDKCONFIG_DEFAULTS" in b32_build,
            "B3.2 build does not supply common defaults.")
    require("B3.2_Build.ps1" in b43,
            "B4.3 does not invoke B3.2 build directly.")

    for relative_path in contract["active_compatibility_paths"]:
        path = repo_root / str(relative_path)
        text = read_text(path)
        require(
            EXPECTED_COMPATIBILITY_ID in text,
            f"Exact compatibility ID is missing: {relative_path}",
        )
        require(
            OLD_ACTIVE_ID_RE.search(text) is None,
            f"Legacy active compatibility ID remains: "
            f"{relative_path}",
        )


def status_paths(repo_root: Path) -> list[str]:
    """Return normalized Git status paths."""

    output = run_git(
        repo_root,
        ["status", "--porcelain", "--untracked-files=all"],
    )
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.strip('"'))
    return paths


def validate_historical_preservation(
    repo_root: Path,
    contract: dict,
) -> None:
    """Validate accepted C2.1 and historical Phase B preservation."""

    c21 = contract["accepted_sources"]["c2_1_board_contract"]
    require(
        git_blob(repo_root, str(c21["path"])) ==
        EXPECTED_C21_BLOB,
        "Accepted C2.1 source blob changed.",
    )
    prefixes = tuple(
        contract["historical_preservation"]["unchanged_prefixes"]
    )
    changed_historical = [
        path
        for path in status_paths(repo_root)
        if path.startswith(prefixes)
    ]
    require(
        not changed_historical,
        "Historical Phase B material changed: "
        + ", ".join(changed_historical),
    )


def validate_document(repo_root: Path) -> None:
    """Validate the C2.2 implementation record."""

    text = read_text(repo_root / DOCUMENT_RELATIVE_PATH)
    for token in (
        "document_id: ESP32S3-PC-C2.2",
        "# C2.2 Board Support Implementation",
        EXPECTED_COMPATIBILITY_ID,
        EXPECTED_REVISION_ENUM,
        EXPECTED_SELECTION,
        "Physical hardware verification: PENDING C2.3",
    ):
        require(token in text,
                f"Implementation-record token is missing: {token}")

    section = re.search(
        r"## Frozen verification requirements\n\n"
        r"(.*?)\n\n## C2\.3 boundary",
        text,
        re.DOTALL,
    )
    require(section is not None,
            "Frozen requirement section is missing.")
    observed = tuple(
        match.group(1)
        for match in re.finditer(
            r"^[0-9]+\. (.+)$",
            section.group(1),
            re.MULTILINE,
        )
    )
    require(
        observed == EXPECTED_DOCUMENT_REQUIREMENTS,
        "Implementation-record requirement inventory is invalid.",
    )


def validate_repository(repo_root: Path, contract_path: Path) -> dict:
    """Validate the complete static C2.2 repository contract."""

    repo_root = repo_root.expanduser().resolve()
    git_root = Path(
        run_git(repo_root, ["rev-parse", "--show-toplevel"])
    ).resolve()
    require(git_root == repo_root,
            "Selected repository root does not match Git root.")

    required_paths = (
        contract_path,
        repo_root / DOCUMENT_RELATIVE_PATH,
        repo_root / PUBLIC_HEADER_RELATIVE_PATH,
        repo_root / PRIVATE_HEADER_RELATIVE_PATH,
        repo_root / MAPPING_SOURCE_RELATIVE_PATH,
        repo_root / BOARD_SOURCE_RELATIVE_PATH,
        repo_root / KCONFIG_RELATIVE_PATH,
        repo_root / CMAKE_RELATIVE_PATH,
        repo_root / SDKCONFIG_RELATIVE_PATH,
        repo_root / "tools/ci/verify_c2_2.py",
    )
    for path in required_paths:
        require(path.is_file(), f"Missing C2.2 file: {path}")

    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            EXPECTED_PARENT_BASELINE,
            "HEAD",
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    require(
        ancestor.returncode == 0,
        "Repository HEAD does not descend from the C2.2 "
        "architecture prerequisite.",
    )

    contract = validate_contract(contract_path)
    validate_implementation_hashes(repo_root, contract)
    validate_public_interface(repo_root, contract)
    validate_private_mapping(repo_root)
    validate_safe_state(repo_root)
    validate_configuration(repo_root, contract)
    validate_historical_preservation(repo_root, contract)
    validate_document(repo_root)
    return contract


def parse_arguments() -> argparse.Namespace:
    """Parse verifier arguments."""

    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description=(
            "Verify the C2.2 board-support implementation "
            "contract."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_root,
        help="Repository root.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="Override the C2.2 contract path.",
    )
    return parser.parse_args()


def main() -> int:
    """Execute C2.2 static verification."""

    arguments = parse_arguments()
    repo_root = arguments.repo_root.expanduser().resolve()
    contract_path = arguments.contract
    if contract_path is None:
        contract_path = repo_root / CONTRACT_RELATIVE_PATH
    elif not contract_path.is_absolute():
        contract_path = repo_root / contract_path
    contract_path = contract_path.resolve()

    try:
        contract = validate_repository(repo_root, contract_path)
        print("C2.2 board-support contract")
        print(f"Repository:            {repo_root}")
        print(
            "Parent baseline:       "
            f"{contract['parent_baseline']}"
        )
        print(
            "Board compatibility:   "
            f"{contract['board_identity']['compatibility_id']}"
        )
        print(
            "Signal mappings:       "
            f"{len(contract['private_mapping']['mappings'])}"
        )
        print(
            "Verification rules:    "
            f"{len(contract['verification_requirements'])}"
        )
        print("Public/private boundary: PASS")
        print("Private GPIO mapping:    PASS")
        print("Safe-state sequencing:   PASS")
        print("Configuration control:   PASS")
        print("Build propagation:       PASS")
        print("Historical preservation: PASS")
        print("Implementation identity: PASS")
        print("")
        print("PASS: C2.2 board support contract validated.")
        return 0
    except VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
