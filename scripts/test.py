"""Build Qt modules and run the unit test suite.

Run: uv run floo-test
"""

import os
import subprocess
import sys
from pathlib import Path

try:
    from scripts.build_qt import main as build_qt
    from scripts.common import ROOT
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.build_qt import main as build_qt
    from scripts.common import ROOT


def main() -> None:
    """Compile Qt modules, then discover and run tests offscreen by default."""
    build_qt()
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        env=env,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
