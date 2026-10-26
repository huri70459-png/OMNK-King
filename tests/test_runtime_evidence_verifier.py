from pathlib import Path

from tier1.runtime_evidence.crypto import RunnerKeyStore
from tier1.runtime_evidence.hashutil import canonical_json, sha256_bytes
from tier1.runtime_evidence.model import Assertion, Contract, Receipt, Target
from tier1.runtime_evidence.verifier import verify_receipt


def contract():
    return Contract(("python", "-m", "fixture"), ".", ("fixture.py",), ({"id": "up", "expected": 200},), "")


def receipt(store, contract_sha="contract", worktree_sha="tree"):
    target = Target(("python", "-m", "fixture"), ".", 10, 5000, "http://127.0.0.1:5000")
    unsigned = Receipt("runner", "s", "f", contract_sha, worktree_sha, target, (), (Assertion("up", "status", 200, 200, True),), "")
    sig = store.sign(canonical_json(unsigned.unsigned_dict()))
    return Receipt(**{**unsigned.__dict__, "signature": sig}), target


def test_verifier_rejects_missing_and_caller_flags_without_receipt():
    result = verify_receipt(None, contract(), None, "tree", b"")
    assert result.status == "NOT_OBSERVED"
    assert result.reason == "receipt required"


def test_verifier_accepts_valid_signature_and_rejects_tamper(tmp_path: Path):
    store = RunnerKeyStore(tmp_path)
    configured = Contract(contract().command, contract().cwd, contract().files, contract().assertions, sha256_bytes(store.public_key_bytes()))
    receipt_value, target = receipt(store, sha256_bytes(canonical_json(configured.to_dict())), "tree")
    valid = verify_receipt(receipt_value, configured, target, "tree", store.public_key_bytes())
    assert valid.status == "VERIFIED"
    forged = Receipt(**{**receipt_value.__dict__, "assertions": (Assertion("up", "status", 200, 500, True),)})
    assert verify_receipt(forged, configured, target, "tree", store.public_key_bytes()).status == "REJECTED"

def test_verifier_rejects_unpinned_or_wrong_runner_key(tmp_path: Path):
    store = RunnerKeyStore(tmp_path / "trusted")
    other = RunnerKeyStore(tmp_path / "other")
    value, target = receipt(store, sha256_bytes(canonical_json(contract().to_dict())), "tree")
    assert verify_receipt(value, contract(), target, "tree", store.public_key_bytes()).status == "REJECTED"
    pinned = Contract(contract().command, contract().cwd, contract().files, contract().assertions, sha256_bytes(store.public_key_bytes()))
    assert verify_receipt(value, pinned, target, "tree", other.public_key_bytes()).status == "REJECTED"

def test_verifier_rejects_invalid_signature(tmp_path: Path):
    store = RunnerKeyStore(tmp_path)
    value, target = receipt(store, sha256_bytes(canonical_json(contract().to_dict())), "tree")
    pinned = Contract(contract().command, contract().cwd, contract().files, contract().assertions, sha256_bytes(store.public_key_bytes()))
    forged = Receipt(**{**value.__dict__, "signature": "ed25519:" + "00" * 64})
    assert verify_receipt(forged, pinned, target, "tree", store.public_key_bytes()).status == "REJECTED"


def test_verifier_rejects_wrong_target_and_stale_hash(tmp_path: Path):
    store = RunnerKeyStore(tmp_path)
    value, target = receipt(store, sha256_bytes(canonical_json(contract().to_dict())), "tree")
    wrong = Target(target.argv, target.cwd, target.pid, target.port + 1, target.origin)
    assert verify_receipt(value, contract(), wrong, "tree", store.public_key_bytes()).status == "REJECTED"
    assert verify_receipt(value, contract(), target, "changed", store.public_key_bytes()).status == "REJECTED"
