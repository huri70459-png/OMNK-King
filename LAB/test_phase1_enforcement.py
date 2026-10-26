import json
from hashlib import sha256
from pathlib import Path
import os
import shutil
import subprocess

import pytest

from rollback_guard import FileOwnership, OwnershipConfirmation, plan_rollback
from sandboxed_write_executor import execute_sandboxed_write
from scope_guard import ChangeContract, ChangedFile, evaluate


def digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def ready_plan(path: str, before: str, *, protected=()):
    return plan_rollback((
        FileOwnership(path, digest(before.encode()), digest(before.encode()), "ai"),
        *(FileOwnership(item, "missing", "missing", "user") for item in protected),
    ))


def test_empty_allow_list_is_blocked_and_defaults_are_tight():
    contract = ChangeContract(goal="add one button")
    result = evaluate(contract, [ChangedFile("src/button.tsx", 1)])
    assert result.status == "BLOCKED"
    assert "allowed file boundary is required" in result.violations
    assert contract.max_files == 3
    assert contract.max_changed_lines == 80


def test_write_failure_restores_every_file(tmp_path: Path, monkeypatch):
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("old-one", encoding="utf-8")
    second.write_text("old-two", encoding="utf-8")
    plan = plan_rollback((
        FileOwnership("one.txt", digest(b"old-one"), digest(b"old-one"), "ai"),
        FileOwnership("two.txt", digest(b"old-two"), digest(b"old-two"), "ai"),
    ))
    original_replace = __import__("os").replace
    calls = {"count": 0}

    def fail_second(source, target):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated crash")
        return original_replace(source, target)

    monkeypatch.setattr("sandboxed_write_executor.os.replace", fail_second)
    result = execute_sandboxed_write(
        tmp_path,
        {"one.txt": "new-one", "two.txt": "new-two"},
        rollback=plan,
        ownership=OwnershipConfirmation("abc", "main", ("one.txt", "two.txt")),
        repository_commit="abc",
        repository_branch="main",
    )
    assert result.status == "FAILED"
    assert first.read_text(encoding="utf-8") == "old-one"
    assert second.read_text(encoding="utf-8") == "old-two"


def test_hooks_are_fail_closed_and_gate_writes():
    hooks = json.loads(Path(".cursor/hooks.json").read_text(encoding="utf-8"))
    assert hooks["failClosed"] is True
    names = set(hooks["hooks"])
    assert {"preToolUse", "beforeShellExecution", "beforeMCPExecution", "sessionStart", "stop"} <= names
    assert any("Write|Delete|Edit|StrReplace" in str(item) for item in hooks["hooks"]["preToolUse"])
    assert Path(".cursor/hooks/phase1-guard.ps1").is_file()


def test_bypass_detector_blocks_live_checkout_writes():
    from phase1_enforcement import authorize_tool_call

    decision = authorize_tool_call(
        "Write", ".env", sandbox_root="C:/sandbox/run-1", cwd="C:/workspace/project"
    )
    assert decision.status == "BLOCKED"
    assert "sandbox" in decision.reason


def test_bypass_detector_allows_only_sandbox_mcp():
    from phase1_enforcement import authorize_tool_call

    assert authorize_tool_call("MCP", "tier1", sandbox_root="C:/sandbox/run-1", cwd="C:/sandbox/run-1").status == "ALLOW"
    assert authorize_tool_call("MCP", "filesystem", sandbox_root="C:/sandbox/run-1", cwd="C:/sandbox/run-1").status == "BLOCKED"


def test_hostile_phase1_proof_preserves_dirty_worktree(tmp_path: Path):
    """Exercise the real hook boundary and prove denials do not mutate git state."""
    from phase1_enforcement import authorize_tool_call

    repo = Path(__file__).resolve().parents[1]
    before_status = subprocess.run(
        ["git", "status", "--short"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout

    files = {}
    ownership = []
    for index in range(1, 6):
        name = f"file-{index}.txt"
        content = f"baseline-{index}"
        (tmp_path / name).write_text(content, encoding="utf-8")
        files[name] = content + "-new"
        ownership.append(FileOwnership(name, digest(content.encode()), digest(content.encode()), "ai"))
    plan = plan_rollback(tuple(ownership))
    original_replace = __import__("os").replace
    calls = {"count": 0}

    def fail_on_file_three(source, target):
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("hostile proof failure on file 3")
        return original_replace(source, target)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("sandboxed_write_executor.os.replace", fail_on_file_three)
    try:
        result = execute_sandboxed_write(
            tmp_path, files, rollback=plan,
            ownership=OwnershipConfirmation("abc", "main", tuple(files)),
            repository_commit="abc", repository_branch="main",
        )
    finally:
        monkeypatch.undo()
    assert result.status == "FAILED"
    assert all((tmp_path / name).read_text(encoding="utf-8") == f"baseline-{i}"
               for i, name in enumerate(files, start=1))

    assert evaluate(ChangeContract(goal="one file"), [ChangedFile("file-1.txt", 1)]).status == "BLOCKED"
    assert authorize_tool_call("Write", "..\\outside.txt", sandbox_root=str(tmp_path), cwd=str(tmp_path)).status == "BLOCKED"

    powershell = shutil.which("pwsh") or shutil.which("powershell")
    assert powershell, "PowerShell is required for the hook proof"
    hook = repo / ".cursor" / "hooks" / "phase1-guard.ps1"

    def run_hook(payload: str, *, env_updates=None):
        env = os.environ.copy()
        env["TIER1_GUARD_SANDBOX_ROOT"] = str(tmp_path)
        env.update(env_updates or {})
        return subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-File", str(hook)],
            input=payload, text=True, capture_output=True, env=env,
        )

    assert run_hook(json.dumps({"hook": "beforeShellExecution", "cwd": str(tmp_path), "command": "echo x > out.txt"})).returncode != 0
    assert run_hook(json.dumps({"hook": "beforeShellExecution", "cwd": str(tmp_path), "command": "python -c \"print(1)\""})).returncode != 0
    assert run_hook(json.dumps({"hook": "beforeMCPExecution", "server": "filesystem"})).returncode != 0
    assert run_hook("not-json").returncode != 0
    assert run_hook("{}", env_updates={"TIER1_GUARD_SANDBOX_ROOT": ""}).returncode != 0

    after_status = subprocess.run(
        ["git", "status", "--short"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert after_status == before_status
