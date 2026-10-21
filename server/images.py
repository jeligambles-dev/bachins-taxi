"""Turn whatever the owner's phone produced into a clean, web-sized photo."""
import io
import warnings

import pillow_heif
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

pillow_heif.register_heif_opener()      # once, at import (HEIC/HEIF from iPhones)
Image.MAX_IMAGE_PIXELS = 60_000_000

MAX_EDGE = 2000
JPEG_QUALITY = 82
MESSAGE = "That file isn't a photo we can use. Try a JPG or PNG."


class ImageError(ValueError):
    pass


_SRGB = None


def _to_srgb(img):
    """Convert from the embedded ICC profile to sRGB so wide-gamut (Display-P3) photos
    keep their colour once the profile is dropped. Any failure: carry on without it."""
    global _SRGB
    icc = img.info.get("icc_profile")
    if not icc or img.mode not in ("RGB", "RGBA"):
        return img
    try:
        if _SRGB is None:
            _SRGB = ImageCms.createProfile("sRGB")
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        out = ImageCms.profileToProfile(img, src, _SRGB, outputMode=img.mode)
        return out if out is not None else img
    except Exception:
        return img


def _opaque(img):
    return img.mode == "RGBA" and img.getchannel("A").getextrema()[0] == 255


def _has_alpha(img):
    return img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info) or "transparency" in img.info


def process_upload(raw: bytes) -> tuple[bytes, str, int, int]:
    """Returns (data, mime, width, height). Upright, long edge <= 2000, no metadata."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(raw))
            if img.format == "JPEG":
                img.draft("RGB", (2000, 2000))   # decode at reduced size: less memory
            img.load()                      # full decode: truncated/corrupt files fail here
            img = ImageOps.exif_transpose(img)
            alpha = _has_alpha(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if alpha else "RGB")
            img = _to_srgb(img)
            if alpha and _opaque(img):
                alpha = False
            img = img.convert("RGBA" if alpha else "RGB")
            img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
            img.info.clear()                # nothing (EXIF, ICC, text) is carried over
            out = io.BytesIO()
            if alpha:
                img.save(out, "PNG", optimize=True)
                mime = "image/png"
            else:
                img.save(out, "JPEG", quality=JPEG_QUALITY, progressive=True, optimize=True)
                mime = "image/jpeg"
            return out.getvalue(), mime, img.width, img.height
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, MemoryError,
            Image.DecompressionBombError, Image.DecompressionBombWarning,
            ZeroDivisionError, TypeError, KeyError, IndexError, EOFError) as e:
        raise ImageError(MESSAGE) from e
