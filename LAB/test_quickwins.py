from pathlib import Path

import pytest

from config_loader import load_guard_config
from quickwin_cli import main
from repository_adapter import inspect_repository, repository_mismatch


def test_repository_adapter_reports_git_identity():
    identity = inspect_repository(Path(__file__).resolve().parents[1])
    assert identity.root.endswith("Rayclaude-wiki")
    assert identity.is_git is True
    assert identity.branch
    assert identity.commit != "unavailable"


def test_config_loader_accepts_scoped_thresholds(tmp_path):
    config = tmp_path / "guards.toml"
    config.write_text('[scope]\nmax_files = 3\nmax_changed_lines = 20\nrisk = "medium"\n', encoding="utf-8")
    result = load_guard_config(config)
    assert (result.max_files, result.max_changed_lines, result.risk) == (3, 20, "medium")


def test_config_loader_rejects_invalid_risk(tmp_path):
    config = tmp_path / "guards.toml"
    config.write_text('risk = "unsafe"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_guard_config(config)


def test_quickwin_cli_is_read_only(capsys):
    assert main([str(Path(__file__).resolve().parents[1])]) == 0
    assert "repository" in capsys.readouterr().out


def test_repository_identity_rejects_wrong_branch_and_stale_commit():
    identity = inspect_repository(Path(__file__).resolve().parents[1])
    assert repository_mismatch(identity, expected_branch="not-main")
    assert repository_mismatch(identity, expected_commit="0000000")


def test_repository_identity_dirty_state_is_observable(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True,
                   capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("base", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True,
                   capture_output=True, text=True)
    clean = inspect_repository(tmp_path)
    assert clean.dirty is False
    (tmp_path / "README.md").write_text("user change", encoding="utf-8")
    assert inspect_repository(tmp_path).dirty is True
