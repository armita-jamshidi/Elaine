"""Overlay mode: the 🥨 box is added to flag answers at review time, desktop only."""

import sys

from fakes import FakeCard, ug_note
from flag_mnemonics import display, overlay
from flag_mnemonics.generator import Mnemonic
from flag_mnemonics.settings import Settings
from flag_mnemonics.storage import MnemonicStore

OVERLAY = Settings.from_config({"storage_mode": "overlay"})
ANSWER = "<div>Poland</div><hr id=answer>Poland"


def store_with_poland(tmp_path):
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(10, "Poland", Mnemonic("White over red, like George's bad date.", "white on top", "", "The Opposite", "Seinfeld"))
    return store


def card(template="Flag - Country", note_type="Ultimate Geography", nid=10):
    return FakeCard(1, ug_note(nid, "Poland") if note_type == "Ultimate Geography" else _other(nid), 4, template)


def _other(nid):
    note = ug_note(nid, "Poland")
    note._note_type = "Basic"
    return note


def test_adds_box_on_answer_side(tmp_path):
    out = overlay.add_overlay(ANSWER, card(), "reviewAnswer", OVERLAY, store_with_poland(tmp_path))
    assert out.startswith(ANSWER)
    assert display.LABEL in out
    assert "White over red" in out
    assert "The Opposite" in out
    assert 'class="flag-mnemonic"' in out


def test_preview_and_card_layout_answers_too(tmp_path):
    store = store_with_poland(tmp_path)
    for kind in ("previewAnswer", "clayoutAnswer"):
        assert display.LABEL in overlay.add_overlay(ANSWER, card(), kind, OVERLAY, store)


def test_never_on_question_side(tmp_path):
    store = store_with_poland(tmp_path)
    for kind in ("reviewQuestion", "previewQuestion", "clayoutQuestion"):
        assert overlay.add_overlay("q", card(), kind, OVERLAY, store) == "q"


def test_only_in_overlay_mode(tmp_path):
    assert overlay.add_overlay(ANSWER, card(), "reviewAnswer", Settings(), store_with_poland(tmp_path)) == ANSWER


def test_only_flag_cards_of_the_note_type(tmp_path):
    store = store_with_poland(tmp_path)
    assert overlay.add_overlay(ANSWER, card("Country - Capital"), "reviewAnswer", OVERLAY, store) == ANSWER
    assert overlay.add_overlay(ANSWER, card(note_type="Basic"), "reviewAnswer", OVERLAY, store) == ANSWER


def test_nothing_without_a_stored_mnemonic(tmp_path):
    assert overlay.add_overlay(ANSWER, card(nid=99), "reviewAnswer", OVERLAY, store_with_poland(tmp_path)) == ANSWER


def test_not_added_twice(tmp_path):
    store = store_with_poland(tmp_path)
    once = overlay.add_overlay(ANSWER, card(), "reviewAnswer", OVERLAY, store)
    assert overlay.add_overlay(once, card(), "reviewAnswer", OVERLAY, store) == once


def test_mnemonic_text_is_escaped(tmp_path):
    store = MnemonicStore(str(tmp_path / "m.json"))
    store.put(10, "Poland", Mnemonic("<script>x</script>", "", "", "", "Seinfeld"))
    out = overlay.add_overlay(ANSWER, card(), "reviewAnswer", OVERLAY, store)
    assert "<script>" not in out


def test_box_matches_field_mode_look():
    snippet = display.template_snippet("Mnemonic")
    assert display.box_html("{{Mnemonic}}") in snippet


def test_register_hooks_card_will_show(tmp_path):
    hooks = sys.modules["aqt.gui_hooks"]
    store = store_with_poland(tmp_path)
    callback = overlay.register(lambda: OVERLAY, store)
    assert callback in hooks.card_will_show
    assert display.LABEL in callback(ANSWER, card(), "reviewAnswer")
    hooks.card_will_show.remove(callback)
