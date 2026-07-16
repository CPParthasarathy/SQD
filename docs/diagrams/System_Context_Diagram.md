---
document_id: ESP32S3-DIAG-CTX-001
title: "System Context Diagram"
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

# System Context Diagram

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-DIAG-CTX-001` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


```mermaid
flowchart TB
  subgraph External
    User[Installer / Maintainer]
    Factory[Factory and Recovery Tool]
    Mobile[Commissioning Application]
    LNS[LoRaWAN Network Server]
    Cloud[Cloud Service]
    Repo[Signed Firmware Repository]
    Power[Power Source]
    Sensor[Sensor / Actuator]
  end

  subgraph Product[ESP32-S3 Product]
    Boot[Boot and Recovery]
    FW[Application Firmware]
    Store[Persistent Store]
    BSP[Board Support]
    Comm[LoRa / Wi-Fi / BLE]
    UI[OLED / LED / Button / USB]
  end

  Power --> Product
  Sensor <--> BSP
  BSP <--> FW
  Boot --> FW
  Boot <--> Store
  FW <--> Store
  FW <--> Comm
  FW <--> UI
  User <--> UI
  Factory <--> UI
  Mobile <--> Comm
  Comm <--> LNS
  LNS <--> Cloud
  Comm <--> Cloud
  Repo --> Cloud
  Cloud --> Comm
```

## Review questions

- Is every external actor shown?
- Does every arrow correspond to an interface record?
- Are factory and field paths distinct?
- Is update authority represented correctly?
- Are trust boundaries present in A1.3?
