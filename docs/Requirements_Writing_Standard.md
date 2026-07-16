---
document_id: ESP32S3-STD-REQ-001
title: "Requirements Writing and Quality Standard"
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

# Requirements Writing and Quality Standard

| Control field | Value |
|---|---|
| Document ID | `ESP32S3-STD-REQ-001` |
| Version | `0.1` |
| Status | Draft |
| Owner / approver | Me |
| Product baseline | Heltec WiFi LoRa 32 V3 / exact revision TBD |
| Target gate | G-A — Phase A baseline approval |
| Change control | Changes after baseline require a recorded change request |
| Evidence rule | A claim is complete only when linked evidence exists |

> **Control note:** `TBD-*` items are not omissions. They are controlled decisions that require an owner, due date, and closure evidence before the applicable gate.


## 1. Requirement form

A requirement shall express one testable obligation:

> The `<system element>` shall `<observable behavior>` when `<condition or trigger>` within `<measurable limit>`.

## 2. Mandatory attributes

| Attribute | Rule |
|---|---|
| ID | Unique, immutable, category-based |
| Statement | Uses `shall`; one obligation |
| Source | Use case, scenario, stakeholder, risk, standard, or interface |
| Rationale | Explains why without weakening the obligation |
| Priority | Must / Should / Could or P0 / P1 / P2 |
| Verification | Test, analysis, inspection, or demonstration |
| Acceptance criterion | Binary pass/fail condition |
| Trace links | Upstream source and downstream test |
| Status | Proposed, Accepted, Changed, Deleted, Verified |

## 3. Prohibited language

Avoid:

- Fast, user-friendly, robust, secure, minimal, sufficient, appropriate.
- “As required,” “where possible,” or “etc.”
- Combined obligations connected by multiple `and` clauses.
- Implementation details without an architectural reason.
- Requirements that merely restate a design.

## 4. Quality checklist

A requirement is acceptable when it is:

- Necessary.
- Correct.
- Unambiguous.
- Complete.
- Singular.
- Feasible.
- Verifiable.
- Traceable.
- Consistent.
- Technology-appropriate.
- Assigned to one responsible system element.

## 5. Identifier scheme

```text
FR-BOOT-001
FR-PROV-001
FR-LORA-001
NFR-PWR-001
NFR-SEC-001
```

IDs are never reused. Deleted requirements remain in history with status `Deleted`.

## 6. Verification codes

| Code | Method |
|---|---|
| T | Test |
| A | Analysis |
| I | Inspection |
| D | Demonstration |

## 7. Baseline rule

No requirement enters the approved baseline with an unresolved contradiction, undefined verification method, or missing source. Numeric limits may remain `TBD` only when a dated closure action exists and the gate allows it.
