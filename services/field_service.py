from typing import override

from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat

from services.unity_service import UnityService
from unity.unity_utils import get_configured_packer, prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import convert_image, crop_to_rect


class FieldService(UnityService):
    def __init__(self):
        super().__init__("fields")

    @override
    def replace_bundle(self) -> None:

        if not self.bundle or not self.image_path:
            return

        f_path = prepare_environment(False, self.bundle)
        env = unity_load(f_path)

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                img = convert_image(self.image_path)
                if self.crop_rect:
                    img = crop_to_rect(img, self.crop_rect)

                data.m_Width, data.m_Height = img.size

                data.set_image(
                    img=img,
                    target_format=TextureFormat.RGBA32,
                    mipmap_count=APP_CONFIG.mipmap_count,
                )

                data.save()
                break

        target_file = getattr(env, "file", None)
        if target_file is None or not hasattr(target_file, "save"):
            raise ValueError(
                f"Game file {self.bundle!r} could not be saved as a Unity bundle."
            )
        saved_bytes = target_file.save(packer=get_configured_packer(APP_CONFIG))
        with open(f_path, "wb") as f:
            f.write(saved_bytes)
