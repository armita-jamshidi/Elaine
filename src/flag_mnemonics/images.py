"""Optional original illustrations for mnemonics, from FLUX.1-schnell on Hugging Face.

Off by default (`images_enabled`). Uses the mnemonic's `image_prompt`, which
the generator is told to keep to objects and settings. A style suffix here
repeats that: no people, no actors, no likenesses, no text.

Calls Hugging Face Inference Providers through the HF router with the
standard library only (add-ons can't pip install `huggingface_hub`). The
same request `InferenceClient(provider=...).text_to_image(prompt, model=MODEL)`
makes. FLUX.1-schnell is served by nscale; hf-inference is tried if nscale
doesn't take the request. No Anki imports.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

MODEL = "black-forest-labs/FLUX.1-schnell"
ROUTER = "https://router.huggingface.co"
SIZE = 512  # small files: these sync to phones
FILE_PREFIX = "flagmnem_"
MAX_PROMPT_CHARS = 900

STYLE = (
    "Original flat vector illustration, bright colors, simple shapes, clean background. "
    "Objects and places only: no people, no faces, no hands, no actors, no celebrities, "
    "no likeness of any real person or TV character, no text, no letters, no logos."
)


class ImageError(Exception):
    """An illustration couldn't be made. The mnemonic is kept without one."""


class MissingHfKeyError(ImageError):
    def __init__(self) -> None:
        super().__init__(
            "Illustrations are turned on (images_enabled) but no Hugging Face token is set. "
            "Add one in Tools > Add-ons > Flag Mnemonics > Config (huggingface_api_key), or set "
            "the HF_TOKEN environment variable. Get a token at https://huggingface.co/settings/tokens "
            '(a "Read" token with "Make calls to Inference Providers" is enough). '
            "Mnemonics are still written, just without pictures."
        )


# Each provider: (url, body builder, response parser).
def _nscale_body(prompt: str) -> dict[str, Any]:
    return {"response_format": "b64_json", "prompt": prompt, "model": MODEL, "size": f"{SIZE}x{SIZE}"}


def _nscale_parse(data: bytes, content_type: str) -> bytes:
    try:
        return base64.b64decode(json.loads(data.decode("utf-8"))["data"][0]["b64_json"])
    except (ValueError, KeyError, IndexError, TypeError) as err:
        raise ImageError(f"Unexpected reply from Hugging Face: {err}") from None


def _hf_inference_body(prompt: str) -> dict[str, Any]:
    return {"inputs": prompt, "parameters": {"width": SIZE, "height": SIZE, "num_inference_steps": 4}}


def _hf_inference_parse(data: bytes, content_type: str) -> bytes:
    if content_type.startswith("application/json"):
        raise ImageError(f"Unexpected reply from Hugging Face: {data[:200]!r}")
    return data


PROVIDERS = (
    ("nscale", f"{ROUTER}/nscale/v1/images/generations", _nscale_body, _nscale_parse),
    ("hf-inference", f"{ROUTER}/hf-inference/models/{MODEL}", _hf_inference_body, _hf_inference_parse),
)

# Transport: (url, body, api_key) -> (status, content_type, data). Raises on network errors.
Transport = Callable[[str, dict, str], "tuple[int, str, bytes]"]


def build_prompt(image_prompt: str) -> str:
    prompt = " ".join(image_prompt.split())[:MAX_PROMPT_CHARS]
    return f"{prompt}. {STYLE}" if prompt else ""


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    raise ImageError("Hugging Face didn't return a PNG, JPEG or WebP image.")


def media_filename(note_id: int, data: bytes) -> str:
    """flagmnem_<note id>_<hash>.<ext>, so a new picture never reuses an old name."""
    digest = hashlib.sha1(data).hexdigest()[:10]
    return f"{FILE_PREFIX}{note_id}_{digest}.{image_extension(data)}"


def is_addon_file(filename: str) -> bool:
    """Only files the add-on made may be deleted by it."""
    return bool(filename) and filename.startswith(FILE_PREFIX) and "/" not in filename and "\\" not in filename


def urllib_transport(url: str, body: dict, api_key: str, timeout: float = 120.0) -> "tuple[int, str, bytes]":
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.headers.get("content-type", ""), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("content-type", "") if err.headers else "", err.read()


def mock_transport(url: str, body: dict, api_key: str) -> "tuple[int, str, bytes]":
    """Offline stand-in: a 1x1 PNG, for tests and `use_mock_api`."""
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
    )
    if "nscale" in url:
        return 200, "application/json", json.dumps({"data": [{"b64_json": base64.b64encode(png).decode()}]}).encode()
    return 200, "image/png", png


def _error_message(status: int, data: bytes) -> str:
    try:
        parsed = json.loads(data.decode("utf-8"))
        message = parsed.get("error") or parsed.get("message") or parsed
        if isinstance(message, dict):
            message = message.get("message", message)
    except (ValueError, AttributeError):
        message = data[:200].decode("utf-8", errors="replace")
    if status == 401:
        return "the Hugging Face token was rejected. Check huggingface_api_key in the add-on config."
    if status == 402:
        return "your Hugging Face account is out of Inference Providers credits."
    return f"HTTP {status}: {message}"


def generate_image(
    image_prompt: str,
    api_key: str,
    transport: Optional[Transport] = None,
    retries: int = 1,
) -> bytes:
    """Return image bytes for the prompt, or raise ImageError."""
    if not api_key:
        raise MissingHfKeyError()
    prompt = build_prompt(image_prompt)
    if not prompt:
        raise ImageError("The mnemonic has no image prompt.")
    transport = transport or urllib_transport
    errors = []
    for name, url, body_for, parse in PROVIDERS:
        for attempt in range(retries + 1):
            try:
                status, content_type, data = transport(url, body_for(prompt), api_key)
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                status, content_type, data = 0, "", str(getattr(err, "reason", err)).encode()
            if status == 200:
                try:
                    image = parse(data, content_type)
                    image_extension(image)  # raises if it isn't an image
                    return image
                except ImageError as err:
                    errors.append(f"{name}: {err}")
                    break
            if status in (401, 402):
                raise ImageError(_error_message(status, data))
            if (status == 0 or status == 429 or status >= 500) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            errors.append(f"{name}: {_error_message(status, data) if status else data.decode(errors='replace')}")
            break
    raise ImageError("Couldn't make an illustration (" + "; ".join(errors) + ")")
