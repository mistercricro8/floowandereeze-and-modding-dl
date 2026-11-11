# Floowandereeze & Modding - Duel Links

A modding tool for Yu-Gi-Oh! Duel Links, built with PySide6 (Qt6) for Windows.

## 🚧 Under Development 🚧

⚠️ **This project is currently in active development. Features may change or break at any time.** ⚠️

[![CI](https://github.com/Nauder/floowandereeze-and-modding-dl/actions/workflows/ci.yml/badge.svg)](https://github.com/Nauder/floowandereeze-and-modding-dl/actions/workflows/ci.yml)
[![Docs](https://github.com/Nauder/floowandereeze-and-modding-dl/actions/workflows/docs.yml/badge.svg)](https://github.com/Nauder/floowandereeze-and-modding-dl/actions/workflows/docs.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

[![Python](https://img.shields.io/badge/python-3.12-blue.svg?logo=python&logoColor=white)](https://www.python.org)
[![uv](https://img.shields.io/badge/uv-package_manager-261230.svg?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![PySide6](https://img.shields.io/badge/PySide6-6-41CD52.svg?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2-29B6F6.svg?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org)
[![UnityPy](https://img.shields.io/badge/UnityPy-1-000000.svg?logo=unity&logoColor=white)](https://github.com/K0lb3/UnityPy)
[![Windows](https://img.shields.io/badge/Windows-10+-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Documentation](docs/index.md)
- [Project Structure](#project-structure)
- [Development](#development)
- [Building](#building)
- [License](#license)
- [Credits](#credits)

## Features

- Unity asset texture extraction and manipulation, including:
  - Card Art
  - Card Sleeve
  - Playmat
  - Character textures, including batch replacement, extraction, and restore
- Searchable accessory names, character search and series filters, and favorites
- Backup inventory with scoped ZIP import, export, and removal
- Steam account discovery and configurable metadata sources
- Responsive image editors with Stretch and Crop modes
- Customizable compression and mipmap count for created assets

## Requirements

- Windows 10 or later
- Python 3.12 or later (uv installs it automatically if missing)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for dependency management
- Yu-Gi-Oh! Duel Links installed with the in-game download
- (Linux dev only) Nix with flakes enabled, for the Qt runtime libraries

## Installation

For end-user documentation, refer to the [documentation](https://nauder.github.io/floowandereeze-and-modding-dl)

1. Clone the repository:

    ```bash
    git clone https://github.com/Nauder/floowandereeze-and-modding-dl.git
    cd floowandereeze-and-modding-dl
    ```

2. Install dependencies (creates `.venv` automatically):

    ```bash
    uv sync
    ```

3. (Optional) Install extra groups:

    ```bash
    uv sync --group dev    # ruff (linter + formatter)
    uv sync --group build  # PyInstaller
    uv sync --group docs   # mkdocs + material
    ```

## Usage

### Running the development environment

```bash
uv run floowandereeze
```

This will:

- Compile Qt UI files and resources (equivalent to `uv run floo-build-qt`)
- Launch the application

Note: The Qt build step is used to:

- Compile Qt resource files (`.qrc`) into Python modules
- Convert Qt Designer UI files (`.ui`) into Python code
- These steps are necessary for the application to run properly

On Linux, run inside the Nix dev shell so Qt finds its system libraries:

```bash
nix develop
uv run floowandereeze
```

### Running tests and checks

```bash
uv run floo-test          # Qt build + unittest suite (offscreen by default)
uv run floo-lint          # ruff check (needs --group dev)
uv run floo-format-check  # ruff format --check (needs --group dev)
uv run floo-format        # ruff --fix + format write (needs --group dev)
uv run floo-check         # ruff check + format --check
```

### Running the documentation

```bash
uv run --group docs mkdocs serve
```

This will serve the documentation in the `docs/` directory at <https://localhost:8000>

### Capturing GUI pictures automatically

After configuring the app and downloading metadata, run:

```bash
uv run floo-capture
```

This updates the documentation screenshots using the real GUI and a disposable
database copy. See the [capture workflow](docs/development/screenshots.md) for page
selection, review output, fixed window sizes, and offscreen capture.

## Project Structure

```txt
floowandereeze-and-modding-dl/
├── pages/            # Main application pages and windows
│   ├── models/       # Asset List Models for data pages
│   └── ui/           # Generated Qt modules (via floo-build-qt, gitignored)
├── widgets/          # Custom Qt widgets
├── services/         # Core functionality services
├── util/             # Utility functions and helpers
├── database/         # Database models and operations
├── unity/            # Unity asset handling
├── dialogs/          # Custom dialog windows
├── scripts/          # Cross-platform task scripts (floo-* entry points)
├── qtdesigner/       # Qt Designer UI files
│   ├── ui/           # UI files (.ui)
│   └── images/       # Application images and resources
├── main.py           # Application entry point
├── pyproject.toml    # Project metadata, deps, groups, tool config
├── uv.lock           # Locked dependency versions
└── flake.nix         # Nix dev shell with Qt runtime libraries
```

## Development
- The project uses PySide6 for the GUI, with Pyside Designer ui files
- SQLAlchemy for database operations
- UnityPy for Unity asset handling
- uv manages the virtualenv and lockfile; task scripts live in `scripts/` and are exposed as `floo-*` commands
- Currently, development is focused on Windows, as that is the main supported desktop OS for Duel Links

## Building

To create a standalone executable (Windows):

```bash
uv sync --group build
uv run --group build floo-build
```

This script will:

1. Compile Qt UI files and resources (same as `floo-build-qt`)
2. Create a single-file executable using PyInstaller
3. Include necessary dependencies and UnityPy assets
4. Generate the executable in the `dist` directory

Set `UNITYPY_PATH` to override the auto-detected UnityPy package location.

## License
This project is licensed under the terms specified in the LICENSE file.
