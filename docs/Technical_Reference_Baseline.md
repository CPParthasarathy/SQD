---
document_id: ESP32S3-REF-001
title: "Technical Reference Baseline"
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

# Technical Reference Baseline

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-REF-001` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


## Purpose

List the authoritative technical sources that constrain Phase A decisions. The exact downloaded revision used by the project should be stored in `docs/evidence/datasheets/` when licensing permits.

## Platform sources

1. Heltec WiFi LoRa 32 official product documentation and exact revision schematic.
2. Espressif ESP32-S3 datasheet and technical reference manual.
3. ESP-IDF Programming Guide for the pinned 5.5.x patch.
4. Semtech SX1262 datasheet.
5. LoRa Alliance LoRaWAN specification and regional parameters for the approved market.

## Framework topics to baseline

- Partition tables.
- OTA and rollback.
- Secure Boot v2.
- Flash encryption.
- NVS and NVS encryption.
- Sleep modes and power management.
- Heap and stack diagnostics.
- Wi-Fi event and reconnect behavior.
- USB serial/JTAG and recovery.
- Core dump and fatal-error behavior.

## Reference-control record

| Reference ID | Document/source | Version/revision | Retrieved | Applicable baseline | Local evidence path |
|---|---|---|---|---|---|
| REF-HELTEC-001 | Heltec WiFi LoRa 32 documentation | TBD | TBD | Exact board | TBD |
| REF-ESP-001 | ESP32-S3 datasheet | TBD | TBD | MCU | TBD |
| REF-IDF-001 | ESP-IDF Programming Guide | 5.5.x exact TBD | TBD | Firmware | TBD |
| REF-SX-001 | SX1262 datasheet | TBD | TBD | LoRa radio | TBD |
| REF-LORA-001 | LoRaWAN spec/regional parameters | TBD | TBD | Network | TBD |

## Technical cautions

- Board product names do not guarantee identical PCB revisions.
- Enabling secure boot or flash encryption can affect bootloader size, debugging, provisioning, and recovery.
- OTA requires a partition design that fits the production image plus growth margin.
- Board-level sleep current can be dominated by regulators, display, radio, pull networks, and external loads.
- Wi-Fi/TLS memory peaks must be measured with the real configuration.
