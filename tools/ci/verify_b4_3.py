#!/usr/bin/env python3
"""Verify the B4.3 clean checkout-to-flash and Cluster B gate contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
COM_RE = re.compile(r"^COM[0-9]+$", re.IGNORECASE)

CONTRACT_RELATIVE_PATH = Path(
    "tools/ci/b4_3_reproduction_contract.json"
)
RECORD_RELATIVE_PATH = Path(
    "docs/phase-b/"
    "B4.3_Clean_Checkout_To_Flash_and_Cluster_B_Gate.md"
)
GIT_ATTRIBUTES_RELATIVE_PATH = Path(".gitattributes")

FOUNDATION_PATHS = (
    GIT_ATTRIBUTES_RELATIVE_PATH,
    Path("main/CMakeLists.txt"),
    Path("main/main.c"),
    CONTRACT_RELATIVE_PATH,
    Path("tools/ci/verify_b4_3.py"),
    Path("tools/ci/tests/test_b4_3_reproduction.py"),
    Path(
        "tools/scripts/"
        "B4.3_Reproduce_Clean_Checkout_To_Flash.ps1"
    ),
    RECORD_RELATIVE_PATH,
)

EXPECTED_CONTRACT = {
    "schema_version": 1,
    "work_package": "B4.3",
    "gate": "G-B",
    "repository": "https://github.com/CPParthasarathy/SQD.git",
    "parent_baseline": (
        "196c46e5b90b568f8639a061e4dc5370db57c091"
    ),
    "orchestrator_path": (
        "tools/scripts/"
        "B4.3_Reproduce_Clean_Checkout_To_Flash.ps1"
    ),
}


REQUIRED_LF_ATTRIBUTE_PATHS = (
    ".gitattributes",
    ".clang-format",
    ".clang-tidy",
    ".editorconfig",
    "tools/ci/requirements-ci.txt",
    "tools/ci/tests/test_ci_contracts.py",
    (
        "tools/scripts/"
        "B4.3_Reproduce_Clean_Checkout_To_Flash.ps1"
    ),
)

REQUIRED_ATTRIBUTE_LINES = (
    "* text=auto eol=lf",
    "*.ps1 text eol=lf",
    "*.cmd text eol=crlf",
    "*.bat text eol=crlf",
    "*.bin binary",
    "*.elf binary",
    "*.pdf binary",
    "*.xlsx binary",
)


class VerificationError(RuntimeError):
    """B4.3 repository, evidence, or gate verification failure."""


def digest(path: Path) -> str:
    """Return a lowercase SHA-256 digest."""

    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_json(path: Path) -> dict:
    """Read a JSON object."""

    if not path.is_file():
        raise VerificationError(f"Missing JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(
            f"Invalid JSON file {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise VerificationError(
            f"JSON root must be an object: {path}"
        )
    return value


def require_mapping(
    value: object,
    description: str,
) -> Mapping[str, object]:
    """Require a mapping."""

    if not isinstance(value, Mapping):
        raise VerificationError(
            f"{description} must be an object."
        )
    return value


def require_sequence(
    value: object,
    description: str,
) -> Sequence[object]:
    """Require a non-string sequence."""

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
    ):
        raise VerificationError(
            f"{description} must be an array."
        )
    return value


def read_front_matter(path: Path) -> tuple[dict, str]:
    """Read YAML front matter and Markdown body."""

    if not path.is_file():
        raise VerificationError(
            f"B4.3 lifecycle record is missing: {path}"
        )
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise VerificationError(
            "B4.3 lifecycle record lacks YAML front matter."
        )
    try:
        closing = lines.index("---", 1)
    except ValueError as error:
        raise VerificationError(
            "B4.3 lifecycle front matter is not terminated."
        ) from error
    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as error:
        raise VerificationError(
            f"B4.3 lifecycle front matter is invalid: {error}"
        ) from error
    if not isinstance(metadata, dict):
        raise VerificationError(
            "B4.3 lifecycle metadata must be a mapping."
        )
    return metadata, "\n".join(lines[closing + 1 :])


def validate_contract(path: Path) -> dict:
    """Validate the machine-readable B4.3 contract."""

    contract = read_json(path)
    for name, expected in EXPECTED_CONTRACT.items():
        if contract.get(name) != expected:
            raise VerificationError(
                f"Incorrect B4.3 contract field {name}: "
                f"{contract.get(name)!r}"
            )

    parent = contract["parent_baseline"]
    if not isinstance(parent, str) or not SHA1_RE.fullmatch(parent):
        raise VerificationError(
            "B4.3 parent_baseline must be a full Git SHA."
        )

    toolchain = require_mapping(
        contract.get("toolchain"),
        "B4.3 toolchain contract",
    )
    expected_toolchain = {
        "esp_idf_version": "v6.0.2",
        "esp_idf_commit": (
            "7101770dc6db2667b3c477cc31365dd1acd6db4e"
        ),
        "python_version": "Python 3.11.15",
        "target": "esp32s3",
    }
    for name, expected in expected_toolchain.items():
        if toolchain.get(name) != expected:
            raise VerificationError(
                f"Incorrect B4.3 toolchain field {name}: "
                f"{toolchain.get(name)!r}"
            )

    hardware = require_mapping(
        contract.get("hardware"),
        "B4.3 hardware contract",
    )
    if hardware.get("compatibility") != "heltec-wifi-lora-32-v3":
        raise VerificationError(
            "B4.3 hardware compatibility is incorrect."
        )
    if hardware.get("serial_baud") != 115200:
        raise VerificationError(
            "B4.3 serial baud must be 115200."
        )

    build = require_mapping(
        contract.get("build"),
        "B4.3 build contract",
    )
    allowed_profiles = list(
        require_sequence(
            build.get("allowed_profiles"),
            "B4.3 allowed profiles",
        )
    )
    if allowed_profiles != ["debug", "validation"]:
        raise VerificationError(
            "B4.3 allowed profiles must be debug and validation."
        )
    if build.get("default_profile") != "validation":
        raise VerificationError(
            "B4.3 default profile must be validation."
        )
    if build.get("existing_build_reuse_permitted") is not False:
        raise VerificationError(
            "B4.3 must prohibit existing build-directory reuse."
        )

    repeatability = require_mapping(
        contract.get("repeatability"),
        "B4.3 repeatability contract",
    )
    if repeatability.get("required_passes") != 2:
        raise VerificationError(
            "B4.3 must require two independent passes."
        )
    if repeatability.get("clone_reuse_permitted") is not False:
        raise VerificationError(
            "B4.3 must prohibit clean-clone reuse."
        )
    if (
        repeatability.get("build_directory_reuse_permitted")
        is not False
    ):
        raise VerificationError(
            "B4.3 must prohibit build-directory reuse."
        )

    metadata_keys = list(
        require_sequence(
            contract.get("required_metadata_keys"),
            "B4.3 metadata-key contract",
        )
    )
    required_metadata = {
        "git_commit",
        "git_dirty",
        "build_profile",
        "target",
        "idf_version",
        "hardware_compatibility",
        "elf_sha256",
    }
    missing_metadata = sorted(
        required_metadata.difference(metadata_keys)
    )
    if missing_metadata:
        raise VerificationError(
            "B4.3 metadata contract is incomplete: "
            + ", ".join(missing_metadata)
        )

    inherited = list(
        require_sequence(
            contract.get("required_inherited_controls"),
            "B4.3 inherited-control contract",
        )
    )
    if len(inherited) != len(set(inherited)):
        raise VerificationError(
            "B4.3 inherited controls contain duplicates."
        )

    evidence_roles = list(
        require_sequence(
            contract.get("required_evidence_roles"),
            "B4.3 evidence-role contract",
        )
    )
    if len(evidence_roles) != len(set(evidence_roles)):
        raise VerificationError(
            "B4.3 evidence roles contain duplicates."
        )

    return contract


def validate_lifecycle_record(path: Path) -> dict:
    """Validate the controlled B4.3 lifecycle record."""

    metadata, body = read_front_matter(path)
    expected = {
        "document_id": "ESP32S3-PB-B4.3",
        "title": (
            "Clean Checkout-to-Flash Reproduction "
            "and Cluster B Gate"
        ),
        "phase": "B",
        "cluster": "B4",
        "work_package": "B4.3",
        "gate": "G-B",
        "owner": "Me",
        "approver": "Me",
        "classification": "Internal Engineering",
        "repository": "https://github.com/CPParthasarathy/SQD",
        "parent_baseline": (
            "196c46e5b90b568f8639a061e4dc5370db57c091"
        ),
    }
    for name, expected_value in expected.items():
        if metadata.get(name) != expected_value:
            raise VerificationError(
                f"Incorrect B4.3 lifecycle field {name}: "
                f"{metadata.get(name)!r}"
            )

    status = metadata.get("status")
    if status not in {"In Progress", "Accepted"}:
        raise VerificationError(
            f"Invalid B4.3 lifecycle status: {status!r}"
        )
    if status == "Accepted":
        if not metadata.get("accepted"):
            raise VerificationError(
                "Accepted B4.3 record lacks an accepted date."
            )
        accepted_commit = metadata.get("accepted_commit")
        if (
            not isinstance(accepted_commit, str)
            or not SHA1_RE.fullmatch(accepted_commit)
        ):
            raise VerificationError(
                "Accepted B4.3 record lacks a full accepted_commit."
            )

    required_body_terms = (
        "tools/ci/b4_3_reproduction_contract.json",
        "tools/ci/verify_b4_3.py",
        "tools/ci/tests/test_b4_3_reproduction.py",
        "tools/scripts/B4.3_Reproduce_Clean_Checkout_To_Flash.ps1",
        "main/CMakeLists.txt",
        "main/main.c",
        "Local hardware verification",
        "Pull-request CI",
        "Post-merge main CI",
        "Cluster B gate",
    )
    for term in required_body_terms:
        if term not in body:
            raise VerificationError(
                "B4.3 lifecycle record omits required content: "
                + term
            )

    return metadata


def run_git(
    repo_root: Path,
    arguments: Sequence[str],
    *,
    allow_failure: bool = False,
) -> str:
    """Run Git and return stripped stdout."""

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


def validate_checkout_policy(repo_root: Path) -> None:
    """Validate deterministic cross-platform Git checkout attributes."""

    attributes_path = repo_root / GIT_ATTRIBUTES_RELATIVE_PATH
    data = attributes_path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise VerificationError(
            ".gitattributes must not contain a UTF-8 BOM."
        )
    if b"\r" in data:
        raise VerificationError(
            ".gitattributes must use LF line endings."
        )
    if not data.endswith(b"\n"):
        raise VerificationError(
            ".gitattributes must end with a newline."
        )

    lines = {
        line.strip()
        for line in data.decode("utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for required_line in REQUIRED_ATTRIBUTE_LINES:
        if required_line not in lines:
            raise VerificationError(
                "Missing deterministic checkout attribute: "
                + required_line
            )

    output = run_git(
        repo_root,
        [
            "check-attr",
            "eol",
            "--",
            *REQUIRED_LF_ATTRIBUTE_PATHS,
        ],
    )
    resolved: dict[str, str] = {}
    for line in output.splitlines():
        try:
            relative_path, attribute, value = line.rsplit(
                ": ",
                maxsplit=2,
            )
        except ValueError as error:
            raise VerificationError(
                f"Invalid git check-attr output: {line!r}"
            ) from error
        if attribute != "eol":
            raise VerificationError(
                f"Unexpected Git attribute field: {attribute!r}"
            )
        resolved[relative_path] = value

    for relative_path in REQUIRED_LF_ATTRIBUTE_PATHS:
        if resolved.get(relative_path) != "lf":
            raise VerificationError(
                "Git checkout policy does not force LF for "
                f"{relative_path}: {resolved.get(relative_path)!r}"
            )


def validate_repository(repo_root: Path) -> tuple[dict, dict]:
    """Validate static B4.3 repository contracts."""

    repo_root = repo_root.resolve()
    for relative_path in FOUNDATION_PATHS:
        path = repo_root / relative_path
        if not path.is_file():
            raise VerificationError(
                f"Required B4.3 foundation file is missing: "
                f"{relative_path.as_posix()}"
            )

    validate_checkout_policy(repo_root)

    contract = validate_contract(
        repo_root / CONTRACT_RELATIVE_PATH
    )
    lifecycle = validate_lifecycle_record(
        repo_root / RECORD_RELATIVE_PATH
    )

    for relative_path in contract["required_inherited_controls"]:
        if not (repo_root / relative_path).is_file():
            raise VerificationError(
                "Required inherited control is missing: "
                + relative_path
            )

    main_cmake = (
        repo_root / "main" / "CMakeLists.txt"
    ).read_text(encoding="utf-8")
    if "PRIV_REQUIRES build_metadata" not in main_cmake:
        raise VerificationError(
            "main component does not require build_metadata."
        )

    main_c = (
        repo_root / "main" / "main.c"
    ).read_text(encoding="utf-8")
    if '#include "sqd_build_metadata.h"' not in main_c:
        raise VerificationError(
            "main firmware does not include build metadata."
        )
    if "sqd_build_metadata_log();" not in main_c:
        raise VerificationError(
            "main firmware does not log build metadata."
        )

    orchestrator_path = repo_root / str(
        contract["orchestrator_path"]
    )
    orchestrator = orchestrator_path.read_text(encoding="utf-8")
    required_orchestrator_terms = (
        "ConfirmHardwareOperations",
        "PlanOnly",
        "Resolve-B43SerialPort",
        "B1.3_Verify_Workstation.ps1",
        "B3.3_ToolchainGuard.ps1",
        "B3.2_Build.ps1",
        "B3.2_Erase.ps1",
        "B3.2_Flash.ps1",
        "B3.2_Monitor.ps1",
        "run_host_tests.py",
        "verify_b4_2.py",
        "SHA256SUMS.txt",
        "B4.3_reproduction_manifest_",
    )
    for term in required_orchestrator_terms:
        if term not in orchestrator:
            raise VerificationError(
                "B4.3 orchestrator omits required control: "
                + term
            )
    if re.search(r'(?i)["\']COM[0-9]+["\']', orchestrator):
        raise VerificationError(
            "B4.3 orchestrator must not hard-code a COM port."
        )

    git_root = run_git(
        repo_root,
        ["rev-parse", "--show-toplevel"],
    )
    if Path(git_root).resolve() != repo_root:
        raise VerificationError(
            "Selected repository root does not match Git root."
        )

    head = run_git(repo_root, ["rev-parse", "HEAD"])
    if not SHA1_RE.fullmatch(head):
        raise VerificationError(
            f"Repository HEAD is not a full SHA: {head!r}"
        )

    parent = str(contract["parent_baseline"])
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", parent, head],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise VerificationError(
            "B4.3 repository HEAD does not descend from "
            f"the accepted parent baseline {parent}."
        )

    return contract, lifecycle


def resolve_evidence_root(
    manifest_path: Path,
    evidence: Mapping[str, object],
) -> Path:
    """Resolve the evidence root without path traversal."""

    root_value = evidence.get("root")
    if not isinstance(root_value, str) or not root_value.strip():
        raise VerificationError(
            "Reproduction manifest evidence.root is missing."
        )
    root = Path(root_value)
    if not root.is_absolute():
        root = manifest_path.parent / root
    return root.resolve()


def parse_checksums(path: Path) -> dict[str, str]:
    """Read a SHA256SUMS-style file."""

    if not path.is_file():
        raise VerificationError(
            f"Evidence checksum inventory is missing: {path}"
        )
    records: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        match = re.fullmatch(
            r"([0-9a-fA-F]{64})  (.+)",
            line,
        )
        if match is None:
            raise VerificationError(
                "Invalid checksum record at "
                f"{path}:{line_number}: {raw_line!r}"
            )
        relative_path = match.group(2).replace("\\", "/")
        if (
            relative_path.startswith("/")
            or ".." in Path(relative_path).parts
        ):
            raise VerificationError(
                f"Unsafe checksum path: {relative_path}"
            )
        if relative_path in records:
            raise VerificationError(
                f"Duplicate checksum path: {relative_path}"
            )
        records[relative_path] = match.group(1).lower()
    return records


def validate_metadata(
    metadata: Mapping[str, object],
    contract: Mapping[str, object],
    source_commit: str,
    profile: str,
) -> None:
    """Validate firmware metadata against source and contract."""

    required_keys = list(contract["required_metadata_keys"])
    missing = [
        key
        for key in required_keys
        if key not in metadata
        or metadata[key] in (None, "")
    ]
    if missing:
        raise VerificationError(
            "Firmware metadata is incomplete: "
            + ", ".join(missing)
        )
    expected = {
        "git_commit": source_commit,
        "git_dirty": "false",
        "build_profile": profile,
        "target": contract["toolchain"]["target"],
        "idf_version": contract["toolchain"]["esp_idf_version"],
        "hardware_compatibility": (
            contract["hardware"]["compatibility"]
        ),
    }
    for name, expected_value in expected.items():
        actual = str(metadata.get(name))
        if actual != str(expected_value):
            raise VerificationError(
                f"Firmware metadata mismatch for {name}: "
                f"expected {expected_value!r}, detected {actual!r}."
            )
    if not SHA256_RE.fullmatch(str(metadata["elf_sha256"])):
        raise VerificationError(
            "Firmware metadata elf_sha256 is invalid."
        )


def validate_manifest(
    manifest_path: Path,
    contract: Mapping[str, object],
) -> dict:
    """Validate one physical B4.3 reproduction manifest."""

    manifest_path = manifest_path.expanduser().resolve()
    manifest = read_json(manifest_path)
    expected = {
        "schema_version": 1,
        "work_package": "B4.3",
        "operation": "clean-checkout-to-flash-reproduction",
        "status": "PASS",
    }
    for name, expected_value in expected.items():
        if manifest.get(name) != expected_value:
            raise VerificationError(
                f"Incorrect reproduction field {name}: "
                f"{manifest.get(name)!r}"
            )

    pass_id = manifest.get("pass_id")
    if not isinstance(pass_id, str) or not pass_id.strip():
        raise VerificationError(
            "Reproduction manifest pass_id is missing."
        )

    source = require_mapping(
        manifest.get("source"),
        "Reproduction source",
    )
    if source.get("repository") != contract["repository"]:
        raise VerificationError(
            "Reproduction source repository mismatch."
        )
    if source.get("parent_baseline") != contract["parent_baseline"]:
        raise VerificationError(
            "Reproduction parent baseline mismatch."
        )
    source_commit = source.get("commit")
    if (
        not isinstance(source_commit, str)
        or not SHA1_RE.fullmatch(source_commit)
    ):
        raise VerificationError(
            "Reproduction source commit is invalid."
        )

    cleanroom = require_mapping(
        manifest.get("cleanroom"),
        "Reproduction cleanroom",
    )
    for name in ("root", "clone_root"):
        if not isinstance(cleanroom.get(name), str):
            raise VerificationError(
                f"Reproduction cleanroom.{name} is missing."
            )
    if cleanroom.get("clone_created") is not True:
        raise VerificationError(
            "Reproduction did not record a created clone."
        )
    if cleanroom.get("existing_directory_reused") is not False:
        raise VerificationError(
            "Reproduction reused an existing cleanroom directory."
        )
    if cleanroom.get("existing_build_reused") is not False:
        raise VerificationError(
            "Reproduction reused an existing build directory."
        )
    if cleanroom.get("tracked_tree_clean_before") is not True:
        raise VerificationError(
            "Clean clone was not clean before execution."
        )
    if cleanroom.get("tracked_tree_clean_after") is not True:
        raise VerificationError(
            "Clean clone was not clean after execution."
        )

    toolchain = require_mapping(
        manifest.get("toolchain"),
        "Reproduction toolchain",
    )
    for name, expected_value in contract["toolchain"].items():
        if toolchain.get(name) != expected_value:
            raise VerificationError(
                f"Reproduction toolchain mismatch for {name}."
            )

    build = require_mapping(
        manifest.get("build"),
        "Reproduction build",
    )
    profile = build.get("profile")
    if profile not in contract["build"]["allowed_profiles"]:
        raise VerificationError(
            f"Unsupported reproduction profile: {profile!r}"
        )
    if build.get("status") != "PASS":
        raise VerificationError(
            "Controlled build status is not PASS."
        )
    if not isinstance(build.get("directory"), str):
        raise VerificationError(
            "Controlled build directory is missing."
        )
    if not SHA256_RE.fullmatch(
        str(build.get("application_sha256", ""))
    ):
        raise VerificationError(
            "Controlled application SHA-256 is invalid."
        )

    device = require_mapping(
        manifest.get("device"),
        "Reproduction device",
    )
    if device.get("status") != "PASS":
        raise VerificationError(
            "Physical device status is not PASS."
        )
    if not COM_RE.fullmatch(str(device.get("port", ""))):
        raise VerificationError(
            "Physical serial port is invalid."
        )
    if (
        device.get("hardware_compatibility")
        != contract["hardware"]["compatibility"]
    ):
        raise VerificationError(
            "Physical hardware compatibility mismatch."
        )
    for name in ("erase_status", "flash_status"):
        if device.get(name) != "PASS":
            raise VerificationError(
                f"Physical {name} is not PASS."
            )

    monitor = require_mapping(
        manifest.get("monitor"),
        "Reproduction monitor",
    )
    if monitor.get("status") != "PASS":
        raise VerificationError(
            "Serial monitor status is not PASS."
        )
    if int(monitor.get("fatal_markers", -1)) != 0:
        raise VerificationError(
            "Serial monitor contains fatal markers."
        )
    if int(monitor.get("heartbeat_records", 0)) < 1:
        raise VerificationError(
            "Serial monitor contains no heartbeat."
        )
    marker_map = require_mapping(
        monitor.get("required_markers"),
        "Serial required-marker results",
    )
    for marker in contract["required_serial_markers"]:
        if marker_map.get(marker) is not True:
            raise VerificationError(
                f"Serial marker was not detected: {marker}"
            )
    metadata = require_mapping(
        monitor.get("metadata"),
        "Firmware metadata",
    )
    validate_metadata(
        metadata,
        contract,
        source_commit,
        str(profile),
    )

    evidence = require_mapping(
        manifest.get("evidence"),
        "Reproduction evidence",
    )
    evidence_root = resolve_evidence_root(
        manifest_path,
        evidence,
    )
    checksum_name = evidence.get("checksums")
    if (
        not isinstance(checksum_name, str)
        or Path(checksum_name).name != "SHA256SUMS.txt"
    ):
        raise VerificationError(
            "Evidence checksum inventory must be SHA256SUMS.txt."
        )
    checksum_path = evidence_root / checksum_name
    checksum_records = parse_checksums(checksum_path)

    files = require_sequence(
        evidence.get("files"),
        "Reproduction evidence files",
    )
    observed_roles: set[str] = set()
    observed_paths: set[str] = set()
    for index, item in enumerate(files):
        record = require_mapping(
            item,
            f"Evidence file record {index}",
        )
        role = record.get("role")
        relative_path = record.get("path")
        expected_hash = str(record.get("sha256", "")).lower()
        if not isinstance(role, str) or not role:
            raise VerificationError(
                f"Evidence record {index} has no role."
            )
        if (
            not isinstance(relative_path, str)
            or not relative_path
        ):
            raise VerificationError(
                f"Evidence record {index} has no path."
            )
        normalized = relative_path.replace("\\", "/")
        if (
            normalized.startswith("/")
            or ".." in Path(normalized).parts
        ):
            raise VerificationError(
                f"Unsafe evidence path: {relative_path}"
            )
        if normalized in observed_paths:
            raise VerificationError(
                f"Duplicate evidence path: {normalized}"
            )
        if not SHA256_RE.fullmatch(expected_hash):
            raise VerificationError(
                f"Invalid evidence SHA-256: {normalized}"
            )
        evidence_path = (evidence_root / normalized).resolve()
        try:
            evidence_path.relative_to(evidence_root)
        except ValueError as error:
            raise VerificationError(
                f"Evidence path escapes root: {normalized}"
            ) from error
        if not evidence_path.is_file():
            raise VerificationError(
                f"Evidence file is missing: {normalized}"
            )
        size_bytes = record.get("size_bytes")
        if (
            not isinstance(size_bytes, int)
            or size_bytes <= 0
            or evidence_path.stat().st_size != size_bytes
        ):
            raise VerificationError(
                f"Evidence size mismatch: {normalized}"
            )
        actual_hash = digest(evidence_path)
        if actual_hash != expected_hash:
            raise VerificationError(
                f"Evidence hash mismatch: {normalized}"
            )
        if checksum_records.get(normalized) != expected_hash:
            raise VerificationError(
                f"Checksum inventory mismatch: {normalized}"
            )
        observed_roles.add(role)
        observed_paths.add(normalized)

    required_roles = set(contract["required_evidence_roles"])
    missing_roles = sorted(required_roles.difference(observed_roles))
    if missing_roles:
        raise VerificationError(
            "Reproduction evidence roles are incomplete: "
            + ", ".join(missing_roles)
        )

    if set(checksum_records) != observed_paths:
        raise VerificationError(
            "SHA256SUMS.txt does not cover exactly the evidence files."
        )

    return manifest


def validate_repeatability(
    manifests: Iterable[dict],
    contract: Mapping[str, object],
) -> None:
    """Validate independent-pass and common-identity constraints."""

    values = list(manifests)
    required_passes = int(
        contract["repeatability"]["required_passes"]
    )
    if len(values) < required_passes:
        raise VerificationError(
            f"B4.3 requires {required_passes} reproduction passes; "
            f"received {len(values)}."
        )

    pass_ids = [str(item["pass_id"]) for item in values]
    clone_roots = [
        str(item["cleanroom"]["clone_root"]).lower()
        for item in values
    ]
    build_directories = [
        str(item["build"]["directory"]).lower()
        for item in values
    ]
    for description, entries in (
        ("pass identifiers", pass_ids),
        ("clean-clone roots", clone_roots),
        ("build directories", build_directories),
    ):
        if len(entries) != len(set(entries)):
            raise VerificationError(
                f"Repeatability reused {description}."
            )

    source_commits = {
        str(item["source"]["commit"]).lower()
        for item in values
    }
    profiles = {
        str(item["build"]["profile"])
        for item in values
    }
    idf_commits = {
        str(item["toolchain"]["esp_idf_commit"]).lower()
        for item in values
    }
    python_versions = {
        str(item["toolchain"]["python_version"])
        for item in values
    }
    for description, entries in (
        ("source commit", source_commits),
        ("build profile", profiles),
        ("ESP-IDF commit", idf_commits),
        ("Python version", python_versions),
    ):
        if len(entries) != 1:
            raise VerificationError(
                f"Repeatability passes disagree on {description}."
            )


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    default_repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description=(
            "Verify the B4.3 clean checkout-to-flash "
            "and Cluster B gate contract."
        )
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help="Repository root.",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="Override the B4.3 contract path.",
    )
    parser.add_argument(
        "--contract-only",
        action="store_true",
        help="Validate repository contracts without evidence.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        default=[],
        help=(
            "Physical reproduction manifest. Specify at least twice "
            "for full repeatability verification."
        ),
    )
    return parser.parse_args()


def main() -> int:
    """Execute B4.3 verification."""

    arguments = parse_arguments()
    repo_root = arguments.repo_root.expanduser().resolve()
    try:
        contract, lifecycle = validate_repository(repo_root)
        if arguments.contract is not None:
            contract = validate_contract(
                arguments.contract.expanduser().resolve()
            )

        print("B4.3 repository contract")
        print(f"Repository:      {repo_root}")
        print(f"Parent baseline: {contract['parent_baseline']}")
        print(f"Lifecycle:       {lifecycle['status']}")
        print("Firmware metadata logging: PASS")
        print("Deterministic checkout policy: PASS")
        print("Inherited control inventory: PASS")
        print("Contract schema: PASS")

        if arguments.contract_only:
            print("")
            print("PASS: B4.3 repository contract validated.")
            return 0

        if not arguments.manifest:
            raise VerificationError(
                "No B4.3 reproduction manifests were supplied."
            )

        manifests = [
            validate_manifest(path, contract)
            for path in arguments.manifest
        ]
        validate_repeatability(manifests, contract)

        print(f"Physical passes: {len(manifests)}")
        print("Evidence integrity: PASS")
        print("Firmware/source traceability: PASS")
        print("Independent repeatability: PASS")
        print("")
        print("PASS: B4.3 reproduction evidence validated.")
        return 0

    except VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
