---
document_id: ESP32S3-EVID-MEAS
title: "Measurement Evidence Rules"
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

# Measurement Evidence Rules

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-EVID-MEAS` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


## Policy

Store raw numeric data in CSV or instrument-native form plus a Markdown test record. Record units, range, sampling rate, calibration status, supply voltage, temperature, and uncertainty.
