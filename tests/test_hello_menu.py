import sys

import flag_mnemonics


def test_tools_menu_item_is_added():
    qt = sys.modules["aqt.qt"]
    mw = sys.modules["aqt"].mw
    qt.QAction.assert_any_call("Hello from Flag Mnemonics", mw)
    mw.form.menuTools.addAction.assert_called()


def test_hello_shows_settings():
    showInfo = sys.modules["aqt.utils"].showInfo
    flag_mnemonics._say_hello()
    text = showInfo.call_args.args[0]
    assert text.startswith("Hello from Flag Mnemonics!")
    assert "Theme: Seinfeld" in text
