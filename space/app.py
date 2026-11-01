"""Flag Mnemonics demo: pick a flag, get a themed mnemonic for it.

See README.md (the Space card) and DEPLOY.md. The logic is in demo_logic.py.
"""

from __future__ import annotations

import gradio as gr

import demo_logic as logic

FLAGS = {f.country: f for f in logic.load_flags()}
PREGENERATED = logic.load_pregenerated()
LIMITER = logic.DailyLimiter(logic.PER_VISITOR_DAILY, logic.GLOBAL_DAILY)

FREE = "Free open model (a few per day)"
OWN_KEY = "My own Claude API key"

INTRO = """# 🥨 Flag Mnemonics
Pick a flag you keep mixing up. You get a short mnemonic, themed on a show you know, that encodes what the flag
actually looks like and how it differs from its look-alikes. It's a demo of an
[Anki add-on](https://github.com/armita-jamshidi/yada-yada-flags) that does this for the flags you keep forgetting in
Ultimate Geography, and syncs the mnemonics to your phone."""

KEY_NOTE = (
    "Your key is used for this one request, straight to Anthropic. It isn't stored, logged, or shared, "
    "and this Space has no Claude key of its own. Get one at console.anthropic.com."
)


def visitor(request: gr.Request | None) -> str:
    if request is None:
        return ""
    headers = {k.lower(): v for k, v in dict(request.headers).items()}
    host = request.client.host if request.client else ""
    return logic.client_address(headers, host)


def show_flag(country: str, request: gr.Request):
    flag = FLAGS[country]
    saved = PREGENERATED.get(country)
    if saved:
        note = saved.get("note") or f"Pre-written ({saved.get('theme', 'Seinfeld')}, {saved.get('model', 'Claude')})."
        mnemonic = logic.Mnemonic(
            saved["mnemonic"],
            saved.get("distinguishing_detail", ""),
            "",
            saved.get("episode_title"),
            context=saved.get("context", ""),
        )
        text = logic.render(logic.Result(True, mnemonic), note)
    else:
        text = "_No pre-written mnemonic for this flag yet. Press **Write a mnemonic**._"
    left = LIMITER.remaining(visitor(request))
    return str(flag.path), flag.similarity or "None listed", text, f"Free mnemonics left today: {left}"


def toggle_key(source: str):
    return gr.update(visible=source == OWN_KEY)


def write(country: str, theme: str, source: str, api_key: str, request: gr.Request):
    flag = logic.flag_input(FLAGS[country])
    theme = logic.clean_theme(theme)
    address = visitor(request)
    if source == OWN_KEY:
        result = logic.generate_claude(flag, theme, api_key)
        label = f"Written just now by Claude ({logic.CLAUDE_MODEL}) with your key."
    else:
        refusal = LIMITER.try_take(address)
        if refusal:
            return f"⚠️ {refusal}", f"Free mnemonics left today: {LIMITER.remaining(address)}"
        result = logic.generate_open(flag, theme)
        if not result.ok:
            LIMITER.give_back(address)  # failures don't use up the visitor's free mnemonics
        label = f"Written just now by {logic.OPEN_MODEL} (open model via Hugging Face)."
    return logic.render(result, label), f"Free mnemonics left today: {LIMITER.remaining(address)}"


with gr.Blocks(title="Flag Mnemonics", analytics_enabled=False) as demo:
    gr.Markdown(INTRO)
    with gr.Row():
        with gr.Column(scale=1):
            country = gr.Dropdown(list(FLAGS), value="Poland", label="Flag")
            image = gr.Image(label="Flag", interactive=False, height=180)
            lookalikes = gr.Textbox(label="Look-alikes", interactive=False)
        with gr.Column(scale=2):
            theme = gr.Textbox(value="Seinfeld", label="Theme", max_length=logic.MAX_THEME_CHARS)
            source = gr.Radio([FREE, OWN_KEY], value=FREE, label="Who writes it")
            api_key = gr.Textbox(label="Claude API key", type="password", visible=False, info=KEY_NOTE)
            button = gr.Button("Write a mnemonic", variant="primary")
            output = gr.Markdown()
            quota = gr.Markdown()
    gr.Markdown(
        "<sub>Flags drawn for this demo from their stripe layouts (public-domain designs). "
        "Mnemonics are AI-written and may be wrong. "
        "Not affiliated with Seinfeld or its makers.</sub>"
    )

    country.change(show_flag, country, [image, lookalikes, output, quota])
    demo.load(show_flag, country, [image, lookalikes, output, quota])
    source.change(toggle_key, source, api_key)
    button.click(write, [country, theme, source, api_key], [output, quota], concurrency_limit=2)


if __name__ == "__main__":
    demo.queue(max_size=20).launch()
