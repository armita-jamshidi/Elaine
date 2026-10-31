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
    utils.tooltip = MagicMock(name="tooltip")
    utils.showWarning = MagicMock(name="showWarning")
    utils.askUser = MagicMock(name="askUser", return_value=True)

    gui_hooks = types.ModuleType("aqt.gui_hooks")
    for hook in ("profile_did_open", "sync_did_finish", "reviewer_did_answer_card"):
        setattr(gui_hooks, hook, [])

    operations = types.ModuleType("aqt.operations")
    operations.QueryOp = FakeQueryOp
    operations.CollectionOp = FakeCollectionOp

    aqt.qt, aqt.utils, aqt.gui_hooks, aqt.operations = qt, utils, gui_hooks, operations
    sys.modules.update(
        {
            "aqt": aqt,
            "aqt.qt": qt,
            "aqt.utils": utils,
            "aqt.gui_hooks": gui_hooks,
            "aqt.operations": operations,
        }
    )


class FakeCollectionOp:
    """Runs the op immediately against `parent.col`."""

    def __init__(self, *, parent, op):
        self.parent, self.op = parent, op
        self.on_success = lambda changes: None

    def success(self, callback):
        self.on_success = callback
        return self

    def run_in_background(self):
        self.on_success(self.op(self.parent.col))


class FakeQueryOp:
    """Runs the op immediately against `parent.col` instead of in a thread."""

    instances: list = []

    def __init__(self, *, parent, op, success):
        self.parent, self.op, self.success = parent, op, success
        self.on_failure = None
        FakeQueryOp.instances.append(self)

    def failure(self, callback):
        self.on_failure = callback
        return self

    def without_collection(self):
        self.no_collection = True
        return self

    def run_in_background(self):
        try:
            result = self.op(self.parent.col)
        except Exception as err:  # mirror Anki: route errors to failure()
            self.on_failure(err)
        else:
            self.success(result)


_install_fake_aqt()


@pytest.fixture
def addon_dir() -> Path:
    return ADDON_DIR


@pytest.fixture
def default_config(addon_dir: Path) -> dict:
    return json.loads((addon_dir / "config.json").read_text(encoding="utf-8"))
