"""Everything the Space does, without Gradio, so it can be tested.

Two ways to write a mnemonic:

- Free: an open vision model through Hugging Face Inference Providers, paid
  for by the Space's own HF_TOKEN secret, with a daily limit per visitor and
  for the whole Space.
- Your own Claude key: sent straight to Anthropic for that one request. It is
  never stored, logged, or put in Gradio state, and never counts against the
  free limit.

The add-on owner's Claude key is never used here: the Space has no Claude key.
The prompt is the add-on's own (generator.py is a copy of
src/flag_mnemonics/generator.py; a test checks they match).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import generator
from generator import FlagImage, FlagInput, GenerationError, Mnemonic

HERE = Path(__file__).resolve().parent
OPEN_MODEL = os.environ.get("OPEN_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", generator.DEFAULT_MODEL)
PER_VISITOR_DAILY = int(os.environ.get("PER_VISITOR_DAILY", "5"))
GLOBAL_DAILY = int(os.environ.get("GLOBAL_DAILY", "200"))
MAX_THEME_CHARS = 60


# --- flags ------------------------------------------------------------------


@dataclass(frozen=True)
class DemoFlag:
    country: str
    path: Path
    similarity: str


def load_flags(directory: Path = HERE) -> list[DemoFlag]:
    data = json.loads((directory / "flags.json").read_text(encoding="utf-8"))
    flags = []
    for spec in data["flags"]:
        name = spec["country"].lower().replace(" ", "-") + ".png"
        flags.append(DemoFlag(spec["country"], directory / "flags" / name, spec.get("similarity", "")))
    return flags


def flag_input(flag: DemoFlag) -> FlagInput:
    return FlagInput(
        country=flag.country,
        image=FlagImage(flag.path.read_bytes(), "image/png"),
        flag_similarity=flag.similarity,
    )


def clean_theme(theme: str) -> str:
    theme = " ".join((theme or "").split())[:MAX_THEME_CHARS]
    return theme or "Seinfeld"


# --- pre-generated examples -------------------------------------------------


def load_pregenerated(path: Path = HERE / "pregenerated.json") -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {entry["country"]: entry for entry in data.get("mnemonics", [])}


# --- daily limit ------------------------------------------------------------


class DailyLimiter:
    """Counts free-model requests per visitor and in total, per UTC day.

    Visitors are identified by a salted hash of their IP address; raw
    addresses are never kept. Counts live in memory, so a Space restart
    resets them (which only ever errs towards fewer requests being refused).
    """

    def __init__(self, per_visitor: int, total: int, clock: Callable[[], float] = time.time) -> None:
        self.per_visitor = per_visitor
        self.total = total
        self.clock = clock
        self._salt = os.urandom(16)
        self._day = ""
        self._counts: dict[str, int] = {}
        self._total_used = 0
        self._lock = threading.Lock()

    def _visitor(self, address: str) -> str:
        return hashlib.sha256(self._salt + address.encode("utf-8")).hexdigest()[:16]

    def _roll(self) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
        if day != self._day:
            self._day, self._counts, self._total_used = day, {}, 0

    def try_take(self, address: str) -> Optional[str]:
        """Use one request. Returns None if allowed, or a message saying why not."""
        with self._lock:
            self._roll()
            visitor = self._visitor(address or "unknown")
            if self._total_used >= self.total:
                return (
                    "The free model has reached today's limit for the whole demo. "
                    "Try again tomorrow (UTC), or use your own Claude key."
                )
            if self._counts.get(visitor, 0) >= self.per_visitor:
                return (
                    f"You've used today's {self.per_visitor} free mnemonics. "
                    "Try again tomorrow (UTC), or use your own Claude key."
                )
            self._counts[visitor] = self._counts.get(visitor, 0) + 1
            self._total_used += 1
            return None

    def give_back(self, address: str) -> None:
        """Return a request that failed on our side, so it doesn't count."""
        with self._lock:
            visitor = self._visitor(address or "unknown")
            if self._counts.get(visitor, 0) > 0:
                self._counts[visitor] -= 1
                self._total_used = max(0, self._total_used - 1)

    def remaining(self, address: str) -> int:
        with self._lock:
            self._roll()
            used = self._counts.get(self._visitor(address or "unknown"), 0)
            return max(0, min(self.per_visitor - used, self.total - self._total_used))


def client_address(headers: dict[str, str], fallback: str = "") -> str:
    """The visitor's IP: first X-Forwarded-For entry (set by the Spaces proxy), else the socket address."""
    forwarded = headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or fallback


# --- generating -------------------------------------------------------------


@dataclass
class Result:
    ok: bool
    mnemonic: Optional[Mnemonic] = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)


def open_model_messages(flag: FlagInput, theme: str) -> list[dict[str, Any]]:
    """The add-on's prompt, in the chat-completions format open models use."""
    image = base64.b64encode(flag.image.data).decode("ascii")
    return [
        {"role": "system", "content": generator.build_system_prompt(theme)},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{flag.image.media_type};base64,{image}"}},
                {"type": "text", "text": generator.build_user_text(flag, [])},
            ],
        },
    ]


def hf_chat(messages: list[dict[str, Any]], model: str, token: str) -> str:
    """Call an open model through HF Inference Providers. Returns the reply text."""
    from huggingface_hub import InferenceClient

    client = InferenceClient(provider="auto", api_key=token)
    reply = client.chat_completion(messages=messages, model=model, max_tokens=700)
    return reply.choices[0].message.content or ""


def generate_open(
    flag: FlagInput,
    theme: str,
    token: Optional[str] = None,
    chat: Callable[[list, str, str], str] = hf_chat,
    model: str = OPEN_MODEL,
) -> Result:
    token = token if token is not None else os.environ.get("HF_TOKEN", "")
    if not token:
        return Result(False, message="The free model isn't set up on this Space (no HF_TOKEN secret).")
    try:
        text = chat(open_model_messages(flag, theme), model, token)
        mnemonic = generator.parse_mnemonic(generator._extract_json(text), theme=theme, model=model)
    except GenerationError as err:
        return Result(False, message=f"The open model's reply couldn't be used: {err} Try again.")
    except Exception as err:  # provider errors, timeouts
        return Result(False, message=f"The free model is unavailable right now ({type(err).__name__}). Try again later.")
    return Result(True, mnemonic, warnings=mnemonic.warnings)


def generate_claude(
    flag: FlagInput,
    theme: str,
    api_key: str,
    transport: Optional[Callable] = None,
    model: str = CLAUDE_MODEL,
) -> Result:
    """Use the visitor's own key for this one request. The key goes nowhere else."""
    api_key = (api_key or "").strip()
    if not api_key:
        return Result(False, message="Paste your Claude API key, or switch to the free model.")
    try:
        mnemonic = generator.generate_mnemonic(flag, theme, api_key, model=model, transport=transport)
    except GenerationError as err:
        message = str(err).replace(api_key, "[key]")
        if "claude_api_key" in message:  # add-on wording about its config
            message = "Claude rejected the key. Check it at console.anthropic.com."
        return Result(False, message=f"Claude couldn't write it: {message}")
    return Result(True, mnemonic, warnings=mnemonic.warnings)


def render(result: Result, source: str) -> str:
    """Markdown for the result box."""
    if not result.ok:
        return f"⚠️ {result.message}"
    m = result.mnemonic
    lines = [f"### 🥨 {m.mnemonic}", ""]
    if m.episode_title:
        lines += [f"📺 Episode: “{m.episode_title}”", ""]
    if m.context:
        lines += [f"_{m.context}_", ""]
    if m.distinguishing_detail:
        lines += [f"🔎 Key detail: {m.distinguishing_detail}", ""]
    lines.append(f"<sub>{source}</sub>")
    if result.warnings:
        lines.append(f"<sub>Note: {' '.join(result.warnings)}</sub>")
    return "\n".join(lines)
