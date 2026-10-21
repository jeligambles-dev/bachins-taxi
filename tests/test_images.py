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


def _p3_jpeg():
    import pathlib
    icc = (pathlib.Path(__file__).parent / "data" / "display-p3.icc").read_bytes()
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (230, 60, 60)).save(buf, "JPEG", quality=95, icc_profile=icc)
    return buf.getvalue()


def test_icc_profile_converted_to_srgb(monkeypatch):
    from PIL import ImageCms
    calls = []
    real = ImageCms.profileToProfile

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(ImageCms, "profileToProfile", spy)
    data, mime, w, h = process_upload(_p3_jpeg())
    assert calls and mime == "image/jpeg"
    assert "icc_profile" not in Image.open(io.BytesIO(data)).info


def test_bad_icc_profile_falls_back_silently():
    buf = io.BytesIO()
    Image.new("RGB", (30, 30), (10, 200, 10)).save(buf, "JPEG", icc_profile=b"not a profile")
    data, mime, w, h = process_upload(buf.getvalue())
    assert mime == "image/jpeg" and (w, h) == (30, 30)


def test_opaque_rgba_becomes_jpeg():
    buf = io.BytesIO()
    Image.new("RGBA", (50, 30), (10, 20, 30, 255)).save(buf, "PNG")
    data, mime, w, h = process_upload(buf.getvalue())
    assert mime == "image/jpeg" and Image.open(io.BytesIO(data)).format == "JPEG"


def test_transparent_rgba_stays_png():
    buf = io.BytesIO()
    Image.new("RGBA", (50, 30), (10, 20, 30, 100)).save(buf, "PNG")
    assert process_upload(buf.getvalue())[1] == "image/png"


def test_jpeg_draft_path_calls_draft_and_sizes_right(monkeypatch):
    from PIL import JpegImagePlugin
    seen = []
    real = JpegImagePlugin.JpegImageFile.draft

    def spy(self, mode, size):
        seen.append((mode, size))
        return real(self, mode, size)
    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", spy)
    data, mime, w, h = process_upload(jpeg((8000, 4000)))
    assert seen == [("RGB", (2000, 2000))]
    assert max(w, h) == 2000 and (w, h) == (2000, 1000)


def test_display_p3_keeps_saturation():
    src = _p3_jpeg()
    data, *_ = process_upload(src)
    converted = Image.open(io.BytesIO(data)).convert("RGB").getpixel((20, 20))
    plain = Image.open(io.BytesIO(src)).convert("RGB").getpixel((20, 20))   # profile just dropped
    assert converted[0] - converted[1] > plain[0] - plain[1] + 3
