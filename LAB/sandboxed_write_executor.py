"""Ownership-gated, repository-local writes with post-write diff verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import os
import tempfile

try:
    from .rollback_guard import OwnershipConfirmation, RollbackPlan, ownership_mismatch
except ImportError:
    from rollback_guard import OwnershipConfirmation, RollbackPlan, ownership_mismatch


@dataclass(frozen=True)
class WriteResult:
    status: str
    written_files: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class RollbackResult:
    status: str
    restored_files: tuple[str, ...] = ()
    protected_files: tuple[str, ...] = ()
    reason: str = ""


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_digest(value: str) -> bool:
    return value == "missing" or len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _safe_path(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def execute_sandboxed_write(
    root: str | Path,
    requested: dict[str, str],
    *,
    rollback: RollbackPlan,
    ownership: OwnershipConfirmation | None,
    repository_commit: str,
    repository_branch: str,
) -> WriteResult:
    """Write an exact approved file set and verify its resulting diff.

    Preflight is complete before the first write. This is deliberately not a
    rollback executor: a failed post-write verification reports failure.
    """
    base = Path(root).resolve()
    if not base.is_dir():
        return WriteResult("BLOCKED", reason="write root is not a directory")
    if rollback.status != "READY":
        return WriteResult("BLOCKED", reason="rollback plan is not ready")
    mismatch = ownership_mismatch(
        rollback, ownership,
        repository_commit=repository_commit,
        repository_branch=repository_branch,
    )
    if mismatch:
        return WriteResult("BLOCKED", reason=mismatch)

    approved = set(rollback.ai_files)
    requested_paths = set(requested)
    if requested_paths != approved:
        return WriteResult("BLOCKED", reason="requested files must exactly match the AI rollback boundary")
    if requested_paths & set(rollback.protected_user_files):
        return WriteResult("BLOCKED", reason="requested files include protected user files")

    targets: dict[str, Path] = {}
    before: dict[str, bytes] = {}
    for relative in sorted(requested_paths):
        target = _safe_path(base, relative)
        if target is None:
            return WriteResult("BLOCKED", reason=f"path escapes repository root: {relative}")
        if target.exists() and target.is_symlink():
            return WriteResult("BLOCKED", reason=f"symlink target is not writable: {relative}")
        if target.exists() and not target.is_file():
            return WriteResult("BLOCKED", reason=f"target is not a regular file: {relative}")
        baseline = dict(rollback.baseline_digests).get(relative)
        if not baseline or not _valid_digest(baseline):
            return WriteResult("BLOCKED", reason=f"invalid baseline digest: {relative}")
        if target.exists():
            current = target.read_bytes()
            if baseline == "missing" or _digest_bytes(current) != baseline:
                return WriteResult("BLOCKED", reason=f"baseline drift detected: {relative}")
            before[relative] = current
        else:
            if baseline != "missing":
                return WriteResult("BLOCKED", reason=f"baseline expects an existing file: {relative}")
            before[relative] = b""
        targets[relative] = target

    staging = Path(tempfile.mkdtemp(prefix="tier1-stage-", dir=str(base)))
    staged: dict[str, Path] = {}
    try:
        for relative in sorted(targets):
            staged_path = staging / relative
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            with staged_path.open("wb") as handle:
                handle.write(requested[relative].encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            staged[relative] = staged_path
        for relative, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged[relative], target)
    except (OSError, UnicodeEncodeError) as exc:
        for relative, original in before.items():
            target = targets[relative]
            try:
                if original:
                    target.write_bytes(original)
                elif target.exists():
                    target.unlink()
            except OSError:
                return WriteResult("FAILED", reason=f"write failed and restore failed: {exc}")
        return WriteResult("FAILED", reason=f"write failed; all files restored: {exc}")
    finally:
        for child in sorted(staging.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        staging.rmdir()

    changed: list[str] = []
    for relative, target in targets.items():
        if not target.exists() or not target.is_file():
            return WriteResult("FAILED", tuple(sorted(targets)), tuple(changed),
                               f"post-write verification failed: {relative} missing")
        if target.read_text(encoding="utf-8") != requested[relative]:
            return WriteResult("FAILED", tuple(sorted(targets)), tuple(changed),
                               f"post-write verification failed: {relative} content mismatch")
        if target.read_bytes() != before[relative]:
            changed.append(relative)
    return WriteResult("WRITTEN", tuple(sorted(targets)), tuple(sorted(changed)),
                       "exact AI-owned diff verified")


def execute_sandboxed_rollback(
    root: str | Path,
    baseline: dict[str, str | None],
    *,
    expected_current_digests: dict[str, str],
    protected_user_digests: dict[str, str],
    rollback: RollbackPlan,
    ownership: OwnershipConfirmation | None,
    repository_commit: str,
    repository_branch: str,
) -> RollbackResult:
    """Restore only the approved AI boundary after verifying current state."""
    base = Path(root).resolve()
    if not base.is_dir() or rollback.status != "READY":
        return RollbackResult("BLOCKED", reason="rollback root or plan is not ready")
    mismatch = ownership_mismatch(rollback, ownership,
                                 repository_commit=repository_commit,
                                 repository_branch=repository_branch)
    if mismatch:
        return RollbackResult("BLOCKED", reason=mismatch)
    if set(baseline) != set(rollback.ai_files):
        return RollbackResult("BLOCKED", reason="rollback content does not exactly match AI boundary")
    if set(expected_current_digests) != set(rollback.ai_files):
        return RollbackResult("BLOCKED", reason="current-state proof does not exactly match AI boundary")

    targets: dict[str, Path] = {}
    for relative in sorted(set(rollback.ai_files) | set(rollback.protected_user_files)):
        target = _safe_path(base, relative)
        if target is None or (target.exists() and target.is_symlink()):
            return RollbackResult("BLOCKED", reason=f"unsafe rollback path: {relative}")
        targets[relative] = target
    for relative in rollback.protected_user_files:
        target = targets[relative]
        current = _digest_bytes(target.read_bytes()) if target.exists() else "missing"
        if current != protected_user_digests.get(relative):
            return RollbackResult("BLOCKED", reason=f"protected user file changed: {relative}")
    for relative in rollback.ai_files:
        target = targets[relative]
        current = _digest_bytes(target.read_bytes()) if target.exists() else "missing"
        if current != expected_current_digests[relative]:
            return RollbackResult("BLOCKED", reason=f"AI file changed after write: {relative}")

    try:
        for relative in rollback.ai_files:
            target = targets[relative]
            content = baseline[relative]
            if content is None:
                if target.exists():
                    target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content.encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    except (OSError, UnicodeEncodeError) as exc:
        return RollbackResult("FAILED", reason=f"rollback failed: {exc}")

    for relative in rollback.ai_files:
        target = targets[relative]
        content = baseline[relative]
        if content is None and target.exists():
            return RollbackResult("FAILED", reason=f"rollback verification failed: {relative} remains")
        if content is not None and (not target.exists() or target.read_text(encoding="utf-8") != content):
            return RollbackResult("FAILED", reason=f"rollback verification failed: {relative}")
    return RollbackResult("ROLLED_BACK", tuple(sorted(rollback.ai_files)),
                          tuple(sorted(rollback.protected_user_files)),
                          "AI-owned baseline restored; protected user files verified unchanged")
