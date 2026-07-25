#!/usr/bin/env python3
"""Create and verify B4.2 firmware artifact archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROFILES = ("debug", "validation", "production")
MANIFEST = "B4.2_artifact_manifest.json"
CHECKSUMS = "SHA256SUMS.txt"
PROVENANCE = "B4.2_profile_build_provenance.json"
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class ArchiveError(RuntimeError):
    """B4.2 archive contract failure."""


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise ArchiveError(f"Missing JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ArchiveError(f"Invalid JSON file {path}: {error}") from error
    if not isinstance(value, dict):
        raise ArchiveError(f"JSON root must be an object: {path}")
    return value


def write_text(path: Path, text: str) -> None:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_text(text.rstrip("\n") + "\n", encoding="utf-8", newline="\n")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        result = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise ArchiveError(f"Path escapes archive root: {path}") from error
    if ".." in result.parts:
        raise ArchiveError(f"Unsafe archive path: {result}")
    return result.as_posix()


def load_contract(path: Path) -> dict:
    contract = read_json(path)
    expected = {
        "schema_version": 1,
        "work_package": "B4.2",
        "archive_root": "artifacts/b4.2/profile-build",
        "profiles": list(PROFILES),
        "retention_days": 30,
        "manifest_path": MANIFEST,
        "checksum_path": CHECKSUMS,
    }
    for name, value in expected.items():
        if contract.get(name) != value:
            raise ArchiveError(
                f"Incorrect contract field {name}: {contract.get(name)!r}"
            )

    static = {
        "build/sdkconfig",
        "build/project_description.json",
        "build/flasher_args.json",
        "build/bootloader/bootloader.bin",
        "build/partition_table/partition-table.bin",
        PROVENANCE,
    }
    if set(contract.get("required_static_paths", [])) != static:
        raise ArchiveError("Incorrect required_static_paths contract.")
    if contract.get("required_project_suffixes") != [".bin", ".elf", ".map"]:
        raise ArchiveError("Incorrect project artifact suffix contract.")
    if contract.get("required_evidence_globs") != [
        "evidence/B3.2_${profile}_build_result_*.json"
    ]:
        raise ArchiveError("Incorrect B3.2 evidence contract.")
    return contract


def payload_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ArchiveError(f"Symlink is forbidden: {path}")
        if path.is_file() and relative(path, root) not in {
            MANIFEST,
            CHECKSUMS,
        }:
            files.append(path)
    files.sort(key=lambda path: relative(path, root))
    if not files:
        raise ArchiveError("Archive contains no payload files.")
    return files


def mandatory_paths(root: Path, profile: str, contract: dict) -> set[str]:
    project = read_json(root / "build" / "project_description.json")
    project_name = project.get("project_name")
    if (
        not isinstance(project_name, str)
        or not project_name
        or Path(project_name).name != project_name
    ):
        raise ArchiveError("Invalid project_name in project_description.json.")

    required = set(contract["required_static_paths"])
    required.update(
        f"build/{project_name}{suffix}"
        for suffix in contract["required_project_suffixes"]
    )
    for pattern in contract["required_evidence_globs"]:
        expanded = pattern.replace("${profile}", profile)
        matches = sorted(root.glob(expanded))
        if not matches:
            raise ArchiveError(f"No evidence matches: {expanded}")
        required.update(relative(path, root) for path in matches if path.is_file())
    return required


def file_records(root: Path) -> list[dict]:
    records = []
    for path in payload_files(root):
        rel = relative(path, root)
        first = Path(rel).parts[0]
        records.append(
            {
                "path": rel,
                "category": (
                    first
                    if first in {"build", "evidence", "logs"}
                    else "metadata"
                ),
                "size_bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        )
    return records


def checksum_text(root: Path, records: list[dict]) -> str:
    entries = [(record["sha256"], record["path"]) for record in records]
    entries.append((digest(root / MANIFEST), MANIFEST))
    entries.sort(key=lambda item: item[1])
    return "".join(f"{sha}  {path}\n" for sha, path in entries)


def verify(
    root: Path,
    contract_path: Path,
    expected_profile: str | None = None,
    expected_source_commit: str | None = None,
) -> None:
    root = root.resolve()
    contract = load_contract(contract_path)
    manifest = read_json(root / MANIFEST)

    if manifest.get("schema_version") != 1:
        raise ArchiveError("Manifest schema_version must be 1.")
    if manifest.get("work_package") != "B4.2":
        raise ArchiveError("Manifest work_package must be B4.2.")
    if manifest.get("status") != "PASS":
        raise ArchiveError("Manifest status must be PASS.")

    archive = manifest.get("archive", {})
    source = manifest.get("source", {})
    profile = archive.get("profile")
    source_commit = source.get("commit")
    records = manifest.get("files")

    if profile not in PROFILES:
        raise ArchiveError(f"Invalid manifest profile: {profile!r}")
    if expected_profile and profile != expected_profile:
        raise ArchiveError("Manifest profile mismatch.")
    if not isinstance(source_commit, str) or not SHA_RE.fullmatch(source_commit):
        raise ArchiveError("Manifest source commit is invalid.")
    if (
        expected_source_commit
        and source_commit.lower() != expected_source_commit.lower()
    ):
        raise ArchiveError("Manifest source commit mismatch.")
    if not isinstance(records, list):
        raise ArchiveError("Manifest files must be an array.")

    actual_paths = {relative(path, root) for path in payload_files(root)}
    recorded_paths = []
    for record in records:
        if not isinstance(record, dict):
            raise ArchiveError("Invalid manifest file record.")
        rel = record.get("path")
        path = root / str(rel)
        if not path.is_file():
            raise ArchiveError(f"Manifest file is missing: {rel}")
        if path.stat().st_size != record.get("size_bytes"):
            raise ArchiveError(f"Size mismatch: {rel}")
        if digest(path) != record.get("sha256"):
            raise ArchiveError(f"SHA-256 mismatch: {rel}")
        recorded_paths.append(str(rel))

    if recorded_paths != sorted(recorded_paths):
        raise ArchiveError("Manifest file records are not sorted.")
    if len(recorded_paths) != len(set(recorded_paths)):
        raise ArchiveError("Manifest contains duplicate paths.")
    if set(recorded_paths) != actual_paths:
        raise ArchiveError("Manifest does not exactly match payload files.")

    missing = mandatory_paths(root, profile, contract) - set(recorded_paths)
    if missing:
        raise ArchiveError(
            "Manifest omits mandatory files: " + ", ".join(sorted(missing))
        )
    if archive.get("payload_file_count") != len(recorded_paths):
        raise ArchiveError("Manifest payload_file_count is incorrect.")

    checksum_path = root / CHECKSUMS
    if not checksum_path.is_file():
        raise ArchiveError(f"Missing checksum inventory: {checksum_path}")
    if checksum_path.read_text(encoding="utf-8") != checksum_text(root, records):
        raise ArchiveError("SHA256SUMS.txt does not match the archive.")


def finalize(arguments: argparse.Namespace) -> None:
    root = arguments.archive_root.resolve()
    contract = load_contract(arguments.contract)
    if not root.is_dir():
        raise ArchiveError(f"Archive root does not exist: {root}")
    if not SHA_RE.fullmatch(arguments.source_commit):
        raise ArchiveError("Source commit must be a full 40-character SHA.")
    if not SHA_RE.fullmatch(arguments.idf_commit):
        raise ArchiveError("ESP-IDF commit must be a full 40-character SHA.")

    (root / MANIFEST).unlink(missing_ok=True)
    (root / CHECKSUMS).unlink(missing_ok=True)
    records = file_records(root)
    missing = mandatory_paths(root, arguments.profile, contract) - {
        record["path"] for record in records
    }
    if missing:
        raise ArchiveError(
            "Mandatory files are missing: " + ", ".join(sorted(missing))
        )

    github_fields = (
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
    github = {
        name.lower().removeprefix("github_"): os.environ.get(name, "")
        for name in github_fields
    }
    manifest = {
        "schema_version": 1,
        "work_package": "B4.2",
        "operation": "artifact-archive-finalization",
        "status": "PASS",
        "created_utc": (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        ),
        "archive": {
            "profile": arguments.profile,
            "hardware_compatibility": arguments.hardware_compatibility,
            "payload_file_count": len(records),
        },
        "source": {
            "repository": arguments.source_repository,
            "commit": arguments.source_commit.lower(),
            "github": github,
        },
        "toolchain": {
            "esp_idf_version": arguments.idf_version,
            "esp_idf_commit": arguments.idf_commit.lower(),
        },
        "files": records,
    }
    write_text(root / MANIFEST, json.dumps(manifest, indent=2))
    write_text(root / CHECKSUMS, checksum_text(root, records))
    verify(
        root,
        arguments.contract,
        expected_profile=arguments.profile,
        expected_source_commit=arguments.source_commit,
    )


def create_fixture(root: Path) -> None:
    files = {
        "build/sdkconfig": 'CONFIG_IDF_TARGET="esp32s3"\n',
        "build/project_description.json": (
            '{"project_name":"sqd_firmware"}\n'
        ),
        "build/flasher_args.json": "{}\n",
        "build/sqd_firmware.bin": "application-bin\n",
        "build/sqd_firmware.elf": "application-elf\n",
        "build/sqd_firmware.map": "application-map\n",
        "build/bootloader/bootloader.bin": "bootloader-bin\n",
        "build/partition_table/partition-table.bin": "partition-bin\n",
        PROVENANCE: '{"status":"PASS"}\n',
        "evidence/B3.2_debug_build_result_20000101_000000.json": (
            '{"status":"PASS"}\n'
        ),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text(path, text)


def self_test(contract: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="sqd-b4.2-") as temporary:
        root = Path(temporary) / "debug"
        root.mkdir()
        create_fixture(root)
        values = argparse.Namespace(
            archive_root=root,
            contract=contract,
            profile="debug",
            source_repository="CPParthasarathy/SQD",
            source_commit="1" * 40,
            hardware_compatibility="heltec-wifi-lora-32-v3",
            idf_version="v6.0.2",
            idf_commit="2" * 40,
        )
        finalize(values)
        verify(root, contract, "debug", "1" * 40)
        (root / "build" / "sqd_firmware.bin").write_text(
            "tampered\n",
            encoding="utf-8",
        )
        try:
            verify(root, contract)
        except ArchiveError:
            return
        raise ArchiveError("Self-test did not detect payload tampering.")


def parse_arguments() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Create and verify B4.2 firmware artifact archives."
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=repo / "tools" / "ci" / "artifact_archive_contract.json",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("contract")
    commands.add_parser("self-test")

    finalizer = commands.add_parser("finalize")
    finalizer.add_argument("--archive-root", type=Path, required=True)
    finalizer.add_argument("--profile", choices=PROFILES, required=True)
    finalizer.add_argument("--source-repository", required=True)
    finalizer.add_argument("--source-commit", required=True)
    finalizer.add_argument("--hardware-compatibility", required=True)
    finalizer.add_argument("--idf-version", required=True)
    finalizer.add_argument("--idf-commit", required=True)

    verifier = commands.add_parser("verify")
    verifier.add_argument("--archive-root", type=Path, required=True)
    verifier.add_argument("--profile", choices=PROFILES)
    verifier.add_argument("--source-commit")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        contract = load_contract(arguments.contract)
        if arguments.command == "contract":
            print("B4.2 artifact archive contract")
            print(f"Profiles: {', '.join(contract['profiles'])}")
            print(f"Retention: {contract['retention_days']} days")
            print("PASS: B4.2 artifact contract validated.")
        elif arguments.command == "self-test":
            self_test(arguments.contract)
            print("Finalization: PASS")
            print("Verification: PASS")
            print("Tamper detection: PASS")
            print("PASS: B4.2 artifact archive self-test completed.")
        elif arguments.command == "finalize":
            finalize(arguments)
            print(f"Archive: {arguments.archive_root.resolve()}")
            print(f"Manifest: {MANIFEST}")
            print(f"Checksums: {CHECKSUMS}")
            print("PASS: B4.2 artifact archive finalized.")
        else:
            verify(
                arguments.archive_root,
                arguments.contract,
                arguments.profile,
                arguments.source_commit,
            )
            print("Manifest inventory: PASS")
            print("Mandatory payloads: PASS")
            print("SHA-256 verification: PASS")
            print("PASS: B4.2 artifact archive verified.")
        return 0
    except ArchiveError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
