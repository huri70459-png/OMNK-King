"""Small, dependency-free Scope Guard prototype.

The prototype evaluates a proposed change set against a user-approved contract.
It does not edit files, run commands, or silently approve scope expansion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
import difflib
import hashlib


@dataclass(frozen=True)
class ChangeContract:
    goal: str
    allowed_files: tuple[str, ...] = ()
    allowed_layers: tuple[str, ...] = ()
    max_files: int = 3
    max_changed_lines: int = 80
    acceptance_tests: tuple[str, ...] = ()
    risk: str = "low"


@dataclass(frozen=True)
class ChangedFile:
    path: str
    changed_lines: int = 0
    layer: str = ""
    generated: bool = False
    destructive: bool = False


@dataclass(frozen=True)
class ScopeResult:
    status: str
    score: float
    required_changes: tuple[str, ...] = ()
    unexpected_changes: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    rollback_available: bool = True

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "score": self.score,
            "required_changes": list(self.required_changes),
            "unexpected_changes": list(self.unexpected_changes),
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "rollback_available": self.rollback_available,
        }


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    digest: str
    text: str


def snapshot_workspace(root: str | Path, *, ignored: tuple[str, ...] = ()) -> dict[str, FileSnapshot]:
    """Capture text files below root for a before/after scope comparison."""
    base = Path(root).resolve()
    result: dict[str, FileSnapshot] = {}
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(base).as_posix()
        if any(_allowed(relative, (pattern,)) for pattern in ignored):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        result[relative] = FileSnapshot(relative, hashlib.sha256(text.encode()).hexdigest(), text)
    return result


def changed_files(before: dict[str, FileSnapshot], after: dict[str, FileSnapshot]) -> list[ChangedFile]:
    """Build a changed-file list from two workspace snapshots."""
    changes: list[ChangedFile] = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old and new and old.digest == new.digest:
            continue
        old_text, new_text = old.text if old else "", new.text if new else ""
        diff = list(difflib.ndiff(old_text.splitlines(), new_text.splitlines()))
        lines = sum(1 for line in diff if line.startswith(("+ ", "- ")))
        lower = path.lower()
        layer = _layer_for(path)
        changes.append(ChangedFile(
            path=path,
            changed_lines=lines,
            layer=layer,
            generated=any(token in lower for token in ("dist/", "build/", ".generated.", ".min.")),
            destructive=path.endswith((".sql", ".db", ".sqlite")) and (new is None or "drop " in new_text.lower()),
        ))
    return changes


def _layer_for(path: str) -> str:
    parts = path.lower().split("/")
    if any(part in parts for part in ("test", "tests", "__tests__")):
        return "test"
    if any(part in parts for part in ("component", "components", "pages", "views")):
        return "ui"
    if any(part in parts for part in ("api", "routes", "middleware")):
        return "api"
    if any(part in parts for part in ("db", "database", "migrations")):
        return "data"
    if any(part in parts for part in ("dist", "build")) or path.endswith((".lock", ".map")):
        return "build"
    if path.endswith((".json", ".toml", ".yaml", ".yml", ".env")):
        return "config"
    return "utility"


def _allowed(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(path, pattern) for pattern in patterns)


def evaluate(contract: ChangeContract, changes: list[ChangedFile]) -> ScopeResult:
    """Evaluate changes without mutating the worktree."""
    violations: list[str] = []
    warnings: list[str] = []
    unexpected: list[str] = []

    if not contract.goal.strip():
        violations.append("change contract has no goal")
    if not contract.allowed_files:
        violations.append("allowed file boundary is required")
    if len(changes) > contract.max_files:
        violations.append(f"file budget exceeded: {len(changes)} > {contract.max_files}")
    total_lines = sum(max(0, change.changed_lines) for change in changes)
    if total_lines > contract.max_changed_lines:
        violations.append(f"line budget exceeded: {total_lines} > {contract.max_changed_lines}")

    for change in changes:
        if not _allowed(change.path, contract.allowed_files):
            unexpected.append(change.path)
        if contract.allowed_layers and change.layer not in contract.allowed_layers:
            violations.append(f"layer outside boundary: {change.path}")
        if change.generated:
            warnings.append(f"generated file requires review: {change.path}")
        if change.destructive:
            violations.append(f"destructive change requires approval: {change.path}")

    if unexpected:
        violations.append("scope expansion requires justification and approval")
    if not contract.acceptance_tests:
        warnings.append("no acceptance tests mapped to the change")

    if violations:
        status = "BLOCKED" if any(
            token in item for item in violations
            for token in ("destructive", "budget", "allowed file boundary")
        ) else "REVIEW"
    elif warnings:
        status = "PARTIAL"
    else:
        status = "PASS"

    score = max(0.0, round(1 - (len(violations) * 0.2) - (len(warnings) * 0.05), 2))
    return ScopeResult(
        status=status,
        score=score,
        unexpected_changes=tuple(unexpected),
        violations=tuple(violations),
        warnings=tuple(warnings),
        rollback_available=not any(change.destructive for change in changes),
    )


def expansion_request(contract: ChangeContract, change: ChangedFile, reason: str) -> dict:
    """Return an approval request instead of silently widening the contract."""
    if not reason.strip():
        raise ValueError("scope expansion reason is required")
    return {
        "type": "scope_expansion",
        "status": "approval_required",
        "original_boundary": list(contract.allowed_files),
        "requested_file": change.path,
        "requested_layer": change.layer,
        "reason": reason.strip(),
        "risk": contract.risk,
    }
