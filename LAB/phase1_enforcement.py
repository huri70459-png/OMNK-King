"""Fail-closed tool boundary for Phase 1 governed execution."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolDecision:
    status: str
    reason: str = ""


def authorize_tool_call(kind: str, target: str, *, sandbox_root: str, cwd: str) -> ToolDecision:
    """Authorize only sandbox-contained writes and the Tier-1 MCP server."""
    sandbox = Path(sandbox_root).resolve()
    current = Path(cwd).resolve()
    if kind.upper() == "MCP":
        return ToolDecision("ALLOW" if target == "tier1" else "BLOCKED", "only tier1 MCP is allowed")
    try:
        current.relative_to(sandbox)
    except ValueError:
        return ToolDecision("BLOCKED", "tool cwd is outside the active sandbox")
    if kind.upper() in {"WRITE", "DELETE", "EDIT", "STRREPLACE"}:
        candidate = (sandbox / target).resolve()
        try:
            candidate.relative_to(sandbox)
        except ValueError:
            return ToolDecision("BLOCKED", "target escapes the active sandbox")
        if any(part in {".git", ".env", ".cursor"} for part in candidate.relative_to(sandbox).parts):
            return ToolDecision("BLOCKED", "protected path cannot be edited")
        return ToolDecision("ALLOW")
    return ToolDecision("BLOCKED", "unsupported tool kind")
