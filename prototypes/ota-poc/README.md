---
document_id: ESP32S3-POC-OTA
title: "OTA and Rollback POC"
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

# OTA and Rollback POC

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-POC-OTA` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


## 1. Objective

Demonstrate that valid images update safely and invalid/interrupted/trial-failing images cannot brick the device.

## 2. Risks addressed

R-MEM-001, R-OTA-001, R-USB-001, R-SEC-002

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
| OTA-T01 | Partition feasibility | Build representative image | Two slots and margin available | Not Run |
| OTA-T02 | Valid update | Signed compatible image | Inactive slot written, trial boot, confirm | Not Run |
| OTA-T03 | Corrupt image | Modified bytes/hash | Rejected | Not Run |
| OTA-T04 | Unauthorized image | Invalid signature/key | Rejected according to production policy | Not Run |
| OTA-T05 | Hardware/version mismatch | Incompatible manifest | Rejected before activation | Not Run |
| OTA-T06 | Network interruption | Interrupt download | Running image preserved; retry/resume safe | Not Run |
| OTA-T07 | Power loss during update | Interrupt at staged points | Known-good image remains bootable | Not Run |
| OTA-T08 | Trial self-test failure | Fail startup criterion | Rollback | Not Run |
| OTA-T09 | Recovery path | Corrupt application slots as safely possible | USB/bootloader recovery demonstrated | Not Run |

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
