# Phase 2 Runtime Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a focused, fail-closed runtime-evidence package whose signed receipts are created only by a runner observing the live process and page.

**Architecture:** Add a new `tier1/runtime_evidence/` package with canonical contracts, receipt serialization, Ed25519 signing, OS identity verification, and a runner-owned HTTP probe. Keep verification pure and reject caller-authored evidence, stale hashes, forged signatures, and wrong targets. Expose the proof through `python -m tier1.runtime_evidence.proof` and a project script entry point.

**Tech Stack:** Python 3.10+, standard library (`hashlib`, `json`, `subprocess`, `socket`, `urllib`), `cryptography` for Ed25519, pytest.

**Spec:** `docs/superpowers/specs/2026-10-26-phase2-runtime-evidence-design.md`

## Global Constraints

- Phase 2 is runtime evidence, not Hermes enforcement.
- Caller-set `grounded`, `ready`, `observed`, and `pass` fields are never trusted.
- Missing evidence remains `NOT_OBSERVED`.
- The private key lives outside the checkout under `%LOCALAPPDATA%\\omnk-runner\\`.
- Receipts bind to the contract hash and named-file worktree digest.
- No `TIER1`, `GROUNDED`, or `ENFORCED` success labels are introduced.
- Do not modify `app/notebook-workspace`, Hermes code, or the existing LAB diagnostic guards.

## Review Focus

- Canonical JSON must be deterministic so signatures cannot vary with key order; test signing and verification after reserialization.
- Caller payloads can contain plausible `grounded` or `ready` flags; test that they remain `UNVERIFIED` without a receipt.
- A valid receipt can become stale after a named file changes; test both contract and worktree invalidation.
- Process identity must be tied to the observed listening port and command line; test wrong PID, port, and origin.
- A killed or failed probe must not promote a partial receipt; test that no final receipt is written.

### Task 1: Receipt schema and canonical hashing

**Files:**
- Create: `tier1/runtime_evidence/__init__.py`
- Create: `tier1/runtime_evidence/model.py`
- Create: `tier1/runtime_evidence/hashutil.py`
- Test: `tests/test_runtime_evidence_model.py`

**Interfaces:**
- Produces `Contract`, `Target`, `Observation`, `Assertion`, and `Receipt` dataclasses with JSON-safe `to_dict()` methods.
- Produces `canonical_json(value: object) -> bytes`, `sha256_bytes(value: bytes) -> str`, and `worktree_digest(root: Path, files: tuple[str, ...]) -> str`.

- [ ] **Step 1: Write failing tests** for deterministic serialization, required receipt fields, and named-file digest changes.
- [ ] **Step 2: Run `pytest tests/test_runtime_evidence_model.py -q` and verify it fails because the package is absent.**
- [ ] **Step 3: Implement the models and hashing helpers with strict required fields and sorted canonical JSON.**
- [ ] **Step 4: Run the focused test and verify it passes.**
- [ ] **Step 5: Commit the model slice with `git add tier1/runtime_evidence tests/test_runtime_evidence_model.py && git commit -m "feat: add runtime evidence receipt models"`.**

### Task 2: Ed25519 signer and fail-closed verifier

**Files:**
- Create: `tier1/runtime_evidence/crypto.py`
- Create: `tier1/runtime_evidence/verifier.py`
- Test: `tests/test_runtime_evidence_verifier.py`

**Interfaces:**
- `RunnerKeyStore(root: Path)` with `ensure_keypair() -> PublicKey` and `sign(payload: bytes) -> str`.
- `verify_receipt(receipt: Receipt, contract: Contract, current_identity: TargetIdentity, current_worktree_sha256: str, public_key: bytes) -> VerificationResult`.
- `VerificationResult.status` is `NOT_OBSERVED`, `REJECTED`, or `VERIFIED`; it includes a reason and never upgrades caller flags.

- [ ] **Step 1: Write failing tests** for no receipt, unsigned receipt, tampering, forged expected/observed data, contract mismatch, worktree mismatch, and valid signature.
- [ ] **Step 2: Run `pytest tests/test_runtime_evidence_verifier.py -q` and verify the expected missing-module failures.**
- [ ] **Step 3: Implement Ed25519 signing with private-key storage outside the checkout and strict verification of the signed canonical payload.**
- [ ] **Step 4: Run the focused verifier tests and verify they pass.**
- [ ] **Step 5: Commit with `git add tier1/runtime_evidence tests/test_runtime_evidence_verifier.py && git commit -m "feat: verify signed runtime evidence"`.**

### Task 3: OS process and HTTP runner

**Files:**
- Create: `tier1/runtime_evidence/identity.py`
- Create: `tier1/runtime_evidence/runner.py`
- Test: `tests/test_runtime_evidence_runner.py`

**Interfaces:**
- `discover_identity(port: int) -> TargetIdentity` obtains listening PID and command line from the OS.
- `probe_http(origin: str, path: str = "/") -> HttpObservation` reads status and body hash itself.
- `run_probe(contract: Contract, key_store: RunnerKeyStore, receipt_path: Path) -> Receipt` starts the committed command, discovers its port, observes HTTP, evaluates assertions, signs only a completed receipt, and cleans up the child process.

- [ ] **Step 1: Write failing tests** using a real local HTTP fixture for body hashing, process/port identity, assertion evaluation, and no partial receipt on startup/probe failure.
- [ ] **Step 2: Run `pytest tests/test_runtime_evidence_runner.py -q` and verify it fails before implementation.**
- [ ] **Step 3: Implement runner-owned observation and cleanup; never accept observations or pass bits from caller JSON.**
- [ ] **Step 4: Run focused runner tests and verify they pass.**
- [ ] **Step 5: Commit with `git add tier1/runtime_evidence tests/test_runtime_evidence_runner.py && git commit -m "feat: add observed runtime probe"`.**

### Task 4: End-to-end proof command and project wiring

**Files:**
- Create: `tier1/runtime_evidence/proof.py`
- Create: `tests/test_runtime_evidence_proof.py`
- Modify: `pyproject.toml`
- Modify: `README.md`

**Interfaces:**
- `python -m tier1.runtime_evidence.proof` exits 0 only after proving real observation, caller-flag rejection, forged receipt rejection, wrong-target rejection, and stale-worktree rejection.
- Add `[project.scripts] phase2-proof = "tier1.runtime_evidence.proof:main"` without changing existing Tier-1 labels.

- [ ] **Step 1: Write failing proof tests** for all five acceptance cases and exit-code behavior.
- [ ] **Step 2: Run `pytest tests/test_runtime_evidence_proof.py -q` and verify it fails before the proof command exists.**
- [ ] **Step 3: Implement the proof harness using a committed local fixture server and the runner/verifier APIs; do not hand-fill receipts.**
- [ ] **Step 4: Add concise README evidence-boundary documentation and the script entry point.**
- [ ] **Step 5: Run `python -m tier1.runtime_evidence.proof` and the complete test suite; verify the proof exits 0 and record unrelated failures separately.**
- [ ] **Step 6: Commit with `git add tier1/runtime_evidence tests pyproject.toml README.md && git commit -m "feat: add phase2 runtime evidence proof"`.**

## Self-review

The plan covers the receipt contract, cryptographic verification, process/page observation, stale and wrong-target rejection, and one-command proof. It deliberately does not implement the requested notebook Playwright journey because this repository contains the Python Tier-1 app rather than the separate notebook app; the runner interface leaves that target-specific journey outside this branch without fabricating it. The proof therefore establishes local HTTP/process observation and all five fail-closed acceptance cases without claiming browser or Hermes evidence.
