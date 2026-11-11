"""Build Qt modules and launch the application.

Cross-platform replacement for dev.ps1. Run: uv run floo-dev
"""

import sys
from pathlib import Path

try:
    from scripts.build_qt import main as build_qt
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.build_qt import main as build_qt


def main() -> None:
    """Compile Qt modules, then launch the app in this process."""
    build_qt()
    from main import main as app_main  # Deferred: pages.ui must exist first.

    app_main()


if __name__ == "__main__":
    main()
