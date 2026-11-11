"""Unity Service Module.

This module provides an abstract base class for Unity asset bundle
manipulation. It includes common functionality for extracting textures,
creating backups, and restoring assets from Unity bundles used in
Yu-Gi-Oh! Duel Links.
"""

from abc import ABC, abstractmethod
from os import makedirs
from os.path import isfile, join
from shutil import copyfile

from UnityPy import load as unity_load

from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import slugify


class UnityService(ABC):
    """
    UnityService class provides methods for fetching and replacing images
    from Unity asset bundles.
    """

    def __init__(self, subfolder: str) -> None:
        self.bundle = None
        self.subfolder: str = subfolder
        self.image_path: str | None = None
        self.crop_rect: tuple[float, float, float, float] | None = None

    @abstractmethod
    def replace_bundle(self) -> None:
        """
        Replaces a Unity asset bundle with a new image.

        :return: None
        :raises NotImplementedError: This method is not implemented in the base class.
        """

    def extract_texture(self, name: str, miss=False) -> None:
        """
        Extracts a texture from a Unity bundle.

        :param name: The name of the texture to extract.
        :param miss: A boolean value indicating if the extraction failed to
        find the bundle in the LocalData folder.
        :return: None
        """
        self.extract_asset_texture(name, "images", miss=miss)

    def create_backup(self, name: str, miss=False) -> None:
        """
        Creates a backup of a Unity asset bundle.

        :param name: The name of the texture to extract.
        :param miss: A boolean value indicating if the extraction failed to
        find the bundle in the LocalData folder.
        :return: None

        """
        self.extract_asset_texture(name, "backups", miss=miss)

    def extract_asset_texture(self, name: str, folder: str, miss=False) -> None:
        """
        Extracts a texture from a Unity bundle.

        :param name: The name of the texture to extract.
        :param folder: The destination root for the extracted texture.
        :param miss: A boolean value indicating if the extraction failed to
        find the bundle.
        :return: None
        """
        try:
            env = unity_load(prepare_environment(miss, self.bundle))
        except FileNotFoundError:
            if miss:
                raise
            return self.extract_asset_texture(name, folder, miss=True)

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                makedirs(join(folder, self.subfolder), exist_ok=True)
                dest = join(folder, self.subfolder, slugify(name) + ".png")

                data.image.save(dest)
                return

        if not miss:
            return self.extract_asset_texture(name, folder, miss=True)
        raise ValueError(f"No Texture2D found in bundle {self.bundle!r}")

    def restore_asset(self, backup_name=None) -> bool:
        """
        Restores a backup of a Unity asset bundle.

        :param backup_name: The name of the backup to restore.
        :return: A boolean value indicating if the backup was restored successfully.
        """

        backup_path = join(
            "backups", self.subfolder, f"{backup_name or self.bundle}.png"
        )
        if isfile(backup_path):
            current_image = self.image_path
            current_crop = self.crop_rect
            self.image_path = backup_path
            self.crop_rect = None
            self.replace_bundle()
            self.image_path = current_image
            self.crop_rect = current_crop
            return True
        return False

    def copy_bundle(self) -> None:
        """
        Copies the current bundle to the bundles folder.
        """
        self.create_bundle_copy("bundles")

    def create_bundle_copy(self, folder="bundles") -> None:
        """
        Creates a copy of the current bundle in the specified folder.

        :param folder: The folder to create the copy in.
        :return: None
        """

        makedirs(join(folder, self.subfolder), exist_ok=True)

        copyfile(
            join(APP_CONFIG.game_path, self.bundle[:2], self.bundle),
            join(folder, self.subfolder, self.bundle),
        )
