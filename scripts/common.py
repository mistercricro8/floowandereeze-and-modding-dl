"""Shared helpers for the project's cross-platform task scripts."""

import subprocess
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(
    cmd: Sequence[str | Path], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run a command from the project root, echoing it first."""
    display = " ".join(str(part) for part in cmd)
    print(f"+ {display}", flush=True)
    completed = subprocess.run([str(part) for part in cmd], cwd=ROOT, env=env)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed
