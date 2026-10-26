import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def worktree_digest(root: Path, files: tuple[str, ...]) -> str:
    payload = []
    for name in sorted(files):
        path = root / name
        payload.append({"path": name, "sha256": sha256_bytes(path.read_bytes())})
    return sha256_bytes(canonical_json(payload))
