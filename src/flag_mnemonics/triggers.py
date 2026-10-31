"""Find flag cards that need a mnemonic.

Three triggers feed the same check:
- on profile open (desktop startup),
- after each sync, which picks up misses made on your phone,
- right after you press Again on a desktop review.

What it finds is handed to `pipeline.Pipeline`, which writes the mnemonics.

The search and threshold logic is plain Python so it can be tested without
Anki. Only `register()` touches `aqt`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from .settings import Settings

MNEMONIC_TAG = "mnemonic-added"
AGAIN = 1


@dataclass(frozen=True)
class StrugglingCard:
    card_id: int
    note_id: int
    country: str
    lapses: int
    template: str


def quote_search_term(value: str) -> str:
    """Quote a value for Anki's search syntax.

    Inside quotes Anki still treats `*` and `_` as wildcards, and `\\` and `"`
    need escaping.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("*", "\\*")
        .replace("_", "\\_")
    )
    return f'"{escaped}"'


def build_search_query(settings: Settings) -> str:
    """Search for flag cards at or above the lapse threshold with no mnemonic yet.

    With default settings:
    deck:"Ultimate Geography" note:"Ultimate Geography"
    (card:"Flag - Country" OR card:"Country - Flag") prop:lapses>=3 -tag:mnemonic-added
    """
    parts = []
    if settings.deck_name:
        parts.append(f"deck:{quote_search_term(settings.deck_name)}")
    if settings.note_type:
        parts.append(f"note:{quote_search_term(settings.note_type)}")
    templates = [t for t in settings.flag_card_templates if t]
    if templates:
        cards = " OR ".join(f"card:{quote_search_term(t)}" for t in templates)
        parts.append(f"({cards})")
    parts.append(f"prop:lapses>={settings.lapse_threshold}")
    parts.append(f"-tag:{MNEMONIC_TAG}")
    return " ".join(parts)


def is_in_deck(card_deck: str, target_deck: str) -> bool:
    """True if `card_deck` is `target_deck` or one of its subdecks."""
    if not target_deck:
        return True
    card_deck, target_deck = card_deck.lower(), target_deck.lower()
    return card_deck == target_deck or card_deck.startswith(target_deck + "::")


def should_generate_after_answer(
    settings: Settings,
    *,
    ease: int,
    lapses: int,
    note_type: str,
    template: str,
    deck: str,
    tags: Iterable[str],
) -> bool:
    """Decide whether pressing a button on this card should trigger a mnemonic.

    Only Again counts, only on flag cards, only once the card has reached the
    threshold, and only if it doesn't already have a mnemonic.
    """
    if ease != AGAIN:
        return False
    if lapses < settings.lapse_threshold:
        return False
    if settings.note_type and note_type != settings.note_type:
        return False
    if settings.flag_card_templates and template not in settings.flag_card_templates:
        return False
    if not is_in_deck(deck, settings.deck_name):
        return False
    return MNEMONIC_TAG.lower() not in {t.lower() for t in tags}


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("&nbsp;", " ").strip()


def find_struggling_cards(col: Any, settings: Settings) -> list[StrugglingCard]:
    """Run the search against a collection. Safe to call off the main thread."""
    found = []
    for card_id in col.find_cards(build_search_query(settings)):
        card = col.get_card(card_id)
        note = card.note()
        country = note[settings.fields.country] if settings.fields.country in note else ""
        found.append(
            StrugglingCard(
                card_id=card_id,
                note_id=note.id,
                country=strip_html(country),
                lapses=card.lapses,
                template=card.template()["name"],
            )
        )
    return found


def unique_notes(cards: Sequence[StrugglingCard]) -> list[StrugglingCard]:
    """One entry per note: a mnemonic belongs to the note, not the card."""
    seen: dict[int, StrugglingCard] = {}
    for card in cards:
        best = seen.get(card.note_id)
        if best is None or card.lapses > best.lapses:
            seen[card.note_id] = card
    return list(seen.values())


def describe(cards: Sequence[StrugglingCard], reason: str) -> str:
    if not cards:
        return f"{reason}: no struggling flag cards need a mnemonic."
    lines = [f"{reason}: {len(cards)} flag(s) need a mnemonic:"]
    for c in sorted(cards, key=lambda c: (-c.lapses, c.country)):
        lines.append(f"  {c.country or '(no country)'}: {c.lapses} lapses (note {c.note_id}, {c.template})")
    return "\n".join(lines)


def get_logger() -> logging.Logger:
    try:
        from aqt import mw

        # Writes to the add-on's logs folder (Anki 2.1.66+).
        return mw.addonManager.get_logger(__name__.split(".")[0])
    except Exception:
        return logging.getLogger("flag_mnemonics")


class Catcher:
    """Runs the struggling-card search in the background and reports the result.

    `on_found` is called on the main thread with the de-duplicated notes.
    By default it only logs; the add-on points it at the generator.
    """

    def __init__(
        self,
        mw: Any,
        get_settings: Callable[[], Settings],
        on_found: Callable[[list[StrugglingCard], str], None] | None = None,
    ) -> None:
        self.mw = mw
        self.get_settings = get_settings
        self.on_found = on_found or self.log_found
        self.running = False

    def log_found(self, cards: list[StrugglingCard], reason: str) -> None:
        message = describe(cards, reason)
        get_logger().info(message)
        if cards:
            from aqt.utils import tooltip

            tooltip(f"Flag Mnemonics: {len(cards)} struggling flag(s) found")

    def scan(
        self,
        reason: str,
        on_found: Callable[[list[StrugglingCard], str], None] | None = None,
    ) -> None:
        """Search in the background. Never blocks the UI.

        `on_found` overrides the default handler for this one scan.
        """
        if self.running or self.mw.col is None:
            return
        from aqt.operations import QueryOp

        settings = self.get_settings()
        self.running = True

        def done(cards: list[StrugglingCard]) -> None:
            self.running = False
            (on_found or self.on_found)(unique_notes(cards), reason)

        def failed(err: Exception) -> None:
            self.running = False
            get_logger().exception("Struggling-card search failed", exc_info=err)

        QueryOp(
            parent=self.mw,
            op=lambda col: find_struggling_cards(col, settings),
            success=done,
        ).failure(failed).run_in_background()

    def on_answer(self, reviewer: Any, card: Any, ease: int) -> None:
        settings = self.get_settings()
        # Anki reloads the card before this hook runs, so lapses already
        # include this miss.
        note = card.note()
        deck = self.mw.col.decks.name(card.current_deck_id())
        if not should_generate_after_answer(
            settings,
            ease=ease,
            lapses=card.lapses,
            note_type=note.note_type()["name"],
            template=card.template()["name"],
            deck=deck,
            tags=note.tags,
        ):
            return
        country = note[settings.fields.country] if settings.fields.country in note else ""
        self.on_found(
            [
                StrugglingCard(
                    card_id=card.id,
                    note_id=note.id,
                    country=strip_html(country),
                    lapses=card.lapses,
                    template=card.template()["name"],
                )
            ],
            "Pressed Again",
        )


def register(mw: Any, get_settings: Callable[[], Settings]) -> Catcher:
    """Hook the catcher into Anki."""
    from aqt import gui_hooks

    catcher = Catcher(mw, get_settings)

    def on_profile_open() -> None:
        if get_settings().catch_up_on_startup:
            catcher.scan("Startup")

    def on_sync_finished() -> None:
        if get_settings().catch_up_after_sync:
            catcher.scan("After sync")

    gui_hooks.profile_did_open.append(on_profile_open)
    gui_hooks.sync_did_finish.append(on_sync_finished)
    gui_hooks.reviewer_did_answer_card.append(catcher.on_answer)
    return catcher
