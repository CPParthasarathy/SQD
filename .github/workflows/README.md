# Continuous-integration workflows

## B4.1 Continuous Integration

The authoritative workflow is:

- .github/workflows/ci.yml

It runs for pull requests, pushes to main and manual dispatch.

## Quality contracts

The Ubuntu quality job performs:

- Pinned CI dependency installation.
- Workflow-contract validation.
- C and C++ formatting verification.
- Clang-Tidy configuration verification.
- Host-side CI tests.

## Controlled profile builds

The Windows matrix builds:

- debug
- validation
- production

Profile builds execute through:

- tools/ci/run_profile_build.ps1

## Evidence

Per-profile evidence is collected under:

- artifacts/b4.1/profile-build/<profile>/

Formal artifact-archive acceptance is owned by B4.2.

## Implementation record

- docs/phase-b/B4.1_Continuous_Integration_Skeleton.md
