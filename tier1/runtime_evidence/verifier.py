from dataclasses import dataclass
from typing import Optional

from .crypto import verify_signature
from .hashutil import canonical_json, sha256_bytes
from .model import Contract, Receipt, Target


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reason: str


def verify_receipt(receipt: Optional[Receipt], contract: Contract, current_identity: Optional[Target], current_worktree_sha256: str, public_key: bytes) -> VerificationResult:
    if receipt is None:
        return VerificationResult("NOT_OBSERVED", "receipt required")
    if receipt.contract_sha256 != sha256_bytes(canonical_json(contract.to_dict())):
        return VerificationResult("REJECTED", "contract hash mismatch")
    if receipt.worktree_sha256 != current_worktree_sha256:
        return VerificationResult("REJECTED", "worktree hash mismatch")
    if not receipt.contract_sha256 or contract.runner_public_key_sha256 != sha256_bytes(public_key):
        return VerificationResult("REJECTED", "runner key is not pinned by contract")
    if current_identity is None or receipt.target != current_identity:
        return VerificationResult("REJECTED", "runtime identity mismatch")
    if not all(item.passed and item.observed == item.expected for item in receipt.assertions):
        return VerificationResult("REJECTED", "assertion mismatch")
    if not verify_signature(canonical_json(receipt.unsigned_dict()), receipt.signature, public_key):
        return VerificationResult("REJECTED", "invalid signature")
    return VerificationResult("VERIFIED", "signed runtime observation verified")
