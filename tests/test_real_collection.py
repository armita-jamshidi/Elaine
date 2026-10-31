"""Runs the struggling-card search against a real Anki collection.

Uses the `anki` package from PyPI (the same backend Anki desktop uses) with a
small copy of the Ultimate Geography note type. Skipped if `anki` isn't
installed.
"""

import pytest

anki_collection = pytest.importorskip("anki.collection")

from flag_mnemonics import triggers  # noqa: E402
from flag_mnemonics.settings import Settings  # noqa: E402

UG_FIELDS = ["Country", "Country info", "Capital", "Capital info", "Capital hint", "Flag", "Flag similarity", "Map"]
UG_TEMPLATES = ["Country - Capital", "Capital - Country", "Flag - Country", "Country - Flag"]


@pytest.fixture
def col(tmp_path):
    col = anki_collection.Collection(str(tmp_path / "collection.anki2"))
    mm = col.models
    model = mm.new("Ultimate Geography")
    for name in UG_FIELDS:
        mm.add_field(model, mm.new_field(name))
    for name in UG_TEMPLATES:
        t = mm.new_template(name)
        t["qfmt"] = f"{name}: {{{{Country}}}}{{{{Flag}}}}"
        t["afmt"] = "{{FrontSide}}<hr id=answer>{{Capital}}"
        mm.add_template(model, t)
    mm.add(model)
    yield col
    col.close()


def add_note(col, country, lapses, deck="Ultimate Geography::Flags", tags=()):
    note = col.new_note(col.models.by_name("Ultimate Geography"))
    note["Country"] = country
    note["Capital"] = "x"
    note["Flag"] = f'<img src="ug-flag-{country.lower()}.svg">'
    note.tags = list(tags)
    col.add_note(note, col.decks.id(deck))
    for card in note.cards():
        card.type = card.queue = 2  # review card
        card.lapses = lapses
        col.update_card(card)
    return note


def test_search_finds_only_struggling_flag_cards(col):
    add_note(col, "Poland", 4)
    add_note(col, "Monaco", 3)
    add_note(col, "Chad", 2)  # below threshold
    add_note(col, "Romania", 5, tags=["mnemonic-added"])  # already done
    add_note(col, "Peru", 6, deck="Spanish")  # wrong deck

    cards = triggers.find_struggling_cards(col, Settings())
    assert sorted({c.template for c in cards}) == ["Country - Flag", "Flag - Country"]
    notes = triggers.unique_notes(cards)
    assert sorted(c.country for c in notes) == ["Monaco", "Poland"]


def test_again_check_with_real_card_objects(col):
    note = add_note(col, "Indonesia", 3)
    card = next(c for c in note.cards() if c.template()["name"] == "Flag - Country")
    assert triggers.should_generate_after_answer(
        Settings(),
        ease=1,
        lapses=card.lapses,
        note_type=note.note_type()["name"],
        template=card.template()["name"],
        deck=col.decks.name(card.current_deck_id()),
        tags=note.tags,
    )
