import json
import sys
from unittest.mock import MagicMock

from fakes import FakeCard, FakeCollection, ug_note
from flag_mnemonics import pipeline
from flag_mnemonics.generator import mock_transport
from flag_mnemonics.pipeline import Pipeline, build_jobs, run_jobs
from flag_mnemonics.settings import Settings
from flag_mnemonics.storage import MnemonicStore
from flag_mnemonics.triggers import StrugglingCard

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2"><rect width="3" height="2" fill="#dc143c"/></svg>'


def setup(tmp_path):
    (tmp_path / "ug-flag-poland.svg").write_bytes(SVG)
    poland = ug_note(10, "<b>Poland</b>", similarity="Indonesia (flipped), Monaco (flipped, narrower)")
    poland.fields["Flag"] = '<img src="ug-flag-poland.svg">'
    monaco = ug_note(20, "Monaco")
    col = FakeCollection([FakeCard(1, poland, 4), FakeCard(2, monaco, 3)], media_dir=str(tmp_path))
    cards = [StrugglingCard(1, 10, "Poland", 4, "Flag - Country"), StrugglingCard(2, 20, "Monaco", 3, "Flag - Country")]
    store = MnemonicStore(str(tmp_path / "user_files" / "mnemonics.json"))
    return col, cards, store


def test_build_jobs_reads_fields_and_image(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.media, "render_svg_to_png", lambda data: None)
    col, cards, store = setup(tmp_path)
    jobs = build_jobs(col, Settings(), cards, store)
    poland = jobs[0].flag
    assert poland.country == "Poland"
    assert poland.flag_similarity.startswith("Indonesia")
    assert poland.image.media_type == "image/svg+xml"
    assert jobs[1].flag.image is None  # no file for Monaco


def test_build_jobs_skips_notes_with_a_mnemonic(tmp_path):
    col, cards, store = setup(tmp_path)
    run_jobs(build_jobs(col, Settings(), cards[:1], store), Settings(), store, "t", transport=mock_transport)
    assert [j.note_id for j in build_jobs(col, Settings(), cards, store)] == [20]


def test_run_jobs_passes_earlier_mnemonics_as_context(tmp_path):
    col, cards, store = setup(tmp_path)
    bodies = []

    def transport(body, key):
        bodies.append(body)
        return mock_transport(body, key)

    result = run_jobs(build_jobs(col, Settings(), cards, store), Settings(), store, "Startup", transport=transport)
    assert [c for _, c, _ in result.written] == ["Poland", "Monaco"]
    assert "[mock] Poland" in bodies[1]["messages"][0]["content"][-1]["text"]
    saved = json.loads((tmp_path / "user_files" / "mnemonics.json").read_text(encoding="utf-8"))
    assert set(saved["mnemonics"]) == {"10", "20"}


def test_theme_and_model_come_from_settings(tmp_path):
    col, cards, store = setup(tmp_path)
    bodies = []
    settings = Settings.from_config({"theme": "The Office", "claude_model": "claude-sonnet-5-5"})
    run_jobs(
        build_jobs(col, settings, cards[:1], store),
        settings,
        store,
        "t",
        transport=lambda b, k: bodies.append(b) or mock_transport(b, k),
    )
    assert bodies[0]["model"] == "claude-sonnet-5-5"
    assert "riffs on The Office" in bodies[0]["system"][0]["text"]
    assert store.get(10)["theme"] == "The Office"


def test_missing_key_stops_batch(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    col, cards, store = setup(tmp_path)
    result = run_jobs(build_jobs(col, Settings(), cards, store), Settings(), store, "t")
    assert result.missing_key and not result.written and len(store) == 0


def test_mock_setting_needs_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    col, cards, store = setup(tmp_path)
    settings = Settings.from_config({"use_mock_api": True})
    result = run_jobs(build_jobs(col, settings, cards, store), settings, store, "t")
    assert len(result.written) == 2


def test_failures_are_collected_and_batch_continues(tmp_path):
    col, cards, store = setup(tmp_path)
    calls = []

    def flaky(body, key):
        calls.append(1)
        if len(calls) == 1:
            return {"stop_reason": "refusal", "content": []}
        return mock_transport(body, key)

    result = run_jobs(build_jobs(col, Settings(), cards, store), Settings(), store, "t", transport=flaky)
    assert [c for _, c, _ in result.failed] == ["Poland"]
    assert [c for _, c, _ in result.written] == ["Monaco"]
    assert "1 failed" in result.summary()


def test_pipeline_generate_runs_without_collection_and_reports(tmp_path, monkeypatch):
    col, cards, _ = setup(tmp_path)
    mw = MagicMock()
    mw.col = col
    p = Pipeline(mw, lambda: Settings.from_config({"use_mock_api": True}), str(tmp_path / "s.json"))
    QueryOp = sys.modules["aqt.operations"].QueryOp
    QueryOp.instances.clear()
    done = []
    p.generate(cards, "After sync", on_done=done.append)
    assert QueryOp.instances[-1].no_collection is True
    assert len(done[0].written) == 2 and len(p.store) == 2
    assert p.running is False
    sys.modules["aqt.utils"].tooltip.assert_called_with("Flag Mnemonics: wrote 2 mnemonic(s).")


def test_pipeline_warns_once_about_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    col, cards, _ = setup(tmp_path)
    mw = MagicMock()
    mw.col = col
    showWarning = sys.modules["aqt.utils"].showWarning = MagicMock()
    p = Pipeline(mw, Settings, str(tmp_path / "s.json"))
    p.generate(cards, "Startup")
    p.generate(cards, "After sync")
    assert showWarning.call_count == 1
    assert "claude_api_key" in showWarning.call_args.args[0]


def test_run_jobs_reports_progress(tmp_path):
    col, cards, store = setup(tmp_path)
    seen = []
    run_jobs(
        build_jobs(col, Settings(), cards, store),
        Settings(),
        store,
        "t",
        transport=mock_transport,
        on_progress=lambda done, total, country: seen.append((done, total, country)),
    )
    assert seen == [(0, 2, "Poland"), (1, 2, "Monaco")]


def test_force_includes_stored_notes_with_previous_mnemonic(tmp_path):
    col, cards, store = setup(tmp_path)
    run_jobs(build_jobs(col, Settings(), cards[:1], store), Settings(), store, "t", transport=mock_transport)
    jobs = build_jobs(col, Settings(), cards, store, force=True)
    assert [j.note_id for j in jobs] == [10, 20]
    assert jobs[0].flag.previous.startswith("[mock] Poland")
    assert jobs[1].flag.previous == ""


def test_manual_batch_shows_progress_window(tmp_path):
    col, cards, store = setup(tmp_path)
    mw = MagicMock()
    mw.col = col
    mw.taskman.run_on_main.side_effect = lambda closure: closure()
    p = Pipeline(mw, lambda: Settings.from_config({"use_mock_api": True}), str(tmp_path / "m.json"))
    assert p.generate(cards, "Manual run", show_progress=True)
    op = sys.modules["aqt.operations"].QueryOp.instances[-1]
    assert op.progress_label == "Writing 2 mnemonic(s)…"
    assert mw.progress.update.call_args.kwargs == {"label": "Writing mnemonic 2 of 2: Monaco", "value": 1, "max": 2}


def test_automatic_runs_stay_quiet(tmp_path):
    col, cards, store = setup(tmp_path)
    mw = MagicMock()
    mw.col = col
    p = Pipeline(mw, lambda: Settings.from_config({"use_mock_api": True}), str(tmp_path / "m.json"))
    assert p.generate(cards, "After answering")
    op = sys.modules["aqt.operations"].QueryOp.instances[-1]
    assert not hasattr(op, "progress_label")
    mw.progress.update.assert_not_called()


def test_generate_returns_false_when_busy(tmp_path):
    col, cards, store = setup(tmp_path)
    mw = MagicMock()
    mw.col = col
    p = Pipeline(mw, lambda: Settings.from_config({"use_mock_api": True}), str(tmp_path / "m.json"))
    p.running = True
    assert p.generate(cards, "t") is False
