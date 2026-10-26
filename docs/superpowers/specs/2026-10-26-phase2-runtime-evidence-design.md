# Phase 2 Runtime Evidence Design

## Intent

Add a focused, fail-closed runtime-evidence package. A runtime result is verified only when a local runner outside the model tool path observes the live process and page, compares those observations with a committed contract, and signs a receipt. Caller-provided `grounded`, `ready`, `observed`, or `pass` fields are never evidence.

## Goals

- Define a canonical receipt and contract representation.
- Sign receipts with an Ed25519 key stored outside the checkout.
- Verify signatures, contract hash, worktree digest, process identity, port, and origin.
- Keep missing, forged, stale, and wrong-target evidence as `NOT_OBSERVED` or rejected.
- Provide a committed probe and one `phase2:proof` command that proves the five required cases.
- Keep the package independent from Hermes enforcement, notebook work, context policy, cost caps, SQL parsing, rollback, and Tier-1 claims.

## Non-goals and anti-goals

- No Hermes or Cursor write blocking.
- No labels named `TIER1`, `GROUNDED`, or `ENFORCED`.
- No caller-controlled success flags or copying expected values into observed values.
- No production deployment or external service dependency.

## Approach

The rejected approach was extending the existing LAB diagnostic guards, because that would blur diagnostic evidence with cryptographically bound live-runtime evidence. The selected approach is a new `tier1/runtime_evidence/` package with small modules for contracts, receipts, signing, verification, process identity, probing, and the proof command. It uses Python's standard library for hashing, subprocess/OS inspection, and Ed25519 via the already-supported `cryptography` runtime if present; the proof command fails clearly when the signing dependency is unavailable.

## Boundaries and decisions

- Branch: `enforcement/phase2-runtime-evidence`.
- The committed contract names the probe script and target files whose content contributes to the worktree digest.
- The runner owns the private key under `%LOCALAPPDATA%\\omnk-runner\\`; the checkout contains only the public key or a generated test key fixture, never the private key.
- The runner starts the existing app command, discovers the listening port, fetches `/`, and records process identity and body hash. Browser journey support is represented by the runner-owned probe interface and is added only where the current repository has a real notebook app target.
- Verification is pure and fail-closed: no valid receipt means `NOT_OBSERVED`; a receipt cannot be promoted to success after signature, identity, contract, worktree, or freshness failure.
- Existing `MASTER-HANDOFF.md` edits remain user-owned and are not reformatted or committed as part of this slice.

## Acceptance proof

`npm run phase2:proof` is not applicable to this Python repository, so the equivalent project command will be `python -m tier1.runtime_evidence.proof`. It must exit 0 only when it demonstrates: a real signed observation, caller flags rejected without a receipt, forged expected/observed data rejected, wrong target rejected, and post-probe file changes marked stale.

## Evidence level

The implementation can establish local runtime and cryptographic verification evidence. It does not establish Hermes live-host enforcement, a merge, a Tier-1 claim, or production evidence.
