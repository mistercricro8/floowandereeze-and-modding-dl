"""
Python utility functions for the application.
This module provides helper functions for subclass discovery and game path validation.
"""


def get_instances_of_subclasses(base_class):
    """
    Returns a list of instances of all subclasses of the given base_class,
    instantiated in alphabetical order of their class names.
    Only creates instances of classes with a parameterless constructor.

    Args:
        base_class: The base class to find subclasses of

    Returns:
        list: List of instances of all subclasses that can be instantiated
        without arguments
    """
    instances = []
    subclasses = base_class.__subclasses__()

    sorted_subclasses = sorted(subclasses, key=lambda cls: cls.__name__)

    for subclass in sorted_subclasses:
        try:
            instance = subclass()
            instances.append(instance)
        except TypeError:
            pass

        instances.extend(get_instances_of_subclasses(subclass))

    return instances


def is_valid_game_path(folder: str) -> tuple[bool, str | None]:
    """
    Validates if the given folder path contains the required Unity game files.

    Args:
        folder: The folder path to validate

    Returns:
        tuple[bool, str | None]: A tuple containing:
            - bool: True if the path is valid, False otherwise
            - str | None: Error message if invalid, None if valid
    """
    from util.game_discovery import normalize_game_path, resolve_game_root

    if not folder:
        return (
            False,
            "Select a Duel Links installation, LocalData, or player data "
            "folder containing dlpc_Data/data.unity3d.",
        )

    cleaned = str(folder).strip().strip("'\"")
    if normalize_game_path(cleaned):
        return (True, None)

    game_root = resolve_game_root(cleaned)
    if game_root is not None:
        local_data = game_root / "LocalData"
        has_player_account = False
        if local_data.is_dir():
            try:
                has_player_account = any(
                    p.is_dir() and p.name != "00000000" for p in local_data.iterdir()
                )
            except OSError:
                has_player_account = False

        if not has_player_account:
            return (
                False,
                f"Found Duel Links installation at '{game_root.name}', but no "
                "player account data was found in LocalData. Please launch "
                "Yu-Gi-Oh! Duel Links once through Steam to initialize account data.",
            )

    return (
        False,
        "Select a Duel Links installation, LocalData, or player data "
        "folder containing dlpc_Data/data.unity3d.",
    )
