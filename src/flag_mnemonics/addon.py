"""Anki wiring: menus, hooks, and the objects they share."""

from __future__ import annotations

from aqt import gui_hooks, mw
from aqt.qt import QAction
from aqt.utils import showInfo, tooltip

from . import triggers
from .field_mode import FieldMode
from .pipeline import Pipeline
from .settings import Settings

ADDON_NAME = "Flag Mnemonics"
PACKAGE = __name__.split(".")[0]

generation: Pipeline
catcher: triggers.Catcher
field_mode: FieldMode


def get_settings() -> Settings:
    return Settings.from_config(mw.addonManager.getConfig(PACKAGE))


def _say_hello() -> None:
    showInfo(
        f"Hello from {ADDON_NAME}!\n\nLoaded settings:\n{get_settings().summary()}\n\n"
        f"Stored mnemonics: {len(generation.store)}",
        title=ADDON_NAME,
    )


def _generate_now() -> None:
    """Find struggling flags and write mnemonics, then show what was written."""

    def found(cards, reason):
        catcher.log_found(cards, reason)
        if not cards:
            showInfo(triggers.describe(cards, reason), title=ADDON_NAME)
            return
        todo = [c for c in cards if c.note_id not in generation.store]
        if not todo:
            showInfo(f"All {len(cards)} struggling flag(s) already have a mnemonic.", title=ADDON_NAME)
            return
        tooltip(f"{ADDON_NAME}: writing {len(todo)} mnemonic(s) in the background…")

        def show(result):
            _after_generation(result)
            if not result.missing_key:
                showInfo(result.summary(), title=ADDON_NAME)

        generation.generate(todo, reason, on_done=show)

    catcher.scan("Manual run", on_found=found)


def _after_generation(result) -> None:
    if result.written:
        field_mode.apply([note_id for note_id, _, _ in result.written])


def _on_found(cards, reason) -> None:
    catcher.log_found(cards, reason)
    generation.generate(cards, reason, on_done=_after_generation)


def setup() -> None:
    global generation, catcher, field_mode
    generation = Pipeline(mw, get_settings)
    field_mode = FieldMode(mw, get_settings, generation.store)
    catcher = triggers.register(mw, get_settings)
    catcher.on_found = _on_found
    # After a deck upgrade, put back the field, the box, and every saved
    # mnemonic. Also catches up on mnemonics that never made it onto cards.
    gui_hooks.profile_did_open.append(lambda: field_mode.repair())
    for label, handler in (
        (f"Hello from {ADDON_NAME}", _say_hello),
        ("Generate mnemonics for struggling flags", _generate_now),
        ("Repair mnemonics after deck upgrade", lambda: field_mode.repair(manual=True)),
    ):
        action = QAction(label, mw)
        action.triggered.connect(handler)
        mw.form.menuTools.addAction(action)
