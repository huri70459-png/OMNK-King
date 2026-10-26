from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Contract:
    command: tuple[str, ...]
    cwd: str
    files: tuple[str, ...]
    assertions: tuple[dict[str, Any], ...]
    runner_public_key_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"command": list(self.command), "cwd": self.cwd, "files": list(self.files), "assertions": list(self.assertions),
                "runner_public_key_sha256": self.runner_public_key_sha256}


@dataclass(frozen=True)
class Target:
    argv: tuple[str, ...]
    cwd: str
    pid: int
    port: int
    origin: str

    def to_dict(self) -> dict[str, Any]:
        return {"argv": list(self.argv), "cwd": self.cwd, "pid": self.pid, "port": self.port, "origin": self.origin}


@dataclass(frozen=True)
class Observation:
    kind: str
    key: str
    values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "url": self.key, **self.values}


@dataclass(frozen=True)
class Assertion:
    id: str
    op: str
    expected: Any
    observed: Any
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "op": self.op, "expected": self.expected, "observed": self.observed, "pass": self.passed}


@dataclass(frozen=True)
class Receipt:
    runner_id: str
    started_at: str
    finished_at: str
    contract_sha256: str
    worktree_sha256: str
    target: Target
    observations: tuple[Observation, ...]
    assertions: tuple[Assertion, ...]
    signature: str

    def unsigned_dict(self) -> dict[str, Any]:
        return {"runner_id": self.runner_id, "started_at": self.started_at, "finished_at": self.finished_at,
                "contract_sha256": self.contract_sha256, "worktree_sha256": self.worktree_sha256,
                "target": self.target.to_dict(), "observations": [x.to_dict() for x in self.observations],
                "assertions": [x.to_dict() for x in self.assertions]}

    def to_dict(self) -> dict[str, Any]:
        data = self.unsigned_dict()
        data["signature"] = self.signature
        return data
