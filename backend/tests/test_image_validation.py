from io import BytesIO

import pytest
from PIL import Image

from dvizh_backend.services.media_errors import InvalidImageError, MediaTooLargeError
from dvizh_backend.services.media_service import normalize_image


@pytest.mark.parametrize("format_name", ["PNG", "JPEG", "WEBP"])
def test_supported_images_are_normalized(format_name: str) -> None:
    stream = BytesIO()
    Image.new("RGB", (20, 30)).save(stream, format=format_name)
    result, width, height = normalize_image(stream.getvalue(), max_pixels=1000, max_bytes=10000)
    assert (width, height) == (20, 30)
    with Image.open(BytesIO(result)) as output:
        assert output.format == "WEBP"


def test_exif_orientation_is_applied_and_metadata_is_removed() -> None:
    stream = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Private image metadata"
    Image.new("RGB", (10, 20)).save(stream, format="JPEG", exif=exif)
    result, width, height = normalize_image(stream.getvalue(), max_pixels=1000, max_bytes=10000)
    assert (width, height) == (20, 10)
    with Image.open(BytesIO(result)) as output:
        assert not output.getexif()


def test_pixel_limit_and_unsupported_content_are_rejected() -> None:
    stream = BytesIO()
    Image.new("RGB", (20, 30)).save(stream, format="PNG")
    with pytest.raises(MediaTooLargeError):
        normalize_image(stream.getvalue(), max_pixels=599, max_bytes=10000)
    with pytest.raises(InvalidImageError):
        normalize_image(b"<svg></svg>", max_pixels=1000, max_bytes=10000)


def test_palette_transparency_is_preserved() -> None:
    stream = BytesIO()
    image = Image.new("P", (5, 5))
    image.save(stream, format="PNG", transparency=0)
    result, _, _ = normalize_image(stream.getvalue(), max_pixels=1000, max_bytes=10000)
    with Image.open(BytesIO(result)) as output:
        assert output.convert("RGBA").getpixel((0, 0))[3] == 0
