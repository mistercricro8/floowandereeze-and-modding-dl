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
    from util.game_discovery import normalize_game_path

    if folder and normalize_game_path(folder):
        return (True, None)
    return (
        False,
        "Select a Duel Links installation, LocalData, or player data "
        "folder containing dlpc_Data/data.unity3d.",
    )
