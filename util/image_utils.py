from re import sub
from unicodedata import normalize

import numpy as np
from PIL import Image, ImageOps


def add_sleeve_border(image: Image.Image, color: str) -> Image.Image:
    """Adds solid color borders to given image"""

    return ImageOps.expand(
        image, border=(int(image.width * 0.06), int(image.height * 0.05)), fill=color
    )


def add_sleeve_border_with_fade(image: Image.Image, color: str) -> Image.Image:
    """Adds borders with fade-in effect that blends with the image content"""

    border_width = int(image.width * 0.05)
    border_height = int(image.height * 0.04)

    new_width = image.width + 2 * border_width
    new_height = image.height + 2 * border_height

    original_color = color
    if color.startswith("#"):
        color = color[1:]
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    result = ImageOps.expand(
        image, border=(border_width, border_height), fill=original_color
    )

    result_array = np.array(result).astype(np.float32)
    original_array = np.array(image).astype(np.float32)

    fade_distance = min(border_width, border_height) * 2.0
    for y in range(new_height):
        for x in range(new_width):
            orig_x = x - border_width
            orig_y = y - border_height

            if 0 <= orig_x < image.width and 0 <= orig_y < image.height:
                dist_to_border_left = orig_x
                dist_to_border_right = image.width - 1 - orig_x
                dist_to_border_top = orig_y
                dist_to_border_bottom = image.height - 1 - orig_y

                min_border_dist = min(
                    dist_to_border_left,
                    dist_to_border_right,
                    dist_to_border_top,
                    dist_to_border_bottom,
                )

                if min_border_dist < fade_distance:
                    base_fade_factor = min_border_dist / fade_distance

                    smooth1 = (
                        base_fade_factor
                        * base_fade_factor
                        * (3.0 - 2.0 * base_fade_factor)
                    )
                    smooth2 = smooth1 * smooth1 * (3.0 - 2.0 * smooth1)

                    fade_factor = 1.0 - np.exp(-4.0 * smooth2)

                    original_pixel = original_array[orig_y, orig_x]
                    border_color = np.array([r, g, b, 255], dtype=np.float32)

                    blended_pixel = (
                        1 - fade_factor
                    ) * border_color + fade_factor * original_pixel
                    result_array[y, x] = blended_pixel
                else:
                    result_array[y, x] = original_array[orig_y, orig_x]
            else:
                result_array[y, x] = [r, g, b, 255]

    result = Image.fromarray(result_array.astype(np.uint8), "RGBA")

    return result


def slugify(value, allow_unicode=False) -> str:
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """

    value = str(value)
    if allow_unicode:
        value = normalize("NFKC", value)
    else:
        value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = sub(r"[^\w\s-]", "", value.lower())
    return sub(r"[-\s]+", "-", value).strip("-_")


def convert_image(path: str) -> Image.Image:
    """Converts the user given image to its proper size using lanczos resampling"""

    return Image.open(path).convert("RGBA")


def content_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    """Return visible alpha bounds, using the full canvas for an empty image."""
    return image.convert("RGBA").getchannel("A").getbbox() or (
        0,
        0,
        image.width,
        image.height,
    )


def crop_to_rect(
    img: Image.Image,
    crop_rect: tuple[float, float, float, float],
) -> Image.Image:
    """
    Crop *img* to the region defined by *crop_rect*.

    *crop_rect* is ``(left, top, right, bottom)`` where each value is a
    fraction in the range 0..1 relative to the image dimensions.
    """
    w, h = img.size
    left = int(crop_rect[0] * w)
    top = int(crop_rect[1] * h)
    right = int(crop_rect[2] * w)
    bottom = int(crop_rect[3] * h)
    left, right = max(0, left), min(w, right)
    top, bottom = max(0, top), min(h, bottom)
    if right <= left or bottom <= top:
        return img
    return img.crop((left, top, right, bottom))
