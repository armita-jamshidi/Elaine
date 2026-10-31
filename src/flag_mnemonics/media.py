"""Read a note's flag image from the collection's media folder.

Ultimate Geography ships its flags as SVG, which Claude's vision input
doesn't accept, so SVGs are rendered to PNG with Qt (bundled with Anki).
If Qt can't render it, the SVG source is sent as text instead.
"""

from __future__ import annotations

import html
import os
import re
from typing import Optional

from .generator import FlagImage

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
RENDER_WIDTH = 800


def image_filename(field_html: str) -> Optional[str]:
    """First <img src="..."> in a field, e.g. 'ug-flag-poland.svg'."""
    match = re.search(r"""<img[^>]*?\ssrc\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))""", field_html, re.IGNORECASE)
    if not match:
        return None
    name = html.unescape(next(g for g in match.groups() if g))
    # Media references are plain filenames; refuse anything path-like.
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    return name


def render_svg_to_png(svg: bytes, width: int = RENDER_WIDTH) -> Optional[bytes]:
    """Render SVG to PNG with Qt. Returns None if Qt or QtSvg isn't available."""
    try:
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        from PyQt6.QtGui import QImage, QPainter
        from PyQt6.QtSvg import QSvgRenderer
    except ImportError:
        return None
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        return None
    size = renderer.defaultSize()
    if size.width() <= 0 or size.height() <= 0:
        return None
    height = max(1, round(width * size.height() / size.width()))
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def load_flag_image(media_dir: str, field_html: str) -> Optional[FlagImage]:
    """The flag image referenced by a field, ready for the generator."""
    name = image_filename(field_html)
    if not name:
        return None
    media_type = IMAGE_TYPES.get(os.path.splitext(name)[1].lower())
    if not media_type:
        return None
    path = os.path.join(media_dir, name)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if media_type == "image/svg+xml":
        png = render_svg_to_png(data)
        if png:
            return FlagImage(png, "image/png")
    return FlagImage(data, media_type)
