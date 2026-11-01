"""Turn struggling cards into mnemonics, in the background.

Reads the notes on the main thread (fast), then calls the API off the main
thread with the collection released, so reviews and syncs carry on while
mnemonics are written. Results go to user_files/mnemonics.json; stage 4
copies them onto the cards.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from . import media
from .generator import (
    FlagInput,
    GenerationError,
    MissingApiKeyError,
    Mnemonic,
    generate_mnemonic,
    mock_transport,
)
from .settings import Settings
from .storage import MnemonicStore
from .triggers import StrugglingCard, get_logger, strip_html

STORE_PATH = os.path.join(os.path.dirname(__file__), "user_files", "mnemonics.json")


@dataclass
class Job:
    note_id: int
    flag: FlagInput
    guid: str = ""


@dataclass
class BatchResult:
    reason: str
    written: list[tuple[int, str, Mnemonic]] = field(default_factory=list)
    failed: list[tuple[int, str, str]] = field(default_factory=list)
    missing_key: bool = False

    def summary(self) -> str:
        lines = [f"{self.reason}: wrote {len(self.written)} mnemonic(s)."]
        for _, country, m in self.written:
            episode = f" (episode: {m.episode_title})" if m.episode_title else ""
            lines.append(f"\n{country}{episode}\n{m.mnemonic}\nKey detail: {m.distinguishing_detail}")
            lines.extend(f"  warning: {w}" for w in m.warnings)
        if self.failed:
            lines.append(f"\n{len(self.failed)} failed:")
            lines.extend(f"  {country}: {error}" for _, country, error in self.failed)
        return "\n".join(lines)


def build_jobs(
    col: Any,
    settings: Settings,
    cards: Sequence[StrugglingCard],
    store: MnemonicStore,
    force: bool = False,
) -> list[Job]:
    """Read flag fields for each note that doesn't have a stored mnemonic yet.

    With `force` (Regenerate in the Browser), notes that already have one are
    included too, and the old mnemonic is passed along so the new one differs.
    """
    media_dir = col.media.dir()
    jobs = []
    seen: set[int] = set()
    for card in cards:
        if card.note_id in seen or (card.note_id in store and not force):
            continue
        seen.add(card.note_id)
        note = col.get_note(card.note_id)
        previous = (store.get(card.note_id) or {}).get("mnemonic", "") if force else ""
        fields = settings.fields

        def field_text(name: str) -> str:
            return note[name] if name and name in note else ""

        jobs.append(
            Job(
                note_id=card.note_id,
                guid=getattr(note, "guid", ""),
                flag=FlagInput(
                    country=strip_html(field_text(fields.country)) or card.country,
                    image=media.load_flag_image(media_dir, field_text(fields.flag)),
                    flag_similarity=strip_html(field_text(fields.flag_similarity)),
                    previous=previous,
                ),
            )
        )
    return jobs


def run_jobs(
    jobs: Sequence[Job],
    settings: Settings,
    store: MnemonicStore,
    reason: str,
    transport: Optional[Callable] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> BatchResult:
    """Generate each mnemonic in turn. Safe off the main thread (no Anki calls).

    `on_progress(done, total, country)` is called before each flag.
    """
    result = BatchResult(reason)
    if transport is None and settings.use_mock_api:
        transport = mock_transport
    for index, job in enumerate(jobs):
        if on_progress:
            on_progress(index, len(jobs), job.flag.country)
        try:
            mnemonic = generate_mnemonic(
                job.flag,
                theme=settings.theme,
                api_key=settings.resolved_claude_key(),
                # Includes mnemonics written earlier in this batch.
                prior=store.prior_mnemonics(),
                model=settings.claude_model,
                transport=transport,
            )
        except MissingApiKeyError:
            result.missing_key = True
            break
        except GenerationError as err:
            result.failed.append((job.note_id, job.flag.country, str(err)))
            continue
        store.put(job.note_id, job.flag.country, mnemonic, guid=job.guid)
        result.written.append((job.note_id, job.flag.country, mnemonic))
    return result


class Pipeline:
    def __init__(self, mw: Any, get_settings: Callable[[], Settings], store_path: str = STORE_PATH) -> None:
        self.mw = mw
        self.get_settings = get_settings
        self.store = MnemonicStore(store_path)
        self.running = False
        self.warned_missing_key = False

    def generate(
        self,
        cards: list[StrugglingCard],
        reason: str,
        on_done: Optional[Callable[[BatchResult], None]] = None,
        show_progress: bool = False,
        force: bool = False,
    ) -> bool:
        """Start writing mnemonics in the background. Returns False if nothing started.

        `show_progress` shows Anki's progress window with one step per flag
        (used when you asked for it from a menu). Automatic runs stay quiet.
        """
        from aqt.operations import QueryOp

        if self.running or not cards:
            return False
        settings = self.get_settings()
        jobs = build_jobs(self.mw.col, settings, cards, self.store, force=force)
        if not jobs:
            return False
        self.running = True
        progress = self._progress_callback() if show_progress else None

        def done(result: BatchResult) -> None:
            self.running = False
            self.report(result)
            if on_done:
                on_done(result)

        def failed(err: Exception) -> None:
            self.running = False
            get_logger().exception("Mnemonic generation failed", exc_info=err)

        op = QueryOp(
            parent=self.mw,
            op=lambda _col: run_jobs(jobs, settings, self.store, reason, on_progress=progress),
            success=done,
        ).failure(failed)
        if show_progress:
            op = op.with_progress(f"Writing {len(jobs)} mnemonic(s)…")
        # The API calls don't touch the collection, so don't hold it.
        op.without_collection().run_in_background()
        return True

    def _progress_callback(self) -> Callable[[int, int, str], None]:
        """Progress updates from the worker thread, applied on the main thread."""

        def update(done: int, total: int, country: str) -> None:
            label = f"Writing mnemonic {done + 1} of {total}: {country}"
            self.mw.taskman.run_on_main(lambda: self.mw.progress.update(label=label, value=done, max=total))

        return update

    def report(self, result: BatchResult) -> None:
        from aqt.utils import showWarning, tooltip

        log = get_logger()
        log.info(result.summary())
        if result.missing_key:
            if not self.warned_missing_key:
                self.warned_missing_key = True
                showWarning(str(MissingApiKeyError()), title="Flag Mnemonics")
            return
        if result.written:
            tooltip(f"Flag Mnemonics: wrote {len(result.written)} mnemonic(s).")
        if result.failed:
            tooltip(f"Flag Mnemonics: {len(result.failed)} mnemonic(s) failed. See the add-on log.")
