import io

import pytest
from PIL import Image

from server.images import ImageError, process_upload


def jpeg(size=(400, 200), exif=None, color=(180, 40, 40)):
    buf = io.BytesIO()
    im = Image.new("RGB", size, color)
    kw = {"exif": exif} if exif is not None else {}
    im.save(buf, "JPEG", **kw)
    return buf.getvalue()


def test_upload_portrait_exif_rotated():
    ex = Image.Exif()
    ex[0x0112] = 6
    data, mime, w, h = process_upload(jpeg((400, 200), ex))
    assert mime == "image/jpeg" and w < h and (w, h) == (200, 400)
    assert Image.open(io.BytesIO(data)).size == (w, h)


def test_upload_strips_gps():
    ex = Image.Exif()
    ex[0x0112] = 1
    ex[0x8825] = {1: "N", 2: (53.0, 20.0, 0.0), 3: "W", 4: (6.0, 15.0, 0.0)}
    src = jpeg((400, 200), ex)
    assert 0x8825 in Image.open(io.BytesIO(src)).getexif()      # the source really has GPS
    data, *_ = process_upload(src)
    out = Image.open(io.BytesIO(data))
    assert len(out.getexif()) == 0
    assert "exif" not in out.info and b"Exif" not in data and b"GPS" not in data


def test_upload_heic():
    import pillow_heif
    buf = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (64, 48), (10, 120, 200))).save(buf, format="HEIF")
    data, mime, w, h = process_upload(buf.getvalue())
    assert mime == "image/jpeg" and (w, h) == (64, 48)
    assert Image.open(io.BytesIO(data)).format == "JPEG"


def test_large_image_resized():
    data, mime, w, h = process_upload(jpeg((5000, 3000)))
    assert (w, h) == (2000, 1200)
    assert Image.open(io.BytesIO(data)).size == (2000, 1200)


def test_png_alpha_kept_png():
    buf = io.BytesIO()
    Image.new("RGBA", (30, 30), (0, 0, 0, 0)).save(buf, "PNG")
    data, mime, w, h = process_upload(buf.getvalue())
    assert mime == "image/png" and Image.open(io.BytesIO(data)).mode == "RGBA"


def test_png_without_alpha_becomes_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (5, 5, 5)).save(buf, "PNG")
    assert process_upload(buf.getvalue())[1] == "image/jpeg"


@pytest.mark.parametrize("raw", [b"", b"not an image at all", b"\xff\xd8\xff\xe0" + b"x" * 50,
                                 jpeg()[:200]])
def test_garbage_rejected(raw):
    with pytest.raises(ImageError) as e:
        process_upload(raw)
    assert str(e.value) == "That file isn't a photo we can use. Try a JPG or PNG."


def test_decompression_bomb_rejected():
    buf = io.BytesIO()
    Image.new("1", (9000, 9000)).save(buf, "PNG")       # 81 MP > 60 MP limit
    with pytest.raises(ImageError):
        process_upload(buf.getvalue())
    buf = io.BytesIO()
    Image.new("1", (8000, 8000)).save(buf, "PNG")       # 64 MP: warning zone
    with pytest.raises(ImageError):
        process_upload(buf.getvalue())
