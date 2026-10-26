import subprocess
import sys


def test_phase2_proof_fails_closed_without_real_app_and_browser_target():
    result = subprocess.run([sys.executable, "-m", "tier1.runtime_evidence.proof"], capture_output=True, text=True, timeout=20)
    assert result.returncode == 2
    assert "NOT_OBSERVED" in result.stdout
