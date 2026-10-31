"""Shared fixtures. Real Anki is never imported: `aqt` is replaced with mocks
before the add-on package is loaded."""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ADDON_DIR = Path(__file__).resolve().parent.parent / "src" / "flag_mnemonics"


def _install_fake_aqt() -> None:
    aqt = types.ModuleType("aqt")
    aqt.mw = MagicMock(name="mw")
    aqt.mw.addonManager.getConfig.return_value = json.loads(
        (ADDON_DIR / "config.json").read_text(encoding="utf-8")
    )
    qt = types.ModuleType("aqt.qt")
    qt.QAction = MagicMock(name="QAction")
    utils = types.ModuleType("aqt.utils")
    utils.showInfo = MagicMock(name="showInfo")
    aqt.qt, aqt.utils = qt, utils
    sys.modules.update({"aqt": aqt, "aqt.qt": qt, "aqt.utils": utils})


_install_fake_aqt()


@pytest.fixture
def addon_dir() -> Path:
    return ADDON_DIR


@pytest.fixture
def default_config(addon_dir: Path) -> dict:
    return json.loads((addon_dir / "config.json").read_text(encoding="utf-8"))
