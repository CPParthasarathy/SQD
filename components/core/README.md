# core component

Purpose: Neutral, dependency-free cross-component type contracts.

`components/core` owns the shared `sqd_status_t` and
`SQD_STATUS_*` classification contract approved by ADR-0003.

The component is header-only, owns no mutable runtime state and must not
become a general utility or miscellaneous-code component.
