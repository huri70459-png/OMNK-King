import json
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

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is declared for supported runs
    psutil = None


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


def _discover_port(process: subprocess.Popen[bytes]) -> int:
    if psutil is None:
        raise RuntimeError("runner requires psutil for PID-owned socket discovery")
    for connection in psutil.net_connections(kind="tcp"):
        if connection.pid != process.pid or connection.status != psutil.CONN_LISTEN or not connection.laddr:
            continue
        host = connection.laddr.ip if hasattr(connection.laddr, "ip") else connection.laddr[0]
        if host in {"127.0.0.1", "::1", "0.0.0.0", "::"}:
            return connection.laddr.port if hasattr(connection.laddr, "port") else connection.laddr[1]
    raise RuntimeError("runner could not discover a listening port owned by spawned PID")


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
            try:
                port = _discover_port(process)
                break
            except RuntimeError:
                pass
            time.sleep(0.05)
        else:
            raise RuntimeError("runner timed out waiting for PID-owned listening socket")
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
