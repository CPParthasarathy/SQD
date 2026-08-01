"""Validate the C1.2 component ownership contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "tools" / "ci" / "c1_2_component_contract.json"


class ContractError(RuntimeError):
    """Raised when the C1.2 contract is invalid."""


def load_contract(path: Path) -> dict[str, Any]:
    """Load the JSON contract."""
    if not path.is_file():
        raise ContractError(f"Contract file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as contract_file:
            contract = json.load(contract_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Could not load contract: {exc}") from exc

    if not isinstance(contract, dict):
        raise ContractError("Contract root must be a JSON object.")

    return contract


def require_unique(values: list[str], label: str) -> None:
    """Require non-empty and unique identifiers."""
    if any(not value for value in values):
        raise ContractError(f"{label} contains an empty identifier.")

    if len(values) != len(set(values)):
        raise ContractError(f"{label} contains duplicate identifiers.")


def verify_contract(contract: dict[str, Any]) -> tuple[int, int]:
    """Verify component and resource identity constraints."""
    components = contract.get("components")
    resources = contract.get("mutable_resources")

    if not isinstance(components, list):
        raise ContractError("components must be an array.")

    if not isinstance(resources, list):
        raise ContractError("mutable_resources must be an array.")

    if len(components) != 14:
        raise ContractError(f"Expected 14 components; found {len(components)}.")

    if len(resources) != 12:
        raise ContractError(f"Expected 12 resources; found {len(resources)}.")

    component_ids = [str(item.get("id", "")) for item in components]
    resource_ids = [str(item.get("id", "")) for item in resources]

    require_unique(component_ids, "components")
    require_unique(resource_ids, "mutable_resources")

    component_by_id = dict(zip(component_ids, components, strict=True))
    resource_by_id = dict(zip(resource_ids, resources, strict=True))

    approved_lateral = contract.get("approved_same_level_dependencies")
    if not isinstance(approved_lateral, list):
        raise ContractError(
            "approved_same_level_dependencies must be an array."
        )

    if approved_lateral:
        raise ContractError(
            "No same-level dependency exception may be pre-approved."
        )

    for component_id, component in component_by_id.items():
        api_namespace = str(component.get("api_namespace", "")).strip()
        execution_model = str(component.get("execution_model", "")).strip()
        dependencies = component.get("permitted_dependencies")

        if not api_namespace:
            raise ContractError(
                f"Component {component_id!r} has no API namespace."
            )

        if not execution_model:
            raise ContractError(
                f"Component {component_id!r} has no execution model."
            )

        if not isinstance(dependencies, list):
            raise ContractError(
                f"Component {component_id!r} permitted_dependencies must be an array."
            )

        normalized_dependencies = [str(item) for item in dependencies]
        require_unique(
            normalized_dependencies,
            f"component {component_id!r} dependencies",
        )

        for dependency_id in normalized_dependencies:
            if dependency_id not in component_by_id:
                raise ContractError(
                    f"Component {component_id!r} references unknown dependency "
                    f"{dependency_id!r}."
                )

            if dependency_id == component_id:
                raise ContractError(
                    f"Component {component_id!r} may not depend on itself."
                )

    for resource_id, resource in resource_by_id.items():
        owner = str(resource.get("owner", ""))
        owner_component = component_by_id.get(owner)

        if owner_component is None:
            raise ContractError(
                f"Resource {resource_id!r} references unknown owner {owner!r}."
            )

        owner_claims = owner_component.get("owned_resource_ids")
        if not isinstance(owner_claims, list):
            raise ContractError(
                f"Component {owner!r} owned_resource_ids must be an array."
            )

        if owner_claims.count(resource_id) != 1:
            raise ContractError(
                f"Owner {owner!r} must claim resource {resource_id!r} exactly once."
            )

    for component_id, component in component_by_id.items():
        claimed_resources = component.get("owned_resource_ids")

        if not isinstance(claimed_resources, list):
            raise ContractError(
                f"Component {component_id!r} owned_resource_ids must be an array."
            )

        normalized_claims = [str(item) for item in claimed_resources]
        require_unique(normalized_claims, f"component {component_id!r} ownership")

        for resource_id in normalized_claims:
            resource = resource_by_id.get(resource_id)

            if resource is None:
                raise ContractError(
                    f"Component {component_id!r} claims unknown resource {resource_id!r}."
                )

            if str(resource.get("owner", "")) != component_id:
                raise ContractError(
                    f"Resource {resource_id!r} does not name {component_id!r} as owner."
                )

    interface_rules = contract.get("interface_rules")

    if not isinstance(interface_rules, dict):
        raise ContractError("interface_rules must be an object.")

    expected_interface_strings = {
        "public_namespace": "sqd_",
        "component_namespace_pattern": "sqd_<component>_",
    }

    for field_name, expected_value in expected_interface_strings.items():
        actual_value = interface_rules.get(field_name)

        if actual_value != expected_value:
            raise ContractError(
                f"interface_rules.{field_name} must be {expected_value!r}; "
                f"found {actual_value!r}."
            )

    required_true_interface_rules = [
        "single_interface_owner_required",
        "single_mutable_resource_owner_required",
        "explicit_dependency_injection",
        "hidden_singleton_dependencies_forbidden",
        "opaque_mutable_contexts",
        "native_handle_escape_forbidden",
        "esp_err_t_above_owner_boundary_forbidden",
        "caller_owned_buffer_default",
        "failed_transfer_retains_caller_ownership",
        "allocator_provides_release_operation",
        "same_level_dependency_requires_c1_3",
    ]

    for field_name in required_true_interface_rules:
        if interface_rules.get(field_name) is not True:
            raise ContractError(
                f"interface_rules.{field_name} must be true."
            )
    expected_identity = {
        "schema_version": 1,
        "work_package": "C1.2",
        "status": "Accepted",
        "parent_baseline": "10ddce93560c94127933f5d6e08f7f6b546f5dc8",
        "specification_document": (
            "docs/phase-c/C1.2_Component_Interface_and_Runtime_Contracts.md"
        ),
        "completion_criterion": (
            "Every mutable resource and interface has a single owner."
        ),
    }

    for field_name, expected_value in expected_identity.items():
        actual_value = contract.get(field_name)
        if actual_value != expected_value:
            raise ContractError(
                f"{field_name} must be {expected_value!r}; found {actual_value!r}."
            )

    specification_path = REPOSITORY_ROOT / str(
        contract["specification_document"]
    )

    if not specification_path.is_file():
        raise ContractError(
            f"Specification document not found: {specification_path}"
        )

    lifecycle = contract.get("lifecycle")
    if not isinstance(lifecycle, dict):
        raise ContractError("lifecycle must be an object.")

    expected_states = [
        "UNINITIALIZED",
        "INITIALIZED",
        "STARTING",
        "RUNNING",
        "STOPPING",
        "STOPPED",
        "FAULTED",
    ]

    expected_operations = [
        "init",
        "start",
        "stop",
        "deinit",
        "get_status",
    ]

    if lifecycle.get("states") != expected_states:
        raise ContractError("Lifecycle states do not match the C1.2 contract.")

    if lifecycle.get("standard_operations") != expected_operations:
        raise ContractError(
            "Lifecycle operations do not match the C1.2 contract."
        )

    if lifecycle.get("repeated_compatible_init") != (
        "idempotent-or-SQD_STATUS_ALREADY_INITIALIZED"
    ):
        raise ContractError(
            "Repeated compatible initialization rule is invalid."
        )

    if lifecycle.get("partial_initialization_rollback_required") is not True:
        raise ContractError(
            "Partial initialization rollback must be required."
        )

    expected_lifecycle_values = {
        "conflicting_init_result": "SQD_STATUS_INVALID_STATE",
        "caller_dependencies_released_by_component": False,
        "system_sequence_owner": "C5",
    }

    for field_name, expected_value in expected_lifecycle_values.items():
        actual_value = lifecycle.get(field_name)

        if actual_value != expected_value:
            raise ContractError(
                f"lifecycle.{field_name} must be {expected_value!r}; "
                f"found {actual_value!r}."
            )
    threading = contract.get("threading")

    if not isinstance(threading, dict):
        raise ContractError("threading must be an object.")

    expected_threading_values = {
        "passive_by_default": True,
        "unregistered_task_creation_forbidden": True,
        "active_execution_owner": "services-supervision-model",
        "task_dimensioning_owner": "C6",
        "allocation_in_isr_forbidden": True,
        "blocking_in_isr_forbidden": True,
        "persistent_storage_in_isr_forbidden": True,
        "product_policy_in_isr_forbidden": True,
        "unbounded_logging_in_isr_forbidden": True,
    }

    for field_name, expected_value in expected_threading_values.items():
        actual_value = threading.get(field_name)

        if actual_value != expected_value:
            raise ContractError(
                f"threading.{field_name} must be {expected_value!r}; "
                f"found {actual_value!r}."
            )

    expected_isr_owners = ["hal", "board"]

    if threading.get("isr_registration_owners") != expected_isr_owners:
        raise ContractError(
            "ISR registration owners must be exactly hal and board."
        )
    errors = contract.get("errors")

    if not isinstance(errors, dict):
        raise ContractError("errors must be an object.")

    if errors.get("cross_component_type") != "sqd_status_t":
        raise ContractError(
            "errors.cross_component_type must be sqd_status_t."
        )

    expected_status_codes = [
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

    if errors.get("status_codes") != expected_status_codes:
        raise ContractError(
            "Error status codes do not match the C1.2 contract."
        )
    required_true_error_rules = [
        "native_error_translation_required",
        "esp_err_t_above_owner_boundary_forbidden",
        "invalid_input_checked_before_state_change",
        "timeout_and_cancellation_distinct",
        "authorization_distinct_from_io",
        "integrity_distinct_from_not_found",
        "silent_log_and_continue_forbidden",
        "secret_disclosure_forbidden",
    ]

    for field_name in required_true_error_rules:
        if errors.get(field_name) is not True:
            raise ContractError(
                f"errors.{field_name} must be true."
            )

    expected_error_policy_owners = {
        "retry_policy_owner": "caller-or-product-policy-owner",
        "fatality_and_safe_mode_policy_owner": "C5",
    }

    for field_name, expected_value in expected_error_policy_owners.items():
        actual_value = errors.get(field_name)

        if actual_value != expected_value:
            raise ContractError(
                f"errors.{field_name} must be {expected_value!r}; "
                f"found {actual_value!r}."
            )
    return len(components), len(resources)


def main() -> int:
    """Run verification."""
    try:
        contract = load_contract(CONTRACT_PATH)
        component_count, resource_count = verify_contract(contract)
    except ContractError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print(f"PASS: components={component_count}")
    print(f"PASS: mutable_resources={resource_count}")
    print("C1.2 contract verification PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
