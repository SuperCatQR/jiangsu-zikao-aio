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
    assert "* maturity-check" in r.stdout
    assert "  maturity" in r.stdout
    assert "* maturity\n" not in r.stdout


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
    assert "[maturity-check] ok" in r.stdout


def test_run_gates_layers_maturity_does_not_abort_on_parent_argv():
    """Optional maturity layer must not parse parent --layers via nested argparse."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run-gates.py"), "--layers", "maturity"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    combined = r.stdout + r.stderr
    assert "unrecognized arguments" not in combined
    assert "error: unrecognized arguments: --layers" not in combined
    assert r.returncode == 0, combined
    assert "[maturity] ok" in r.stdout or "maturity" in combined.lower()
