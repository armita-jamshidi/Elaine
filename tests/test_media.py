import pytest

from flag_mnemonics import media

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="5"><rect width="8" height="5" fill="#dc143c"/><rect width="8" height="2.5" fill="#fff"/></svg>'


@pytest.mark.parametrize(
    "html, name",
    [
        ('<img src="ug-flag-poland.svg" />', "ug-flag-poland.svg"),
        ("<IMG class='x' SRC='a b.png'>", "a b.png"),
        ("<img src=plain.jpg>", "plain.jpg"),
        ('<img src="caf&amp;e.png">', "caf&e.png"),
        ("no image here", None),
        ('<img src="../secrets.png">', None),
        ('<img src="sub/dir.png">', None),
    ],
)
def test_image_filename(html, name):
    assert media.image_filename(html) == name


def test_load_png(tmp_path):
    (tmp_path / "flag.png").write_bytes(b"\x89PNG data")
    image = media.load_flag_image(str(tmp_path), '<img src="flag.png">')
    assert image.media_type == "image/png" and image.data == b"\x89PNG data"


def test_missing_or_unknown_files(tmp_path):
    assert media.load_flag_image(str(tmp_path), '<img src="nope.png">') is None
    (tmp_path / "flag.bmp").write_bytes(b"BM")
    assert media.load_flag_image(str(tmp_path), '<img src="flag.bmp">') is None
    assert media.load_flag_image(str(tmp_path), "") is None


def test_svg_falls_back_to_source_without_qt(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "render_svg_to_png", lambda data: None)
    (tmp_path / "f.svg").write_bytes(SVG)
    image = media.load_flag_image(str(tmp_path), '<img src="f.svg">')
    assert image.media_type == "image/svg+xml" and image.data == SVG


def test_svg_renders_to_png_with_qt(tmp_path):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PyQt6.QtSvg")
    QtGui = pytest.importorskip("PyQt6.QtGui")
    QGuiApplication, QImage = QtGui.QGuiApplication, QtGui.QImage
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    (tmp_path / "f.svg").write_bytes(SVG)
    image = media.load_flag_image(str(tmp_path), '<img src="f.svg">')
    assert image.media_type == "image/png" and image.data.startswith(b"\x89PNG")
    png = QImage.fromData(image.data)
    assert png.width() == media.RENDER_WIDTH and png.height() == 500
    assert png.pixelColor(10, 10).name() == "#ffffff"  # white on top
    assert png.pixelColor(10, 490).name() == "#dc143c"  # red below
