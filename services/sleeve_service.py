from typing import override

from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat

from services.unity_service import UnityService
from unity.unity_utils import get_configured_packer, prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import (
    add_sleeve_border,
    add_sleeve_border_with_fade,
    convert_image,
    crop_to_rect,
)


class SleeveService(UnityService):
    def __init__(self):
        super().__init__("sleeves")
        self.border: bool | None = None
        self.border_color: str | None = "#FFFFFF"
        self.border_fade: bool | None = None

    @override
    def replace_bundle(self) -> None:

        if not self.bundle or not self.image_path:
            return

        f_path = prepare_environment(False, self.bundle)
        env = unity_load(f_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                raw = convert_image(self.image_path)
                if self.crop_rect:
                    raw = crop_to_rect(raw, self.crop_rect)

                if self.border:
                    if self.border_fade:
                        img = add_sleeve_border_with_fade(raw, self.border_color)
                    else:
                        img = add_sleeve_border(raw, self.border_color)
                else:
                    img = raw

                data.m_Width, data.m_Height = img.size

                data.set_image(
                    img=img,
                    target_format=TextureFormat.RGBA32,
                    mipmap_count=APP_CONFIG.mipmap_count,
                )

                data.save()
                break

            type_tree = obj.read_typetree()
            if (
                obj.type.name == "Material"
                and "_LightPower" in type_tree["m_SavedProperties"]["m_Floats"][10][0]
            ):
                type_tree["m_SavedProperties"]["m_Floats"][10] = (
                    "_LightPower",
                    0.0,
                )
                obj.save_typetree(type_tree)

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=get_configured_packer(APP_CONFIG)))
