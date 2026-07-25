#!/usr/bin/env python3
"""Validate the controlled B4.2 GitHub Actions workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml


EXPECTED_WORKFLOW_NAME = "B4.2 Artifact Archive and Traceability"
EXPECTED_PROFILES = (
    "debug",
    "validation",
    "production",
)

REQUIRED_TRIGGERS = frozenset(
    {
        "pull_request",
        "push",
        "workflow_dispatch",
    }
)

REQUIRED_ACTIONS = frozenset(
    {
        "actions/checkout@v4",
        "actions/setup-python@v6",
        "actions/cache@v4",
        "actions/upload-artifact@v4",
    }
)


class WorkflowContractError(RuntimeError):
    """Raised when the workflow does not meet the B4.2 contract."""


def require_mapping(
    value: Any,
    description: str,
) -> Mapping[str, Any]:
    """Require a mapping and return it."""

    if not isinstance(value, Mapping):
        raise WorkflowContractError(
            f"{description} must be a mapping."
        )

    return value


def require_sequence(
    value: Any,
    description: str,
) -> Sequence[Any]:
    """Require a non-string sequence and return it."""

    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
    ):
        raise WorkflowContractError(
            f"{description} must be a sequence."
        )

    return value


def read_controlled_text(path: Path) -> str:
    """Read a UTF-8, LF-only file with a final newline."""

    if not path.is_file():
        raise WorkflowContractError(
            f"Workflow does not exist: {path}"
        )

    data = path.read_bytes()

    if data.startswith(b"\xef\xbb\xbf"):
        raise WorkflowContractError(
            f"Workflow contains an unexpected UTF-8 BOM: {path}"
        )

    if b"\r" in data:
        raise WorkflowContractError(
            f"Workflow contains non-LF line endings: {path}"
        )

    if not data.endswith(b"\n"):
        raise WorkflowContractError(
            f"Workflow does not end with a newline: {path}"
        )

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WorkflowContractError(
            f"Workflow is not valid UTF-8: {error}"
        ) from error


def load_workflow(path: Path) -> Mapping[str, Any]:
    """Parse the workflow while preserving YAML keys such as 'on'."""

    raw_workflow = read_controlled_text(path)

    try:
        document = yaml.load(
            raw_workflow,
            Loader=yaml.BaseLoader,
        )
    except yaml.YAMLError as error:
        raise WorkflowContractError(
            f"Workflow YAML parsing failed: {error}"
        ) from error

    return require_mapping(
        document,
        "Workflow document",
    )


def collect_steps(
    job: Mapping[str, Any],
    job_name: str,
) -> list[Mapping[str, Any]]:
    """Return all steps in a job as mappings."""

    raw_steps = require_sequence(
        job.get("steps"),
        f"Job '{job_name}' steps",
    )

    steps: list[Mapping[str, Any]] = []

    for index, raw_step in enumerate(raw_steps):
        steps.append(
            require_mapping(
                raw_step,
                f"Job '{job_name}' step {index}",
            )
        )

    return steps


def collect_action_references(
    jobs: Mapping[str, Any],
) -> set[str]:
    """Collect all external action references."""

    references: set[str] = set()

    for job_name, raw_job in jobs.items():
        job = require_mapping(
            raw_job,
            f"Job '{job_name}'",
        )

        for step in collect_steps(job, str(job_name)):
            action_reference = step.get("uses")

            if isinstance(action_reference, str):
                references.add(action_reference)

    return references


def collect_run_text(
    steps: Iterable[Mapping[str, Any]],
) -> str:
    """Join all run blocks for deterministic contract searches."""

    return "\n".join(
        str(step["run"])
        for step in steps
        if "run" in step
    )


def walk_values(value: Any) -> Iterable[Any]:
    """Yield every nested YAML value."""

    yield value

    if isinstance(value, Mapping):
        for nested_value in value.values():
            yield from walk_values(nested_value)
    elif (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
    ):
        for nested_value in value:
            yield from walk_values(nested_value)


def validate_workflow(path: Path) -> Mapping[str, Any]:
    """Validate the full B4.2 workflow contract."""

    workflow = load_workflow(path)

    if workflow.get("name") != EXPECTED_WORKFLOW_NAME:
        raise WorkflowContractError(
            "Unexpected workflow name: "
            f"'{workflow.get('name')}'."
        )

    triggers = require_mapping(
        workflow.get("on"),
        "Workflow triggers",
    )

    trigger_names = frozenset(
        str(trigger_name)
        for trigger_name in triggers
    )

    if trigger_names != REQUIRED_TRIGGERS:
        raise WorkflowContractError(
            "Workflow triggers differ from the controlled set: "
            f"{sorted(trigger_names)}"
        )

    if "pull_request_target" in trigger_names:
        raise WorkflowContractError(
            "pull_request_target is forbidden for this workflow."
        )

    push_contract = require_mapping(
        triggers.get("push"),
        "Push trigger",
    )

    push_branches = require_sequence(
        push_contract.get("branches"),
        "Push branches",
    )

    if list(push_branches) != ["main"]:
        raise WorkflowContractError(
            "Push execution must be restricted to main."
        )

    permissions = require_mapping(
        workflow.get("permissions"),
        "Workflow permissions",
    )

    if dict(permissions) != {"contents": "read"}:
        raise WorkflowContractError(
            "Workflow permissions must be exactly "
            "{'contents': 'read'}."
        )

    for nested_value in walk_values(workflow):
        if nested_value == "write":
            raise WorkflowContractError(
                "Workflow contains a forbidden write permission."
            )

    concurrency = require_mapping(
        workflow.get("concurrency"),
        "Workflow concurrency",
    )

    if concurrency.get("cancel-in-progress") != "true":
        raise WorkflowContractError(
            "Workflow must cancel superseded executions."
        )

    if (
        concurrency.get("group")
        != "b4-2-ci-${{ github.workflow }}-${{ github.ref }}"
    ):
        raise WorkflowContractError(
            "Workflow concurrency group is incorrect."
        )

    environment = require_mapping(
        workflow.get("env"),
        "Workflow environment",
    )

    expected_environment = {
        "PYTHON_VERSION": "3.11",
        "IDF_VERSION": "v6.0.2",
        "IDF_COMMIT_PREFIX": "7101770",
    }

    if dict(environment) != expected_environment:
        raise WorkflowContractError(
            "Workflow environment differs from the controlled "
            f"toolchain values: {dict(environment)}"
        )

    jobs = require_mapping(
        workflow.get("jobs"),
        "Workflow jobs",
    )

    if set(jobs) != {"quality", "profile-build"}:
        raise WorkflowContractError(
            "Workflow jobs must be exactly 'quality' and "
            "'profile-build'."
        )

    quality = require_mapping(
        jobs.get("quality"),
        "Quality job",
    )

    if quality.get("runs-on") != "ubuntu-latest":
        raise WorkflowContractError(
            "Quality job must run on ubuntu-latest."
        )

    if quality.get("timeout-minutes") != "15":
        raise WorkflowContractError(
            "Quality job timeout must be 15 minutes."
        )

    quality_steps = collect_steps(
        quality,
        "quality",
    )

    quality_run_text = collect_run_text(
        quality_steps
    )

    required_quality_commands = (
        "tools/ci/check_workflow.py",
        "tools/ci/artifact_archive.py contract",
        "tools/ci/artifact_archive.py self-test",
        "tools/ci/verify_b4_2.py --contract-only",
        "tools/ci/check_format.py",
        "tools/ci/check_clang_tidy.py --config-only",
        "tools/ci/run_host_tests.py",
    )

    for required_command in required_quality_commands:
        if required_command not in quality_run_text:
            raise WorkflowContractError(
                "Quality job is missing command: "
                f"{required_command}"
            )

    profile_build = require_mapping(
        jobs.get("profile-build"),
        "Profile-build job",
    )

    if profile_build.get("needs") != "quality":
        raise WorkflowContractError(
            "Profile-build job must depend on quality."
        )

    if profile_build.get("runs-on") != "windows-2022":
        raise WorkflowContractError(
            "Profile-build job must run on windows-2022."
        )

    if profile_build.get("timeout-minutes") != "90":
        raise WorkflowContractError(
            "Profile-build timeout must be 90 minutes."
        )

    strategy = require_mapping(
        profile_build.get("strategy"),
        "Profile-build strategy",
    )

    if strategy.get("fail-fast") != "false":
        raise WorkflowContractError(
            "Profile-build matrix must use fail-fast: false."
        )

    matrix = require_mapping(
        strategy.get("matrix"),
        "Profile-build matrix",
    )

    profiles = require_sequence(
        matrix.get("profile"),
        "Profile-build matrix profiles",
    )

    if tuple(profiles) != EXPECTED_PROFILES:
        raise WorkflowContractError(
            "Profile-build matrix differs from the controlled "
            f"profiles: {list(profiles)}"
        )

    profile_steps = collect_steps(
        profile_build,
        "profile-build",
    )

    profile_run_text = collect_run_text(
        profile_steps
    )

    required_profile_commands = (
        "git clone",
        "--branch $env:IDF_VERSION",
        "describe --tags --exact-match",
        "install.ps1",
        "tools\\ci\\run_profile_build.ps1",
        '-Profile "${{ matrix.profile }}"',
        "artifact_archive.py verify",
    )

    for required_command in required_profile_commands:
        if required_command not in profile_run_text:
            raise WorkflowContractError(
                "Profile-build job is missing contract text: "
                f"{required_command}"
            )

    action_references = collect_action_references(
        jobs
    )

    if not REQUIRED_ACTIONS.issubset(action_references):
        missing_actions = sorted(
            REQUIRED_ACTIONS - action_references
        )

        raise WorkflowContractError(
            "Workflow is missing required actions: "
            f"{missing_actions}"
        )

    for action_reference in action_references:
        if action_reference.startswith("./"):
            continue

        if "@" not in action_reference:
            raise WorkflowContractError(
                "External action is not versioned: "
                f"{action_reference}"
            )

        _, action_version = action_reference.rsplit(
            "@",
            maxsplit=1,
        )

        if action_version in {"main", "master", "latest"}:
            raise WorkflowContractError(
                "Floating action reference is forbidden: "
                f"{action_reference}"
            )

    upload_steps = [
        step
        for step in profile_steps
        if step.get("uses") == "actions/upload-artifact@v4"
    ]
    if len(upload_steps) != 1:
        raise WorkflowContractError(
            "Profile-build job must contain exactly one artifact "
            "upload step."
        )

    if upload_steps[0].get("if") != "${{ always() }}":
        raise WorkflowContractError(
            "Artifact upload must execute with always()."
        )

    upload_contract = require_mapping(
        upload_steps[0].get("with"),
        "Artifact upload contract",
    )

    expected_artifact_name = (
        "b4-2-${{ matrix.profile }}-${{ github.sha }}-"
        "run-${{ github.run_id }}-attempt-${{ github.run_attempt }}"
    )
    if upload_contract.get("name") != expected_artifact_name:
        raise WorkflowContractError(
            "Artifact upload name is incorrect."
        )

    if (
        upload_contract.get("path")
        != "artifacts/b4.2/profile-build/${{ matrix.profile }}"
    ):
        raise WorkflowContractError(
            "Artifact upload path is incorrect."
        )

    if upload_contract.get("if-no-files-found") != "error":
        raise WorkflowContractError(
            "Missing profile archives must fail the upload step."
        )

    if upload_contract.get("retention-days") != "30":
        raise WorkflowContractError(
            "Artifact retention must be 30 days."
        )

    if upload_contract.get("compression-level") != "6":
        raise WorkflowContractError(
            "Artifact compression level must be 6."
        )

    return workflow


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""

    default_repo_root = Path(__file__).resolve().parents[2]

    parser = argparse.ArgumentParser(
        description=(
            "Validate the controlled B4.2 GitHub Actions workflow."
        )
    )

    parser.add_argument(
        "--repo-root",
        type=Path,
        default=default_repo_root,
        help="Repository root.",
    )

    parser.add_argument(
        "--workflow",
        type=Path,
        default=None,
        help=(
            "Workflow path. Defaults to "
            "<repo>/.github/workflows/ci.yml."
        ),
    )

    return parser.parse_args()


def main() -> int:
    """Execute workflow validation."""

    arguments = parse_arguments()
    repo_root = arguments.repo_root.expanduser().resolve()

    if arguments.workflow is None:
        workflow_path = (
            repo_root / ".github" / "workflows" / "ci.yml"
        )
    else:
        workflow_path = arguments.workflow.expanduser().resolve()

    try:
        validate_workflow(workflow_path)

        print("B4.2 workflow contract")
        print(f"Repository: {repo_root}")
        print(f"Workflow:   {workflow_path}")
        print("YAML parsing: PASS")
        print("Triggers: PASS")
        print("Permissions: PASS")
        print("Quality job: PASS")
        print("Profile matrix: PASS")
        print("Artifact contract: PASS")
        print("")
        print("PASS: B4.2 GitHub Actions workflow validated.")

        return 0

    except WorkflowContractError as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
