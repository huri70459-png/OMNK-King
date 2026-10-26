import subprocess
import sys


def test_phase2_proof_command_passes_all_acceptance_cases():
    result = subprocess.run([sys.executable, "-m", "tier1.runtime_evidence.proof"], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "phase2 proof: VERIFIED" in result.stdout
