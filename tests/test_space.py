"""The Hugging Face Space's logic (space/demo_logic.py), without Gradio or network."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPACE = ROOT / "space"
sys.path.insert(0, str(SPACE))
import demo_logic as logic  # noqa: E402

GOOD_JSON = json.dumps(
    {
        "mnemonic": "Jerry's blue blazer is a shade lighter than Chad's.",
        "episode_title": "",
        "context": "Jerry is the clean-cut one who always dresses neatly.",
        "distinguishing_detail": "lighter blue",
        "image_prompt": "a blazer",
    }
)


@pytest.fixture
def chad():
    return logic.flag_input(next(f for f in logic.load_flags() if f.country == "Chad"))


def test_generator_copy_matches_the_addon():
    assert (SPACE / "generator.py").read_bytes() == (ROOT / "src" / "flag_mnemonics" / "generator.py").read_bytes()


def test_flags_load_with_images_and_lookalikes():
    flags = logic.load_flags()
    assert {"Poland", "Indonesia", "Monaco", "Chad", "Romania"} <= {f.country for f in flags}
    for f in flags:
        assert f.path.read_bytes().startswith(b"\x89PNG"), f.country
        assert f.similarity


def test_flags_are_drawn_not_copied():
    about = json.loads((SPACE / "flags.json").read_text())["_about"]
    assert "drawn for this demo" in about and "public domain" in about


def test_pregenerated_example_is_labeled():
    poland = logic.load_pregenerated()["Poland"]
    assert "Hand-written example" in poland["note"]
    assert not poland.get("model")


def test_theme_is_cleaned():
    assert logic.clean_theme("") == "Seinfeld"
    assert logic.clean_theme("  The   Office ") == "The Office"
    assert len(logic.clean_theme("x" * 500)) == logic.MAX_THEME_CHARS


# --- limiter ----------------------------------------------------------------


def test_per_visitor_limit_and_reset_next_day():
    now = [1_000_000.0]
    limiter = logic.DailyLimiter(per_visitor=2, total=100, clock=lambda: now[0])
    assert limiter.try_take("1.2.3.4") is None
    assert limiter.try_take("1.2.3.4") is None
    assert "today's 2 free" in limiter.try_take("1.2.3.4")
    assert limiter.try_take("5.6.7.8") is None  # someone else is fine
    now[0] += 86_400
    assert limiter.try_take("1.2.3.4") is None


def test_global_cap():
    limiter = logic.DailyLimiter(per_visitor=5, total=3)
    for ip in ("a", "b", "c"):
        assert limiter.try_take(ip) is None
    assert "whole demo" in limiter.try_take("d")
    assert limiter.remaining("d") == 0


def test_raw_ips_are_not_kept():
    limiter = logic.DailyLimiter(per_visitor=5, total=5)
    limiter.try_take("203.0.113.9")
    assert "203.0.113.9" not in repr(limiter.__dict__)


def test_client_address_prefers_forwarded_for():
    assert logic.client_address({"x-forwarded-for": "198.51.100.7, 10.0.0.1"}, "10.0.0.1") == "198.51.100.7"
    assert logic.client_address({}, "10.0.0.2") == "10.0.0.2"


# --- free model -------------------------------------------------------------


def test_open_model_gets_the_addon_prompt_and_image(chad):
    seen = {}

    def chat(messages, model, token):
        seen.update(messages=messages, model=model, token=token)
        return "```json\n" + GOOD_JSON + "\n```"

    result = logic.generate_open(chad, "Seinfeld", token="hf_space", chat=chat, model="some/vlm")
    assert result.ok and result.mnemonic.mnemonic.startswith("Jerry's blue blazer")
    system, user = seen["messages"]
    assert "Seinfeld" in system["content"] and "JSON" in system["content"]
    assert user["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "Country: Chad" in user["content"][1]["text"]
    assert "Romania" in user["content"][1]["text"]
    assert seen["token"] == "hf_space"


def test_open_model_without_token(chad, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    result = logic.generate_open(chad, "Seinfeld", chat=lambda *a: GOOD_JSON)
    assert not result.ok and "HF_TOKEN" in result.message


def test_open_model_bad_reply_and_outage(chad):
    bad = logic.generate_open(chad, "Seinfeld", token="t", chat=lambda *a: "Sure! Here's a joke.")
    assert not bad.ok and "Try again" in bad.message

    def down(*a):
        raise TimeoutError("slow")

    assert "unavailable" in logic.generate_open(chad, "Seinfeld", token="t", chat=down).message


# --- visitor's Claude key ---------------------------------------------------


def test_claude_uses_only_the_visitors_key(chad):
    from generator import mock_transport

    keys = []

    def transport(body, key):
        keys.append(key)
        return mock_transport(body, key)

    result = logic.generate_claude(chad, "Seinfeld", "  sk-ant-visitor  ", transport=transport)
    assert result.ok and keys == ["sk-ant-visitor"]


def test_claude_without_key_never_calls_out(chad):
    result = logic.generate_claude(chad, "Seinfeld", "", transport=lambda *a: pytest.fail("called"))
    assert not result.ok and "Paste your Claude API key" in result.message


def test_claude_error_never_echoes_the_key(chad):
    from generator import ApiError

    def transport(body, key):
        raise ApiError(400, f"bad request for {key}")

    result = logic.generate_claude(chad, "Seinfeld", "sk-ant-secret-123", transport=transport)
    assert not result.ok and "sk-ant-secret-123" not in result.message


def test_space_has_no_claude_key_anywhere():
    for path in SPACE.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".md", ".json", ".txt"):
            assert "sk-ant-api" not in path.read_text(encoding="utf-8", errors="ignore"), path
    assert "ANTHROPIC_API_KEY" not in (SPACE / "app.py").read_text()
    assert "ANTHROPIC_API_KEY" not in (SPACE / "demo_logic.py").read_text()


def test_render():
    m = logic.Mnemonic("Text.", "detail", "", "The Opposite")
    out = logic.render(logic.Result(True, m), "source")
    assert "🥨 Text." in out and "The Opposite" in out and "source" in out
    assert logic.render(logic.Result(False, message="nope"), "s") == "⚠️ nope"


def test_render_explains_the_episode():
    m = logic.Mnemonic("Text.", "detail", "", "The Opposite", context="George does the opposite.")
    out = logic.render(logic.Result(True, m), "source")
    assert out.index("The Opposite") < out.index("George does the opposite.")


def test_pregenerated_examples_explain_their_episode():
    for entry in logic.load_pregenerated().values():
        if entry.get("episode_title"):
            assert entry.get("context")


def test_failed_requests_are_given_back():
    limiter = logic.DailyLimiter(per_visitor=1, total=10)
    assert limiter.try_take("a") is None
    limiter.give_back("a")
    assert limiter.try_take("a") is None
    assert limiter.try_take("a") is not None
