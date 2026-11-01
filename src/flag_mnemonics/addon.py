"""Anki wiring: menus, hooks, and the objects they share."""

from __future__ import annotations

from aqt import gui_hooks, mw
from aqt.qt import QAction
from aqt.utils import showInfo, tooltip

from . import browser_actions, overlay, triggers
from .field_mode import FieldMode
from .pipeline import Pipeline
from .settings import Settings

ADDON_NAME = "Flag Mnemonics"
PACKAGE = __name__.split(".")[0]

generation: Pipeline
catcher: triggers.Catcher
field_mode: FieldMode
browser: browser_actions.BrowserActions


def get_settings() -> Settings:
    return Settings.from_config(mw.addonManager.getConfig(PACKAGE))


def _about() -> None:
    showInfo(
        f"{ADDON_NAME}\n\nThemed mnemonics for the flags you keep forgetting.\n\n"
        f"Settings:\n{get_settings().summary()}\n\n"
        f"Saved mnemonics: {len(generation.store)}\n\n"
        "Change settings in Tools > Add-ons > Flag Mnemonics > Config.",
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
        def show(result):
            _after_generation(result)
            if not result.missing_key:
                showInfo(result.summary(), title=ADDON_NAME)

        if not generation.generate(todo, reason, on_done=show, show_progress=True):
            tooltip(f"{ADDON_NAME}: mnemonics are already being written. Try again in a moment.")

    catcher.scan("Manual run", on_found=found)


def _after_generation(result) -> None:
    if result.written:
        field_mode.apply([note_id for note_id, _, _ in result.written])


def _on_found(cards, reason) -> None:
    catcher.log_found(cards, reason)
    generation.generate(cards, reason, on_done=_after_generation)


def setup() -> None:
    global generation, catcher, field_mode, browser
    generation = Pipeline(mw, get_settings)
    field_mode = FieldMode(mw, get_settings, generation.store)
    catcher = triggers.register(mw, get_settings)
    catcher.on_found = _on_found
    overlay.register(get_settings, generation.store)
    browser = browser_actions.BrowserActions(mw, get_settings, generation, field_mode, _after_generation)
    browser_actions.register(browser)
    # After a deck upgrade, put back the field, the box, and every saved
    # mnemonic. Also catches up on mnemonics that never made it onto cards.
    gui_hooks.profile_did_open.append(lambda: field_mode.repair())
    for label, handler in (
        ("Generate mnemonics for struggling flags", _generate_now),
        ("Repair mnemonics after deck upgrade", lambda: field_mode.repair(manual=True)),
        (f"About {ADDON_NAME}", _about),
    ):
        action = QAction(label, mw)
        action.triggered.connect(handler)
        mw.form.menuTools.addAction(action)
