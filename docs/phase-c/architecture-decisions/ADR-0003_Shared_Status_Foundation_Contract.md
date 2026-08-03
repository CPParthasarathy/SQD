---
document_id: ESP32S3-PC-ADR-0003
title: "Shared Status Foundation Contract"
phase: "C"
cluster: "C2"
work_package: "C2.2"
decision_id: "ADR-0003"
status: "Proposed"
version: "0.1"
owner: "Me"
approver: "Me"
classification: "Internal Engineering"
created: "2026-08-03"
platform: "ESP32-S3, 8 MB flash baseline"
toolchain: "ESP-IDF 6.0.2"
parent_baseline: "d16f0d3223fa8d895f65837450acb346d3256b22"
machine_amendment: "tools/ci/c2_2_architecture_amendment.json"
verification_script: "tools/scripts/C2.2_Verify_Architecture_Prerequisite.ps1"
---

# ADR-0003 Shared Status Foundation Contract

## Context

The accepted C1.2 runtime contract requires cross-component interfaces
to use `sqd_status_t` and the controlled `SQD_STATUS_*` classes.

No tracked source implementation currently owns or defines that type.

The C2.2 board component requires the common status contract but must not
depend upward on platform, HAL, device-driver or product components.

Board ownership is rejected because a board-specific component must not
own a system-wide interface contract.

Platform ownership is rejected because it would create an upward
dependency from board to platform.

Public `esp_err_t` is rejected because accepted C1.2 requires native
ESP-IDF errors to be translated at the owning component boundary.

## Decision

Introduce `components/core` as a neutral, header-only foundation
contract component.

`components/core` owns:

- `sqd_status_t`
- `SQD_STATUS_*`
- `components/core/include/sqd_status.h`

The component:

- Owns no mutable runtime state.
- Creates no tasks, queues, locks, timers or interrupt handlers.
- Depends on no SQD component.
- Depends on no ESP-IDF runtime facility.
- Contains no board, platform or product policy.
- Exposes only controlled cross-component type contracts.

`components/board` may depend downward on `components/core`.

Future components may use `components/core` only for neutral shared
contracts approved through architecture control. It must not become a
general utility or miscellaneous-code component.

## Namespace decision

`components/core` owns these explicit identifiers:

- `sqd_status_t`
- `SQD_STATUS_OK`
- `SQD_STATUS_INVALID_ARGUMENT`
- `SQD_STATUS_INVALID_STATE`
- `SQD_STATUS_ALREADY_INITIALIZED`
- `SQD_STATUS_NOT_FOUND`
- `SQD_STATUS_BUSY`
- `SQD_STATUS_TIMEOUT`
- `SQD_STATUS_IO`
- `SQD_STATUS_INTEGRITY`
- `SQD_STATUS_AUTHORIZATION`
- `SQD_STATUS_NO_MEMORY`
- `SQD_STATUS_NOT_SUPPORTED`
- `SQD_STATUS_CANCELLED`
- `SQD_STATUS_INTERNAL`

No other namespace exception is approved.

## Dependency direction

The approved dependency is:

    board -> core

This is a downward dependency. It is not a same-level dependency.

`components/core` has no permitted SQD dependency.

## Accepted-baseline preservation

The accepted C1.1, C1.2 and C1.3 documents and their machine-readable
contracts remain unchanged.

The additive amendment is recorded in:

    tools/ci/c2_2_architecture_amendment.json

## Constraints

- `components/core` must remain header-only unless a later ADR approves
  a runtime implementation.
- No board GPIO definitions may appear in `components/core`.
- No product policy may appear in `components/core`.
- No unrelated helpers, algorithms or utilities may be added.

## Decision status

The decision is proposed on the C2.2 feature branch and becomes accepted
only through the controlled C2.2 review and merge workflow.
