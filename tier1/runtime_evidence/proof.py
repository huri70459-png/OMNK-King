import json
import sys
import tempfile
from pathlib import Path

from .crypto import RunnerKeyStore
from .hashutil import canonical_json, sha256_bytes, worktree_digest
from .model import Assertion, Contract, Receipt, Target
from .runner import run_probe
from .verifier import verify_receipt


def _fixture(root: Path) -> Path:
    path = root / "phase2_fixture.py"
    path.write_text("""import http.server, socketserver\nclass H(http.server.SimpleHTTPRequestHandler):\n    def log_message(self, *args): pass\nwith socketserver.TCPServer(('127.0.0.1', 0), H) as s:\n    print(f'PORT={s.server_address[1]}', flush=True)\n    s.serve_forever()\n""", encoding="utf-8")
    return path


def run_acceptance() -> bool:
    with tempfile.TemporaryDirectory(prefix="omnk-phase2-") as raw:
        root = Path(raw)
        fixture = _fixture(root)
        keys = RunnerKeyStore(root / "runner-key")
        contract = Contract((sys.executable, str(fixture)), str(root), (fixture.name,), ({"id": "page-up", "op": "status", "expected": 200},), sha256_bytes(keys.public_key_bytes()))
        receipt_path = root / "receipt.json"
        receipt = run_probe(contract, keys, receipt_path)
        current = verify_receipt(receipt, contract, receipt.target, worktree_digest(root, contract.files), keys.public_key_bytes())
        if current.status != "VERIFIED":
            return False
        if verify_receipt(None, contract, None, "anything", keys.public_key_bytes()).status != "NOT_OBSERVED":
            return False
        forged = Receipt(**{**receipt.__dict__, "assertions": (Assertion("page-up", "status", 200, 200, False),)})
        if verify_receipt(forged, contract, receipt.target, worktree_digest(root, contract.files), keys.public_key_bytes()).status != "REJECTED":
            return False
        wrong = Target(receipt.target.argv, receipt.target.cwd, receipt.target.pid, receipt.target.port + 1, receipt.target.origin)
        if verify_receipt(receipt, contract, wrong, worktree_digest(root, contract.files), keys.public_key_bytes()).status != "REJECTED":
            return False
        fixture.write_text(fixture.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        if verify_receipt(receipt, contract, receipt.target, worktree_digest(root, contract.files), keys.public_key_bytes()).status != "REJECTED":
            return False
    return True


def main() -> int:
    # The repository does not contain the target notebook app or a runner-owned
    # browser journey. A fixture-only result must never be promoted to Phase 2.
    print("phase2 proof: NOT_OBSERVED (real app/browser target unavailable)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
