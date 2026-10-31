import sys
from unittest.mock import MagicMock

import pytest

from fakes import FakeCard, FakeCollection, ug_note
from flag_mnemonics import triggers
from flag_mnemonics.settings import Settings
from flag_mnemonics.triggers import (
    Catcher,
    StrugglingCard,
    build_search_query,
    find_struggling_cards,
    should_generate_after_answer,
    unique_notes,
)

S = Settings()


# --- search query ---------------------------------------------------------


def test_default_query():
    assert build_search_query(S) == (
        'deck:"Ultimate Geography" note:"Ultimate Geography" '
        '(card:"Flag - Country" OR card:"Country - Flag") '
        "prop:lapses>=3 -tag:mnemonic-added"
    )


def test_query_uses_custom_settings():
    s = Settings.from_config(
        {"deck_name": "My Flags", "note_type": "Basic", "flag_card_templates": ["Card 1"], "lapse_threshold": 5}
    )
    assert build_search_query(s) == (
        'deck:"My Flags" note:"Basic" (card:"Card 1") prop:lapses>=5 -tag:mnemonic-added'
    )


def test_query_escapes_special_characters():
    s = Settings.from_config({"deck_name": 'Geo_"Flags"*', "note_type": "", "flag_card_templates": []})
    assert build_search_query(s) == r'deck:"Geo\_\"Flags\"\*" prop:lapses>=3 -tag:mnemonic-added'


# --- Again hook threshold logic -------------------------------------------


def again(**overrides):
    args = dict(
        ease=1,
        lapses=3,
        note_type="Ultimate Geography",
        template="Flag - Country",
        deck="Ultimate Geography",
        tags=[],
    )
    args.update(overrides)
    return should_generate_after_answer(S, **args)


def test_again_at_threshold_triggers():
    assert again()


@pytest.mark.parametrize(
    "overrides",
    [
        {"ease": 2},  # Hard
        {"ease": 3},  # Good
        {"lapses": 2},  # below threshold
        {"note_type": "Basic"},
        {"template": "Country - Capital"},
        {"deck": "Spanish"},
        {"deck": "Ultimate Geography Extra"},  # not a subdeck
        {"tags": ["Mnemonic-Added"]},  # already has one (tags are case-insensitive)
    ],
)
def test_again_does_not_trigger(overrides):
    assert not again(**overrides)


def test_again_above_threshold_and_in_subdeck_triggers():
    assert again(lapses=7, deck="Ultimate Geography::Flags")


# --- collection search ----------------------------------------------------


def make_col():
    poland, monaco = ug_note(10, "<b>Poland</b>"), ug_note(20, "Monaco")
    return FakeCollection(
        [
            FakeCard(1, poland, lapses=4),
            FakeCard(2, poland, lapses=3, template="Country - Flag"),
            FakeCard(3, monaco, lapses=5),
        ]
    )


def test_find_struggling_cards_reads_cards_and_strips_html():
    col = make_col()
    cards = find_struggling_cards(col, S)
    assert col.queries == [build_search_query(S)]
    assert [c.country for c in cards] == ["Poland", "Poland", "Monaco"]
    assert cards[0] == StrugglingCard(card_id=1, note_id=10, country="Poland", lapses=4, template="Flag - Country")


def test_unique_notes_keeps_worst_card_per_note():
    notes = unique_notes(find_struggling_cards(make_col(), S))
    assert sorted((c.note_id, c.lapses) for c in notes) == [(10, 4), (20, 5)]


def test_describe():
    cards = unique_notes(find_struggling_cards(make_col(), S))
    text = triggers.describe(cards, "Startup")
    assert text.splitlines()[0] == "Startup: 2 flag(s) need a mnemonic:"
    assert text.index("Monaco") < text.index("Poland")  # most lapses first
    assert triggers.describe([], "After sync") == "After sync: no struggling flag cards need a mnemonic."


# --- Catcher (background scan + Again hook) -------------------------------


def make_catcher(col):
    mw = MagicMock()
    mw.col = col
    found = []
    catcher = Catcher(mw, lambda: S, on_found=lambda cards, reason: found.append((reason, cards)))
    return catcher, found


def test_scan_runs_in_query_op_and_reports_notes():
    QueryOp = sys.modules["aqt.operations"].QueryOp
    QueryOp.instances.clear()
    catcher, found = make_catcher(make_col())
    catcher.scan("Startup")
    assert len(QueryOp.instances) == 1
    reason, cards = found[0]
    assert reason == "Startup" and len(cards) == 2
    assert catcher.running is False


def test_scan_skips_when_no_collection():
    catcher, found = make_catcher(None)
    catcher.scan("Startup")
    assert found == []


def test_scan_failure_is_logged_not_raised():
    col = make_col()
    col.find_cards = MagicMock(side_effect=RuntimeError("boom"))
    catcher, found = make_catcher(col)
    catcher.scan("Startup")
    assert found == [] and catcher.running is False


def test_on_answer_reports_card_that_reaches_threshold():
    card = FakeCard(5, ug_note(30, "Chad"), lapses=3)
    catcher, found = make_catcher(FakeCollection([card]))
    catcher.on_answer(None, card, 1)
    assert found == [("Pressed Again", [StrugglingCard(5, 30, "Chad", 3, "Flag - Country")])]


def test_on_answer_ignores_good():
    note = ug_note(30, "Chad")
    card = FakeCard(5, note, lapses=9)
    catcher, found = make_catcher(FakeCollection([card]))
    catcher.on_answer(None, card, 3)
    assert found == []


# --- hook registration ----------------------------------------------------


def test_register_hooks_respect_settings():
    import flag_mnemonics  # noqa: F401  (registers the real hooks)

    hooks = sys.modules["aqt.gui_hooks"]
    assert hooks.profile_did_open and hooks.sync_did_finish and hooks.reviewer_did_answer_card

    mw = MagicMock()
    for hook in (hooks.profile_did_open, hooks.sync_did_finish):
        hook.clear()
    off = Settings.from_config({"catch_up_on_startup": False, "catch_up_after_sync": False})
    catcher = triggers.register(mw, lambda: off)
    catcher.scan = MagicMock()
    hooks.profile_did_open[-1]()
    hooks.sync_did_finish[-1]()
    catcher.scan.assert_not_called()


def test_register_hooks_scan_on_startup_and_sync():
    hooks = sys.modules["aqt.gui_hooks"]
    catcher = triggers.register(MagicMock(), lambda: S)
    catcher.scan = MagicMock()
    hooks.profile_did_open[-1]()
    hooks.sync_did_finish[-1]()
    assert [c.args[0] for c in catcher.scan.call_args_list] == ["Startup", "After sync"]
    assert hooks.reviewer_did_answer_card[-1] == catcher.on_answer
