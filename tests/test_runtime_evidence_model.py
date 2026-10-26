from pathlib import Path

from tier1.runtime_evidence.hashutil import canonical_json, sha256_bytes, worktree_digest
from tier1.runtime_evidence.model import Assertion, Contract, Observation, Receipt, Target


def test_canonical_json_is_stable_and_receipt_has_required_fields():
    left = canonical_json({"b": 2, "a": 1})
    right = canonical_json({"a": 1, "b": 2})
    assert left == right
    receipt = Receipt(
        runner_id="omnk-local", started_at="s", finished_at="f", contract_sha256="c",
        worktree_sha256="w", target=Target(("python", "-m", "app"), ".", 3, 5173, "http://127.0.0.1:5173"),
        observations=(Observation("http", "/", {"status": 200}),),
        assertions=(Assertion("page-up", "status", 200, 200, True),), signature="ed25519:x",
    )
    assert receipt.to_dict()["runner_id"] == "omnk-local"
    assert sha256_bytes(left)


def test_worktree_digest_changes_when_named_file_changes(tmp_path: Path):
    file = tmp_path / "contract.txt"
    file.write_text("one", encoding="utf-8")
    first = worktree_digest(tmp_path, ("contract.txt",))
    file.write_text("two", encoding="utf-8")
    assert worktree_digest(tmp_path, ("contract.txt",)) != first
