import base64
import io
import json
import urllib.error

import pytest

from flag_mnemonics import generator
from flag_mnemonics.generator import (
    EXAMPLE_MNEMONIC,
    FlagImage,
    FlagInput,
    GenerationError,
    MissingApiKeyError,
    PriorMnemonic,
    build_request,
    build_system_prompt,
    build_user_text,
    count_sentences,
    generate_mnemonic,
    mock_transport,
    parse_response,
    select_context,
)

POLAND_SIMILARITY = (
    "Indonesia (white and red flipped, brighter red), Monaco (white and red flipped, narrower)"
)
PNG = FlagImage(b"\x89PNG fake", "image/png")
POLAND = FlagInput("Poland", PNG, POLAND_SIMILARITY)


def reply(payload, **extra):
    body = {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(payload)}]}
    body.update(extra)
    return body


GOOD = {
    "mnemonic": "Poland is white over red, the opposite of Indonesia, like George in 'The Opposite.'",
    "episode_title": "The Opposite",
    "distinguishing_detail": "white on top",
    "image_prompt": "A white-over-red flag beside a diner booth",
}


# --- system prompt --------------------------------------------------------


def test_system_prompt_contains_all_rules_and_example():
    prompt = build_system_prompt("Seinfeld")
    for phrase in [
        "riffs on Seinfeld",
        "Encode the flag itself",
        "No made-up episodes",
        "episode_title",
        "your own words",
        "Avoid confusion with other flags",
        "One to three sentences",
        "Never include any people",
    ]:
        assert phrase in prompt
    assert EXAMPLE_MNEMONIC in prompt
    assert "'The Opposite,'" in EXAMPLE_MNEMONIC


def test_theme_changes_prompt():
    office = build_system_prompt("The Office")
    assert "riffs on The Office" in office
    assert "draw on The Office" in office
    assert build_system_prompt("  ") == build_system_prompt("Seinfeld")


# --- context selection and user message -----------------------------------


def test_select_context_puts_lookalikes_first_and_skips_self():
    prior = [
        PriorMnemonic("Chad", "chad joke"),
        PriorMnemonic("Monaco", "monaco joke", "short and stubby"),
        PriorMnemonic("Poland", "old poland joke"),
        PriorMnemonic("Indonesia", "indonesia joke"),
    ]
    picked = select_context(prior, "Poland", POLAND_SIMILARITY)
    assert [p.country for p in picked] == ["Monaco", "Indonesia", "Chad"]
    assert select_context(prior, "Poland", POLAND_SIMILARITY, limit=1)[0].country == "Monaco"


def test_user_text_includes_country_similarity_and_prior():
    text = build_user_text(POLAND, [PriorMnemonic("Monaco", "monaco joke", "short and stubby")])
    assert "Country: Poland" in text
    assert POLAND_SIMILARITY in text
    assert "- Monaco: monaco joke [distinguishing detail: short and stubby]" in text
    assert text.endswith("Write the mnemonic for Poland.")


def test_user_text_without_similarity_or_image():
    text = build_user_text(FlagInput("Nepal"), [])
    assert "none listed" in text
    assert "No image of the flag is attached" in text


def test_request_body_shape():
    body = build_request(POLAND, "Seinfeld", [PriorMnemonic("Monaco", "m")], model="claude-opus-5-5")
    assert body["model"] == "claude-opus-5-5"
    assert body["system"][0]["text"] == build_system_prompt("Seinfeld")
    assert body["output_config"]["format"] == {"type": "json_schema", "schema": generator.MNEMONIC_SCHEMA}
    assert body["fallbacks"] == "default"
    image, text = body["messages"][0]["content"]
    assert image == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(PNG.data).decode()},
    }
    assert "Monaco: m" in text["text"]
    assert "temperature" not in body  # rejected on current API versions


def test_svg_is_sent_as_text_not_image():
    svg = FlagInput("Chad", FlagImage(b'<svg><rect fill="#002664"/></svg>', "image/svg+xml"))
    content = build_request(svg, "Seinfeld")["messages"][0]["content"]
    assert content[0]["type"] == "text" and '<rect fill="#002664"/>' in content[0]["text"]
    assert "SVG source" in content[1]["text"]


def test_schema_requires_every_field():
    schema = generator.MNEMONIC_SCHEMA
    assert set(schema["required"]) == {"mnemonic", "episode_title", "distinguishing_detail", "image_prompt"}
    assert schema["additionalProperties"] is False


# --- parsing --------------------------------------------------------------


def test_parse_good_response():
    m = parse_response(reply(GOOD), theme="Seinfeld")
    assert m.mnemonic.startswith("Poland is white over red")
    assert m.episode_title == "The Opposite"
    assert m.distinguishing_detail == "white on top"
    assert m.model == "claude-opus-5-5" and m.theme == "Seinfeld"
    assert m.warnings == []


def test_empty_episode_title_becomes_none():
    assert parse_response(reply({**GOOD, "episode_title": "  "})).episode_title is None


def test_parse_skips_thinking_blocks_and_code_fences():
    body = {
        "stop_reason": "end_turn",
        "content": [
            {"type": "thinking", "thinking": ""},
            {"type": "text", "text": "```json\n" + json.dumps(GOOD) + "\n```"},
        ],
    }
    assert parse_response(body).episode_title == "The Opposite"


def test_parse_json_with_surrounding_text():
    body = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Here you go: " + json.dumps(GOOD)}]}
    assert parse_response(body).mnemonic == GOOD["mnemonic"]


@pytest.mark.parametrize(
    "body, message",
    [
        ({"stop_reason": "refusal", "stop_details": {"category": "cyber"}, "content": []}, "declined"),
        ({"stop_reason": "max_tokens", "content": []}, "cut off"),
        ({"stop_reason": "end_turn", "content": []}, "no text"),
        ({"stop_reason": "end_turn", "content": [{"type": "text", "text": "not json"}]}, "wasn't JSON"),
        ({"stop_reason": "end_turn", "content": [{"type": "text", "text": "[1, 2]"}]}, "JSON object"),
        (reply({**GOOD, "mnemonic": ""}), "no mnemonic"),
    ],
)
def test_parse_errors(body, message):
    with pytest.raises(GenerationError, match=message):
        parse_response(body)


def test_too_many_sentences_is_a_warning():
    long = "One. Two. Three. Four."
    assert count_sentences(long) == 4
    assert parse_response(reply({**GOOD, "mnemonic": long})).warnings


def test_sentence_count_ignores_quoted_titles():
    assert count_sentences(EXAMPLE_MNEMONIC) == 2


# --- generate_mnemonic and transports -------------------------------------


def test_missing_key_raises_clear_error():
    with pytest.raises(MissingApiKeyError, match="claude_api_key"):
        generate_mnemonic(POLAND, "Seinfeld", api_key="")


def test_generate_with_injected_transport():
    seen = {}

    def transport(body, key):
        seen["body"], seen["key"] = body, key
        return reply(GOOD)

    m = generate_mnemonic(POLAND, "The Office", api_key="sk-test", prior=[PriorMnemonic("Monaco", "m")], transport=transport)
    assert seen["key"] == "sk-test"
    assert "riffs on The Office" in seen["body"]["system"][0]["text"]
    assert m.theme == "The Office"


def test_mock_transport_works_without_key():
    m = generate_mnemonic(POLAND, "Seinfeld", api_key="", transport=mock_transport)
    assert m.mnemonic.startswith("[mock] Poland")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, body, headers=None):
    return urllib.error.HTTPError(generator.API_URL, code, "err", headers or {}, io.BytesIO(json.dumps(body).encode()))


def test_urllib_transport_sends_headers(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["body"] = json.loads(request.data)
        return FakeResponse(json.dumps(reply(GOOD)).encode())

    monkeypatch.setattr(generator.urllib.request, "urlopen", fake_urlopen)
    out = generator.urllib_transport({"model": "x"}, "sk-test")
    assert out["stop_reason"] == "end_turn"
    assert captured["headers"]["x-api-key"] == "sk-test"
    assert captured["headers"]["anthropic-version"] == generator.API_VERSION
    assert captured["headers"]["anthropic-beta"] == generator.FALLBACK_BETA


def test_urllib_transport_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise http_error(529, {"error": {"message": "overloaded"}}, {"retry-after": "0"})
        return FakeResponse(json.dumps(reply(GOOD)).encode())

    monkeypatch.setattr(generator.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(generator.time, "sleep", lambda s: None)
    assert generator.urllib_transport({}, "k")["stop_reason"] == "end_turn"
    assert len(calls) == 2


def test_urllib_transport_bad_key_message(monkeypatch):
    def fake_urlopen(request, timeout):
        raise http_error(401, {"error": {"message": "invalid x-api-key"}})

    monkeypatch.setattr(generator.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(generator.ApiError, match="key was rejected"):
        generator.urllib_transport({}, "bad")


def test_generator_has_no_anki_imports():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(generator))
    imported = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert not imported & {"aqt", "anki", "PyQt6"}
    assert all(m in {"__future__", "base64", "json", "re", "time", "urllib", "dataclasses", "typing"} for m in imported), imported


def test_regenerate_mentions_the_mnemonic_being_replaced():
    from flag_mnemonics.generator import FlagInput, build_user_text

    text = build_user_text(FlagInput("Poland", previous="Kramer bursts in."), [])
    assert "didn't stick: Kramer bursts in." in text
    assert "different scene" in text
    assert "didn't stick" not in build_user_text(FlagInput("Poland"), [])
