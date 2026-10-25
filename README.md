# Vesper

Paste what you meant to read today. Get a three-minute show, in a voice,
that you can listen to with your eyes shut.

Gemma 4 (Apache 2.0, open weights) reads the material, writes a script shaped
for speech rather than for the page, and picks which of three moods the screen
wears. ElevenLabs speaks it. The screen is one player.

## Run locally

    pip install -r app/requirements.txt
    cp .env.example .env     # fill in both keys (Windows: copy .env.example .env)
    uvicorn main:app --app-dir app --reload --port 7860

The app loads `.env` itself, so this works the same in bash and PowerShell.
On the ElevenLabs free plan, `ELEVENLABS_VOICE_ID` must be a premade voice;
library voices are refused with a 402.

Open http://localhost:7860

## Run Gemma on your own machine

Install [Ollama](https://ollama.com), pull a small Gemma, and point Vesper at it:

    ollama pull gemma4:e4b
    # in .env
    GEMMA_LOCAL_URL=http://localhost:11434/v1/chat/completions
    GEMMA_MODELS=gemma4:e4b

No OpenRouter key is needed then, and what you paste never leaves the laptop.
Only the finished script goes to ElevenLabs to be voiced. On a CPU-only
machine expect a minute or more per show.

## Deploy

**Render:** New → Blueprint, pick this repo, and paste `OPENROUTER_API_KEY`
and `ELEVENLABS_API_KEY` when asked. `render.yaml` sets up a free Docker web
service with a health check. Free instances sleep when idle, so the first
visit after a quiet spell takes about a minute to wake.

**Hugging Face:** one Space, Docker SDK, free CPU tier. Push this repo to it and
set `OPENROUTER_API_KEY` and `ELEVENLABS_API_KEY` as Space secrets.

## Honest notes

- Word highlighting uses ElevenLabs character timestamps when available. If
  that endpoint fails, timings are estimated from word length and drift
  slightly on longer shows. The API response says which you got.
- Gemma picks a mood by name from a fixed list. It never chooses colours.
- Each mood has an ambient bed, made by ElevenLabs sound generation the first
  time that mood plays and cached in `.cache/ambient` after that. The key
  needs the `sound_generation` permission; without it the show plays bare.
- Nothing you paste is stored. Audio is returned inline and lives only in your browser.