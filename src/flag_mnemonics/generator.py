"""Build the prompt, call Claude, and parse the mnemonic it returns.

This module must never import Anki (or anything outside the standard
library), so the Hugging Face Space can reuse it unchanged. API calls use
`urllib` because Anki add-ons can't pip install the Anthropic SDK.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Optional, Sequence

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
DEFAULT_MODEL = "claude-opus-5-5"
# If the model's safety classifiers decline a (benign) request, the API
# re-runs it on Anthropic's recommended fallback model instead of failing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 4000
# Mnemonics for other flags sent as context. Look-alikes always go first.
MAX_CONTEXT_MNEMONICS = 30

SUPPORTED_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")

EXAMPLE_MNEMONIC = (
    "Indonesia and Monaco are both red over white, and Monaco's flag is shorter and "
    "stubbier, like George. Poland is upside down (white over red), like George in "
    "'The Opposite,' when he does the opposite of every instinct."
)

MNEMONIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mnemonic": {
            "type": "string",
            "description": "One to three sentences tying the theme to what the flag looks like.",
        },
        "episode_title": {
            "type": "string",
            "description": "Exact title of the real episode referenced, or an empty string if none.",
        },
        "distinguishing_detail": {
            "type": "string",
            "description": "The visual detail that separates this flag from its look-alikes.",
        },
        "image_prompt": {
            "type": "string",
            "description": "Prompt for an original illustration: the flag plus objects from the joke, no people.",
        },
    },
    "required": ["mnemonic", "episode_title", "distinguishing_detail", "image_prompt"],
    "additionalProperties": False,
}


class GenerationError(Exception):
    """Generation failed in a way worth showing to the user."""


class MissingApiKeyError(GenerationError):
    def __init__(self) -> None:
        super().__init__(
            "No Claude API key is set. Add one in Tools > Add-ons > Flag Mnemonics > Config "
            "(claude_api_key), or set the ANTHROPIC_API_KEY environment variable. "
            "Get a key at https://console.anthropic.com."
        )


class ApiError(GenerationError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"Claude API error {status}: {message}")


@dataclass(frozen=True)
class FlagImage:
    """A flag image ready to send. `data` is raw bytes."""

    data: bytes
    media_type: str

    def __post_init__(self) -> None:
        if self.media_type not in SUPPORTED_IMAGE_TYPES and self.media_type != "image/svg+xml":
            raise ValueError(f"Unsupported image type: {self.media_type}")


@dataclass(frozen=True)
class FlagInput:
    country: str
    image: Optional[FlagImage] = None
    flag_similarity: str = ""


@dataclass(frozen=True)
class PriorMnemonic:
    """A mnemonic already written for another flag, sent so new ones don't clash."""

    country: str
    mnemonic: str
    distinguishing_detail: str = ""


@dataclass
class Mnemonic:
    mnemonic: str
    distinguishing_detail: str
    image_prompt: str
    episode_title: Optional[str] = None
    theme: str = ""
    model: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- prompt building ------------------------------------------------------


def build_system_prompt(theme: str) -> str:
    theme = theme.strip() or "Seinfeld"
    return f"""You write mnemonics that help someone remember what a country's flag looks like. They study flashcards and keep forgetting this flag. Every mnemonic riffs on {theme}.

Rules:
1. Theme: draw on {theme}: its characters, catchphrases, objects, places, and well-known episodes or moments.
2. Encode the flag itself. Connect the joke to the flag's real visual details: its colors, their order, the layout, any symbols, and above all what makes it different from the look-alike flags you're given. A funny line that doesn't help someone picture this exact flag is a failure. Look at the image carefully and get the details right.
3. No made-up episodes. Only use real characters, catchphrases, and well-known episodes. If you reference a specific episode, put its exact title in episode_title so it can be checked. If you aren't sure an episode is real or what it's called, don't name one: use characters and their traits instead, and leave episode_title empty.
4. Use your own words. A short nod to a famous line is fine, but never quote more than a few words of actual dialogue.
5. Avoid confusion with other flags. You'll see mnemonics already written for other flags. Don't give two similar flags similar mnemonics: if a look-alike already uses a character or gag, pick a different one, and make the contrast between the two flags the point.
6. One to three sentences.

Here is an example of the kind of mnemonic that works, for the theme Seinfeld. It names the look-alikes, says exactly how they differ (color order, proportions), and ties each difference to something memorable:
"{EXAMPLE_MNEMONIC}"

Reply with JSON only:
- mnemonic: the mnemonic itself, one to three sentences.
- episode_title: the exact title of the real episode you referenced, or "" if none.
- distinguishing_detail: one short phrase naming the visual detail that sets this flag apart from its look-alikes.
- image_prompt: a prompt for an original illustration showing this flag together with objects or places from the joke (for example a diner booth, a puffy shirt, a marble rye). Describe the flag's real colors and layout. Never include any people, actors, or anyone resembling the cast; objects and settings only."""


def select_context(
    prior: Iterable[PriorMnemonic],
    country: str,
    flag_similarity: str,
    limit: int = MAX_CONTEXT_MNEMONICS,
) -> list[PriorMnemonic]:
    """Pick which existing mnemonics to send: look-alikes first, then the rest."""
    similarity = flag_similarity.lower()
    others = [p for p in prior if p.country.strip().lower() != country.strip().lower()]
    lookalikes = [p for p in others if p.country and p.country.lower() in similarity]
    rest = [p for p in others if p not in lookalikes]
    return (lookalikes + rest)[:limit]


def build_user_text(flag: FlagInput, context: Sequence[PriorMnemonic]) -> str:
    lines = [f"Country: {flag.country}"]
    if flag.flag_similarity.strip():
        lines.append(f"Look-alike flags (from the deck): {flag.flag_similarity.strip()}")
    else:
        lines.append("Look-alike flags (from the deck): none listed. Use your own knowledge of similar flags.")
    if flag.image is None:
        lines.append("No image of the flag is attached; rely on your knowledge of it.")
    elif flag.image.media_type == "image/svg+xml":
        lines.append("The flag is attached as SVG source code.")
    if context:
        lines.append("")
        lines.append("Mnemonics already written for other flags (don't repeat their gags for similar flags):")
        for p in context:
            detail = f" [distinguishing detail: {p.distinguishing_detail}]" if p.distinguishing_detail else ""
            lines.append(f"- {p.country}: {p.mnemonic}{detail}")
    lines.append("")
    lines.append(f"Write the mnemonic for {flag.country}.")
    return "\n".join(lines)


def build_user_content(flag: FlagInput, context: Sequence[PriorMnemonic]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if flag.image is not None:
        if flag.image.media_type == "image/svg+xml":
            # Vision doesn't take SVG; the source itself describes the flag well.
            svg = flag.image.data.decode("utf-8", errors="replace")
            content.append({"type": "text", "text": f"<flag_svg>\n{svg}\n</flag_svg>"})
        else:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": flag.image.media_type,
                        "data": base64.standard_b64encode(flag.image.data).decode("ascii"),
                    },
                }
            )
    content.append({"type": "text", "text": build_user_text(flag, context)})
    return content


def build_request(
    flag: FlagInput,
    theme: str,
    prior: Iterable[PriorMnemonic] = (),
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """The JSON body for POST /v1/messages."""
    context = select_context(prior, flag.country, flag.flag_similarity)
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [
            {
                "type": "text",
                "text": build_system_prompt(theme),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": build_user_content(flag, context)}],
        "output_config": {
            "effort": "medium",
            "format": {"type": "json_schema", "schema": MNEMONIC_SCHEMA},
        },
        "fallbacks": "default",
    }


# --- response parsing -----------------------------------------------------


def count_sentences(text: str) -> int:
    # Ignore periods inside quotes like 'The Opposite.' by stripping quoted titles first.
    stripped = re.sub(r"['\"‘’“”][^'\"‘’“”]{1,80}['\"‘’“”]", "X", text)
    return len([s for s in re.split(r"(?<=[.!?])\s+", stripped.strip()) if s])


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise GenerationError("Claude's reply wasn't JSON.") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as err:
            raise GenerationError(f"Claude's reply wasn't valid JSON: {err}") from None
    if not isinstance(data, dict):
        raise GenerationError("Claude's reply wasn't a JSON object.")
    return data


def parse_mnemonic(data: dict[str, Any], theme: str = "", model: str = "") -> Mnemonic:
    """Validate the model's JSON object and turn it into a Mnemonic."""

    def text(key: str) -> str:
        value = data.get(key)
        return value.strip() if isinstance(value, str) else ""

    mnemonic = text("mnemonic")
    if not mnemonic:
        raise GenerationError("Claude's reply had no mnemonic.")
    warnings = []
    sentences = count_sentences(mnemonic)
    if sentences > 3:
        warnings.append(f"Mnemonic has {sentences} sentences (asked for 1 to 3).")
    distinguishing = text("distinguishing_detail")
    if not distinguishing:
        warnings.append("No distinguishing detail given.")
    return Mnemonic(
        mnemonic=mnemonic,
        distinguishing_detail=distinguishing,
        image_prompt=text("image_prompt"),
        episode_title=text("episode_title") or None,
        theme=theme,
        model=model,
        warnings=warnings,
    )


def parse_response(response: dict[str, Any], theme: str = "") -> Mnemonic:
    """Parse a Messages API response body into a Mnemonic."""
    stop = response.get("stop_reason")
    if stop == "refusal":
        details = response.get("stop_details") or {}
        raise GenerationError(
            f"Claude declined to write this mnemonic ({details.get('category') or 'no category'})."
        )
    if stop == "max_tokens":
        raise GenerationError("Claude's reply was cut off before it finished.")
    texts = [b.get("text", "") for b in response.get("content", []) if b.get("type") == "text"]
    if not texts:
        raise GenerationError("Claude's reply had no text.")
    return parse_mnemonic(_extract_json("".join(texts)), theme=theme, model=response.get("model", ""))


# --- transport ------------------------------------------------------------

Transport = Callable[[dict[str, Any], str], dict[str, Any]]


def urllib_transport(body: dict[str, Any], api_key: str, timeout: float = 120.0, retries: int = 2) -> dict[str, Any]:
    """POST to the Messages API with the standard library, retrying 429/5xx."""
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "anthropic-beta": FALLBACK_BETA,
    }
    for attempt in range(retries + 1):
        request = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", errors="replace")
            try:
                message = json.loads(raw)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = raw[:300] or err.reason
            retryable = err.code == 429 or err.code >= 500
            if retryable and attempt < retries:
                delay = float(err.headers.get("retry-after") or 2 ** (attempt + 1))
                time.sleep(min(delay, 30))
                continue
            if err.code == 401:
                message = "the API key was rejected. Check claude_api_key in the add-on config."
            raise ApiError(err.code, message) from None
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            raise GenerationError(f"Couldn't reach the Claude API: {getattr(err, 'reason', err)}") from None
    raise AssertionError("unreachable")


def mock_transport(body: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Offline stand-in for the API, for tests and `use_mock_api`."""
    user_text = body["messages"][0]["content"][-1]["text"]
    country = re.search(r"^Country: (.+)$", user_text, re.MULTILINE).group(1)
    reply = {
        "mnemonic": f"[mock] {country}'s flag walks into Monk's Café and orders the usual.",
        "episode_title": "",
        "distinguishing_detail": f"[mock] what sets {country} apart",
        "image_prompt": f"[mock] the flag of {country} on a diner table",
    }
    return {
        "model": "mock",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(reply)}],
    }


def generate_mnemonic(
    flag: FlagInput,
    theme: str,
    api_key: str,
    prior: Iterable[PriorMnemonic] = (),
    model: str = DEFAULT_MODEL,
    transport: Optional[Transport] = None,
) -> Mnemonic:
    """Generate one mnemonic. Raises GenerationError with a readable message."""
    if transport is None:
        if not api_key:
            raise MissingApiKeyError()
        transport = urllib_transport
    body = build_request(flag, theme, prior, model)
    return parse_response(transport(body, api_key), theme=theme or "Seinfeld")
