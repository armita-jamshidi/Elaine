"""Flag Mnemonics: themed mnemonics for the flag cards you keep forgetting."""

from __future__ import annotations

from aqt import mw
from aqt.qt import QAction
from aqt.utils import showInfo

from .settings import Settings

ADDON_NAME = "Flag Mnemonics"


def get_settings() -> Settings:
    return Settings.from_config(mw.addonManager.getConfig(__name__))


def _say_hello() -> None:
    showInfo(
        f"Hello from {ADDON_NAME}!\n\nLoaded settings:\n{get_settings().summary()}",
        title=ADDON_NAME,
    )


def _add_tools_menu() -> None:
    action = QAction(f"Hello from {ADDON_NAME}", mw)
    action.triggered.connect(_say_hello)
    mw.form.menuTools.addAction(action)


_add_tools_menu()
