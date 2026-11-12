"""PyInstaller runtime hook to isolate frozen bundle from host environment."""

import os
import sys

if getattr(sys, "frozen", False):
    os.environ.pop("_PYTHON_SYSCONFIGDATA_NAME", None)
