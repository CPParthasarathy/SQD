---
document_id: ESP32S3-DIAG-STATE-001
title: "Device State Model"
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

# Device State Model

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-DIAG-STATE-001` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


```mermaid
stateDiagram-v2
  [*] --> Off
  Off --> Booting
  Booting --> Provisioning: no valid config
  Booting --> Joining: valid config
  Booting --> Recovery: image/config fatal
  Provisioning --> Joining: commit valid config
  Joining --> Operational: joined or offline policy
  Operational --> Acquiring
  Acquiring --> Operational
  Operational --> Communicating
  Communicating --> Operational
  Operational --> Sleeping
  Sleeping --> Booting: deep sleep wake
  Operational --> Maintenance
  Maintenance --> Updating
  Updating --> Booting
  Operational --> Degraded: recoverable fault
  Degraded --> Operational: restored
  Degraded --> Recovery: escalation
  Recovery --> Booting: repair/reset
```

## State-definition rule

Each state must define entry conditions, allowed events, prohibited operations, timeout, persistent effects, exit conditions, UI indication, and diagnostic events.
