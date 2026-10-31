"""Minimal stand-ins for Anki's Collection, Card and Note."""

from __future__ import annotations


class FakeNote:
    def __init__(self, nid, fields, tags=(), note_type="Ultimate Geography"):
        self.id = nid
        self.fields = dict(fields)
        self.tags = list(tags)
        self._note_type = note_type

    def __getitem__(self, key):
        return self.fields[key]

    def __contains__(self, key):
        return key in self.fields

    def note_type(self):
        return {"name": self._note_type}


class FakeCard:
    def __init__(self, cid, note, lapses, template="Flag - Country", deck_id=1):
        self.id = cid
        self._note = note
        self.lapses = lapses
        self._template = template
        self.deck_id = deck_id

    def note(self):
        return self._note

    def template(self):
        return {"name": self._template}

    def current_deck_id(self):
        return self.deck_id


class FakeDecks:
    def __init__(self, names):
        self.names = names

    def name(self, did):
        return self.names[did]


class FakeCollection:
    def __init__(self, cards, decks=None, search_results=None):
        self.cards = {c.id: c for c in cards}
        self.decks = FakeDecks(decks or {1: "Ultimate Geography"})
        self.search_results = search_results
        self.queries = []

    def find_cards(self, query):
        self.queries.append(query)
        if self.search_results is not None:
            return list(self.search_results)
        return list(self.cards)

    def get_card(self, cid):
        return self.cards[cid]


def ug_note(nid, country, tags=()):
    return FakeNote(
        nid,
        {"Country": country, "Flag": f'<img src="ug-flag-{country.lower()}.svg">', "Flag similarity": ""},
        tags=tags,
    )
