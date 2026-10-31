"""Flag Mnemonics: themed mnemonics for the flag cards you keep forgetting."""

from __future__ import annotations

from aqt import mw
from aqt.qt import QAction
from aqt.utils import showInfo

from . import triggers
from .settings import Settings

ADDON_NAME = "Flag Mnemonics"


def get_settings() -> Settings:
    return Settings.from_config(mw.addonManager.getConfig(__name__))


def _say_hello() -> None:
    showInfo(
        f"Hello from {ADDON_NAME}!\n\nLoaded settings:\n{get_settings().summary()}",
        title=ADDON_NAME,
    )


def _show_struggling_now() -> None:
    """Run the same search as startup and show the result in a dialog."""

    def show(cards, reason):
        catcher.log_found(cards, reason)
        showInfo(
            f"{triggers.describe(cards, reason)}\n\nSearch used:\n"
            f"{triggers.build_search_query(get_settings())}",
            title=ADDON_NAME,
        )

    catcher.scan("Manual check", on_found=show)


def _add_tools_menu() -> None:
    for label, handler in (
        (f"Hello from {ADDON_NAME}", _say_hello),
        ("Find struggling flags (log only)", _show_struggling_now),
    ):
        action = QAction(label, mw)
        action.triggered.connect(handler)
        mw.form.menuTools.addAction(action)


catcher = triggers.register(mw, get_settings)
_add_tools_menu()
