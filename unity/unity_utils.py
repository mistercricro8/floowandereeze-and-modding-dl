from os.path import join

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6 import QtGui
from sqlalchemy.orm import Mapped
from UnityPy import load as unity_load

from database.models import FieldModel
from util.constants import APP_CONFIG, FILE
from util.enums import FieldCoordinates


def prepare_environment(miss: bool, bundle: str) -> str:
    """returns the UnityPy environment path related to the bundle and game path given"""

    return (
        join(
            APP_CONFIG.game_path[:-18],
            "dlpc_Data",
            "StreamingAssets",
            "AssetBundle",
            bundle[:2],
            bundle,
        )
        if miss
        else join(APP_CONFIG.game_path, bundle[:2], bundle)
    )


def fetch_bundle_thumb(
    bundle: str | Mapped[str],
    ratio: tuple[int, int] | None,
    unity_file: bool = False,
    crop_coordinates: tuple[int, int, int, int] | None = None,
) -> QtGui.QIcon | None:
    """
    Fetches a thumbnail image from a Unity3D bundle.

    This function locates a texture object within a Unity3D bundle and then resizes it
    to the specified dimensions before converting it to RGB format.

    :param bundle: The bundle to fetch the thumbnail from.
    :type bundle: str | Mapped[str]
    :param ratio: The dimensions to resize the image to.
    :type ratio: tuple[int, int] | None
    :param unity_file: Whether to use the Unity3D file.
    :type unity_file: bool, optional
    :param crop_coordinates: The coordinates to crop the image (top_left_x,
    top_left_y, bottom_right_x, bottom_right_y).
    :type crop_coordinates: tuple[int, int, int, int] | None, optional
    :returns: A QIcon object representing the thumbnail image.
    :rtype: QtGui.QIcon | None
    """

    env = unity_load(prepare_environment(unity_file, bundle))

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            data = obj.read()

            img = data.image

            if crop_coordinates:
                img = img.crop(crop_coordinates)

            if ratio:
                img = img.resize(ratio)

            img.name = FILE["IMAGE_NAME"]

            icon = QtGui.QIcon()
            icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

            return icon


def fetch_field_thumb(field: FieldModel) -> QtGui.QIcon | None:
    """
    Fetches a thumbnail image from a Unity3D field.

    This function locates a texture object within a Unity3D field and then resizes it
    to the specified dimensions before converting it to RGB format.

    :param field: The field to fetch the thumbnail from.
    :type field: FieldModel
    :returns: A QIcon object representing the thumbnail image.
    :rtype: QtGui.QIcon | None
    """

    env = unity_load(prepare_environment(False, field.bundle))

    for obj in env.objects:
        if obj.type.name == "Texture2D":
            data = obj.read()

            if "01_BaseColor_near" in data.m_Name:
                img: Image.Image = data.image

                if not field.bottom:
                    if field.flipped:
                        img_field = img.crop(FieldCoordinates.FLIPPED.value).rotate(180)
                    else:
                        img_field = img.crop(FieldCoordinates.TOP.value)
                else:
                    if field.flipped:
                        img_field = img.crop(
                            FieldCoordinates.BOTTOM_FLIPPED.value
                        ).rotate(180)
                    else:
                        img_field = img.crop(FieldCoordinates.BOTTOM.value)

                img_field.thumbnail((900, img_field.size[1]), Image.Resampling.LANCZOS)
                img = img_field

                img.name = FILE["IMAGE_NAME"]

                icon = QtGui.QIcon()
                icon.addPixmap(QtGui.QPixmap(ImageQt(img)))

                return icon
