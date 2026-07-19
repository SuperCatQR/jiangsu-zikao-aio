"""Unified run-gates entrypoint."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_gates_list():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run-gates.py"), "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert "content" in r.stdout
    assert "publish" in r.stdout


def test_run_gates_default_passes_on_repo():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run-gates.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "All gates passed" in r.stdout
