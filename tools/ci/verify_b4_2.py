#!/usr/bin/env python3
"""Verify the B4.2 artifact archive and traceability contract."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence

import yaml

PROFILES = ("debug", "validation", "production")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class VerificationError(RuntimeError):
    """B4.2 repository or archive verification failure."""


def load_module(module_name: str, module_path: Path) -> ModuleType:
    """Load a repository Python file without requiring a package."""

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise VerificationError(
            f"Unable to load module specification: {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def read_front_matter(path: Path) -> tuple[dict, str]:
    """Read YAML front matter and the Markdown body."""

    if not path.is_file():
        raise VerificationError(f"Lifecycle record is missing: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise VerificationError("Lifecycle record lacks YAML front matter.")
    try:
        closing = lines.index("---", 1)
    except ValueError as error:
        raise VerificationError(
            "Lifecycle record front matter is not terminated."
        ) from error
    try:
        metadata = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as error:
        raise VerificationError(
            f"Lifecycle record front matter is invalid: {error}"
        ) from error
    if not isinstance(metadata, dict):
        raise VerificationError("Lifecycle record metadata must be a mapping.")
    return metadata, "\n".join(lines[closing + 1 :])


def validate_lifecycle_record(path: Path) -> dict:
    """Validate the controlled B4.2 lifecycle record."""

    metadata, body = read_front_matter(path)
    expected = {
        "document_id": "ESP32S3-PB-B4.2",
        "title": "Artifact Archive and Traceability",
        "phase": "B",
        "cluster": "B4",
        "work_package": "B4.2",
        "owner": "Me",
        "approver": "Me",
        "classification": "Internal Engineering",
        "repository": "https://github.com/CPParthasarathy/SQD",
    }
    for name, value in expected.items():
        if metadata.get(name) != value:
            raise VerificationError(
                f"Incorrect lifecycle field {name}: {metadata.get(name)!r}"
            )

    status = metadata.get("status")
    if status not in {"In Progress", "Accepted"}:
        raise VerificationError(f"Invalid B4.2 lifecycle status: {status!r}")
    if status == "Accepted":
        if not metadata.get("accepted"):
            raise VerificationError("Accepted record lacks an accepted date.")
        accepted_commit = metadata.get("accepted_commit")
        if not isinstance(accepted_commit, str) or not SHA_RE.fullmatch(
            accepted_commit
        ):
            raise VerificationError(
                "Accepted record lacks a full accepted_commit SHA."
            )

    authoritative_paths = (
        ".github/workflows/ci.yml",
        "tools/ci/artifact_archive.py",
        "tools/ci/artifact_archive_contract.json",
        "tools/ci/check_workflow.py",
        "tools/ci/run_profile_build.ps1",
        "tools/ci/verify_b4_2.py",
        "tools/ci/tests/test_artifact_archive.py",
    )
    for relative_path in authoritative_paths:
        if f"- {relative_path}" not in body:
            raise VerificationError(
                "Lifecycle record omits authoritative file: " + relative_path
            )
    return metadata


def repository_commit(repo_root: Path) -> str:
    """Resolve the repository HEAD as a full commit identifier."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        diagnostic = (result.stderr or result.stdout).strip()
        raise VerificationError(f"Unable to resolve repository HEAD: {diagnostic}")
    commit = result.stdout.strip()
    if not SHA_RE.fullmatch(commit):
        raise VerificationError(f"Repository HEAD is not a full SHA: {commit!r}")
    return commit.lower()


def validate_traceability(manifest: dict, expected_profile: str) -> None:
    """Validate traceability fields beyond payload integrity."""

    archive = manifest.get("archive")
    source = manifest.get("source")
    toolchain = manifest.get("toolchain")
    if not isinstance(archive, dict):
        raise VerificationError("Manifest archive metadata is missing.")
    if not isinstance(source, dict):
        raise VerificationError("Manifest source metadata is missing.")
    if not isinstance(toolchain, dict):
        raise VerificationError("Manifest toolchain metadata is missing.")

    if archive.get("profile") != expected_profile:
        raise VerificationError("Manifest profile traceability mismatch.")
    if not archive.get("hardware_compatibility"):
        raise VerificationError("Manifest hardware compatibility is missing.")
    if not source.get("repository"):
        raise VerificationError("Manifest source repository is missing.")
    source_commit = source.get("commit")
    if not isinstance(source_commit, str) or not SHA_RE.fullmatch(source_commit):
        raise VerificationError("Manifest source commit is invalid.")
    if not toolchain.get("esp_idf_version"):
        raise VerificationError("Manifest ESP-IDF version is missing.")
    idf_commit = toolchain.get("esp_idf_commit")
    if not isinstance(idf_commit, str) or not SHA_RE.fullmatch(idf_commit):
        raise VerificationError("Manifest ESP-IDF commit is invalid.")

    github = source.get("github")
    if not isinstance(github, dict):
        raise VerificationError("Manifest GitHub traceability object is missing.")
    if str(github.get("actions", "")).lower() == "true":
        required_github_fields = (
            "workflow",
            "job",
            "run_id",
            "run_number",
            "run_attempt",
            "event_name",
            "ref",
            "sha",
            "repository",
        )
        missing = [
            name for name in required_github_fields if not github.get(name)
        ]
        if missing:
            raise VerificationError(
                "GitHub archive traceability is incomplete: "
                + ", ".join(missing)
            )
        if str(github["sha"]).lower() != source_commit.lower():
            raise VerificationError(
                "GitHub SHA does not match the manifest source commit."
            )


def validate_repository(repo_root: Path) -> tuple[ModuleType, dict]:
    """Validate static B4.2 repository contracts."""

    repo_root = repo_root.resolve()
    archive_path = repo_root / "tools" / "ci" / "artifact_archive.py"
    workflow_check_path = repo_root / "tools" / "ci" / "check_workflow.py"
    contract_path = (
        repo_root / "tools" / "ci" / "artifact_archive_contract.json"
    )
    workflow_path = repo_root / ".github" / "workflows" / "ci.yml"
    record_path = (
        repo_root
        / "docs"
        / "phase-b"
        / "B4.2_Artifact_Archive_and_Traceability.md"
    )

    archive_module = load_module("sqd_b42_artifact_archive", archive_path)
    workflow_module = load_module("sqd_b42_check_workflow", workflow_check_path)
    contract = archive_module.load_contract(contract_path)
    archive_module.self_test(contract_path)
    workflow_module.validate_workflow(workflow_path)
    validate_lifecycle_record(record_path)
    return archive_module, contract


def verify_archive_matrix(
    repo_root: Path,
    archive_root: Path,
    profiles: Sequence[str],
    source_commit: str,
) -> None:
    """Verify all requested profile archives and traceability metadata."""

    if not SHA_RE.fullmatch(source_commit):
        raise VerificationError("Expected source commit must be a full SHA.")
    archive_module, _ = validate_repository(repo_root)
    contract_path = (
        repo_root / "tools" / "ci" / "artifact_archive_contract.json"
    )
    for profile in profiles:
        profile_root = archive_root / profile
        if not profile_root.is_dir():
            raise VerificationError(
                f"Profile archive directory is missing: {profile_root}"
            )
        archive_module.verify(
            profile_root,
            contract_path,
            expected_profile=profile,
            expected_source_commit=source_commit,
        )
        manifest = archive_module.read_json(
            profile_root / archive_module.MANIFEST
        )
        validate_traceability(manifest, profile)


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description=(
            "Verify B4.2 repository contracts and finalized profile archives."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=default_root)
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument(
        "--profile",
        action="append",
        choices=PROFILES,
        dest="profiles",
    )
    parser.add_argument("--source-commit")
    return parser.parse_args()


def main() -> int:
    """Run B4.2 verification."""

    arguments = parse_arguments()
    repo_root = arguments.repo_root.resolve()
    archive_root = (
        arguments.archive_root.resolve()
        if arguments.archive_root
        else repo_root / "artifacts" / "b4.2" / "profile-build"
    )
    profiles = tuple(arguments.profiles or PROFILES)

    try:
        print("B4.2 artifact archive verification")
        print(f"Repository: {repo_root}")
        validate_repository(repo_root)
        print("Workflow contract: PASS")
        print("Archive contract: PASS")
        print("Archive self-test: PASS")
        print("Lifecycle record: PASS")

        if arguments.contract_only:
            print("")
            print("PASS: B4.2 repository contract validated.")
            return 0

        source_commit = (
            arguments.source_commit.lower()
            if arguments.source_commit
            else repository_commit(repo_root)
        )
        print(f"Source commit: {source_commit}")
        print(f"Archive root:  {archive_root}")
        verify_archive_matrix(
            repo_root,
            archive_root,
            profiles,
            source_commit,
        )
        for profile in profiles:
            print(f"{profile} archive: PASS")
        print("")
        print("PASS: B4.2 profile archive matrix verified.")
        return 0
    except (VerificationError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
