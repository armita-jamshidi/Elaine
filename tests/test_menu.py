import sys

import flag_mnemonics  # noqa: F401  (runs addon.setup() against the fake aqt)
from flag_mnemonics import addon


def test_tools_menu_items_are_added():
    qt = sys.modules["aqt.qt"]
    mw = sys.modules["aqt"].mw
    qt.QAction.assert_any_call("Generate mnemonics for struggling flags", mw)
    qt.QAction.assert_any_call("About Flag Mnemonics", mw)
    labels = [c.args[0] for c in qt.QAction.call_args_list]
    assert not any(label.startswith("Hello") for label in labels)
    mw.form.menuTools.addAction.assert_called()


def test_about_shows_settings():
    showInfo = sys.modules["aqt.utils"].showInfo
    addon._about()
    text = showInfo.call_args.args[0]
    assert text.startswith("Flag Mnemonics")
    assert "Theme: Seinfeld" in text
    assert "Saved mnemonics:" in text


def test_overlay_and_browser_hooks_registered():
    hooks = sys.modules["aqt.gui_hooks"]
    assert addon.browser.add_to_menu in hooks.browser_will_show_context_menu
    assert len(hooks.card_will_show) >= 1


def test_found_cards_go_to_the_generator():
    assert addon.catcher.on_found is addon._on_found


def test_repair_action_and_startup_hook():
    qt = sys.modules["aqt.qt"]
    hooks = sys.modules["aqt.gui_hooks"]
    qt.QAction.assert_any_call("Repair mnemonics after deck upgrade", sys.modules["aqt"].mw)
    assert len(hooks.profile_did_open) >= 2  # struggling-card scan + repair check
