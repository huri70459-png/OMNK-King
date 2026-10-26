import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .crypto import RunnerKeyStore
from .hashutil import canonical_json, sha256_bytes, worktree_digest
from .identity import identity_for_process
from .model import Assertion, Contract, Observation, Receipt


@dataclass(frozen=True)
class HttpObservation:
    status: int
    body_sha256: str


def probe_http(origin: str, path: str = "/") -> HttpObservation:
    request = urllib.request.Request(origin.rstrip("/") + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            return HttpObservation(response.status, sha256_bytes(body))
    except urllib.error.HTTPError as error:
        body = error.read()
        return HttpObservation(error.code, sha256_bytes(body))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _discover_port(output: bytes, process: subprocess.Popen[bytes]) -> int:
    match = re.search(rb"(?:PORT=|port\s+)(\d+)", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # A fixed-port command is allowed when the contract supplies it.
    for token in process.args:
        if isinstance(token, str) and token.isdigit() and int(token) > 0:
            return int(token)
    raise RuntimeError("runner could not discover listening port")


def run_probe(contract: Contract, key_store: RunnerKeyStore, receipt_path: Path) -> Receipt:
    output_file = tempfile.NamedTemporaryFile(mode="w+b", delete=False)
    process = subprocess.Popen(list(contract.command), cwd=contract.cwd, stdout=output_file, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 5
        output = b""
        while time.time() < deadline:
            if process.poll() is not None:
                output_file.flush()
                output_file.seek(0)
                output = output_file.read()
                raise RuntimeError("probe process exited before observation")
            output_file.flush()
            output_file.seek(0)
            output = output_file.read()
            if b"Serving HTTP" in output or b"PORT=" in output or any(isinstance(x, str) and x.isdigit() and int(x) > 0 for x in process.args):
                break
            time.sleep(0.05)
        port = _discover_port(output, process)
        origin = f"http://127.0.0.1:{port}"
        observation = probe_http(origin)
        target = identity_for_process(tuple(process.args), str(Path(contract.cwd).resolve()), process.pid, port, origin).as_target()
        assertion = Assertion("page-up", "status", 200, observation.status, observation.status == 200)
        receipt = Receipt("omnk-local", _now(), _now(), sha256_bytes(canonical_json(contract.to_dict())),
                          worktree_digest(Path(contract.cwd), contract.files), target,
                          (Observation("http", "/", {"status": observation.status, "body_sha256": observation.body_sha256}),),
                          (assertion,), "")
        signed = Receipt(**{**receipt.__dict__, "signature": key_store.sign(canonical_json(receipt.unsigned_dict()))})
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(signed.to_dict(), sort_keys=True), encoding="utf-8")
        return signed
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
        output_file.close()
