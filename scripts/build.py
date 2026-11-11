"""Build a standalone executable with PyInstaller.

Cross-platform replacement for build.ps1. Run: uv run --group build floo-build
"""

import os
import sys
from importlib.util import find_spec
from pathlib import Path

import UnityPy

try:
    from scripts.build_qt import main as build_qt
    from scripts.common import ROOT, run
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.build_qt import main as build_qt
    from scripts.common import ROOT, run

APP_NAME = "Floowandereeze & Modding - Duel Links"


def unity_package_dir() -> Path:
    """Locate the installed UnityPy package, honoring UNITYPY_PATH."""
    override = os.environ.get("UNITYPY_PATH")
    path = Path(override) if override else Path(UnityPy.__file__).parent
    if not path.is_dir():
        raise SystemExit(f"UnityPy package not found: {path}")
    return path


def main() -> None:
    """Compile Qt modules, then bundle the app with PyInstaller."""
    if find_spec("PyInstaller") is None:
        raise SystemExit("PyInstaller is not installed. Run: uv sync --group build")
    build_qt()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--add-data",
        f"{unity_package_dir()}{os.pathsep}UnityPy/",
        "--add-data",
        f"{ROOT / 'pages' / 'ui'}{os.pathsep}pages/ui/",
        "--hidden-import",
        "pyarrow",
        "--name",
        APP_NAME,
    ]
    if sys.platform == "win32":
        cmd.extend(["--icon", str(ROOT / "qtdesigner" / "images" / "icon.ico")])
    else:
        print(f"Skipping Windows icon on {sys.platform}")
    cmd.append(str(ROOT / "main.py"))
    run(cmd)


if __name__ == "__main__":
    main()
