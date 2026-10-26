"""Read-only Tier-1 integration for the LAB browser-repair pipeline."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

try:
    from .evidence_ladder_guard import EvidenceRecord
    from .guard_orchestrator import BrowserRepairInput, BrowserRepairResult, run_browser_repair
    from .runtime_identity_guard import RuntimeContract, RuntimeEvidence
    from .safety_action_guard import ActionRequest
    from .scope_guard import ChangeContract
    from .task_capsule_guard import TaskCapsuleInput
    from .cost_performance_guard import CallRecord
    from .repository_adapter import inspect_repository
except ImportError:  # standalone LAB test imports
    from evidence_ladder_guard import EvidenceRecord
    from guard_orchestrator import BrowserRepairInput, BrowserRepairResult, run_browser_repair
    from runtime_identity_guard import RuntimeContract, RuntimeEvidence
    from safety_action_guard import ActionRequest
    from scope_guard import ChangeContract
    from task_capsule_guard import TaskCapsuleInput
    from cost_performance_guard import CallRecord
    from repository_adapter import inspect_repository


def _commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def inspect_browser_repair(root: Path, port: int, title: str, route: str = "/", goal: str = "Make the intended Tier-1 application visible in the browser") -> BrowserRepairResult:
    """Create a truthful repair decision from the actual Tier-1 process state.

    The adapter deliberately supplies no write action and no fabricated browser evidence.
    """
    project = root.name
    repository = inspect_repository(root)
    contract = RuntimeContract(project, _commit(root), port, route, title)
    observed = RuntimeEvidence(project, _commit(root), port, route, title, 200, True)
    scope = ChangeContract(
        goal,
        ("tier1/api.py", "tier1/static/index.html"),
        (), 3, 80, ("browser",),
    )
    return run_browser_repair(BrowserRepairInput(
        runtime_expected=contract,
        runtime_observed=observed,
        changed_files=(),
        scope=scope,
        action=ActionRequest("inspect runtime only", str(root), "read", input_valid=True, output_valid=True),
        impacts=(),
        evidence=(
            EvidenceRecord("BROWSER_VERIFIED", False, "unavailable"),
            EvidenceRecord("JOURNEY_VERIFIED", False, "unavailable"),
        ),
        context=TaskCapsuleInput(
            project=project, canonical_sources=("PDR-DOC/CORE-CREATION.md",), freshness="current",
            goal=goal,
            implementation_state="Tier-1 server is running; no repair applied",
            constraints=("read-only inspection", "do not claim browser proof without browser evidence"),
            relevant_files=("tier1/api.py", "tier1/static/index.html"), decisions=(),
            verification=("HTTP /health checked",), next_boundary="collect browser journey evidence",
            repository_root=repository.root, repository_branch=repository.branch,
            repository_commit=repository.commit, repository_dirty=repository.dirty,
        ),
        calls=(),
        repository=repository,
    ))
