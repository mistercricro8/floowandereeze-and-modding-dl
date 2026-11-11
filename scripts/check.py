"""Run the project's static checks (ruff lint + format).

- uv run floo-lint          (ruff check)
- uv run floo-format-check  (ruff format --check)
- uv run floo-format        (ruff check --fix + ruff format -w)
- uv run floo-check         (both checks)
"""

import shutil
import subprocess
import sys
from pathlib import Path

try:
    from scripts.common import ROOT
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.common import ROOT


def ruff() -> str:
    """Resolve the ruff binary from the environment."""
    binary = shutil.which("ruff")
    if binary is None:
        raise SystemExit("ruff is not installed. Run: uv sync --group dev")
    return binary


def lint_main() -> None:
    """Run ruff check (rules configured in pyproject.toml)."""
    completed = subprocess.run([ruff(), "check", "."], cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def format_main() -> None:
    """Run ruff format --check."""
    completed = subprocess.run([ruff(), "format", "--check", "."], cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def fix_main() -> None:
    """Apply safe lint fixes, then format the tree."""
    for args in (["check", "--fix", "."], ["format", "."]):
        completed = subprocess.run([ruff(), *args], cwd=ROOT)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)


def main() -> None:
    """Run ruff check, then ruff format --check."""
    lint_main()
    format_main()


if __name__ == "__main__":
    main()
