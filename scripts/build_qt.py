"""Compile Qt resources and Designer UI files into Python modules.

Cross-platform replacement for build_qt.ps1. Run: uv run floo-build-qt
"""

import shutil
import sys
from pathlib import Path

try:
    from scripts.common import ROOT, run
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.common import ROOT, run


def main() -> None:
    """Compile resources.qrc and every .ui file under qtdesigner/ui."""
    rcc = shutil.which("pyside6-rcc")
    uic = shutil.which("pyside6-uic")
    if rcc is None or uic is None:
        raise SystemExit("PySide6 tools not found on PATH. Run: uv sync")

    out_dir = ROOT / "pages" / "ui"
    out_dir.mkdir(parents=True, exist_ok=True)

    run(
        [
            rcc,
            str(ROOT / "qtdesigner" / "resources.qrc"),
            "-o",
            str(out_dir / "resources_rc.py"),
        ]
    )

    ui_dir = ROOT / "qtdesigner" / "ui"
    ui_files = sorted(ui_dir.glob("*.ui"))
    if not ui_files:
        raise SystemExit(f"No .ui files found in {ui_dir}")
    for ui_file in ui_files:
        name = "main_window" if ui_file.stem == "mainwindow" else ui_file.stem
        output = out_dir / f"{name}.py"
        run([uic, str(ui_file), "-o", str(output), "--from-imports"])
        print(f"Converted {ui_file} to {output}")


if __name__ == "__main__":
    main()
