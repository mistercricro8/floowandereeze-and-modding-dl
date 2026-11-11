"""Defaults and validation shared by metadata downloaders and Configuration."""

import json
import re
from pathlib import Path

DEFAULT_METADATA_REPOSITORY = "Nauder/floowandereeze-and-modding-etl-dl"
DEFAULT_METADATA_BRANCH = ""
METADATA_FILES = (
    "version.txt",
    "cards.parquet",
    "sleeves.parquet",
    "fields.parquet",
    "characters.parquet",
)


def is_local_metadata_source(repository):
    """Recognize local folders, including relative paths and missing absolute paths."""
    return bool(repository) and (
        Path(repository).expanduser().is_absolute()
        or repository.startswith((".", "~"))
        or Path(repository).expanduser().is_dir()
    )


def normalize_metadata_source(repository, branch=""):
    """Accept a GitHub source or a local checkout containing exported metadata."""
    repository = repository.strip()
    branch = branch.strip()
    if is_local_metadata_source(repository):
        root = Path(repository).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Local metadata folder does not exist: {root}")
        missing = [
            name for name in METADATA_FILES if not (root / "data" / name).is_file()
        ]
        if missing:
            raise ValueError(
                "Local repository is missing data files: " + ", ".join(missing)
            )
        return str(root), ""
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError(
            "Enter a local repository folder or owner/repository, for example "
            + DEFAULT_METADATA_REPOSITORY
            + "."
        )
    owner, repo = repository.split("/")
    if len(owner) > 39 or len(repo) > 100 or repo in {".", ".."}:
        raise ValueError("Invalid GitHub repository name.")
    if len(branch) > 255 or any(char.isspace() or ord(char) < 32 for char in branch):
        raise ValueError(
            "Branch must be a name/ref without whitespace, or blank for "
            "the repository default."
        )
    return repository, branch


def metadata_source_key(repository, branch):
    """Track successful sources independently of their metadata version dates."""
    repository, branch = normalize_metadata_source(repository, branch)
    return json.dumps([repository.casefold(), branch])
