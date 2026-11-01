"""Overlay mode: show the mnemonic on the answer side at review time, desktop only.

Nothing on the cards or the note type changes (apart from the
`mnemonic-added` tag), so the mnemonic never reaches AnkiMobile or AnkiDroid.
Hooked into `card_will_show`, which lets add-ons change the card's HTML just
before Anki displays it.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from . import display
from .settings import Settings
from .storage import MnemonicStore

ANSWER_KINDS = ("reviewAnswer", "previewAnswer", "clayoutAnswer")
MARKER = 'class="flag-mnemonic"'


def _note_id(card: Any) -> Optional[int]:
    nid = getattr(card, "nid", None)
    if nid is None:
        nid = card.note().id
    return nid


def overlay_html(entry: dict) -> str:
    return display.box_html(display.field_html(entry))


def add_overlay(text: str, card: Any, kind: str, settings: Settings, store: MnemonicStore) -> str:
    """Append the mnemonic box to a flag card's answer, if one is stored."""
    if settings.storage_mode != "overlay" or kind not in ANSWER_KINDS:
        return text
    if MARKER in text:  # already there (e.g. field mode snippet left on the template)
        return text
    try:
        if card.note_type()["name"] != settings.note_type:
            return text
        if card.template()["name"] not in settings.flag_card_templates:
            return text
        entry = store.get(_note_id(card))
    except Exception:
        return text
    if not entry or not entry.get("mnemonic"):
        return text
    return f"{text}\n{overlay_html(entry)}"


def register(get_settings: Callable[[], Settings], store: MnemonicStore) -> Callable[[str, Any, str], str]:
    from aqt import gui_hooks

    def on_card_will_show(text: str, card: Any, kind: str) -> str:
        return add_overlay(text, card, kind, get_settings(), store)

    gui_hooks.card_will_show.append(on_card_will_show)
    return on_card_will_show
