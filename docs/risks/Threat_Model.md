---
document_id: ESP32S3-THREAT-MODEL
title: "Preliminary STRIDE Threat Model"
phase: ""
cluster: ""
work_package: ""
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

# Preliminary STRIDE Threat Model

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-THREAT-MODEL` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


## 1. Method and scope

The model uses STRIDE to identify threats across device, boot/update, storage, local service, radio/network, cloud, and manufacturing trust boundaries. It is preliminary and does not claim formal certification.

## 2. Security objectives

- Only authorized software executes.
- Only authorized devices and services participate.
- Commands are authentic, authorized, fresh, and bounded.
- Credentials remain confidential.
- Configuration and security state maintain integrity.
- Recovery does not bypass trust controls.
- Denial-of-service behavior is bounded by power and retry policies.
- Release and factory actions are attributable.

## 3. Threat register

| Threat ID | Asset/boundary | STRIDE | Scenario | Candidate controls | Verification | Status |
|---|---|---|---|---|---|---|
| TH-001 | Device identity | Spoofing | Counterfeit device joins service | Unique identity, server registration, authenticated join | A3.2 LoRa/factory tests | Open |
| TH-002 | Firmware image | Tampering | Malicious image executes | Signed image validation, secure-boot policy, release authorization | Invalid image/boot tests | Open |
| TH-003 | OTA channel | Tampering/DoS | Update replaced or interrupted | TLS, signature, hash, inactive slot, rollback | OTA POC | Open |
| TH-004 | Commands | Spoofing/replay | Unauthorized state change | Authentication, authorization, freshness, deduplication | Negative command tests | Open |
| TH-005 | Credentials | Information disclosure | Network/service compromise | No logs, protected storage, controlled provisioning | Log scan/factory review | Open |
| TH-006 | Persistent config | Tampering | Unsafe or malicious configuration | Integrity, schema/range checks, atomic commit | Storage POC | Open |
| TH-007 | Diagnostics | Information disclosure | Sensitive operational data exposed | Access control and redaction | Diagnostic inspection | Open |
| TH-008 | Factory interface | Elevation of privilege | Field user enters privileged mode | Lifecycle control, physical/process authorization | Production config test | Open |
| TH-009 | Network interface | Denial of service | Battery drain/retry storm | Rate limits, backoff, wake budget | Fault/stress test | Open |
| TH-010 | Release process | Repudiation/tampering | Unknown artifact provenance | Signed release, hashes, approvals, reproducible build | Release evidence | Open |
| TH-011 | Boot state | Rollback | Old vulnerable image activated | Security version/anti-rollback policy | OTA/boot test | Open |
| TH-012 | Physical access | Information disclosure/tampering | Flash/debug extraction or modification | Flash encryption/secure boot/debug lifecycle decision | Security configuration review | Open |

## 4. Security lifecycle decisions

| Decision | Options | Consequence |
|---|---|---|
| Secure Boot v2 | Enable production / defer with risk | Authentic boot chain and irreversible provisioning considerations |
| Flash encryption | Enable production / defer with risk | Confidentiality and debug/rework implications |
| NVS encryption | Enable for secret-bearing partitions | Key partition and recovery implications |
| Anti-rollback | Enable security version / controlled downgrade | Service and recovery trade-off |
| JTAG/USB debug | Disable/restrict/lifecycle control | Debuggability vs field attack surface |
| Factory key injection | External HSM/tool/manual prototype | Traceability and secret exposure |
| Device certificate model | Per-device/shared/not used | Authentication strength and operations |

## 5. Abuse cases

- Attacker repeatedly triggers join or Wi-Fi scans to drain battery.
- Attacker replays a valid command.
- Malformed payload causes parser overflow or state corruption.
- Old but valid firmware is forced onto device.
- Factory reset preserves a credential that should be erased.
- Diagnostic mode exposes secrets or privileged functions.
- Power is removed during image/configuration commit.
- Counterfeit device uses copied identity material.

## 6. Gate criteria

- Critical assets and boundaries identified.
- Critical threats mapped to candidate controls.
- Controls mapped to requirements and tests.
- Irreversible security configuration decisions are not executed without approved procedure.
- Residual high/critical risks are explicitly accepted or mitigated.
