from pathlib import Path
from typing import override

from PIL import Image
from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat

from database.models import CardModel
from database.objects import session
from services import unity_service
from services.unity_service import UnityService
from unity.unity_utils import (
    bundle_exists,
    get_configured_packer,
    prepare_environment,
)
from util.constants import APP_CONFIG
from util.enums import CardArtCoordinates
from util.image_utils import convert_image, crop_to_rect, slugify
from util.paths import get_backups_dir


class CardService(UnityService):
    def __init__(self):
        super().__init__("cards")
        self.unity_file: bool = False

    @override
    def replace_bundle(self) -> None:
        if not self.bundle or not self.image_path:
            return

        card: CardModel = (
            session.query(CardModel)
            .filter(CardModel.large_bundle == self.bundle)
            .first()
        )
        if card is None:
            card = (
                session.query(CardModel)
                .filter(CardModel.medium_bundle == self.bundle)
                .first()
            )
        if card is None:
            raise ValueError(f"No card found for bundle {self.bundle!r}")

        self.unity_file = card.unity_file

        for bundle, size in zip(
            [card.small_bundle, card.medium_bundle, card.large_bundle],
            [
                CardArtCoordinates.SMALL,
                CardArtCoordinates.MEDIUM,
                CardArtCoordinates.LARGE,
            ],
            strict=True,
        ):
            if not bundle or not bundle_exists(bundle, self.unity_file):
                continue
            f_path = prepare_environment(self.unity_file, bundle)
            env = unity_load(f_path)

            found_texture = False
            for obj in env.objects:
                if obj.type.name == "Texture2D":
                    data = obj.read()

                    original_img = data.image.copy()

                    new_img = convert_image(self.image_path)
                    if self.crop_rect:
                        new_img = crop_to_rect(new_img, self.crop_rect)
                    coord_width = size.value[2] - size.value[0]
                    coord_height = size.value[3] - size.value[1]
                    new_img = new_img.resize((coord_width, coord_height))

                    original_img.paste(new_img, (size.value[0], size.value[1]))

                    data.set_image(
                        img=original_img,
                        target_format=TextureFormat.RGBA32,
                        mipmap_count=APP_CONFIG.mipmap_count,
                    )

                    data.save()
                    found_texture = True
                    break

            if not found_texture:
                continue

            target_file = getattr(env, "file", None)
            if target_file is None or not hasattr(target_file, "save"):
                continue

            saved_bytes = target_file.save(packer=get_configured_packer(APP_CONFIG))
            with open(f_path, "wb") as f:
                f.write(saved_bytes)

    def _get_crop_coordinates_for_size(
        self, size: tuple[int, int]
    ) -> CardArtCoordinates | None:
        if size == (512, 512):
            return CardArtCoordinates.LARGE
        if size == (256, 256):
            return CardArtCoordinates.MEDIUM
        if size == (128, 128):
            return CardArtCoordinates.SMALL
        return None

    def _get_crop_coordinates(self, bundle: str) -> CardArtCoordinates | None:
        if not bundle:
            return None
        try:
            card = (
                session.query(CardModel)
                .filter(
                    (CardModel.large_bundle == bundle)
                    | (CardModel.medium_bundle == bundle)
                    | (CardModel.small_bundle == bundle)
                )
                .first()
            )
            if not card:
                return None
            if bundle == card.large_bundle:
                return CardArtCoordinates.LARGE
            if bundle == card.small_bundle:
                return CardArtCoordinates.SMALL
            return CardArtCoordinates.MEDIUM
        except Exception:
            return None

    @override
    def _process_extracted_image(self, image: Image.Image) -> Image.Image:
        """Extract card artwork cropped to inner asset coordinates."""
        coords = self._get_crop_coordinates_for_size(image.size)
        if coords is not None:
            return image.crop(coords.value)
        return image

    @override
    def restore_asset(self, backup_name=None) -> bool:
        """Restore original card artwork, auto-migrating full-card legacy backups if needed."""
        backup_bundle = backup_name or self.bundle
        backup_path = (
            get_backups_dir() / self.subfolder / f"{slugify(backup_bundle)}.png"
        )
        if not backup_path.is_file():
            return False

        with Image.open(backup_path) as saved_img:
            saved_size = saved_img.size
            coords = self._get_crop_coordinates_for_size(saved_size)
            if coords is not None:
                inner_asset = saved_img.crop(coords.value)
                inner_asset.save(str(backup_path))

        current_image = self.image_path
        current_crop = self.crop_rect
        self.image_path = str(backup_path)
        self.crop_rect = None
        self.replace_bundle()
        self.image_path = current_image
        self.crop_rect = current_crop
        return True

    def get_names(self) -> list[str]:
        return [card.name for card in session.query(CardModel).all()]
