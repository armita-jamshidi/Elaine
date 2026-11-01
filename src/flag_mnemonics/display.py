"""How a mnemonic looks on the card.

Field mode puts a small, self-contained snippet at the end of the flag cards'
back template. It renders only when the Mnemonic field has content, and uses
inline styles (no changes to the note type's CSS) with translucent colors that
read well on light and dark backgrounds in Anki desktop, AnkiMobile, and
AnkiDroid. Pure Python with no Anki imports.
"""

from __future__ import annotations

import html
import re
from typing import Any, Mapping, Optional

SNIPPET_START = "<!-- flag-mnemonics:start -->"
SNIPPET_END = "<!-- flag-mnemonics:end -->"
LABEL = "🥨 Mnemonic"

BOX_STYLE = (
    "margin:1em auto 0;max-width:30em;padding:.6em .8em;text-align:left;"
    "border-left:4px solid #d4a017;border-radius:6px;"
    "background:rgba(212,160,23,.12);font-size:.9em;line-height:1.4"
)
LABEL_STYLE = "font-weight:bold;font-size:.85em;letter-spacing:.02em;margin-bottom:.3em;opacity:.85"
EPISODE_STYLE = "margin-top:.4em;font-size:.85em;opacity:.75"
CONTEXT_STYLE = "margin-top:.2em;font-size:.85em;opacity:.75;font-style:italic"
IMAGE_STYLE = "display:block;width:100%;max-width:16em;height:auto;margin:.5em auto 0;border-radius:4px"


def box_html(inner_html: str) -> str:
    """The 🥨 box around a mnemonic. Same look in field and overlay mode."""
    return (
        f'<div class="flag-mnemonic" style="{BOX_STYLE}">'
        f'<div style="{LABEL_STYLE}">{LABEL}</div>'
        f"{inner_html}"
        f"</div>"
    )


def template_snippet(field_name: str) -> str:
    """The block added to the back template. Hidden while the field is empty."""
    return (
        f"{SNIPPET_START}\n"
        f"{{{{#{field_name}}}}}\n"
        f"{box_html('{{' + field_name + '}}')}\n"
        f"{{{{/{field_name}}}}}\n"
        f"{SNIPPET_END}"
    )


_SNIPPET_RE = re.compile(re.escape(SNIPPET_START) + r".*?" + re.escape(SNIPPET_END), re.DOTALL)


def has_snippet(template_html: str, field_name: str) -> bool:
    """True if the current snippet (for this field) is in the template."""
    return template_snippet(field_name) in template_html


def remove_snippet(template_html: str) -> str:
    return _SNIPPET_RE.sub("", template_html).rstrip() + ("\n" if template_html.endswith("\n") else "")


def add_snippet(template_html: str, field_name: str) -> str:
    """Append the snippet, replacing any older version. Idempotent."""
    if has_snippet(template_html, field_name):
        return template_html
    base = remove_snippet(template_html).rstrip()
    return f"{base}\n\n{template_snippet(field_name)}\n"


def field_html(entry: Mapping[str, Any], image_filename: Optional[str] = None) -> str:
    """What goes in the Mnemonic field: the mnemonic, the episode and what happens in it, the image."""
    parts = [html.escape(str(entry.get("mnemonic", "")).strip())]
    episode = (entry.get("episode_title") or "").strip()
    context = (entry.get("context") or "").strip()
    if episode:
        parts.append(f'<div style="{EPISODE_STYLE}">📺 Episode: “{html.escape(episode)}”</div>')
    if context:
        label = "" if episode else "📺 "
        parts.append(f'<div style="{CONTEXT_STYLE}">{label}{html.escape(context)}</div>')
    image = image_filename or entry.get("image")
    if image:
        parts.append(f'<img src="{html.escape(image, quote=True)}" alt="" style="{IMAGE_STYLE}">')
    return "".join(parts)
