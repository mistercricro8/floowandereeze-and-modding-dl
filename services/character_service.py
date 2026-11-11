import logging
import struct
from pathlib import Path
from typing import override

from PIL import Image, ImageOps
from UnityPy import load as unity_load
from UnityPy.enums import TextureFormat

from database.models import CharacterAssetLayout, CharacterModel
from database.objects import DBsession, session
from services.unity_service import UnityService
from unity.unity_utils import prepare_environment
from util.constants import APP_CONFIG
from util.image_utils import content_bounds, convert_image, crop_to_rect, slugify

logger = logging.getLogger(__name__)


class CharacterService(UnityService):
    def __init__(self):
        super().__init__("characters")
        self.preserve_transparent_padding = True

    def original_content_bounds(
        self, bundle: str, image: Image.Image
    ) -> tuple[int, int, int, int]:
        """Persist each bundle's initial layout before any replacement is written."""
        with DBsession() as layout_session:
            layout = layout_session.get(CharacterAssetLayout, bundle)
            if layout and (layout.width, layout.height) == image.size:
                return tuple(layout.bounds)

            bounds = content_bounds(image)
            backup = Path("backups") / self.subfolder / f"{slugify(bundle)}.png"
            if backup.is_file():
                with Image.open(backup) as original:
                    if original.size == image.size:
                        bounds = content_bounds(original)
            if layout is None:
                layout = CharacterAssetLayout(bundle=bundle)
                layout_session.add(layout)
            layout.width, layout.height = image.size
            layout.bounds = list(bounds)
            layout_session.commit()
            return bounds

    def replacement_content_bounds(
        self, bundle: str, image: Image.Image
    ) -> tuple[int, int, int, int]:
        """Choose the original content area or full canvas for replacement."""
        bounds = self.original_content_bounds(bundle, image)
        if self.preserve_transparent_padding:
            return bounds
        return (0, 0, image.width, image.height)

    @override
    def replace_bundle(self) -> None:
        if not self.bundle or not self.image_path:
            return

        f_path = prepare_environment(False, self.bundle)
        env = unity_load(f_path)

        new_img = convert_image(self.image_path)
        if self.crop_rect:
            new_img = crop_to_rect(new_img, self.crop_rect)

        orig_size = None

        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()

                orig_size = (data.m_Width, data.m_Height)
                bounds = self.replacement_content_bounds(self.bundle, data.image)
                if self.crop_rect:
                    left, top, right, bottom = bounds
                    content = ImageOps.fit(
                        new_img,
                        (right - left, bottom - top),
                        method=Image.Resampling.LANCZOS,
                    )
                    new_img = Image.new("RGBA", orig_size, (0, 0, 0, 0))
                    new_img.paste(content, (left, top))
                elif new_img.size != orig_size:
                    new_img = new_img.resize(orig_size, Image.Resampling.LANCZOS)

                data.set_image(
                    img=new_img,
                    target_format=TextureFormat.RGBA32,
                    mipmap_count=APP_CONFIG.mipmap_count,
                )
                data.save()
                break

        if orig_size:
            w, h = orig_size
            for obj in env.objects:
                if obj.type.name == "Sprite":
                    try:
                        tt = obj.read_typetree()

                        if "m_Rect" in tt:
                            tt["m_Rect"] = {
                                "x": 0.0,
                                "y": 0.0,
                                "width": float(w),
                                "height": float(h),
                            }

                        if "m_IsPolygon" in tt:
                            tt["m_IsPolygon"] = 0

                        if "m_PhysicsShape" in tt:
                            tt["m_PhysicsShape"] = []

                        if "m_RD" in tt:
                            rd = tt["m_RD"]

                            if "textureRect" in rd:
                                rd["textureRect"] = {
                                    "x": 0.0,
                                    "y": 0.0,
                                    "width": float(w),
                                    "height": float(h),
                                }

                            if "textureRectOffset" in rd:
                                rd["textureRectOffset"] = {"x": 0.0, "y": 0.0}

                            if "m_VertexData" in rd and "m_IndexBuffer" in rd:
                                ppu = float(tt.get("m_PixelsToUnits", 100.0))
                                half_w = (w / 2.0) / ppu
                                half_h = (h / 2.0) / ppu

                                pos_data = struct.pack(
                                    "<12f",
                                    -half_w,
                                    -half_h,
                                    0.0,
                                    half_w,
                                    -half_h,
                                    0.0,
                                    half_w,
                                    half_h,
                                    0.0,
                                    -half_w,
                                    half_h,
                                    0.0,
                                )
                                uv_data = struct.pack(
                                    "<8f",
                                    0.0,
                                    0.0,
                                    1.0,
                                    0.0,
                                    1.0,
                                    1.0,
                                    0.0,
                                    1.0,
                                )
                                vd = rd["m_VertexData"]
                                vd["m_VertexCount"] = 4
                                vd["m_DataSize"] = pos_data + uv_data

                                rd["m_IndexBuffer"] = list(
                                    struct.pack("<6H", 0, 1, 2, 0, 2, 3)
                                )

                                if "m_SubMeshes" in rd and rd["m_SubMeshes"]:
                                    sm = rd["m_SubMeshes"][0]
                                    sm["firstByte"] = 0
                                    sm["indexCount"] = 6
                                    sm["firstVertex"] = 0
                                    sm["vertexCount"] = 4
                                    if "localAABB" in sm:
                                        sm["localAABB"] = {
                                            "m_Center": {"x": 0.0, "y": 0.0, "z": 0.0},
                                            "m_Extent": {
                                                "x": half_w,
                                                "y": half_h,
                                                "z": 0.0,
                                            },
                                        }

                        obj.save_typetree(tt)
                    except Exception as e:
                        logger.warning("Error processing sprite: %s", e)
                        continue

        with open(f_path, "wb") as f:
            f.write(env.file.save(packer=APP_CONFIG.packer))

    def get_series_list(self) -> list[str]:
        """Get unique list of character series for filtering."""
        series_list = session.query(CharacterModel.series).distinct().all()
        return [series[0] for series in series_list if series[0]]
