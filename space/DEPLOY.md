# Deploying the demo Space

**Not deployed.** Hugging Face now requires a PRO subscription to host Gradio Spaces, even on free CPU hardware (only static Spaces are free), so the demo isn't online. It still runs locally with `python app.py`. The steps below apply if that changes or you subscribe.

Nothing has been deployed. These are the steps for you, under your Hugging Face account. **Create it as a private Space.** Making it public is a separate decision.

## 1. Before deploying (on your computer)

```bash
cd space
pip install huggingface_hub gradio==6.31.0 Pillow
ANTHROPIC_API_KEY=sk-ant-... python pregenerate.py   # optional: real Seinfeld mnemonics for all 12 flags
python app.py                                         # try it at http://127.0.0.1:7860
```

Without `pregenerate.py`, only Poland has a pre-written mnemonic: the hand-written example from the add-on's prompt, labeled as such. Read what `pregenerate.py` writes before deploying: those mnemonics are the first thing visitors see. Your key is only read from the environment for that run, and never written to a file or to the Space.

To try the free model locally, also `export HF_TOKEN=hf_...`.

## 2. Create the Space (private)

1. https://huggingface.co/new-space → name `flag-mnemonics`, SDK **Gradio**, hardware **CPU basic** (free; the models run elsewhere), visibility **Private**.
2. Upload the contents of `space/`: everything except `__pycache__/` and `dataset/`. Either drag the files into the web UI (Files → Add file → Upload files), or:

   ```bash
   pip install huggingface_hub
   hf auth login
   hf upload <your-username>/flag-mnemonics . . --repo-type space --exclude "__pycache__/*" "dataset/*"
   ```

## 3. Secrets (Settings → Variables and secrets)

| Name | Type | Value |
| --- | --- | --- |
| `HF_TOKEN` | **Secret** | A fine-grained token with only "Make calls to Inference Providers". Pays for the free model. |
| `PER_VISITOR_DAILY` | Variable | Optional. Free mnemonics per visitor per UTC day (default 5). |
| `GLOBAL_DAILY` | Variable | Optional. Free mnemonics for the whole Space per day (default 200). |
| `OPEN_MODEL` | Variable | Optional. Another vision chat model if the default stops being served. |

**Never add an Anthropic key to the Space.** Visitors who want Claude bring their own.

Set a monthly spending limit for Inference Providers in your Hugging Face billing settings. With the defaults, the free model makes at most 200 small requests a day.

## 4. Check it

Open the Space. Pick Chad, press **Write a mnemonic**. You should get a mnemonic within a few seconds. The free model's quality varies more than Claude's; if the default model isn't served any more, the page says the free model is unavailable. Pick another vision model that Inference Providers serves for chat (filter models by "Image-Text-to-Text" and "Inference Providers") and set `OPEN_MODEL`.

Try "My own Claude API key" with your own key once, then remove it from the box. It's not kept anywhere.

## 5. Going public: ask first

The Space stays private until you decide. Before switching it to public (Settings → Change visibility), check:

- [ ] Pre-written mnemonics read well and contain nothing you wouldn't want public.
- [ ] `HF_TOKEN` is a secret with only Inference Providers permission, and a spending limit is set.
- [ ] Daily limits suit your budget.

Then add the Space link to the add-on's README ("Try it in your browser").

## Optional: the dataset

`python make_dataset.py` writes `dataset/` (data.jsonl, images, and a dataset card) from the Claude-written entries in `pregenerated.json`. Nothing is uploaded. To publish it, if you want to:

```bash
hf repo create flag-mnemonics-seinfeld --repo-type dataset --private
hf upload <your-username>/flag-mnemonics-seinfeld dataset . --repo-type dataset
```
