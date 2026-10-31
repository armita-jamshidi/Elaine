"""Flag Mnemonics: themed mnemonics for the flag cards you keep forgetting.

Inside Anki this wires up the menus and hooks (see `addon.py`). Outside Anki
(tests, scripts, the Hugging Face Space) importing the package does nothing,
so modules like `generator` can be reused on their own.
"""

try:
    from aqt import mw
except ImportError:
    mw = None

if mw is not None:
    from . import addon

    addon.setup()
