# OLYMPUS 0.6.6 - Verification Engine

Status: implemented baseline aligned to Product Technical Specification v1.0.

## Contract

`FINISH` is a request for verification, not authority to mark an execution completed.
Only a `VerificationReport` with status `full` authorizes `AgentStatus.COMPLETED`.

## Core types

- `VerificationPlan`
- `VerificationCheck`
- `VerificationEvidence`
- `VerificationReport`
- `VerificationStatus`: none / partial / full / failed

## Current checks

The coding runtime currently emits structured evidence for Python syntax and targeted unit tests. The contract is domain-neutral so document, spreadsheet, page, data, integration and other verifiers can be added without changing completion semantics.

## Safety rule

Confidence summarizes observed checks. It never substitutes for evidence.
