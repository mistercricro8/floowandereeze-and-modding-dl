"""Update the database from local working-tree exports or a GitHub repository."""

from pathlib import Path

import pandas as pd
import requests
from pandas import DataFrame, read_parquet
from pandas.errors import EmptyDataError
from requests.exceptions import HTTPError, RequestException, Timeout

from database.models import (
    AppConfig,
    CardModel,
    CharacterModel,
    FieldModel,
    SleeveModel,
)
from database.objects import DBsession
from util.metadata_source import (
    DEFAULT_METADATA_BRANCH,
    DEFAULT_METADATA_REPOSITORY,
    is_local_metadata_source,
    normalize_metadata_source,
)


def _configured_source() -> tuple[str, str]:
    """Read saved settings with a separate session for each update worker."""
    with DBsession() as local_session:
        config = local_session.query(AppConfig).first()
        return (
            getattr(config, "metadata_repository", None) or DEFAULT_METADATA_REPOSITORY,
            getattr(config, "metadata_branch", None) or DEFAULT_METADATA_BRANCH,
        )


def _local_metadata_file(
    path: str,
    owner: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
) -> Path | None:
    """Read working-tree files directly unless a GitHub source was
    explicitly supplied."""
    if any(value is not None for value in (owner, repo, branch)):
        return None
    repository, selected_branch = _configured_source()
    if not is_local_metadata_source(repository):
        return None
    repository, _ = normalize_metadata_source(repository, selected_branch)
    root = Path(repository)
    file = (root / path).resolve()
    if not file.is_relative_to(root):
        raise ValueError("Metadata file must be inside the local repository.")
    return file


def _github_source(
    owner: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Resolve saved GitHub settings or explicit overrides."""
    repository, selected_branch = _configured_source()
    if is_local_metadata_source(repository):
        repository, selected_branch = (
            DEFAULT_METADATA_REPOSITORY,
            DEFAULT_METADATA_BRANCH,
        )
    repository, selected_branch = normalize_metadata_source(repository, selected_branch)
    selected_owner, selected_repo = repository.split("/")
    owner = selected_owner if owner is None else owner
    repo = selected_repo if repo is None else repo
    _, branch = normalize_metadata_source(
        f"{owner}/{repo}", selected_branch if branch is None else branch
    )
    return owner, repo, {"ref": branch} if branch else {}


def get_github_raw_file(
    path: str,
    owner: str | None = None,
    repo: str | None = None,
    branch: str | None = None,
) -> str:
    """
    Read a text file from the saved local checkout or GitHub source.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.
    :param branch: Optional branch/ref; blank follows the repository default.
        Omitted source arguments use saved Configuration settings.

    :return: The raw content of the file.
    :raises HTTPError: If the GitHub API request fails
    :raises Timeout: If the request times out
    :raises RequestException: For other request-related errors
    :raises ValueError: If the response doesn't contain a download URL
    """
    local_file = _local_metadata_file(path, owner, repo, branch)
    if local_file is not None:
        return local_file.read_text(encoding="utf-8")
    owner, repo, params = _github_source(owner, repo, branch)
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        file_data = response.json()

        if "download_url" not in file_data:
            raise ValueError("No download URL found in the response.")

        raw_url = file_data["download_url"]

        raw_response = requests.get(raw_url, headers=headers, timeout=10)
        raw_response.raise_for_status()

        return raw_response.text

    except Timeout as e:
        raise Timeout(f"Request timed out: {str(e)}") from e
    except HTTPError as e:
        raise HTTPError(f"GitHub API request failed: {str(e)}") from e
    except RequestException as e:
        raise RequestException(f"Request failed: {str(e)}") from e


def get_github_parquet_file(path: str, owner=None, repo=None, branch=None) -> DataFrame:
    """
    Read a Parquet file from the saved local checkout or GitHub source.

    :param owner: GitHub username or organization name that owns the repository.
    :param repo: Repository name.
    :param path: Path to the file in the repository.
    :param branch: Optional branch/ref; blank follows the repository default.
        Omitted source arguments use saved Configuration settings.

    :return: The raw content of the file as a pandas DataFrame.
    :raises HTTPError: If the GitHub API request fails
    :raises Timeout: If the request times out
    :raises RequestException: For other request-related errors
    :raises ValueError: If the response doesn't contain a download URL
    :raises EmptyDataError: If the parquet file is empty or invalid
    """
    local_file = _local_metadata_file(path, owner, repo, branch)
    if local_file is not None:
        return read_parquet(local_file)
    owner, repo, params = _github_source(owner, repo, branch)
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    headers = {"Accept": "application/vnd.github.v3+json"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        file_data = response.json()

        if "download_url" not in file_data:
            raise ValueError("No download URL found in the response.")

        raw_url = file_data["download_url"]

        return read_parquet(raw_url)

    except Timeout as e:
        raise Timeout(f"Request timed out: {str(e)}") from e
    except HTTPError as e:
        raise HTTPError(f"GitHub API request failed: {str(e)}") from e
    except RequestException as e:
        raise RequestException(f"Request failed: {str(e)}") from e
    except EmptyDataError as e:
        raise EmptyDataError(f"Failed to read parquet file: {str(e)}") from e


def asset_label(row):
    """Accept both new named metadata and older Parquet exports."""
    value = row.get("name")
    return str(value).strip() or None if pd.notna(value) else None


def update_sleeves() -> None:
    """
    Updates the sleeves in the database by completely replacing all existing sleeves
    with the latest data from the remote source.

    This function:
    1. Fetches the latest sleeves data from the remote parquet file
    2. Deletes all existing sleeves from the database
    3. Adds all sleeves from the remote data
    """
    local_session = DBsession()
    try:
        remote_sleeves = get_github_parquet_file("data/sleeves.parquet")
        states = {
            asset.medium_bundle: (asset.favorite, asset.has_backup)
            for asset in local_session.query(SleeveModel).all()
        }
        local_session.query(SleeveModel).delete(synchronize_session=False)
        local_session.add_all(
            [
                SleeveModel(
                    name=asset_label(sleeve),
                    favorite=states.get(sleeve["medium"], (False, False))[0],
                    has_backup=states.get(sleeve["medium"], (False, False))[1],
                    medium_bundle=sleeve["medium"],
                    small_bundle=sleeve["small"],
                )
                for _, sleeve in remote_sleeves.iterrows()
                if not pd.isnull(sleeve["medium"]) and not pd.isnull(sleeve["small"])
            ]
        )
        local_session.commit()
    except Exception:
        local_session.rollback()
        raise
    finally:
        local_session.close()


def update_cards() -> None:
    """
    Updates the cards in the database by completely replacing all existing cards
    with the latest data from the remote source.

    This function:
    1. Fetches the latest cards data from the remote parquet file
    2. Deletes all existing cards from the database
    3. Adds all cards from the remote data with their bundle, name,
    description, and data_index
    """
    local_session = DBsession()
    try:
        remote_cards = get_github_parquet_file("data/cards.parquet")
        local_session.query(CardModel).delete()
        local_session.add_all(
            [
                CardModel(
                    name=card["name"],
                    large_bundle=card["large"],
                    medium_bundle=card["medium"],
                    small_bundle=card["small"],
                )
                for _, card in remote_cards.iterrows()
            ]
        )
        local_session.commit()
    except Exception:
        local_session.rollback()
        raise
    finally:
        local_session.close()


def update_fields() -> None:
    """
    Updates the fields in the database by completely replacing all existing fields
    with the latest data from the remote source.

    This function:
    1. Fetches the latest fields data from the remote parquet file
    2. Deletes all existing fields from the database
    3. Adds all fields from the remote data with their bundle, flipped,
    and bottom properties
    """
    local_session = DBsession()
    try:
        remote_fields = get_github_parquet_file("data/fields.parquet")
        states = {
            asset.medium_bundle: (asset.favorite, asset.has_backup)
            for asset in local_session.query(FieldModel).all()
        }
        local_session.query(FieldModel).delete(synchronize_session=False)
        local_session.add_all(
            [
                FieldModel(
                    name=asset_label(field),
                    favorite=states.get(field["medium"], (False, False))[0],
                    has_backup=states.get(field["medium"], (False, False))[1],
                    medium_bundle=field["medium"],
                    small_bundle=field["small"],
                )
                for _, field in remote_fields.iterrows()
                if not pd.isnull(field["medium"]) and not pd.isnull(field["small"])
            ]
        )
        local_session.commit()
    except Exception:
        local_session.rollback()
        raise
    finally:
        local_session.close()


def update_characters() -> None:
    """
    Updates the characters in the database by completely replacing all existing
    characters with the latest data from the remote source.

    This function:
    1. Fetches the latest characters data from the remote parquet file
    2. Deletes all existing characters from the database
    3. Adds all characters from the remote data with their name, konami_id,
    series, and asset bundles
    """
    local_session = DBsession()
    try:
        remote_characters = get_github_parquet_file("data/characters.parquet")
        local_session.query(CharacterModel).delete()

        characters_to_add = []
        for _, character_row in remote_characters.iterrows():
            if pd.isnull(character_row["konami_id"]):
                continue

            character = CharacterModel(
                name=asset_label(character_row),
                konami_id=character_row["konami_id"],
                series=(
                    character_row["series"]
                    if not pd.isnull(character_row["series"])
                    else "unknown"
                ),
            )

            from database.models import CharacterAssets

            for attr_name in CharacterAssets._ENUM_TO_ATTR.values():
                if attr_name in character_row and not pd.isnull(
                    character_row[attr_name]
                ):
                    setattr(character, attr_name, character_row[attr_name])

            characters_to_add.append(character)

        local_session.add_all(characters_to_add)
        local_session.commit()
    except Exception:
        local_session.rollback()
        raise
    finally:
        local_session.close()
