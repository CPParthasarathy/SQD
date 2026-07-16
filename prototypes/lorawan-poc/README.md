---
document_id: ESP32S3-POC-LORA
title: "LoRaWAN POC"
phase: "A"
cluster: "A3"
work_package: "A3.2"
status: "Draft"
version: "0.1"
owner: "Me"
approver: "Me"
classification: "Internal Engineering"
created: "2026-07-14"
baseline_gate: "G-A"
platform: "ESP32-S3, 8 MB flash baseline"
toolchain: "ESP-IDF 5.5.x"
---

# LoRaWAN POC

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-POC-LORA` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


## 1. Objective

Demonstrate viable LoRaWAN activation, telemetry, command, retry, and session behavior on the target board.

## 2. Risks addressed

R-RF-001, R-LORA-001, R-RF-002

## 3. Entry criteria

- Exact target board and pin constraints recorded.
- ESP-IDF patch version pinned.
- Test credentials/environment isolated from production.
- Secrets excluded from repository and logs.
- Acceptance criteria reviewed.
- Recovery method available before destructive tests.

## 4. Implementation boundary

The POC shall contain only the minimum components required to prove the objective. It shall not establish the production architecture, public API, task model, or coding pattern by accident.

## 5. Test matrix

| Test ID | Objective | Stimulus/setup | Acceptance criterion | Result |
|---|---|---|---|---|
| LORA-T01 | Radio bring-up | Exact pin map and antenna | SX1262 initializes without error | Not Run |
| LORA-T02 | OTAA join candidate | Valid credentials/gateway | Join succeeds and session recorded | Not Run |
| LORA-T03 | Join failure backoff | Gateway unavailable | Bounded retries and measured backoff | Not Run |
| LORA-T04 | Telemetry uplink | Versioned test payload | Server receives correct bytes | Not Run |
| LORA-T05 | Downlink command | Valid command | Validated, deduplicated, bounded execution | Not Run |
| LORA-T06 | Replay downlink | Repeat command | Rejected without side effect | Not Run |
| LORA-T07 | Reset/session behavior | Reset after join | Approved rejoin/session policy observed | Not Run |
| LORA-T08 | Wi-Fi coexistence sequence | Alternate radio activity | No uncontrolled conflict; current measured | Not Run |

## 6. Required evidence

- Clean build log.
- `sdkconfig` and partition table where applicable.
- Board identity and wiring/setup photograph.
- Raw serial logs.
- Network/server evidence where applicable.
- Current/memory measurements where applicable.
- Failure-injection logs.
- Git commit and tool versions.
- Result summary and residual risks.

## 7. Result record

| Field | Value |
|---|---|
| Board/revision/serial | TBD |
| ESP-IDF/toolchain | TBD |
| Git commit | TBD |
| Configuration | TBD |
| Test date | TBD |
| Overall result | Not Run |
| Evidence path | TBD |
| Limitations | TBD |
| Architecture recommendation | TBD |
| New/updated risks | TBD |

## 8. Exit criteria

- [ ] All mandatory tests executed or explicitly blocked.
- [ ] Happy path and negative path demonstrated.
- [ ] Critical interruption/failure tests executed.
- [ ] Raw evidence indexed.
- [ ] Resource impact measured.
- [ ] Residual risks recorded.
- [ ] Recommendation documented.
