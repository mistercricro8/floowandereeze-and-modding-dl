from typing import override

from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat

from database.models import CardModel
from database.objects import session
from services.unity_service import UnityService
from unity.unity_utils import bundle_exists, prepare_environment
from util.constants import APP_CONFIG
from util.enums import CardArtCoordinates
from util.image_utils import convert_image, crop_to_rect


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
                    break

            with open(f_path, "wb") as f:
                f.write(env.file.save(packer=APP_CONFIG.packer))

    def get_names(self) -> list[str]:
        return [card.name for card in session.query(CardModel).all()]
